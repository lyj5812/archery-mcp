# Archery MCP

[![许可证：MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

面向 [Archery](https://github.com/hhyo/Archery) 的安全只读 [Model Context Protocol](https://modelcontextprotocol.io/) Server。项目使用 Archery 用户名和密码认证，维护 Django Session 与 CSRF 状态，并向 AI 客户端提供实例查询、工单查询和受限 SQL 查询工具。

## 功能特性

- 通过 Archery `/authenticate/` 接口使用用户名和密码登录。
- 自动处理 CSRF、复用 Session，并在会话过期后重新登录一次。
- 使用 SQL AST 解析器对只读 SQL 做本地强校验。
- 实例归属、查询权限、超时、行数限制、审计日志和数据脱敏继续由 Archery 服务端负责。
- 不提供工单审批、变更 SQL 执行或任意 HTTP 代理工具。
- 已在 Archery v1.14.0 上完成真实环境验证。

## MCP 工具

| 工具 | 说明 |
|---|---|
| `archery_health` | 检查 Archery 连通性并识别版本 |
| `archery_login_status` | 验证配置的账号能否建立 Session |
| `archery_list_instances` | 查询账号有权查看的实例，需要实例列表权限 |
| `archery_list_query_instances` | 查询账号可用于只读查询的实例 |
| `archery_list_databases` | 查询指定实例中的数据库 |
| `archery_query` | 执行一条受限只读查询，最多返回 5000 行 |
| `archery_export_query` | 将查询结果分批写入 CSV，默认不限制总行数 |
| `archery_list_workflows` | 查询当前账号可见的 SQL 工单 |
| `archery_workflow_status` | 查询工单状态 |
| `archery_workflow_detail` | 查询工单审核或执行明细 |

## 安装方式一：Windows EXE（推荐）

Windows 用户可以直接使用发布产物 `archery-mcp.exe`，无需安装 Python，也无需单独安装依赖。

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "archery": {
      "command": "D:/tools/archery-mcp.exe",
      "env": {
        "ARCHERY_URL": "https://archery.example.com",
        "ARCHERY_USERNAME": "service-account",
        "ARCHERY_PASSWORD": "use-your-secret-store",
        "ARCHERY_VERIFY_TLS": "true",
        "ARCHERY_EXPORT_DIR": "D:/tools/archery-exports"
      }
    }
  }
}
```

EXE 使用标准输入输出与 MCP 客户端通信，因此不要直接双击运行。启动和停止由 MCP 客户端负责。

### 本地构建 EXE

维护者需要 Python 3.10 或更高版本执行构建，最终使用者不需要 Python：

```powershell
.\build-exe.ps1 -Python python
```

脚本会依次安装构建依赖、执行全部单元测试、使用 PyInstaller 生成单文件 EXE，并通过真实 MCP stdio 握手检查全部工具。成功产物位于：

```text
dist/archery-mcp.exe
```

GitHub Actions 中的“构建 Windows EXE”工作流支持手动触发，也会在推送 `v*` 标签时自动构建并上传 `archery-mcp-windows-x64` Artifact。

## 安装方式二：Docker

使用方无需安装 Python，但需要安装 Docker。镜像使用标准输入输出传输 MCP 协议，因此必须使用 `-i` 保持 stdin 打开。

### 构建并验证镜像

Windows PowerShell：

```powershell
.\build-docker.ps1 -Image archery-mcp:local -Python python
```

也可以手工执行：

```bash
docker build -t archery-mcp:local .
python scripts/smoke_test_docker.py archery-mcp:local
```

### Docker MCP 客户端配置

下面的 `-e ARCHERY_*` 只传递变量名，实际值来自 MCP 客户端进程环境，不会出现在 Docker 命令行参数中：

```json
{
  "mcpServers": {
    "archery": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777",
        "--security-opt",
        "no-new-privileges:true",
        "-e",
        "ARCHERY_URL",
        "-e",
        "ARCHERY_USERNAME",
        "-e",
        "ARCHERY_PASSWORD",
        "-e",
        "ARCHERY_VERIFY_TLS",
        "-e",
        "ARCHERY_TIMEOUT",
        "-e",
        "ARCHERY_EXPORT_DIR",
        "--volume",
        "D:/tools/archery-exports:/exports",
        "archery-mcp:local"
      ],
      "env": {
        "ARCHERY_URL": "https://archery.example.com",
        "ARCHERY_USERNAME": "service-account",
        "ARCHERY_PASSWORD": "use-your-secret-store",
        "ARCHERY_VERIFY_TLS": "true",
        "ARCHERY_TIMEOUT": "30",
        "ARCHERY_EXPORT_DIR": "/exports"
      }
    }
  }
}
```

项目也提供 `docker-compose.yml`。在宿主机设置所需环境变量后，可以执行：

```bash
docker compose build
docker compose run --rm archery-mcp
```

不要使用缺少 `-i` 的 `docker run`，否则容器无法接收 MCP 客户端发送的 stdio 消息。

## 安装方式三：Python

需要 Python 3.10 或更高版本。

```bash
git clone <仓库地址>
cd archery-mcp
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pip install .
```

Linux 或 macOS：

```bash
./.venv/bin/python -m pip install .
```

## 环境变量

| 环境变量 | 说明 |
|---|---|
| `ARCHERY_URL` | Archery 根地址，例如 `https://archery.example.com` |
| `ARCHERY_USERNAME` | 最小权限服务账号用户名 |
| `ARCHERY_PASSWORD` | 服务账号密码 |
| `ARCHERY_VERIFY_TLS` | 是否校验 TLS 证书，默认为 `true` |
| `ARCHERY_TIMEOUT` | HTTP 超时时间，默认 30 秒，最大 120 秒 |
| `ARCHERY_EXPORT_DIR` | CSV 导出目录，Python/EXE 默认是当前目录下的 `exports` |

