import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {
    "archery_health",
    "archery_login_status",
    "archery_list_instances",
    "archery_list_query_instances",
    "archery_list_databases",
    "archery_query",
    "archery_export_query",
    "archery_list_workflows",
    "archery_workflow_status",
    "archery_workflow_detail",
}


async def verify(executable: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "ARCHERY_URL": "https://archery.example.com",
            "ARCHERY_USERNAME": "smoke-test",
            "ARCHERY_PASSWORD": "smoke-test",
        }
    )
    parameters = StdioServerParameters(command=executable, env=env)
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()

    actual = {tool.name for tool in result.tools}
    if actual != EXPECTED_TOOLS:
        missing = sorted(EXPECTED_TOOLS - actual)
        unexpected = sorted(actual - EXPECTED_TOOLS)
        raise RuntimeError(f"工具列表不一致，缺少={missing}，多出={unexpected}")
    print(f"EXE MCP 握手成功，已注册 {len(actual)} 个工具")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法：python scripts/smoke_test_exe.py <archery-mcp.exe>")
    asyncio.run(verify(os.path.abspath(sys.argv[1])))
