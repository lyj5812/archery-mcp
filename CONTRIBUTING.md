# 贡献指南

欢迎提交 Issue 和 Pull Request。

## 开发环境

```bash
python -m venv .venv
python -m pip install -e ".[test]"
python -m pytest -q
```

行为变更需要增加有针对性的测试。安全控制必须采用失败关闭策略：无法解析的 SQL、未知的可写语法、非法对象标识和不明确的认证状态都应拒绝处理。

Issue、测试、固定数据、日志和提交记录中禁止包含真实 Archery 地址、账号密码、SQL 查询结果、客户数据或生产对象标识。

代码应保持改动范围清晰，不要在功能提交中混入无关重构。提交 Pull Request 前请确保全部测试通过。
