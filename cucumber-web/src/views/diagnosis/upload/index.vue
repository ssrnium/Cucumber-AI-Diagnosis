<template>
  <div>
    <el-card shadow="never">
      <template #header>上传黄瓜叶片图片，进行病害智能识别与辅助诊断</template>
      <el-upload drag :auto-upload="false" :show-file-list="false" accept="image/*"
                 :on-change="onFileChange">
        <el-icon size="48" color="#909399"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽图片到此处，或 <em>点击选择图片</em>（不超过 20MB）</div>
      </el-upload>
      <div class="symptom-area">
        <div class="symptom-chips">
          <span class="chips-label">常见症状：</span>
          <el-tag v-for="chip in SYMPTOM_CHIPS" :key="chip" class="symptom-chip"
                  :type="symptomText.includes(chip) ? 'success' : 'info'"
                  @click="appendSymptom(chip)">{{ chip }}</el-tag>
        </div>
        <el-input v-model="symptomText" type="textarea" :rows="2"
                  placeholder="补充症状描述（选填），如：叶片正面出现黄斑，叶背有灰紫色霉层" />
      </div>
      <div class="action-bar">
        <el-button v-if="loading" type="danger" plain @click="onCancelDiagnose">取消诊断</el-button>
        <el-button type="primary" :disabled="!rawFile" :loading="loading" @click="onDiagnose">
          {{ loading ? scanPhaseText : '开始诊断' }}
        </el-button>
      </div>
    </el-card>

    <el-row v-if="previewUrl" :gutter="16" class="result-row">
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>
            病斑检测结果<template v-if="record">（{{ record.model_version }}<span v-if="record.inference_ms"> · 推理耗时 {{ record.inference_ms.toFixed(0) }}ms</span>）</template>
          </template>
          <div class="image-wrapper">
            <img ref="imgRef" :src="previewUrl" class="leaf-image" @load="onImageLoad" />
            <div v-for="(box, index) in scaledBoxes" :key="index" class="detect-box"
                 :class="{ 'detect-box-active': box.label === selectedLabel }" :style="box.style">
              <span class="detect-label">{{ box.label }} {{ (box.confidence * 100).toFixed(0) }}%</span>
            </div>
            <!-- 扫描加载动画：诊断中在叶片预览图上叠加绿光条上下扫描（仿 qingye 原型 .scanner/@keyframes scan） -->
            <div v-if="loading" class="scan-mask">
              <div class="scan-line" />
              <div class="scan-text">{{ scanPhaseText }}…</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card v-if="loading" shadow="never" v-loading="true" element-loading-text="正在诊断，可随时取消"
                 class="placeholder-card" />
        <template v-else-if="record">
          <el-card v-if="record.status === 'PENDING'" shadow="never">
            <el-alert type="info" :closable="false"
                      title="诊断任务已受理（异步模式），请在「诊断记录」页查看结果" />
          </el-card>
          <el-card v-else-if="record.status === 'FAILED'" shadow="never">
            <el-alert type="error" :closable="false" title="AI 服务暂不可用，诊断失败，请稍后重试" />
          </el-card>
          <template v-else-if="report">
            <el-alert v-if="dirty" type="warning" :closable="false" class="block-gap"
                      title="输入已修改（症状描述与本轮诊断时不一致），请重新诊断" />
            <el-alert v-if="uncertain" type="warning" :closable="false" class="block-gap"
                      show-icon title="需要补充信息：当前结果不确定性较高">
              <ul class="alert-list">
                <li v-for="(reason, i) in uncertainReasons" :key="i">{{ reason }}</li>
                <li>建议补拍更清晰的叶片特写（叶背 / 病斑细节），或在上方补充症状描述后重新诊断。</li>
                <li v-if="autoReviewed">本记录已按后端口径（最高置信度 &lt; {{ (REVIEW_THRESHOLD * 100).toFixed(0) }}%）自动转入专家复核，可在「专家复核」页跟进。</li>
              </ul>
            </el-alert>
            <el-card shadow="never" class="report-card">
              <template #header>
                诊断结论：
                <el-tag v-if="inconclusive" type="info" size="large">信息不足，无法判定</el-tag>
                <template v-else>
                  <el-tag type="danger" size="large">{{ report.disease_type }}</el-tag>
                  <span class="confidence">置信度 {{ (report.confidence * 100).toFixed(1) }}%</span>
                </template>
              </template>

              <!-- 候选排序列表：按病害类别聚合 detections（同类取最高置信度），点击切换查看各候选依据 -->
              <div v-if="candidates.length" class="candidates">
                <div class="candidates-title">
                  <strong>候选结果</strong>
                  <span v-if="candidates.length > 1">点击切换，查看对应依据</span>
                </div>
                <div v-for="(c, i) in candidates" :key="c.label" class="candidate"
                     :class="{ 'candidate-selected': c.label === selectedLabel }"
                     @click="selectedLabel = c.label">
                  <span class="candidate-rank">{{ String(i + 1).padStart(2, '0') }} / {{ i === 0 ? '首位候选' : '备选' }}</span>
                  <span class="candidate-name">{{ c.label }}</span>
                  <span class="candidate-score">{{ (c.confidence * 100).toFixed(1) }}<small>%</small></span>
                  <div class="score-bar"><i :style="{ width: `${c.confidence * 100}%` }" /></div>
                </div>
                <div v-if="candidates.length > 1" class="candidate-toolbar">
                  <el-button size="small" @click="openCompare">对比候选</el-button>
                </div>
              </div>
              <el-alert v-else-if="inconclusive" type="warning" :closable="false" class="block-gap"
                        title="未检出可信病斑，当前结果不足以判断叶片是否健康；本记录已自动转入专家复核" />
              <el-alert v-else type="info" :closable="false" class="block-gap"
                        title="未检出明显病斑，以下为图像级诊断结论" />

              <!-- 三 tab 结果区 -->
              <el-tabs v-model="activeTab" class="result-tabs">
                <el-tab-pane label="图文依据" name="evidence">
                  <template v-if="selectedCandidate">
                    <h4>检测证据（{{ selectedCandidate.label }}）</h4>
                    <p class="evidence-text">
                      左侧原图中共检出 {{ selectedCandidate.count }} 处该病类病斑，最高置信度
                      {{ (selectedCandidate.confidence * 100).toFixed(1) }}%，检测框已按原图坐标缩放标注。
                    </p>
                  </template>
                  <h4>本轮症状线索</h4>
                  <div class="input-quote">{{ diagnosedSymptom || '未填写症状描述。' }}</div>
                  <template v-if="selectedLabel === topLabel">
                    <h4>知识来源</h4>
                    <el-tag v-for="sid in report.source_ids" :key="sid" class="source-tag"
                            @click="showSource(sid)">{{ sid }}</el-tag>
                    <p v-if="!report.source_ids?.length" class="evidence-text">本轮报告未引用知识来源。</p>
                  </template>
                  <template v-else>
                    <h4>{{ selectedLabel }} · 知识库条目</h4>
                    <template v-if="selectedKnowledge.length">
                      <div v-for="entry in selectedKnowledge" :key="entry.source_id" class="knowledge-entry">
                        <span class="source-tag-wrap">
                          <el-tag class="source-tag" @click="showSource(entry.source_id)">{{ entry.source_id }}</el-tag>
                        </span>
                        <span>{{ entry.title }}</span>
                      </div>
                    </template>
                    <p v-else class="evidence-text">知识库未检索到「{{ selectedLabel }}」相关条目。</p>
                    <p class="evidence-text">报告正文基于首位候选「{{ topLabel }}」生成，备选候选仅展示知识库参考。</p>
                  </template>
                </el-tab-pane>

                <el-tab-pane label="诊断说明" name="explain">
                  <h4>分数与依据怎么来的</h4>
                  <ul><li v-for="(item, i) in report.basis" :key="'b' + i">{{ item }}</li></ul>
                  <p class="evidence-text">
                    结论类别按规则取全图最高置信度病斑框所属类别；置信度为该框的检测置信度，非患病概率。
                    报告生成方式：{{ report.report_status === 'polished' ? 'LLM 受控润色并通过校验' : report.report_status === 'inconclusive' ? '无检测框，按信息不足口径直接返回（不调用 LLM）' : '确定性骨架回退（LLM 未通过校验或不可用）' }}。
                  </p>
                  <h4>还需排查什么</h4>
                  <p class="evidence-text">
                    {{ report.uncertainty_note || '本次未发现显著不确定性信号；候选库仅覆盖已登记病害，未覆盖混合感染与生理性损伤，田间确诊请结合现场检查。' }}
                  </p>
                </el-tab-pane>

                <el-tab-pane label="下一步建议" name="next">
                  <h4>农艺措施</h4>
                  <ul><li v-for="(item, i) in report.agronomy" :key="'a' + i">{{ item }}</li></ul>
                  <h4>化学防治</h4>
                  <ul><li v-for="(item, i) in report.chemical" :key="'c' + i">{{ item }}</li></ul>
                  <h4>安全注意</h4>
                  <ul><li v-for="(item, i) in report.safety" :key="'s' + i">{{ item }}</li></ul>
                </el-tab-pane>
              </el-tabs>

              <div class="result-foot">
                <el-button size="small" @click="exportReport">导出 TXT 报告</el-button>
              </div>
            </el-card>
          </template>
        </template>
        <el-card v-else shadow="never" class="empty-card">
          <el-empty description="尚未诊断：上传叶片图片后点击「开始诊断」，将展示候选排序、诊断依据与防治建议">
            <el-button type="primary" plain @click="useSample">试试示例图</el-button>
          </el-empty>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-else shadow="never" class="result-row empty-card">
      <el-empty description="上传黄瓜叶片图片开始诊断；也可以先试用示例图体验完整流程">
        <el-button type="primary" plain @click="useSample">试试示例图</el-button>
      </el-empty>
    </el-card>

    <!-- 候选对比弹窗（P2）：逐项对照匹配分 / 检出框数 / 典型特征 / 知识来源 -->
    <el-dialog v-model="compareVisible" title="把相似候选，放在一起看" width="640px">
      <div class="compare-selectors">
        <span>候选 A
          <el-select v-model="compareA" style="width: 160px" @change="onCompareChange('A')">
            <el-option v-for="c in candidates" :key="c.label" :label="c.label" :value="c.label" />
          </el-select>
        </span>
        <span>候选 B
          <el-select v-model="compareB" style="width: 160px" @change="onCompareChange('B')">
            <el-option v-for="c in candidates.filter(x => x.label !== compareA)" :key="c.label"
                       :label="c.label" :value="c.label" />
          </el-select>
        </span>
      </div>
      <el-table :data="compareRows" border>
        <el-table-column prop="dim" label="比较维度" width="110" />
        <el-table-column :label="compareA" prop="a" />
        <el-table-column :label="compareB" prop="b" />
      </el-table>
      <p class="compare-tip">对比表为知识库特征参考与检测分数对照，不构成对本次图像的实验验证。</p>
    </el-dialog>

    <el-dialog v-model="sourceDialogVisible" :title="`来源原文：${currentSource?.source_id || ''}`"
               width="520px">
      <template v-if="sourceLoading">
        <el-skeleton :rows="4" animated />
      </template>
      <template v-else-if="currentSource">
        <h4>{{ currentSource.title }}
          <el-tag size="small">{{ currentSource.level }} 级 / {{ currentSource.category }}</el-tag>
        </h4>
        <p>{{ currentSource.content }}</p>
      </template>
      <el-empty v-else description="未查询到该来源" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadFile } from 'element-plus'
