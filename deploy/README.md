# 云服务器部署手册（无 GPU 单机，Ubuntu 22.04）

> 目标：一台 4 核 8G 无卡服务器上，`docker compose up -d --build` 一键起全平台。
> 验收口径：健康检查全过 → 前端可登录 → 上传诊断出报告 → 智能体可对话 → MQ 链路消费 → 容器重启后状态恢复。

## 1. 准备

```bash
# Docker（Ubuntu 22.04 官方一键）
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER && newgrp docker
docker compose version   # 需 v2.x
```

## 2. 部署

```bash
git clone https://github.com/ssrnium/Cucumber-AI-Diagnosis.git
cd Cucumber-AI-Diagnosis
cp .env.example .env          # 编辑填 key：LLM_PROVIDER / ANTHROPIC_API_KEY(或 KIMI_API_KEY) / JWT_SECRET
docker compose up -d --build  # 首次构建约 10-20 分钟（ai 镜像含 torch）
```

## 3. 验证清单

| 检查 | 命令/路径 | 预期 |
| --- | --- | --- |
| 健康状态 | `docker compose ps` | 全部 healthy/running |
| AI 服务 | `curl localhost:8000/health` | `llm_provider` 与 .env 一致 |
| 前端 | `http://<服务器IP>:8088` | 登录页（admin/Admin@123、user/User@123） |
| 诊断主链路 | 前端上传 test-assets 叶片图 | 病斑框 + 候选 + 报告（mock 或 polished） |
| 智能体 | 智能体对话页问"霜霉病怎么治" | 带 KB 引用回答（需 ANTHROPIC_API_KEY） |
| MQ 链路 | `docker compose logs cucumber-admin \| grep -i rabbit` | 无连接异常 |
| 重启恢复 | `docker compose restart && docker compose ps` | 数据卷数据仍在（诊断记录/知识库） |

## 4. 备注

- 端口：8088(web) / 8080(admin) / 8000(ai) / 8002(agent) / 15672(RabbitMQ 管理页，可选开放)；云安全组按需放行 8088 即可，其余建议仅内网。
- `LLM_PROVIDER=mock` 时报告走确定性骨架（无需任何 key）；置 deepseek/kimi 走真实润色。
- 监控可选：`docker compose --profile monitor up -d` 起 Prometheus（9090）。
- agent 容器内 Chroma 为嵌入式降级时无需 chromadb 容器（compose 已带服务端模式）。
