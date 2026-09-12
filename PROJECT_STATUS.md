# PROJECT_STATUS — 黄瓜叶片病害智能识别与可信辅助诊断平台

> 更新日期：2026-09-12 ｜ 当前版本：**v0.1.0-acceptance** ｜ 仓库基线：见 git log

## 状态速览

| 项 | 当前状态 |
|---|---|
| 诊断是否为 Mock | **是（检测为 MockDetector 固定病斑框；cucumber-ai 的 LLM 为 mock provider）**。智能体服务（cucumber-agent）使用真实 LLM（DeepSeek `deepseek-flash`，Anthropic 兼容协议） |
| 已验证运行环境 | Windows 11 本地：便携 PostgreSQL 16.10（127.0.0.1:5432）+ 便携 Redis 5.0.14（6379）+ JDK 17.0.2 + Node 24 + Python 3.9 venv；**Docker 未安装，compose 链路未验证** |
| 已通过测试 | 浏览器级主链路 17/17（tools/acceptance/d1_main.py）；异常场景 17/17（tools/acceptance/d2_exceptions.py）；cucumber-ai pytest 2 passed；cucumber-agent pytest 13 passed；admin `mvn package` BUILD SUCCESS；web `npm run build` 绿 |
| 当前已知问题 | 见下"已知问题"节 |
| 下一阶段入口 | E2_gfix 真实模型接入（等服务器权重文件） |

## 已完成（全部有运行验证证据）

1. 六服务本地一键启动与互联：admin(8080) / ai(8000) / agent(8002) / web(5173) / PostgreSQL / Redis；
2. 登录与 JWT 鉴权（admin/expert/user/svc-agent 四角色；未登录 401、越权 403、错误密码提示）；
3. 图片上传 + 诊断任务创建（文件类型校验、20MB 上限、上传目录自动创建）；
4. 诊断主链路：admin → ai `/detect` + `/diagnose` → 病斑框/类别/置信度展示 → 结构化报告五段（结论/依据/农艺/化防/安全）；
5. 报告来源追溯（source_id → 知识库原文弹窗）；
6. 历史诊断记录（分页/状态筛选/详情抽屉；普通用户只看自己，专家/管理员看全部）；
7. 用户纠错反馈 → 专家复核流转（PENDING → REVIEWED，含复核人落库）；
8. 重复任务处理（内容哈希文件名 + 120s 窗口去重，改名重传仍命中，前端提示"已打开原记录"）；
9. 操作日志（OperLog AOP 落库 + `GET /api/v1/system/log` 只读查询接口，admin 权限）；
10. 模型版本与诊断结果关联（record.model_version，无 ACTIVE 模型时记 `mock-detector`）；
11. 农技诊断 Agent 多轮追问（意图徽标/主 Agent 徽标/RAG 徽标/工具轨迹抽屉；对话落 agent_session/agent_message 审计表）；
12. 异常降级：AI 宕机→记录 FAILED+友好提示；LLM 宕机→骨架降级报告；agent 宕机→代理层友好错误；DB 宕机→统一 500 JSON；Redis 宕机→admin 不受影响、agent 降级应答；
13. 前端空数据态/错误提示态/加载态；
14. git 建仓与验收基线提交。

## 正在开发（下一阶段，均未开始编码）

1. **E2_gfix 真实模型接入**（等服务器权重；接入点见验收报告第 9 节）；
2. agent_v1 受控生成工作流迁移进 cucumber-ai `app/services/report.py`；
3. 真实农业知识库完善（28 条论文知识库对齐进 admin/ai 双侧）；
4. cucumber-ai 真实 LLM 联调（Kimi key 或论文口径定夺）；
5. 评测数据补充（agent `/eval/run` 真实跑分留证）。

## 后续规划（非秋招必需）

- Docker compose 全栈验证（含 RabbitMQ 异步诊断链路）；
- 低置信度自动转专家复核（阈值规则 + 自动建反馈单）；
- 操作日志前端查询页；
- 来源弹窗加载骨架屏（当前加载期闪现"未查询到该来源"）；
- 推理耗时展示（detect 响应加 inference_ms，前端显示）；
- 三维/大屏等展示增强（不做进秋招版）。

## 已知问题

| # | 问题 | 影响 | 对策/状态 |
|---|---|---|---|
| 1 | 检测与报告为 Mock | 演示时病斑框固定 | 下一阶段接 E2_gfix 后消除；演示稿需先声明 |
| 2 | DB 宕机时接口阻塞约 30s 才返回 500 | 极端场景体验 | HikariCP 连接超时所致，可接受；已验证恢复后自动可用 |
| 3 | RabbitMQ 异步链路（PENDING→MQ→DONE）未真实验证 | compose 模式行为与本地不同 | 装 Docker 后按 README 验证 |
| 4 | 来源弹窗加载期闪现"未查询到该来源" | 轻微视觉瑕疵 | 后续加 loading 态 |
| 5 | 操作日志无前端页面（仅 API+Swagger） | 演示时经 Swagger 展示 | 后续规划 |

## 验证命令速查

```bash
# 编译/构建
mvn -s tools/settings.xml -DskipTests package        # cucumber-admin（需 JAVA_HOME=tools/jdk17/...）
npm run build                                        # cucumber-web
# 单测
cucumber-ai/.venv/Scripts/python -m pytest tests/    # cucumber-ai
cucumber-agent/.venv/Scripts/python -m pytest tests/ # cucumber-agent（在 echomind/ 目录下跑）
# 验收
tools/pw-venv/Scripts/python tools/acceptance/d1_main.py        # 浏览器主链路
tools/pw-venv/Scripts/python tools/acceptance/d2_exceptions.py  # 异常场景（会停启服务）
```