import { uploadDiagnosis } from '../../../api/diagnosis'
import { knowledgeList } from '../../../api/knowledge'
import sampleLeafUrl from '@/assets/sample-leaf.jpg'

// 后端低置信复核口径：DiagnosisController 中最高检测置信度低于 0.75 时自动创建专家复核单
const REVIEW_THRESHOLD = 0.75
// 前端"需要补充信息"不确定性提示阈值（仿 qingye 原型 diagnosis.js:169-172 的判定口径）：
// 首位候选置信度低于 65%，或与次位候选分差小于 20% 时视为不确定
const UNCERTAIN_TOP_THRESHOLD = 0.65
const UNCERTAIN_MARGIN_THRESHOLD = 0.20
const SYMPTOM_CHIPS = ['黄斑', '白粉', '霜霉', '枯萎', '畸形']

interface Candidate {
  label: string
  confidence: number
  count: number
}

const rawFile = ref<File | null>(null)
const previewUrl = ref('')
const loading = ref(false)
const record = ref<any>(null)
const imgRef = ref<HTMLImageElement>()
const scale = ref(1)

const report = computed(() => record.value?.report)

// 症状输入（前端辅助信息，随诊断请求发送给后端，并随导出报告与图文依据展示）
const symptomText = ref('')
const diagnosedSymptom = ref('')
const dirty = computed(() =>
  !!record.value && symptomText.value.trim() !== diagnosedSymptom.value
)

