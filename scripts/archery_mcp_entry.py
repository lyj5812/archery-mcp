import logging
import sys

from archery_mcp.server import main


class _SilentStderr:
    encoding = "utf-8"
    errors = "replace"
    closed = False

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


if __name__ == "__main__":
    # MCP 使用 stdout 传输协议；发布版不向客户端写第三方调试日志。
    logging.disable(logging.CRITICAL)
    sys.stderr = _SilentStderr()
    main()
