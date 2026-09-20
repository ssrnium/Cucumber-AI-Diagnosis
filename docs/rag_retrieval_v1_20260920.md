# RAG 检索对照实验 V1 运行摘要

- 配置：基线：Chroma 内置 all-MiniLM-L6-v2（英文）裸向量检索
- embedding：chroma-onnx-all-MiniLM-L6-v2
- git commit：17ae521b3791f3f9ff18f537f79707923fa34bad
- 用例集：eval_cases.json（dev，version 2026-09-20）
- 用例数：26（可答进分母 23，域外对抗不进分母 3）

| 指标 | 值 |
| --- | --- |
| Recall@1 | 0.0435 |
| Recall@3 | 0.1304 |
| Recall@5 | 0.2609 |
| MRR | 0.108 |
| Top-1 source_id 命中率 | 0.0435 |
| 平均查询延迟 (ms) | 14.7 |
| 冷启动 (s) | 0.19 |
| 模型体积 (MB) | 166.4 |
| 内存 RSS 增量 (MB) | 9.7 |
| 安全类子集 n=6 Recall@5 | 0.1667 |
| 安全类子集 Top-1 | 0.0 |
| 域外对抗 Top-1 平均置信度 | 0.2414 |