// 把自由文本症状拆成条目列表（按中英文逗号/顿号/分号/换行分隔），与 chips 拼接格式一致
const symptomList = (text: string): string[] =>
  text.split(/[，,、；;\n]/).map(s => s.trim()).filter(Boolean)

const appendSymptom = (chip: string) => {
  if (symptomText.value.includes(chip)) return
  symptomText.value = symptomText.value.trim()
    ? `${symptomText.value.trim()}，${chip}`
    : chip
}

// 候选排序：detections 按病害类别聚合，同类取最高置信度，降序排列
const candidates = computed<Candidate[]>(() => {
  const detections: any[] = record.value?.detections || []
  const byLabel = new Map<string, Candidate>()
  for (const d of detections) {
    const existing = byLabel.get(d.label)
    if (existing) {
      existing.count += 1
      existing.confidence = Math.max(existing.confidence, d.confidence)
    } else {
      byLabel.set(d.label, { label: d.label, confidence: d.confidence, count: 1 })
    }
  }
  return [...byLabel.values()].sort((a, b) => b.confidence - a.confidence)
})

const selectedLabel = ref('')
const topLabel = computed(() => candidates.value[0]?.label || '')
const selectedCandidate = computed(() =>
  candidates.value.find(c => c.label === selectedLabel.value) || null
)
const activeTab = ref('evidence')

