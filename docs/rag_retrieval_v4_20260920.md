# RAG 检索对照实验 V4 运行摘要

- 配置：v3 + 关键词混合检索（确定性重排）
- embedding：BAAI/bge-small-zh-v1.5 (cpu, local cache)
- git commit：17ae521b3791f3f9ff18f537f79707923fa34bad
- 用例集：eval_cases.json（dev，version 2026-09-20）
- 用例数：26（可答进分母 23，域外对抗不进分母 3）

| 指标 | 值 |
| --- | --- |
| Recall@1 | 0.8261 |
| Recall@3 | 0.913 |
| Recall@5 | 0.9565 |
| MRR | 0.8783 |
| Top-1 source_id 命中率 | 0.8261 |
| 平均查询延迟 (ms) | 8.3 |
| 冷启动 (s) | 2.36 |
| 模型体积 (MB) | 91.9 |
| 内存 RSS 增量 (MB) | 413.4 |
| 安全类子集 n=6 Recall@5 | 0.8333 |
| 安全类子集 Top-1 | 0.6667 |
| 域外对抗 Top-1 平均置信度 | 0.7029 |
