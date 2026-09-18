# PROJECT_STATUS — 黄瓜叶片病害智能识别与可信辅助诊断平台

> 更新日期：2026-09-18 ｜ 当前版本：**v0.3.0-controlled-generation**（论文受控生成已迁移，诊断主链路全部真实化）

## 状态速览

| 项 | 当前状态 |
|---|---|
| 诊断是否为 Mock | **否（全链路真实）**。检测：E2_gfix 论文冻结权重（`E2_gfix:ch4v22` ACTIVE）；报告：论文 agent_v1 受控生成流水线（六步），LLM 润色默认 **Kimi k3**（论文第六章同端点），12 项校验 + 确定性骨架回退；智能体：DeepSeek `deepseek-flash` |
| 已验证运行环境 | Windows 11 本地：便携 PostgreSQL 16.10 + 便携 Redis 5.0.14 + JDK 17.0.2 + Node 24 + Python 3.9 venv（torch 2.8.0 + vendor ultralytics 8.4.90）；**Docker 未安装，compose 链路未验证** |
| 已通过测试 | 浏览器主链路 17/17（d1）；异常场景 17/17（d2）；**ai pytest 26 passed**（含受控生成 24 项迁移测试）；agent pytest 13 passed；**admin mvn test 36 项全绿**；web `npm run build` 绿（含 vue-tsc type-check 前置） |
| 真实链路实测 | test301 检测冒烟：100% 有检出、均值 57ms；Kimi k3 真实润色：报告 status=polished、来源 9-11 个真实 KB 编号、端到端 40-50s（含纠错重润）；低置信（空白图）→ 健康叶 0.0 → 自动复核单创建 → 专家页"低置信复核"标签 |
| 下一阶段入口 | 评测数据补充（agent `/eval/run` 真实跑分）/ Docker 全栈 / 奶牛项目 |

## 已完成（全部有运行验证证据）

1. 六服务本地启动互联 + 登录 JWT 四角色 + 401/403 边界；
2. 图片上传诊断任务（文件类型校验 + 重复任务内容哈希去重）；
3. **E2_gfix 真实模型推理**（vendor 训练侧运行时；中文类别；CPU 56-128ms）；
4. **病斑框/类别/置信度/推理耗时展示**；
5. **论文受控生成诊断报告（agent_v1 迁移版）**：证据构建（rule A + 低置信/冲突双 flag）→ 知识显式映射检索（28 个合法 source_id）→ 确定性骨架 → LLM 受控润色（prompt 原文、PROTECTED 程序回填原则）→ 12 项校验 → 仅 1 次纠错重润 → 骨架回退（交付率 100% 机制）；报告含 `report_status`（polished / fallback_to_skeleton）与 `uncertainty_note`；
6. **报告来源追溯**：真实 28 条知识来源（由论文嵌套知识库聚合）同步业务库，弹窗可查原文；
7. 历史诊断记录 + 用户纠错反馈 + 专家复核流转；
8. **低置信度自动转专家复核**：检测最高置信度 < 0.75（含无检出）自动创建 UNCERTAIN 待复核单，复核页专用标签；
9. 操作日志（AOP 落库 + 只读查询接口）；
10. 模型版本登记激活（E2_gfix:ch4v22，sha256 + 官方口径指标）；
11. 农技诊断 Agent 多轮追问（意图/角色/RAG 徽标、工具轨迹、审计落库）；
12. 异常降级：AI 宕机 FAILED 落库、LLM 宕机骨架降级、agent 宕机友好错误、DB 宕机统一 500 可恢复、Redis 宕机双边降级、**LLM 输出不合规自动纠错重润与骨架回退**；
13. git 阶段提交。
14. 文档与资产收尾（2026-09-12 晚）：README 重写（论文资产集成现状表 + 4 张真实截图 + 主链路演示脚本，消除"插入点/Mock 骨架"过时表述）、验收报告与截图归档 docs/、E2_gfix 权重入库 git、ai Dockerfile 补齐 vendor/weights、docs/项目状态详录_20260914.md（含运行手册与坑位清单）。
15. 评测与备用通道（2026-09-14）：**智能体真实评测**（15 条意图用例 100%/Macro-F1 1.0，对话 Judge 六维 0.58-0.67，基线建立，见 docs/评测记录_20260914.md 与 eval_run_20260914.json）；**DeepSeek 备用通道联调**（LLM_PROVIDER=deepseek 下受控生成 polished、12 项校验全过、端到端 15s，与 Kimi 解耦成立）。
16. 面试官视角强化（2026-09-18）：**cucumber-admin 单元测试 36 项**（诊断去重/权限边界/文件类型/AI 宕机/反馈流转/低置信复核/模型激活互斥/日志查询 + 智能体对话转发与审计/登录签发 JWT/JWT 过期与篡改验签/MQ 生产消费成败路径，mvn test 全绿）；**操作日志前端查询页**（系统管理→操作日志，admin 权限，菜单按权过滤）；来源弹窗加载骨架屏（消除"未查询到"闪现）。

## 正在开发（下一阶段）

1. Docker compose 全栈验证（含 RabbitMQ 异步诊断链路）；
2. 对话 Agent prompt 完整度调优后重跑评测对比基线。

## 后续规划（非秋招必需）

- ~~操作日志前端查询页~~（已完成，见"已完成"第 16 项，a7f7dbe）；
- ~~来源弹窗加载骨架屏~~（已完成，见"已完成"第 16 项，a7f7dbe）；
- 批量评测页（test301 跑分留证）；
- 奶牛项目（单独任务书）。

## 已知问题

| # | 问题 | 影响 | 对策/状态 |
|---|---|---|---|
| 1 | Kimi k3 润色端到端 40-50s（首润可能丢 protected 字段触发纠错重润，与论文首过率 15% 同现象） | 演示等待较长 | admin 读超时已调至 150s；可切 `LLM_PROVIDER=deepseek` 提速（同校验管线）；异步 MQ 模式（compose）可彻底解耦 |
| 2 | DB 宕机时接口阻塞约 30s 才返回 500 | 极端场景体验 | HikariCP 连接超时，可接受；恢复后自动可用 |
| 3 | RabbitMQ 异步链路未真实验证 | compose 模式行为差异 | 装 Docker 后验证 |
| 4 | ~~来源弹窗加载期闪现"未查询到该来源"~~ | ~~轻微视觉瑕疵~~ | **已修复（a7f7dbe）**：弹窗加入加载骨架屏，消除闪现 |
| 5 | OOD 图片（非叶片）可能产生高置信误检 | 模型固有边界（非 OOD 检测器） | 面试话术素材：低置信复核只覆盖低置信，OOD 靠人工反馈闭环 |
| 6 | ~~操作日志无前端页面（仅 API+Swagger）~~ | ~~演示经 Swagger~~ | **已修复（a7f7dbe）**：系统管理→操作日志前端查询页（admin 权限，菜单按权过滤） |

## 验证命令速查

```bash
# 编译/构建
mvn -s tools/settings.xml -DskipTests package        # cucumber-admin（JAVA_HOME=tools/jdk17/...）
npm run build                                        # cucumber-web
# 单测
cucumber-ai/.venv/Scripts/python -m pytest tests/    # 26 项（含受控生成迁移测试）
cucumber-agent/.venv/Scripts/python -m pytest tests/ # 13 项（在 echomind/ 目录）
# 验收
tools/pw-venv/Scripts/python tools/acceptance/d1_main.py
tools/pw-venv/Scripts/python tools/acceptance/d2_exceptions.py
# 真实链路冒烟
# POST localhost:8000/api/v1/diagnose（detections 来自 /detect）→ report_status=polished
```