// 无检出语义：diagnosis_status=INCONCLUSIVE 时报告不给病害结论（disease_type/confidence 为 null，
// 无信息 ≠ 健康）；旧记录无该字段时按原展示口径回退
const inconclusive = computed(() => report.value?.diagnosis_status === 'INCONCLUSIVE')

// 不确定性判定：首位置信度过低或与次位分差过小（单候选/无候选时不做分差判断）
const uncertain = computed(() => {
  const top = candidates.value[0]
  if (!top) return false
  if (top.confidence < UNCERTAIN_TOP_THRESHOLD) return true
  const second = candidates.value[1]
  return !!second && top.confidence - second.confidence < UNCERTAIN_MARGIN_THRESHOLD
})
const uncertainReasons = computed(() => {
  const reasons: string[] = []
  const top = candidates.value[0]
  if (!top) return reasons
  if (top.confidence < UNCERTAIN_TOP_THRESHOLD) {
    reasons.push(`首位候选「${top.label}」置信度仅 ${(top.confidence * 100).toFixed(1)}%（低于 ${UNCERTAIN_TOP_THRESHOLD * 100}%）。`)
  }
  const second = candidates.value[1]
  if (second && top.confidence - second.confidence < UNCERTAIN_MARGIN_THRESHOLD) {
    reasons.push(`前两位候选分差仅 ${((top.confidence - second.confidence) * 100).toFixed(1)}%（小于 ${UNCERTAIN_MARGIN_THRESHOLD * 100}%），类别归属存在竞争。`)
  }
  return reasons
})
// 是否已触发后端自动专家复核（口径同 DiagnosisController：最高置信度 < 0.75，含无检出）
const autoReviewed = computed(() => (candidates.value[0]?.confidence ?? 0) < REVIEW_THRESHOLD)

const scaledBoxes = computed(() => {
  const detections = record.value?.detections || []
  return detections.map((d: any) => ({
    label: d.label,
    confidence: d.confidence,
    style: {
      left: `${d.x1 * scale.value}px`,
      top: `${d.y1 * scale.value}px`,
      width: `${(d.x2 - d.x1) * scale.value}px`,
      height: `${(d.y2 - d.y1) * scale.value}px`
    }
  }))
})