## Python 方式的 MCP 客户端配置

Windows 示例：

```json
{
  "mcpServers": {
    "archery": {
      "command": "D:/path/to/archery-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "archery_mcp.server"],
      "env": {
        "ARCHERY_URL": "https://archery.example.com",
        "ARCHERY_USERNAME": "service-account",
        "ARCHERY_PASSWORD": "use-your-secret-store",
        "ARCHERY_VERIFY_TLS": "true",
        "ARCHERY_EXPORT_DIR": "D:/path/to/archery-exports"
      }
    }
  }
}
```

不要将真实凭据提交到 Git。`${ENV_VAR}` 占位符是否生效取决于 MCP 客户端，建议通过客户端进程环境或密钥管理服务注入凭据。

## 查询安全

`archery_query` 只接受一条 `SELECT`、`WITH` 或集合查询，并拒绝：

- 多条 SQL；
- 新增、更新、删除、DDL 和管理命令；
- `FOR UPDATE` 等锁查询；
- 文件导入、文件读取和文件导出操作；
- `sleep`、`benchmark` 等延迟或资源消耗函数；
- 普通查询超过 5000 行的返回请求。

## 分页导出

`archery_export_query` 适合导出超过 Archery 单次查询上限的数据。默认每页查询 5000 行，不限制总行数，并持续分页到 Archery 返回不足一页为止。工具不会把大量数据返回给 AI，而是流式写入 CSV，只返回文件路径、实际行数、分页次数和是否因显式限制而截断。

示例参数：

```json
{
  "instance_name": "read-replica",
  "database": "example",
  "sql": "select id, name from account order by id",
  "page_size": 5000,
  "max_rows": 0,
  "filename": "accounts.csv"
}
```

多页导出要求 SQL 顶层包含稳定且尽量唯一的 `ORDER BY`，例如 `order by id`。传入 SQL 不能自行包含 `LIMIT` 或 `OFFSET`，分页条件由 MCP 统一生成。CSV 使用 UTF-8 BOM 以兼容 Excel，并对 `=`、`+`、`-`、`@` 等开头的文本增加前缀，降低 CSV 公式注入风险。

`max_rows=0` 表示不限制总行数；传入正数时可以主动设置本次导出上限。不限量导出可能持续占用 Archery 查询资源和本地磁盘，请确保 SQL 使用稳定排序，并监控导出目录容量。

导出文件只能写入 `ARCHERY_EXPORT_DIR`。Docker 模式必须把宿主机目录挂载到 `/exports`；Compose 默认将项目下的 `exports` 目录挂载进去。

CSV 可能包含敏感业务数据。请限制导出目录的操作系统访问权限，设置定期清理策略，不要把导出目录提交到 Git、打进镜像或暴露为公共下载目录。

本地 SQL 校验属于纵深防御，不能替代 Archery 或数据库权限。生产环境必须使用专用最小权限账号，优先关联只读数据库实例，并保持 Archery 的资源组、查询权限、超时、审计日志、行数限制和数据脱敏配置有效。

启用交互式 2FA 的账号无法用于机器登录。服务检测到 2FA 后会终止登录，应为 MCP 创建未启用交互式 2FA 的最小权限服务账号。

## 本地开发

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

提交代码前请阅读 [贡献指南](CONTRIBUTING.md)。安全问题请按 [安全策略](SECURITY.md) 处理。

## 许可证

本项目使用 [MIT License](LICENSE)。许可证文件保留标准英文法律文本。
