import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import ArcheryClient, ArcheryConfig


mcp = FastMCP("archery-readonly")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() not in {"true", "false"}:
        raise ValueError(f"{name} 只能是 true 或 false")
    return value.lower() == "true"


@lru_cache(maxsize=1)
def get_client() -> ArcheryClient:
    return ArcheryClient(
        ArcheryConfig(
            base_url=os.environ["ARCHERY_URL"],
            username=os.environ["ARCHERY_USERNAME"],
            password=os.environ["ARCHERY_PASSWORD"],
            verify_tls=_env_bool("ARCHERY_VERIFY_TLS", True),
            timeout_seconds=float(os.getenv("ARCHERY_TIMEOUT", "30")),
        )
    )


@mcp.tool()
async def archery_health() -> dict[str, Any]:
    """检查 Archery 是否可访问并返回版本；不执行登录。"""
    return await get_client().health()


@mcp.tool()
async def archery_login_status() -> dict[str, Any]:
    """使用配置的用户名和密码登录，确认账号可用于 MCP。"""
    await get_client().login()
    return {"authenticated": True}


@mcp.tool()
async def archery_list_instances(
    limit: int = 50, offset: int = 0, search: str = ""
) -> dict[str, Any]:
    """分页查询当前 Archery 账号有权查看的数据库实例。"""
    return await get_client().list_instances(limit=limit, offset=offset, search=search)


@mcp.tool()
async def archery_list_query_instances() -> dict[str, Any]:
    """查询当前账号所在资源组中允许只读查询的实例。"""
    return await get_client().list_query_instances()


@mcp.tool()
async def archery_list_databases(instance_name: str) -> dict[str, Any]:
    """查询指定可读实例中的数据库；实例归属由 Archery 校验。"""
    return await get_client().list_databases(instance_name)


@mcp.tool()
async def archery_query(
    instance_name: str,
    database: str,
    sql: str,
    limit: int = 100,
    schema: str = "",
) -> dict[str, Any]:
    """执行单条受限只读查询；最多返回 5000 行。"""
    return await get_client().query(
        instance_name=instance_name,
        database=database,
        sql=sql,
        limit=limit,
        schema=schema,
    )


@mcp.tool()
async def archery_export_query(
    instance_name: str,
    database: str,
    sql: str,
    max_rows: int = 0,
    page_size: int = 5000,
    schema: str = "",
    filename: str = "",
) -> dict[str, Any]:
    """将只读查询分批导出为 CSV；默认每页 5000 行，不限制总行数。"""
    export_dir = Path(os.getenv("ARCHERY_EXPORT_DIR", "exports"))
    return await get_client().export_query(
        instance_name=instance_name,
        database=database,
        sql=sql,
        export_dir=export_dir,
        max_rows=max_rows,
        page_size=page_size,
        schema=schema,
        filename=filename,
    )


@mcp.tool()
async def archery_list_workflows(
    limit: int = 20, offset: int = 0, search: str = ""
) -> dict[str, Any]:
    """分页查询当前账号有权查看的 SQL 工单。"""
    return await get_client().list_workflows(limit=limit, offset=offset, search=search)


@mcp.tool()
async def archery_workflow_status(workflow_id: int) -> dict[str, Any]:
    """查询一个有权查看的 SQL 工单当前状态。"""
    return await get_client().workflow_status(workflow_id)


@mcp.tool()
async def archery_workflow_detail(workflow_id: int) -> dict[str, Any]:
    """查询一个有权查看的 SQL 工单审核或执行明细。"""
    return await get_client().workflow_detail(workflow_id)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
