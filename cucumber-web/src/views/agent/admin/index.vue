<template>
  <div>
    <el-tabs v-model="tab">
      <el-tab-pane label="Skills 管理" name="skills">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>已加载 Skills（{{ skills.length }}）</span>
              <el-button size="small" type="primary" :loading="reloading" @click="onReload">
                热加载
              </el-button>
            </div>
          </template>
          <el-table :data="skills" size="small" border>
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column prop="description" label="说明" min-width="240" show-overflow-tooltip />
            <el-table-column label="适用 Agent" width="180">
              <template #default="{ row }">
                <el-tag v-for="a in row.agents" :key="a" size="small" style="margin-right: 4px">{{ a }}</el-tag>
                <span v-if="!row.agents?.length">全部</span>
              </template>
            </el-table-column>
            <el-table-column prop="content_chars" label="长度" width="80" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                  {{ row.enabled ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-alert v-for="(err, i) in skillErrors" :key="i" :title="err" type="error"
                    :closable="false" style="margin-top: 8px" />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="知识库导入" name="knowledge">
        <el-card shadow="never">
          <el-form label-width="110px" style="max-width: 720px">
            <el-form-item label="标题">
              <el-input v-model="docForm.title" placeholder="如：黄瓜霜霉病化学防治方案" />
            </el-form-item>
            <el-form-item label="来源编号">
              <el-input v-model="docForm.source_id" placeholder="KB-XXX-NNN（可选，用于来源追溯）" />
            </el-form-item>
            <el-form-item label="病害类型">
              <el-select v-model="docForm.disease_type" clearable placeholder="可选">
                <el-option v-for="t in diseaseTypes" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
            <el-form-item label="内容">
              <el-input v-model="docForm.content" type="textarea" :rows="6" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="adding" @click="onAddDoc">导入知识库</el-button>
            </el-form-item>
          </el-form>
          <el-divider>或上传文件（.txt / .md / .json 数组）</el-divider>
          <el-upload :show-file-list="false" :http-request="onUploadFile" accept=".txt,.md,.json">
            <el-button>选择文件上传</el-button>
          </el-upload>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="评测" name="eval">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>端到端评测（意图准确率 + LLM-as-Judge 六维评分 + 回归检测）</span>
              <el-button type="primary" :loading="evalRunning" @click="onRunEval">
                运行默认用例
              </el-button>
            </div>
          </template>
          <template v-if="evalReport">
            <el-row :gutter="12">
              <el-col :span="6">
                <el-statistic title="通过率" :value="Math.round((evalReport.pass_rate || 0) * 100)" suffix="%" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="用例总数" :value="evalReport.total || 0" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="意图准确率"
                              :value="Math.round(((evalReport.avg_scores || {}).intent_accuracy || 0) * 100)"
                              suffix="%" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="综合均分"
                              :value="(((evalReport.avg_scores || {}).overall) || avgOverall).toFixed(3)" />
              </el-col>
            </el-row>
            <el-divider>维度均分</el-divider>
            <el-table :data="scoreRows" size="small" border style="max-width: 640px">
              <el-table-column prop="dim" label="维度" width="200" />
              <el-table-column label="得分">
                <template #default="{ row }">
                  <el-progress :percentage="Math.round(row.value * 100)" />
                </template>
              </el-table-column>
            </el-table>
            <template v-if="(evalReport.regressions || []).length">
              <el-divider>回归警告</el-divider>
              <el-alert v-for="(r, i) in evalReport.regressions" :key="i" :title="r" type="error"
                        :closable="false" style="margin-bottom: 6px" />
            </template>
            <template v-if="(evalReport.recommendations || []).length">
              <el-divider>优化建议</el-divider>
              <el-alert v-for="(r, i) in evalReport.recommendations" :key="i" :title="r" type="info"
                        :closable="false" style="margin-bottom: 6px" />
            </template>
            <el-divider>明细</el-divider>
            <el-table :data="evalReport.results || []" size="small" border max-height="360">
              <el-table-column prop="test_id" label="用例" width="180" />
              <el-table-column label="通过" width="70">
                <template #default="{ row }">
                  <el-tag :type="row.passed ? 'success' : 'danger'" size="small">
                    {{ row.passed ? '通过' : '未过' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="detail" label="详情" min-width="260" show-overflow-tooltip />
            </el-table>
          </template>
          <el-empty v-else description="尚未运行评测" />
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  agentEvalRun,
  agentKnowledgeAdd,
  agentSkills,
  agentSkillsReload
} from '../../../api/agent'
import request from '../../../utils/request'

const tab = ref('skills')

// ── Skills ──
const skills = ref<any[]>([])
const skillErrors = ref<string[]>([])
const reloading = ref(false)

const loadSkills = async () => {
  try {
    const res: any = await agentSkills()
    skills.value = res?.data?.skills || []
    skillErrors.value = res?.data?.errors || []
  } catch {
    skills.value = []
  }
}

const onReload = async () => {
  reloading.value = true
  try {
    const res: any = await agentSkillsReload()
    skills.value = res?.data?.skills || []
    skillErrors.value = res?.data?.errors || []
    ElMessage.success('Skills 已热加载')
  } finally {
    reloading.value = false
  }
}

// ── 知识库导入 ──
const diseaseTypes = ['黄瓜霜霉病', '黄瓜白粉病', '黄瓜炭疽病', '黄瓜蔓枯病', '健康叶片', '通用']
const docForm = ref({ title: '', content: '', source_id: '', disease_type: '' })
const adding = ref(false)

const onAddDoc = async () => {
  if (!docForm.value.title || !docForm.value.content) {
    ElMessage.warning('请填写标题和内容')
    return
  }
  adding.value = true
  try {
    const res: any = await agentKnowledgeAdd([{ ...docForm.value }])
    ElMessage.success(res?.data?.message || '导入成功')
    docForm.value = { title: '', content: '', source_id: '', disease_type: '' }
  } finally {
    adding.value = false
  }
}

const onUploadFile = async (options: any) => {
  const formData = new FormData()
  formData.append('file', options.file)
  try {
    const res: any = await request.post('/api/v1/agent/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    ElMessage.success(res?.data?.message || '文件导入成功')
  } catch {
    // 错误已由拦截器提示
  }
}

// ── 评测 ──
const evalRunning = ref(false)
const evalReport = ref<any>(null)

const DIM_LABELS: Record<string, string> = {
  relevance: '相关性',
  accuracy: '准确性',
  completeness: '完整性',
  helpfulness: '有用性',
  diagnosis_accuracy: '诊断准确性',
  medication_safety: '用药安全性',
  intent_accuracy: '意图识别准确率'
}

const scoreRows = computed(() =>
  Object.entries(evalReport.value?.avg_scores || {})
    .filter(([k]) => k !== 'overall')
    .map(([k, v]) => ({ dim: DIM_LABELS[k] || k, value: v as number }))
)

const avgOverall = computed(() => {
  const rows = scoreRows.value.filter((r) => r.dim !== '意图识别准确率')
  if (!rows.length) return 0
  return rows.reduce((sum, r) => sum + r.value, 0) / rows.length
})

const onRunEval = async () => {
  evalRunning.value = true
  try {
    const res: any = await agentEvalRun()
    evalReport.value = res?.data || null
    ElMessage.success('评测完成')
  } catch {
    ElMessage.error('评测失败（确认 cucumber-agent 已配置 ANTHROPIC_API_KEY）')
  } finally {
    evalRunning.value = false
  }
}

onMounted(loadSkills)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
