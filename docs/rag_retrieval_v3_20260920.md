# RAG 检索对照实验 V3 运行摘要

- 配置：v2 + 查询侧别名归一化
- embedding：BAAI/bge-small-zh-v1.5 (cpu, local cache)
- git commit：17ae521b3791f3f9ff18f537f79707923fa34bad
- 用例集：eval_cases.json（dev，version 2026-09-20）
- 用例数：26（可答进分母 23，域外对抗不进分母 3）

| 指标 | 值 |
| --- | --- |
| Recall@1 | 0.3043 |
| Recall@3 | 0.6087 |
| Recall@5 | 0.6957 |
| MRR | 0.4326 |
| Top-1 source_id 命中率 | 0.3043 |
| 平均查询延迟 (ms) | 8.3 |
| 冷启动 (s) | 2.43 |
| 模型体积 (MB) | 91.9 |
| 内存 RSS 增量 (MB) | 411.8 |
| 安全类子集 n=6 Recall@5 | 0.6667 |
| 安全类子集 Top-1 | 0.5 |
| 域外对抗 Top-1 平均置信度 | 0.5881 |
