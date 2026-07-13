import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from smoke_test_exe import EXPECTED_TOOLS


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


async def verify(image: str) -> None:
    parameters = StdioServerParameters(
        command="docker",
        args=[
            "run",
            "--rm",
            "-i",
            "--read-only",
            "--tmpfs",
            "/tmp:size=64m,mode=1777",
            "--security-opt",
            "no-new-privileges:true",
            "-e",
            "ARCHERY_URL=https://archery.example.com",
            "-e",
            "ARCHERY_USERNAME=smoke-test",
            "-e",
            "ARCHERY_PASSWORD=smoke-test",
            "-e",
            "ARCHERY_EXPORT_DIR=/tmp/exports",
            image,
        ],
        env=os.environ.copy(),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()

    actual = {tool.name for tool in result.tools}
    if actual != EXPECTED_TOOLS:
        missing = sorted(EXPECTED_TOOLS - actual)
        unexpected = sorted(actual - EXPECTED_TOOLS)
        raise RuntimeError(f"工具列表不一致，缺少={missing}，多出={unexpected}")
    print(f"Docker MCP 握手成功，已注册 {len(actual)} 个工具")


if __name__ == "__main__":
    image_name = sys.argv[1] if len(sys.argv) > 1 else "archery-mcp:local"
    asyncio.run(verify(image_name))
