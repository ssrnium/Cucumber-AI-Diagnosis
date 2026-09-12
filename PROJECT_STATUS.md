# PROJECT_STATUS — 黄瓜叶片病害智能识别与可信辅助诊断平台

> 更新日期：2026-09-12 ｜ 当前版本：**v0.2.0-real-model**（E2_gfix 论文冻结权重已接入并激活）

## 状态速览

| 项 | 当前状态 |
|---|---|
| 诊断是否为 Mock | **否（真实模型）**。检测：E2_gfix 论文冻结权重（sha256 `d9e4ce25…447db`，模型版本页登记为 `E2_gfix:ch4v22` ACTIVE）；报告生成：cucumber-ai 的 LLM 仍为 mock provider（真实 LLM 联调属下一阶段）；智能体服务使用真实 LLM（DeepSeek `deepseek-flash`） |
| 已验证运行环境 | Windows 11 本地：便携 PostgreSQL 16.10 + 便携 Redis 5.0.14 + JDK 17.0.2 + Node 24 + Python 3.9 venv（torch 2.8.0 + vendor ultralytics 8.4.90）；**Docker 未安装，compose 链路未验证** |
| 已通过测试 | 浏览器主链路 17/17（d1_main.py）；异常场景 17/17（d2_exceptions.py）；ai pytest 2 passed；agent pytest 13 passed；admin `mvn package` BUILD SUCCESS；web `npm run build` 绿；真实模型浏览器验收（炭疽病 93.3%、耗时 64ms、真实版本展示） |
| 真实模型冒烟 | test301 批量：301/301 有检出，耗时均值 57ms / p50 61ms / 最大 162ms（CPU）；top1 类别一致 285/301=94.7%（运维口径，非官方 mAP；官方口径见模型版本页 metrics：P=92.48/R=87.37/mAP50=90.55，test301/imgsz640/conf0.001/iou0.7） |
| 当前已知问题 | 见下"已知问题"节 |
| 下一阶段入口 | agent_v1 受控生成工作流迁移（服务器最新版代码已在 `资料分析/handoff_20260912/`） |

## 已完成（全部有运行验证证据）

1. 六服务本地一键启动与互联：admin(8080) / ai(8000) / agent(8002) / web(5173) / PostgreSQL / Redis；
2. 登录与 JWT 鉴权（admin/expert/user/svc-agent 四角色；未登录 401、越权 403、错误密码提示）；
3. 图片上传 + 诊断任务创建（文件类型校验、20MB 上限、上传目录自动创建）；
4. **E2_gfix 真实模型推理**：vendor 内置训练侧运行时（ultralytics 8.4.90 + 融合模块），部署口径 imgsz=640/conf=0.25/iou=0.7/CPU；中文类别映射（健康叶/炭疽病/霜霉病/蔓枯病/白粉病）；
5. **病斑框、病害类别、置信度、推理耗时展示**（上传页结果卡头 `E2_gfix:ch4v22 · 推理耗时 xx ms`，记录详情同显）；
6. 基于知识库的结构化诊断报告（五段式）+ 来源追溯（source_id 弹窗原文）；
7. 历史诊断记录（分页/状态筛选/详情抽屉；权限隔离）；
8. 用户纠错反馈 → 专家复核流转（PENDING → REVIEWED）；
9. 重复任务处理（内容哈希 + 120s 窗口去重，改名重传仍命中）；
10. 操作日志（AOP 落库 + 只读查询接口）；
11. **模型版本登记与激活**：`E2_gfix:ch4v22` ACTIVE（含 sha256 与官方口径指标），新记录自动携带真实版本号；
12. 农技诊断 Agent 多轮追问（意图/角色/RAG 徽标、工具轨迹、审计落库）；
13. 异常降级：AI 宕机 FAILED 落库、LLM 宕机骨架降级、agent 宕机友好错误、DB 宕机统一 500 并可恢复、Redis 宕机双边降级；
14. 前端空数据态/错误提示态/加载态；
15. git 建仓与阶段提交。

## 正在开发（下一阶段，均未开始编码）

1. **agent_v1 受控生成工作流迁移**（服务器最新版在 `资料分析/handoff_20260912/handoff_20260912/agent_v1_code/`，含消融开关与 29 项单测）；
2. cucumber-ai 真实 LLM 联调（Kimi key 或论文口径定夺；替换 mock provider）；
3. 真实农业知识库完善（28 条论文知识库对齐进 admin/ai 双侧）；
4. 评测数据补充（agent `/eval/run` 真实跑分留证）。

## 后续规划（非秋招必需）

- Docker compose 全栈验证（含 RabbitMQ 异步诊断链路）；
- 低置信度自动转专家复核（检测低置信标记 rule A 已有口径，可接反馈单自动创建）；
- 操作日志前端查询页；
- 来源弹窗加载骨架屏；
- 模型版本页与 test301 批量评测页打通（批量跑分留证）。

## 已知问题

| # | 问题 | 影响 | 对策/状态 |
|---|---|---|---|
| 1 | 报告生成为 mock provider（非 LLM 真写） | 报告文本为模板化骨架 | 下一阶段接 agent_v1/真实 LLM；演示稿需声明 |
| 2 | DB 宕机时接口阻塞约 30s 才返回 500 | 极端场景体验 | HikariCP 连接超时所致，可接受；已验证恢复后自动可用 |
| 3 | RabbitMQ 异步链路未真实验证 | compose 模式行为与本地不同 | 装 Docker 后按 README 验证 |
| 4 | 来源弹窗加载期闪现"未查询到该来源" | 轻微视觉瑕疵 | 后续加 loading 态 |
| 5 | 操作日志无前端页面（仅 API+Swagger） | 演示时经 Swagger 展示 | 后续规划 |
| 6 | 去重命中时不展示推理耗时（未发生新推理） | 属正确语义，勿误判为缺字段 | 已在前端 toast 说明 |

## 验证命令速查

```bash
# 编译/构建
mvn -s tools/settings.xml -DskipTests package        # cucumber-admin（JAVA_HOME=tools/jdk17/...）
npm run build                                        # cucumber-web
# 单测
cucumber-ai/.venv/Scripts/python -m pytest tests/    # cucumber-ai
cucumber-agent/.venv/Scripts/python -m pytest tests/ # cucumber-agent（在 echomind/ 目录下跑）
# 验收
tools/pw-venv/Scripts/python tools/acceptance/d1_main.py        # 浏览器主链路
tools/pw-venv/Scripts/python tools/acceptance/d2_exceptions.py  # 异常场景（会停启服务）
# 真实模型冒烟（需 ai 在跑）
# 直接对 localhost:8000/api/v1/detect POST 叶片图，应返回中文类别+耗时+model_version=E2_gfix
```
