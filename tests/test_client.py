import httpx
import pytest
from urllib.parse import parse_qs

from archery_mcp.client import (
    ArcheryClient,
    ArcheryConfig,
    ArcheryError,
    ArcheryTwoFactorRequired,
)


LOGIN_HTML = "<html>Login To Archery Archery</strong>&nbsp;(v1.14.0)</html>"


def config() -> ArcheryConfig:
    return ArcheryConfig(
        base_url="https://archery.example.com",
        username="mcp-user",
        password="test-only-secret",
    )


def login_response() -> httpx.Response:
    return httpx.Response(
        200,
        text=LOGIN_HTML,
        headers={"set-cookie": "csrftoken=csrf; Path=/"},
    )


@pytest.mark.asyncio
async def test_login_and_list_workflows() -> None:
    authenticated = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal authenticated
        if request.url.path == "/login/":
            return login_response()
        if request.url.path == "/authenticate/":
            assert request.headers["x-csrftoken"] == "csrf"
            authenticated = True
            return httpx.Response(
                200,
                json={"status": 0, "msg": "ok", "data": None},
                headers={"set-cookie": "sessionid=session; Path=/"},
            )
        if request.url.path == "/index/":
            return httpx.Response(200, text="index" if authenticated else LOGIN_HTML)
        if request.url.path == "/sqlworkflow_list/":
            assert request.headers["x-csrftoken"] == "csrf"
            return httpx.Response(200, json={"total": 1, "rows": [{"id": "1"}]})
        raise AssertionError(request.url)

    client = ArcheryClient(config(), transport=httpx.MockTransport(handler))
    try:
        result = await client.list_workflows()
        assert result["total"] == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_rejects_two_factor_account() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/":
            return login_response()
        return httpx.Response(
            200, json={"status": 0, "msg": "ok", "data": "temporary-session"}
        )

    client = ArcheryClient(config(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ArcheryTwoFactorRequired):
            await client.login()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_rejects_invalid_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/":
            return login_response()
        return httpx.Response(200, json={"status": 1, "msg": "invalid credentials"})

    client = ArcheryClient(config(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ArcheryError, match="invalid credentials"):
            await client.login()
    finally:
        await client.close()


def test_rejects_non_https_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        ArcheryConfig(
            base_url="http://archery.example.com",
            username="user",
            password="test-only-secret",
        )


@pytest.mark.parametrize(
    "sql",
    [
        "delete from account",
        "update account set amount = 0",
        "select 1; select 2",
        "select sleep(10)",
        "select * from account for update",
        "select * from account into outfile '/tmp/a'",
    ],
)
def test_rejects_unsafe_query(sql: str) -> None:
    with pytest.raises(ValueError):
        ArcheryClient._validate_readonly_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "select id, name from account where id = 1",
        "with active as (select id from account) select id from active",
        "select id from a union all select id from b",
    ],
)
def test_accepts_readonly_query(sql: str) -> None:
    ArcheryClient._validate_readonly_sql(sql)


@pytest.mark.asyncio
async def test_query_posts_bounded_readonly_request() -> None:
    authenticated = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal authenticated
        if request.url.path == "/login/":
            return login_response()
        if request.url.path == "/authenticate/":
            authenticated = True
            return httpx.Response(
                200,
                json={"status": 0, "msg": "ok", "data": None},
                headers={"set-cookie": "sessionid=session; Path=/"},
            )
        if request.url.path == "/index/":
            return httpx.Response(200, text="index" if authenticated else LOGIN_HTML)
        if request.url.path == "/query/":
            assert b"limit_num=25" in request.content
            assert b"instance_name=read-replica" in request.content
            return httpx.Response(
                200,
                json={"status": 0, "msg": "ok", "data": {"rows": [[1]]}},
            )
        raise AssertionError(request.url)

    client = ArcheryClient(config(), transport=httpx.MockTransport(handler))
    try:
        result = await client.query(
            instance_name="read-replica",
            database="example",
            sql="select 1",
            limit=25,
        )
        assert result["data"]["rows"] == [[1]]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_export_query_paginates_and_writes_csv(tmp_path) -> None:
    authenticated = False
    offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal authenticated
        if request.url.path == "/login/":
            return login_response()
        if request.url.path == "/authenticate/":
            authenticated = True
            return httpx.Response(
                200,
                json={"status": 0, "msg": "ok", "data": None},
                headers={"set-cookie": "sessionid=session; Path=/"},
            )
        if request.url.path == "/index/":
            return httpx.Response(200, text="index" if authenticated else LOGIN_HTML)
        if request.url.path == "/query/":
            form = parse_qs(request.content.decode())
            sql = form["sql_content"][0].lower()
            offset = int(sql.rsplit(" offset ", 1)[1])
            offsets.append(offset)
            rows = [[offset + 1, "=formula"]] if offset < 3 else []
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "msg": "ok",
                    "data": {"column_list": ["id", "value"], "rows": rows},
                },
            )
        raise AssertionError(request.url)

    client = ArcheryClient(config(), transport=httpx.MockTransport(handler))
    try:
        result = await client.export_query(
            instance_name="read-replica",
            database="example",
            sql="select id, value from account order by id",
            export_dir=tmp_path,
            max_rows=0,
            page_size=1,
            filename="accounts.csv",
        )
        assert result["row_count"] == 3
        assert result["page_count"] == 4
        assert result["truncated"] is False
        assert result["max_rows"] is None
        assert offsets == [0, 1, 2, 3]
        content = (tmp_path / "accounts.csv").read_text(encoding="utf-8-sig")
        assert content.splitlines() == ["id,value", "1,'=formula", "2,'=formula", "3,'=formula"]
    finally:
        await client.close()


@pytest.mark.parametrize(
    "sql,error",
    [
        ("select id from account", "ORDER BY"),
        ("select id from account order by id limit 10", "LIMIT"),
        ("select id from account order by id offset 10", "OFFSET"),
    ],
)
@pytest.mark.asyncio
async def test_export_query_rejects_unsafe_pagination(tmp_path, sql: str, error: str) -> None:
    client = ArcheryClient(config(), transport=httpx.MockTransport(lambda request: login_response()))
    try:
        with pytest.raises(ValueError, match=error):
            await client.export_query(
                instance_name="read-replica",
                database="example",
                sql=sql,
                export_dir=tmp_path,
                max_rows=20000,
            )
    finally:
        await client.close()


@pytest.mark.parametrize("filename", ["../data.csv", "a/b.csv", "数据.csv"])
def test_export_filename_rejects_unsafe_name(filename: str) -> None:
    with pytest.raises(ValueError):
        ArcheryClient._export_filename(filename)
