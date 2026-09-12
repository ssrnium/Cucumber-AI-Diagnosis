# cucumber-agent Skills 文档

cucumber-agent 启动时会从 `ECHOMIND_SKILLS_DIR` 读取 Skills，并在匹配用户请求时注入到对应 Agent 的 system prompt。Skills 适合维护诊断引导规范、防治知识引用规则、用药合规边界、升级交接规则和禁止事项。

当前内置四类 Skills：

```text
skills/disease_diagnosis/SKILL.md    # 病害诊断：症状采集、图片诊断引导、报告解读、分诊
skills/prevention_knowledge/SKILL.md # 防治知识：RAG 检索问答、source_id 来源引用、知识边界
skills/medication_advice/SKILL.md    # 用药建议：药剂合规检查、安全间隔期、轮换用药、禁限用边界
skills/human_escalation/SKILL.md     # 人工升级：交接摘要、专家复核反馈创建、保守后续说明
```

## Skill 文件格式

推荐每个 Skill 使用独立目录，并将主文件命名为 `SKILL.md`：

```text
skills/<skill_name>/SKILL.md
```

文件顶部使用简单 front matter：

```markdown
---
name: 黄瓜用药安全建议规范
description: 适用于 MedicationAgent 的药剂合规检查与安全间隔期规范
keywords: 药,杀菌剂,剂量,安全间隔期,喷施
agents: medication
enabled: true
---
```

字段说明：

- `name`：Skill 展示名称，会出现在注入给模型的 prompt 中。
- `description`：简短说明，方便 `/skills` 接口排查。
- `keywords`：触发关键词，用户消息命中后才注入；多个关键词用英文逗号或中文逗号分隔均可。
- `agents`：适用 Agent，可填 `diagnosis`、`prevention`、`medication`、`escalation`，多个值用逗号分隔。
- `enabled`：是否启用，支持 `true/false`。

## 编写要求

- 重要规则放在文档前半部分，因为过长内容会按 prompt 预算截断。
- 一类 Skill 只描述一类职责，不要把诊断、防治、用药规则混在一个文件里。
- 必须包含“角色定位”“处理流程”“升级条件”“禁止事项”等稳定章节。
- 涉及用药的内容必须写明安全间隔期提醒与禁限用农药边界。
- 对无法保证的事项使用保守措辞，例如“通常”“以登记标签为准”“需要核验后确认”。
- 对需要人工专家复核的场景要明确写出升级条件。

## 热加载

修改 Skill 文件后，不需要重启服务，调用：

```bash
curl -X POST http://localhost:8002/skills/reload
```

查看加载结果和解析错误：

```bash
curl http://localhost:8002/skills
```
