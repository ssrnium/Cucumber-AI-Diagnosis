<template>
  <div>
    <el-card shadow="never">
      <template #header>上传黄瓜叶片图片，进行病害智能识别与辅助诊断</template>
      <el-upload drag :auto-upload="false" :show-file-list="false" accept="image/*"
                 :on-change="onFileChange">
        <el-icon size="48" color="#909399"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽图片到此处，或 <em>点击选择图片</em>（不超过 20MB）</div>
      </el-upload>
      <div class="action-bar">
        <el-button type="primary" :disabled="!rawFile" :loading="loading" @click="onDiagnose">
          开始诊断
        </el-button>
      </div>
    </el-card>

    <el-row v-if="record" :gutter="16" class="result-row">
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>病斑检测结果（{{ record.model_version }}<span v-if="record.inference_ms"> · 推理耗时 {{ record.inference_ms.toFixed(0) }}ms</span>）</template>
          <div class="image-wrapper">
            <img ref="imgRef" :src="previewUrl" class="leaf-image" @load="onImageLoad" />
            <div v-for="(box, index) in scaledBoxes" :key="index" class="detect-box" :style="box.style">
              <span class="detect-label">{{ box.label }} {{ (box.confidence * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card v-if="record.status === 'PENDING'" shadow="never">
          <el-alert type="info" :closable="false"
                    title="诊断任务已受理（异步模式），请在「诊断记录」页查看结果" />
        </el-card>
        <el-card v-else-if="record.status === 'FAILED'" shadow="never">
          <el-alert type="error" :closable="false" title="AI 服务暂不可用，诊断失败，请稍后重试" />
        </el-card>
        <template v-else-if="report">
          <el-card shadow="never" class="report-card">
            <template #header>
              诊断结论：
              <el-tag type="danger" size="large">{{ report.disease_type }}</el-tag>
              <span class="confidence">置信度 {{ (report.confidence * 100).toFixed(1) }}%</span>
            </template>
            <h4>诊断依据</h4>
            <ul><li v-for="(item, i) in report.basis" :key="'b' + i">{{ item }}</li></ul>
            <h4>农艺措施</h4>
            <ul><li v-for="(item, i) in report.agronomy" :key="'a' + i">{{ item }}</li></ul>
            <h4>化学防治</h4>
            <ul><li v-for="(item, i) in report.chemical" :key="'c' + i">{{ item }}</li></ul>
            <h4>安全注意</h4>
            <ul><li v-for="(item, i) in report.safety" :key="'s' + i">{{ item }}</li></ul>
            <h4>来源追溯</h4>
            <el-tag v-for="sid in report.source_ids" :key="sid" class="source-tag"
                    @click="showSource(sid)">{{ sid }}</el-tag>
          </el-card>
        </template>
      </el-col>
    </el-row>

    <el-dialog v-model="sourceDialogVisible" :title="`来源原文：${currentSource?.source_id || ''}`"
               width="520px">
      <template v-if="currentSource">
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
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadFile } from 'element-plus'
import { uploadDiagnosis } from '../../../api/diagnosis'
import { knowledgeList } from '../../../api/knowledge'

const rawFile = ref<File | null>(null)
const previewUrl = ref('')
const loading = ref(false)
const record = ref<any>(null)
const imgRef = ref<HTMLImageElement>()
const scale = ref(1)

const report = computed(() => record.value?.report)

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

const onFileChange = (uploadFile: UploadFile) => {
  if (!uploadFile.raw) return
  if (uploadFile.raw.size > 20 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 20MB')
    return
  }
  rawFile.value = uploadFile.raw
  previewUrl.value = URL.createObjectURL(uploadFile.raw)
  record.value = null
}

const onImageLoad = () => {
  const img = imgRef.value
  if (img && img.naturalWidth > 0) {
    scale.value = img.clientWidth / img.naturalWidth
  }
}

const onDiagnose = async () => {
  if (!rawFile.value) return
  loading.value = true
  try {
    const res: any = await uploadDiagnosis(rawFile.value)
    record.value = res.data
    if (res.data?.duplicated) {
      ElMessage.info('检测到重复上传，已为你打开原诊断记录')
    } else if (res.data?.status === 'DONE') {
      ElMessage.success('诊断完成')
    }
  } catch {
    // 错误已由响应拦截器提示
  } finally {
    loading.value = false
  }
}

// 来源追溯：按 source_id 从业务库知识条目查询原文
const sourceDialogVisible = ref(false)
const currentSource = ref<any>(null)
const showSource = async (sourceId: string) => {
  currentSource.value = null
  sourceDialogVisible.value = true
  try {
    const res: any = await knowledgeList({ page: 1, size: 5, keyword: sourceId })
    const entry = (res.data?.list || []).find((item: any) => item.source_id === sourceId)
    currentSource.value = entry || null
  } catch {
    currentSource.value = null
  }
}
</script>

<style scoped>
.action-bar {
  margin-top: 16px;
  text-align: center;
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
</style>
