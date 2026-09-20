# acceptance/ — 验收与验证脚本

本目录收录黄瓜平台的浏览器级/评测级验证脚本（自工作区 `tools/acceptance/` 入库，2026-09-20）。

| 脚本 | 用途 | 最近一次结果 |
|---|---|---|
| `d1_main.py` | 浏览器级主链路验收（登录→上传→诊断→报告→来源→记录→复核，Playwright） | 17/17 通过（2026-09-12） |
| `d2_exceptions.py` | 异常场景验收（AI/LLM/DB/Redis/agent 故障注入与恢复，**会真实停启服务**） | 17/17 通过（2026-09-12） |
| `cucumber_eval_run.py` | 智能体 `/eval/run` 评测跑分（需有效 LLM key） | 见 `docs/评测记录_20260914.md`、`docs/评测报告_20260920.md` |
| `verify_upload_0920.py` | 诊断上传页重构验证（候选列表/三 tab/不确定性/对比/导出） | 11/11 通过（2026-09-20） |
| `verify_upload_blank.py` | 空白图"未检出"降级路径验证 | 通过（2026-09-20） |
| `cucumber_demo_record.py` | 46s 演示视频录制（Playwright recordVideo，登录→上传诊断→候选三栏→来源弹窗→智能体真实对话） | 已录制（2026-09-20，GIF 见 `docs/screenshots/demo-cucumber-20260920.gif`） |

## 运行前置

- 服务：admin(8080) / ai(8000) / web(5173) / PostgreSQL / Redis 全部在跑（agent(8002) 仅 agent 相关用例需要）
- Playwright 环境：`tools/pw-venv`（本机工作区），或任意 `pip install playwright && playwright install chromium` 的环境
- 运行方式（仓库根目录）：`tools/pw-venv/Scripts/python acceptance/d1_main.py`

## 注意

- 脚本默认调用 PATH 中的 `psql`；使用便携 PostgreSQL 时通过环境变量覆盖（`PSQL` / `PGCTL` / `PGDATA` 等，见各脚本顶部常量）；
- 截图输出到脚本上两级目录的 `logs/shots/`（本机留存，不入库）；实证截图已精选入 `docs/screenshots/`；
- `d2_exceptions.py` 会停启本地服务，勿在演示期间运行。
