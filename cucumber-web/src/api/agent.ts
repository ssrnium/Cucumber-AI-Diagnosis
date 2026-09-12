import request from '../utils/request'

/**
 * 智能体模块 API（cucumber-admin 代理 cucumber-agent）。
 * 设计借鉴 EchoMindFrontend lib/backends.js 的响应归一化：
 * 所有函数返回归一化后的对象，字段名在此层完成 snake_case → camelCase 转换。
 */

export interface AgentChatResult {
  convId: string
  requestId: string
  response: string
  intent: string
  intentGroup: string
  agentType: string
  agentTypes: string[]
  primaryAgent: string
  supportingAgents: string[]
  toolsUsed: string[]
  routingReason: string
  routingConfidence: number
  escalated: boolean
  latencyMs: number
  knowledgeUsed: boolean
  intentConfidence: number
}

export interface AgentChatPayload {
  message: string
  convId?: string
  imageUrl?: string
  recordId?: number
}

/** 对话（cucumber-agent /chat 的 snake_case 响应在此归一化为 camelCase） */
export const agentChat = async (payload: AgentChatPayload): Promise<AgentChatResult> => {
  const res: any = await request.post('/api/v1/agent/chat', payload, { timeout: 150000 })
  const d = res?.data ?? {}
  return {
    convId: d.conv_id ?? payload.convId ?? '',
    requestId: d.request_id ?? '',
    response: d.response ?? '',
    intent: d.intent ?? 'other',
    intentGroup: d.intent_group ?? 'other',
    agentType: d.agent_type ?? '',
    agentTypes: d.agent_types ?? [],
    primaryAgent: d.primary_agent ?? '',
    supportingAgents: d.supporting_agents ?? [],
    toolsUsed: d.tools_used ?? [],
    routingReason: d.routing_reason ?? '',
    routingConfidence: d.routing_confidence ?? 0,
    escalated: Boolean(d.escalated),
    latencyMs: d.latency_ms ?? 0,
    knowledgeUsed: Boolean(d.knowledge_used),
    intentConfidence: d.intent_confidence ?? 0
  }
}

export const agentMonitor = () => request.get('/api/v1/agent/monitor')

export const agentEvalRun = (body?: object) =>
  request.post('/api/v1/agent/eval/run', body ?? {}, { timeout: 300000 })

export const agentSkills = () => request.get('/api/v1/agent/skills')

export const agentSkillsReload = () => request.post('/api/v1/agent/skills/reload')

export const agentToolTrace = (requestId: string) =>
  request.get(`/api/v1/agent/trace/tool/${requestId}`)

export const agentRecentTraces = (limit = 20) =>
  request.get('/api/v1/agent/trace/tools', { params: { limit } })

export const agentKnowledgeAdd = (documents: Array<{
  title: string
  content: string
  source_id?: string
  disease_type?: string
  level?: string
  category?: string
}>) => request.post('/api/v1/agent/knowledge/add', { documents })

export const agentKnowledgeStats = () => request.get('/api/v1/agent/knowledge/stats')