// 扫描加载动画：三阶段文案按时间推进（单次 HTTP 无法细分进度，仅为体验提示）
const scanPhase = ref(0)
const scanPhaseText = computed(() => ['上传中', '检测中', '生成报告中'][scanPhase.value])
let stageTimers: number[] = []
const clearStageTimers = () => {
  stageTimers.forEach(t => clearTimeout(t))
  stageTimers = []
}
// 自增 runId 令牌：取消或重新发起后，迟到旧结果直接丢弃，不覆盖新图
const runId = ref(0)

const onFileChange = (uploadFile: UploadFile) => {
  if (!uploadFile.raw) return
  if (uploadFile.raw.size > 20 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 20MB')
    return
  }
  runId.value++ // 换图后旧诊断结果一律作废
  clearStageTimers()
  loading.value = false
  rawFile.value = uploadFile.raw
  previewUrl.value = URL.createObjectURL(uploadFile.raw)
  record.value = null
  selectedLabel.value = ''
}

const onImageLoad = () => {
  const img = imgRef.value
  if (img && img.naturalWidth > 0) {
    scale.value = img.clientWidth / img.naturalWidth
  }
}

const onDiagnose = async () => {
  if (!rawFile.value || loading.value) return
  const myRun = ++runId.value
  loading.value = true
  scanPhase.value = 0
  stageTimers.push(window.setTimeout(() => { if (myRun === runId.value) scanPhase.value = 1 }, 1200))
  stageTimers.push(window.setTimeout(() => { if (myRun === runId.value) scanPhase.value = 2 }, 3000))
  try {
    const res: any = await uploadDiagnosis(rawFile.value, symptomList(symptomText.value))
    if (myRun !== runId.value) return // 已取消或已换图，丢弃迟到结果
    record.value = res.data
    diagnosedSymptom.value = symptomText.value.trim()
    selectedLabel.value = ''
    activeTab.value = 'evidence'
    if (res.data?.duplicated) {
      ElMessage.info('检测到重复上传，已为你打开原诊断记录')
    } else if (res.data?.status === 'DONE') {
      ElMessage.success('诊断完成')
    }
  } catch {
    // 错误已由响应拦截器提示
  } finally {
    if (myRun === runId.value) {
      loading.value = false
      clearStageTimers()
    }
  }
}

const onCancelDiagnose = () => {
  runId.value++
  clearStageTimers()
  loading.value = false
  ElMessage.info('已取消本次诊断')
}

// 空态引导：示例图为 test-assets 真实黄瓜叶片（炭疽病），走同一上传诊断流程
const useSample = async () => {
  try {
    const resp = await fetch(sampleLeafUrl)
    const blob = await resp.blob()
    rawFile.value = new File([blob], 'sample-leaf.jpg', { type: blob.type || 'image/jpeg' })
    runId.value++
    record.value = null
    selectedLabel.value = ''
    previewUrl.value = sampleLeafUrl
    onDiagnose()
  } catch {
    ElMessage.error('示例图加载失败')
  }
}

// 备选候选的知识库参考（按类别关键词检索，结果缓存）
const knowledgeCache = ref<Record<string, any[]>>({})
const ensureKnowledge = async (label: string) => {
  if (!label || knowledgeCache.value[label]) return
  try {
    const res: any = await knowledgeList({ page: 1, size: 3, keyword: label })
    knowledgeCache.value[label] = res.data?.list || []
  } catch {
    knowledgeCache.value[label] = []
  }
}
const selectedKnowledge = computed(() => knowledgeCache.value[selectedLabel.value] || [])

