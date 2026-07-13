import asyncio
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlglot import exp, parse
from sqlglot.errors import ParseError


class ArcheryError(RuntimeError):
    """Archery 请求或认证失败。"""


class ArcheryTwoFactorRequired(ArcheryError):
    """账号需要交互式双因素认证。"""


@dataclass(frozen=True)
class ArcheryConfig:
    base_url: str
    username: str
    password: str
    verify_tls: bool = True
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("ARCHERY_URL 必须是有效的 HTTPS 地址")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("ARCHERY_URL 只能包含协议和主机名")
        if not self.username or not self.password:
            raise ValueError("ARCHERY_USERNAME 和 ARCHERY_PASSWORD 不能为空")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise ValueError("ARCHERY_TIMEOUT 必须在 0 到 120 秒之间")


class ArcheryClient:
    def __init__(
        self,
        config: ArcheryConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._login_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            follow_redirects=True,
            verify=config.verify_tls,
            timeout=config.timeout_seconds,
            transport=transport,
            headers={"User-Agent": "archery-mcp/0.1"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def login(self, force: bool = False) -> None:
        async with self._login_lock:
            if not force and await self._is_authenticated():
                return

            self._client.cookies.clear()
            response = await self._client.get("/login/")
            self._raise_for_http_error(response)
            csrf = self._client.cookies.get("csrftoken")
            if not csrf:
                raise ArcheryError("Archery 登录页未返回 CSRF Token")

            response = await self._client.post(
                "/authenticate/",
                data={"username": self.config.username, "password": self.config.password},
                headers={
                    "X-CSRFToken": csrf,
                    "Referer": f"{self.config.base_url.rstrip('/')}/login/",
                },
            )
            self._raise_for_http_error(response)
            payload = self._json(response)
            if payload.get("status") != 0:
                raise ArcheryError(
                    f"Archery 登录失败: {payload.get('msg', '未知错误')}"
                )
            if payload.get("data"):
                raise ArcheryTwoFactorRequired(
                    "该账号启用了 2FA，用户名密码无法完成机器登录；请使用未启用交互式 2FA 的最小权限服务账号"
                )
            if not await self._is_authenticated():
                raise ArcheryError("Archery 返回登录成功，但会话未建立")

    async def health(self) -> dict[str, Any]:
        response = await self._client.get("/login/")
        self._raise_for_http_error(response)
        return {
            "reachable": True,
            "status_code": response.status_code,
            "archery_version": self._extract_version(response.text),
        }

    async def list_instances(
        self, *, limit: int = 50, offset: int = 0, search: str = ""
    ) -> dict[str, Any]:
        self._validate_page(limit, offset)
        return await self._post(
            "/instance/list/",
            data={
                "limit": str(limit),
                "offset": str(offset),
                "search": search[:100],
                "type": "",
                "db_type": "",
                "sortName": "instance_name",
                "sortOrder": "asc",
            },
        )

    async def list_query_instances(self) -> dict[str, Any]:
        return await self._get(
            "/group/user_all_instances/", params={"tag_codes[]": "can_read"}
        )

    async def list_databases(self, instance_name: str) -> dict[str, Any]:
        self._validate_name("instance_name", instance_name)
        return await self._get(
            "/instance/instance_resource/",
            params={"instance_name": instance_name, "resource_type": "database"},
        )

    async def query(
        self,
        *,
        instance_name: str,
        database: str,
        sql: str,
        limit: int = 100,
        schema: str = "",
    ) -> dict[str, Any]:
        self._validate_name("instance_name", instance_name)
        self._validate_name("database", database)
        if schema:
            self._validate_name("schema", schema)
        self._validate_readonly_sql(sql)
        if limit < 1 or limit > 5000:
            raise ValueError("limit 必须在 1 到 5000 之间")

        result = await self._post(
            "/query/",
            data={
                "instance_name": instance_name,
                "db_name": database,
                "schema_name": schema,
                "tb_name": "",
                "sql_content": sql.strip(),
                "limit_num": str(limit),
            },
        )
        if result.get("status") != 0:
            raise ArcheryError(
                f"Archery 查询失败: {result.get('msg', '未知错误')}"
            )
        return result

    async def export_query(
        self,
        *,
        instance_name: str,
        database: str,
        sql: str,
        export_dir: Path,
        max_rows: int = 0,
        page_size: int = 5000,
        schema: str = "",
        filename: str = "",
    ) -> dict[str, Any]:
        self._validate_name("instance_name", instance_name)
        self._validate_name("database", database)
        if schema:
            self._validate_name("schema", schema)
        statement = self._parse_export_sql(sql)
        if page_size < 1 or page_size > 5000:
            raise ValueError("page_size 必须在 1 到 5000 之间")
        if max_rows < 0:
            raise ValueError("max_rows 不能小于 0；0 表示不限制总行数")
        if (max_rows == 0 or max_rows > page_size) and statement.args.get("order") is None:
            raise ValueError("多页导出必须在 SQL 顶层指定 ORDER BY，避免重复或遗漏数据")

        export_dir = export_dir.expanduser().resolve()
        export_dir.mkdir(parents=True, exist_ok=True)
        output_name = self._export_filename(filename)
        output_path = (export_dir / output_name).resolve()
        if output_path.parent != export_dir:
            raise ValueError("导出文件必须位于 ARCHERY_EXPORT_DIR 中")

        row_count = 0
        page_count = 0
        columns: list[Any] | None = None
        truncated = False
        try:
            with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                while True:
                    current_page_size = (
                        page_size if max_rows == 0 else min(page_size, max_rows - row_count)
                    )
                    page_sql = (
                        statement.copy()
                        .limit(current_page_size)
                        .offset(row_count)
                        .sql()
                    )
                    result = await self.query(
                        instance_name=instance_name,
                        database=database,
                        sql=page_sql,
                        limit=current_page_size,
                        schema=schema,
                    )
                    data = result.get("data") or {}
                    page_columns = data.get("column_list") or []
                    rows = data.get("rows") or []
                    if columns is None:
                        columns = list(page_columns)
                        writer.writerow(columns)
                    elif list(page_columns) != columns:
                        raise ArcheryError("分页查询返回的列结构不一致，已终止导出")

                    for row in rows:
                        writer.writerow([self._escape_csv_cell(value) for value in row])
                    row_count += len(rows)
                    page_count += 1
                    if len(rows) < current_page_size:
                        break
                    if max_rows > 0 and row_count >= max_rows:
                        truncated = True
                        break
        except Exception:
            output_path.unlink(missing_ok=True)
            raise

        return {
            "file_path": str(output_path),
            "row_count": row_count,
            "page_count": page_count,
            "page_size": page_size,
            "max_rows": max_rows or None,
            "truncated": truncated,
        }

    async def list_workflows(
        self, *, limit: int = 20, offset: int = 0, search: str = ""
    ) -> dict[str, Any]:
        self._validate_page(limit, offset)
        return await self._post(
            "/sqlworkflow_list/",
            data={"limit": str(limit), "offset": str(offset), "search": search[:100]},
        )

    async def workflow_status(self, workflow_id: int) -> dict[str, Any]:
        self._validate_workflow_id(workflow_id)
        return await self._post(
            "/getWorkflowStatus/", data={"workflow_id": str(workflow_id)}
        )

    async def workflow_detail(self, workflow_id: int) -> dict[str, Any]:
        self._validate_workflow_id(workflow_id)
        return await self._get(
            "/sqlworkflow/detail_content/", params={"workflow_id": str(workflow_id)}
        )

    async def _get(self, path: str, *, params: dict[str, str]) -> dict[str, Any]:
        await self.login()
        response = await self._client.get(path, params=params)
        if self._looks_logged_out(response):
            await self.login(force=True)
            response = await self._client.get(path, params=params)
        self._raise_for_http_error(response)
        return self._json(response)

    async def _post(self, path: str, *, data: dict[str, str]) -> dict[str, Any]:
        await self.login()
        response = await self._client.post(path, data=data, headers=self._csrf_headers())
        if self._looks_logged_out(response):
            await self.login(force=True)
            response = await self._client.post(path, data=data, headers=self._csrf_headers())
        self._raise_for_http_error(response)
        return self._json(response)

    async def _is_authenticated(self) -> bool:
        if "sessionid" not in self._client.cookies:
            return False
        response = await self._client.get("/index/")
        return not self._looks_logged_out(response) and response.status_code == 200

    def _csrf_headers(self) -> dict[str, str]:
        csrf = self._client.cookies.get("csrftoken")
        if not csrf:
            raise ArcheryError("当前会话缺少 CSRF Token")
        return {
            "X-CSRFToken": csrf,
            "Referer": f"{self.config.base_url.rstrip('/')}/index/",
        }

    @staticmethod
    def _looks_logged_out(response: httpx.Response) -> bool:
        return response.url.path == "/login/" or "Login To Archery" in response.text

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ArcheryError(
                f"Archery 返回了非 JSON 响应: {response.url.path}"
            ) from exc
        if not isinstance(payload, dict):
            raise ArcheryError("Archery 返回格式异常，预期 JSON 对象")
        return payload

    @staticmethod
    def _raise_for_http_error(response: httpx.Response) -> None:
        if response.status_code == 403:
            raise ArcheryError("Archery 拒绝访问：账号无权限或 CSRF 校验失败")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ArcheryError(
                f"Archery 请求失败: HTTP {response.status_code} {response.url.path}"
            ) from exc

    @staticmethod
    def _extract_version(html: str) -> str | None:
        marker = "Archery</strong>&nbsp;(v"
        if marker not in html:
            return None
        return html.split(marker, 1)[1].split(")", 1)[0]

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if limit < 1 or limit > 100:
            raise ValueError("limit 必须在 1 到 100 之间")
        if offset < 0 or offset > 10000:
            raise ValueError("offset 必须在 0 到 10000 之间")

    @staticmethod
    def _validate_workflow_id(workflow_id: int) -> None:
        if workflow_id < 1:
            raise ValueError("workflow_id 必须大于 0")

    @staticmethod
    def _validate_name(field: str, value: str) -> None:
        if not value or len(value) > 128 or any(char in value for char in "\r\n\x00"):
            raise ValueError(
                f"{field} 不能为空、不能超过 128 字符且不能包含控制字符"
            )

    @staticmethod
    def _validate_readonly_sql(sql: str) -> None:
        if not sql or len(sql) > 20000:
            raise ValueError("sql 不能为空且不能超过 20000 字符")
        try:
            statements = [statement for statement in parse(sql) if statement]
        except ParseError as exc:
            raise ValueError(f"SQL 无法解析: {exc}") from exc
        if len(statements) != 1:
            raise ValueError("只允许提交一条 SQL")

        statement = statements[0]
        if not isinstance(statement, exp.Query):
            raise ValueError("只允许 SELECT 或 WITH 查询")

        forbidden_nodes = (
            exp.Delete,
            exp.Insert,
            exp.Update,
            exp.Create,
            exp.Drop,
            exp.Alter,
            exp.Command,
            exp.Lock,
            exp.Merge,
        )
        if any(statement.find(node_type) is not None for node_type in forbidden_nodes):
            raise ValueError("SQL 包含写操作、管理命令或锁操作")

        normalized = statement.sql().lower()
        forbidden_fragments = (
            " into outfile",
            " into dumpfile",
            " for update",
            " lock in share mode",
            "sleep(",
            "benchmark(",
            "pg_sleep(",
            "load_file(",
        )
        if any(fragment in normalized for fragment in forbidden_fragments):
            raise ValueError("SQL 包含禁止的导出、锁定或高风险函数")

    @classmethod
    def _parse_export_sql(cls, sql: str) -> exp.Query:
        cls._validate_readonly_sql(sql)
        statement = parse(sql)[0]
        if statement.args.get("limit") is not None or statement.args.get("offset") is not None:
            raise ValueError("导出 SQL 不能包含 LIMIT 或 OFFSET，分页由 MCP 统一控制")
        return statement

    @staticmethod
    def _export_filename(filename: str) -> str:
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            return f"archery-export-{timestamp}-{uuid4().hex[:8]}.csv"
        if len(filename) > 128 or not re.fullmatch(r"[A-Za-z0-9._-]+", filename):
            raise ValueError("filename 只能包含英文、数字、点、下划线和中划线，且不能超过 128 字符")
        if filename in {".", ".."}:
            raise ValueError("filename 非法")
        return filename if filename.lower().endswith(".csv") else f"{filename}.csv"

    @staticmethod
    def _escape_csv_cell(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
            return f"'{value}"
        return value
