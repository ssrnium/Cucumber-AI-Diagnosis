<template>
  <div class="agent-chat">
    <div class="chat-main">
      <div ref="msgListRef" class="msg-list">
        <div v-for="(msg, idx) in messages" :key="idx"
             :class="['msg-item', msg.role === 'user' ? 'msg-user' : 'msg-assistant']">
          <div class="msg-bubble">
            <div v-if="msg.imageUrl" class="msg-image">
              <el-image :src="msg.imageUrl" fit="cover" style="width: 160px; height: 120px" />
            </div>
            <div class="msg-text">{{ msg.content }}</div>
            <div v-if="msg.meta" class="msg-meta">
              <el-tag size="small" type="info">意图 {{ intentLabel(msg.meta.intent) }}</el-tag>
              <el-tag size="small" type="primary">主 Agent {{ agentLabel(msg.meta.primaryAgent) }}</el-tag>
              <el-tag v-if="msg.meta.knowledgeUsed" size="small" type="success">RAG</el-tag>
              <el-tag v-if="msg.meta.escalated" size="small" type="danger">转人工</el-tag>
              <el-tag v-if="msg.meta.supportingAgents.length" size="small" type="warning">
                协作 {{ msg.meta.supportingAgents.map(agentLabel).join('/') }}
              </el-tag>
              <el-link v-if="msg.meta.requestId" type="info" size="small"
                       @click="openTrace(msg.meta.requestId)">工具轨迹</el-link>
            </div>
          </div>
        </div>
        <div v-if="sending" class="msg-item msg-assistant">
          <div class="msg-bubble"><div class="msg-text">思考中…</div></div>
        </div>
      </div>

      <div class="chat-input">
        <el-upload :show-file-list="false" accept="image/*" :http-request="onUploadImage">
          <el-button :icon="Picture" circle title="上传叶片图片随消息诊断" />
        </el-upload>
        <el-input v-model="input" type="textarea" :rows="2" resize="none"
                  placeholder="描述症状 / 咨询防治 / 用药问题，或上传叶片照片诊断…"
                  @keydown.enter.exact.prevent="onSend" />
        <el-button type="primary" :loading="sending" @click="onSend">发送</el-button>
      </div>
      <div v-if="pendingImage" class="pending-image">
        <el-tag closable @close="pendingImage = ''">已附加图片：{{ pendingImage }}</el-tag>
      </div>
    </div>

    <el-drawer v-model="traceVisible" title="工具调用轨迹" size="480px">
      <el-skeleton v-if="traceLoading" :rows="6" animated />
      <template v-else-if="trace">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="request_id">{{ trace.request_id }}</el-descriptions-item>
          <el-descriptions-item label="意图">{{ intentLabel(trace.intent) }}</el-descriptions-item>
          <el-descriptions-item label="主 Agent">{{ agentLabel(trace.primary_agent) }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ trace.latency_ms }} ms</el-descriptions-item>
          <el-descriptions-item label="转人工">{{ trace.escalated ? '是' : '否' }}</el-descriptions-item>
        </el-descriptions>
        <el-table :data="trace.tool_calls || []" size="small" style="margin-top: 12px">
          <el-table-column prop="tool_name" label="工具" width="170" />
          <el-table-column label="结果" width="70">
            <template #default="{ row }">
              <el-tag :type="row.success && row.result_success !== false ? 'success' : 'danger'" size="small">
                {{ row.success && row.result_success !== false ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="latency_ms" label="ms" width="70" />
          <el-table-column label="缓存/重排">
            <template #default="{ row }">
              <el-tag v-if="row.cached" size="small" type="info">缓存</el-tag>
              <el-tag v-if="row.reranked" size="small" type="warning">重排</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </template>
      <el-empty v-else description="未找到该请求的轨迹（轨迹保留最近 200 次）" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import { agentChat, agentToolTrace, type AgentChatResult } from '../../../api/agent'
import { uploadDiagnosis } from '../../../api/diagnosis'

interface MsgMeta {
  requestId: string
  intent: string
  primaryAgent: string
  supportingAgents: string[]
  knowledgeUsed: boolean
  escalated: boolean
}

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  imageUrl?: string
  meta?: MsgMeta
}

const INTENT_LABELS: Record<string, string> = {
  disease_diagnosis: '病害诊断',
  prevention_qa: '防治问答',
  medication_advice: '用药建议',
  human_handoff: '转人工',
  greeting: '问候',
  other: '其他'
}

const AGENT_LABELS: Record<string, string> = {
  diagnosis: '诊断',
  prevention: '防治',
  medication: '用药',
  escalation: '人工升级'
}

const intentLabel = (v?: string) => INTENT_LABELS[v || ''] || v || '-'
const agentLabel = (v?: string) => AGENT_LABELS[v || ''] || v || '-'

const messages = ref<ChatMsg[]>([])
const input = ref('')
const convId = ref('')
const sending = ref(false)
const pendingImage = ref('')
const pendingRecordId = ref<number | undefined>(undefined)
const msgListRef = ref<HTMLElement>()

const traceVisible = ref(false)
const traceLoading = ref(false)
const trace = ref<any>(null)

const scrollBottom = async () => {
  await nextTick()
  if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight
}

/** 上传图片：复用诊断上传链路拿到 imageUrl 与 recordId，附加到下一条对话消息 */
const onUploadImage = async (options: any) => {
  try {
    const res: any = await uploadDiagnosis(options.file)
    const record = res?.data
    pendingImage.value = record?.image_url || ''
    pendingRecordId.value = record?.id
    ElMessage.success('图片已上传，发送消息后将由诊断 Agent 解读')
  } catch {
    ElMessage.error('图片上传失败')
  }
}

const onSend = async () => {
  const text = input.value.trim()
  if (!text || sending.value) return
  sending.value = true
  messages.value.push({ role: 'user', content: text, imageUrl: pendingImage.value || undefined })
  input.value = ''
  await scrollBottom()
  try {
    const result: AgentChatResult = await agentChat({
      message: text,
      convId: convId.value || undefined,
      imageUrl: pendingImage.value || undefined,
      recordId: pendingRecordId.value
    })
    convId.value = result.convId
    messages.value.push({
      role: 'assistant',
      content: result.response,
      meta: {
        requestId: result.requestId,
        intent: result.intent,
        primaryAgent: result.primaryAgent,
        supportingAgents: result.supportingAgents,
        knowledgeUsed: result.knowledgeUsed,
        escalated: result.escalated
      }
    })
    pendingImage.value = ''
    pendingRecordId.value = undefined
  } finally {
    sending.value = false
    await scrollBottom()
  }
}

const openTrace = async (requestId: string) => {
  traceVisible.value = true
  traceLoading.value = true
  trace.value = null
  try {
    const res: any = await agentToolTrace(requestId)
    trace.value = res?.data?.found ? res.data.trace : null
  } finally {
    traceLoading.value = false
  }
}
</script>

<style scoped>
.agent-chat {
  height: calc(100vh - 120px);
  display: flex;
}
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  padding: 12px;
}
.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.msg-item {
  display: flex;
  margin-bottom: 12px;
}
.msg-user {
  justify-content: flex-end;
}
.msg-bubble {
  max-width: 72%;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f0f2f5;
}
.msg-user .msg-bubble {
  background: #d6e4ff;
}
.msg-text {
  white-space: pre-wrap;
  line-height: 1.6;
}
.msg-image {
  margin-bottom: 6px;
}
.msg-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.chat-input {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding-top: 8px;
  border-top: 1px solid #e4e7ed;
}
.pending-image {
  padding-top: 6px;
}
</style>
