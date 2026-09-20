# RAG 检索对照实验 V4 运行摘要

- 配置：v3 + 关键词混合检索（确定性重排）
- embedding：BAAI/bge-small-zh-v1.5 (cpu, local cache)
- git commit：17ae521b3791f3f9ff18f537f79707923fa34bad
- 用例集：eval_cases_heldout.json（held_out，version 2026-09-20）
- 用例数：23（可答进分母 23，域外对抗不进分母 0）

| 指标 | 值 |
| --- | --- |
| Recall@1 | 0.7826 |
| Recall@3 | 0.913 |
| Recall@5 | 0.9565 |
| MRR | 0.8565 |
| Top-1 source_id 命中率 | 0.7826 |
| 平均查询延迟 (ms) | 8.7 |
| 冷启动 (s) | 2.06 |
| 模型体积 (MB) | 91.9 |
| 内存 RSS 增量 (MB) | 175.7 |
| 安全类子集 n=6 Recall@5 | 0.8333 |
| 安全类子集 Top-1 | 0.5 |
| 域外对抗 Top-1 平均置信度 | None |