// 候选对比弹窗（P2）
const compareVisible = ref(false)
const compareA = ref('')
const compareB = ref('')
const openCompare = () => {
  compareA.value = selectedLabel.value || topLabel.value
  compareB.value = candidates.value.find(c => c.label !== compareA.value)?.label || ''
  compareVisible.value = true
  ensureKnowledge(compareA.value)
  ensureKnowledge(compareB.value)
}
const onCompareChange = (which: 'A' | 'B') => {
  if (compareA.value === compareB.value) {
    const other = candidates.value.find(c => c.label !== compareA.value)
    if (which === 'A') compareB.value = other?.label || ''
    else compareA.value = other?.label || ''
  }
  ensureKnowledge(compareA.value)
  ensureKnowledge(compareB.value)
}
const knowledgeSummary = (label: string) => {
  const entries = knowledgeCache.value[label]
  if (!entries) return '加载中…'
  if (!entries.length) return '知识库未检索到相关条目'
  const first = entries[0]
  const content = (first.content || '').slice(0, 80)
  return `${first.title}：${content}${(first.content || '').length > 80 ? '…' : ''}`
}
const knowledgeSources = (label: string) => {
  const entries = knowledgeCache.value[label]
  if (!entries) return '加载中…'
  return entries.length ? entries.map(e => e.source_id).join('、') : '无'
}
const compareRows = computed(() => {
  const find = (label: string) => candidates.value.find(c => c.label === label)
  const a = find(compareA.value)
  const b = find(compareB.value)
  if (!a || !b) return []
  return [
    { dim: '最高置信度', a: `${(a.confidence * 100).toFixed(1)}%`, b: `${(b.confidence * 100).toFixed(1)}%` },
    { dim: '检出框数量', a: `${a.count} 处`, b: `${b.count} 处` },
    { dim: '典型特征', a: knowledgeSummary(a.label), b: knowledgeSummary(b.label) },
    { dim: '知识来源', a: knowledgeSources(a.label), b: knowledgeSources(b.label) }
  ]
})

