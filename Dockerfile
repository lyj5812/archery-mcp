# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS builder

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir --upgrade build \
    && python -m build --wheel

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

LABEL org.opencontainers.image.title="Archery MCP" \
      org.opencontainers.image.description="面向 Archery 的安全只读 MCP Server" \
      org.opencontainers.image.licenses="MIT"

RUN groupadd --system --gid 10001 archery-mcp \
    && useradd --system --uid 10001 --gid archery-mcp --no-create-home archery-mcp \
    && mkdir -p /exports \
    && chown 10001:10001 /exports

COPY --from=builder /build/dist/*.whl /tmp/
RUN python -m pip install --no-cache-dir /tmp/*.whl \
    && rm -f /tmp/*.whl

USER 10001:10001
WORKDIR /app
ENV ARCHERY_EXPORT_DIR=/exports

# MCP 使用标准输入输出通信，运行容器时必须保留 stdin（docker run -i）。
ENTRYPOINT ["archery-mcp"]