// 导出 TXT 报告（P2，纯前端 Blob 下载）
const exportReport = () => {
  if (!record.value || !report.value) return
  const r = report.value
  const lines: string[] = [
    '黄瓜病害智能诊断报告',
    `记录编号：${record.value.record_no || '-'}`,
    `诊断时间：${record.value.create_time || '-'}`,
    `模型版本：${record.value.model_version || '-'}`,
    '',
    '【输入摘要】',
    `症状描述：${diagnosedSymptom.value || '未填写'}`,
    `检出病斑：${(record.value.detections || []).length} 处`,
    '',
    '【候选排序】',
    ...(candidates.value.length
      ? candidates.value.map((c, i) => `${i + 1}. ${c.label}（最高置信度 ${(c.confidence * 100).toFixed(1)}%，${c.count} 处病斑）`)
      : ['未检出明显病斑']),
    '',
    `【诊断结论】${r.disease_type == null
      ? '信息不足，无法判定（未检出可信病斑）'
      : `${r.disease_type}（置信度 ${(r.confidence * 100).toFixed(1)}%）`}`,
    '',
    '【诊断依据】',
    ...(r.basis || []).map((s: string) => `- ${s}`),
    ...(r.uncertainty_note ? [`不确定性说明：${r.uncertainty_note}`] : []),
    '',
    '【农艺措施】',
    ...(r.agronomy || []).map((s: string) => `- ${s}`),
    '【化学防治】',
    ...(r.chemical || []).map((s: string) => `- ${s}`),
    '【安全注意】',
    ...(r.safety || []).map((s: string) => `- ${s}`),
    '',
    `【知识来源】${(r.source_ids || []).join('、') || '无'}`,
    '',
    '本报告为 AI 辅助诊断结果，不可替代田间确诊与植保专业意见。'
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `诊断报告_${record.value.record_no || Date.now()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

// 来源追溯：按 source_id 从业务库知识条目查询原文
const sourceDialogVisible = ref(false)
const sourceLoading = ref(false)
const currentSource = ref<any>(null)
const showSource = async (sourceId: string) => {
  currentSource.value = null
  sourceDialogVisible.value = true
  sourceLoading.value = true
  try {
    const res: any = await knowledgeList({ page: 1, size: 5, keyword: sourceId })
    const entry = (res.data?.list || []).find((item: any) => item.source_id === sourceId)
    currentSource.value = entry || null
  } catch {
    currentSource.value = null
  } finally {
    sourceLoading.value = false
  }
}

// 选中候选变化时预取知识条目（备选候选的图文依据与对比弹窗共用缓存）
watch(selectedLabel, label => {
  if (label && label !== topLabel.value) ensureKnowledge(label)
})
// 新结果到达或候选集变化时，默认选中首位候选
watch(candidates, list => {
  if (!list.length) {
    selectedLabel.value = ''
  } else if (!list.some(c => c.label === selectedLabel.value)) {
    selectedLabel.value = list[0].label
  }
})
</script>

<style scoped>
.action-bar {
  margin-top: 16px;
  text-align: center;
}
.symptom-area {
  margin-top: 16px;
}
.symptom-chips {
  margin-bottom: 8px;
}
.chips-label {
  font-size: 13px;
  color: #909399;
  margin-right: 4px;
}
.symptom-chip {
  margin-right: 8px;
  cursor: pointer;
}
.result-row {
  margin-top: 16px;
}
.image-wrapper {
  position: relative;
  display: inline-block;
  max-width: 100%;
}
.leaf-image {
  max-width: 100%;
  display: block;
}
.detect-box {
  position: absolute;
  border: 2px solid #f56c6c;
  box-sizing: border-box;
  opacity: 0.45;
}
.detect-box-active {
  opacity: 1;
  box-shadow: 0 0 6px rgba(245, 108, 108, 0.6);
}
.detect-label {
  position: absolute;
  top: -20px;
  left: 0;
  background: #f56c6c;
  color: #fff;
  font-size: 12px;
  padding: 0 4px;
  white-space: nowrap;
}
/* 扫描加载动画（仿 qingye 原型 .scanner / @keyframes scan） */
.scan-mask {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: rgba(27, 67, 50, 0.18);
}
.scan-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 3px;
  background: #7fb069;
  box-shadow: 0 0 20px #98be7a;
  animation: scan 1.4s ease-in-out infinite alternate;
}
@keyframes scan {
  from {
    top: 8%;
  }
  to {
    top: 92%;
  }
}
.scan-text {
  position: absolute;
  bottom: 12px;
  left: 0;
  right: 0;
  text-align: center;
  color: #e6f4ea;
  font-size: 13px;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
}
.placeholder-card {
  min-height: 320px;
}
.empty-card :deep(.el-empty) {
  padding: 48px 0;
}
.block-gap {
  margin-bottom: 12px;
}
.alert-list {
  margin: 4px 0 0;
  padding-left: 18px;
}
.report-card h4 {
  margin: 12px 0 4px;
  color: #1d5e2a;
}
.report-card ul {
  margin: 0;
  padding-left: 20px;
}
.confidence {
  margin-left: 12px;
  color: #909399;
}
.source-tag {
  margin-right: 8px;
  cursor: pointer;
}
.candidates {
  margin-bottom: 8px;
}
.candidates-title {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
  color: #606266;
  font-size: 13px;
}
.candidate {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.candidate:hover {
  border-color: #7fb069;
}
.candidate-selected {
  border-color: #1d5e2a;
  background: #f2f8ef;
}
.candidate-rank {
  font-size: 12px;
  color: #909399;
  margin-right: 10px;
}
.candidate-name {
  font-weight: 600;
  margin-right: 10px;
}
.candidate-score {
  float: right;
  font-size: 18px;
  color: #1d5e2a;
}
.candidate-score small {
  font-size: 12px;
}
.score-bar {
  clear: both;
  height: 6px;
  background: #eef1e8;
  border-radius: 3px;
  margin-top: 6px;
  overflow: hidden;
}
.score-bar i {
  display: block;
  height: 100%;
  background: #7fb069;
  border-radius: 3px;
}
.candidate-toolbar {
  text-align: right;
  margin-bottom: 4px;
}
.result-tabs {
  margin-top: 8px;
}
.evidence-text {
  margin: 4px 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.7;
}
.input-quote {
  background: #f5f7fa;
  border-radius: 4px;
  padding: 8px 12px;
  color: #606266;
  font-size: 13px;
}
.knowledge-entry {
  margin: 6px 0;
  font-size: 13px;
}
.source-tag-wrap {
  margin-right: 6px;
}
.result-foot {
  margin-top: 12px;
  text-align: right;
}
.compare-selectors {
  display: flex;
  gap: 24px;
  margin-bottom: 12px;
}
.compare-selectors span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.compare-tip {
  margin-top: 10px;
  color: #909399;
  font-size: 12px;
}
</style>
