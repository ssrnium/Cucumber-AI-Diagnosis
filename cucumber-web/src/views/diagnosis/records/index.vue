<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="query.status" placeholder="按状态筛选" clearable style="width: 160px"
                 @change="loadData">
        <el-option label="待处理" value="PENDING" />
        <el-option label="已完成" value="DONE" />
        <el-option label="失败" value="FAILED" />
      </el-select>
      <el-button type="primary" @click="loadData">查询</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" border>
      <el-table-column prop="record_no" label="记录编号" width="200" />
      <el-table-column label="图片" width="100">
        <template #default="{ row }">
          <el-image :src="row.image_url" fit="cover" style="width: 64px; height: 64px"
                    :preview-src-list="[row.image_url]" preview-teleported />
        </template>
      </el-table-column>
      <el-table-column label="诊断结论">
        <template #default="{ row }">
          {{ row.report?.disease_type || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="model_version" label="模型版本" width="160" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" label="诊断时间" width="180" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="showDetail(row)">详情</el-button>
          <el-button link type="warning" :disabled="row.status !== 'DONE'"
                     @click="openFeedback(row)">诊断有误</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                   :current-page="query.page" :page-size="query.size"
                   @current-change="(p: number) => { query.page = p; loadData() }" />

    <el-drawer v-model="drawerVisible" title="诊断详情" size="46%">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="记录编号">{{ detail.record_no }}</el-descriptions-item>
          <el-descriptions-item label="模型版本">{{ detail.model_version }}</el-descriptions-item>
          <el-descriptions-item v-if="detail.inference_ms" label="推理耗时">
            {{ detail.inference_ms.toFixed(0) }} ms
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusType(detail.status)">{{ statusText(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="时间">{{ detail.create_time }}</el-descriptions-item>
        </el-descriptions>
        <el-image :src="detail.image_url" fit="contain" class="detail-image" />
        <template v-if="detail.report">
          <h3>诊断结论：{{ detail.report.disease_type }}
            <small>（置信度 {{ (detail.report.confidence * 100).toFixed(1) }}%）</small>
          </h3>
          <h4>诊断依据</h4>
          <ul><li v-for="(item, i) in detail.report.basis" :key="'b' + i">{{ item }}</li></ul>
          <h4>农艺措施</h4>
          <ul><li v-for="(item, i) in detail.report.agronomy" :key="'a' + i">{{ item }}</li></ul>
          <h4>化学防治</h4>
          <ul><li v-for="(item, i) in detail.report.chemical" :key="'c' + i">{{ item }}</li></ul>
          <h4>安全注意</h4>
          <ul><li v-for="(item, i) in detail.report.safety" :key="'s' + i">{{ item }}</li></ul>
          <h4>来源追溯</h4>
          <el-tag v-for="sid in detail.report.source_ids" :key="sid" class="source-tag">{{ sid }}</el-tag>
        </template>
      </template>
    </el-drawer>

    <el-dialog v-model="feedbackVisible" title="诊断纠错反馈" width="480px">
      <el-form label-width="90px">
        <el-form-item label="判定">
          <el-radio-group v-model="feedbackForm.verdict">
            <el-radio value="WRONG">诊断有误</el-radio>
            <el-radio value="CORRECT">诊断正确</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="feedbackForm.verdict === 'WRONG'" label="正确病害">
          <el-select v-model="feedbackForm.correctedDiseaseType" placeholder="选择正确的病害类型">
            <el-option v-for="d in diseaseTypes" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="feedbackForm.comment" type="textarea" :rows="3"
                    placeholder="补充说明（选填）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="feedbackVisible = false">取消</el-button>
        <el-button type="primary" :loading="feedbackLoading" @click="onSubmitFeedback">提交</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { diagnosisDetail, diagnosisList, submitFeedback } from '../../../api/diagnosis'

const loading = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 10, status: '' })

const drawerVisible = ref(false)
const detail = ref<any>(null)

const feedbackVisible = ref(false)
const feedbackLoading = ref(false)
const feedbackRecordId = ref<number>(0)
const feedbackForm = reactive({ verdict: 'WRONG', correctedDiseaseType: '', comment: '' })

const diseaseTypes = ['炭疽病', '霜霉病', '蔓枯病', '白粉病', '健康叶']

const statusType = (status: string) =>
  status === 'DONE' ? 'success' : status === 'FAILED' ? 'danger' : 'info'
const statusText = (status: string) =>
  status === 'DONE' ? '已完成' : status === 'FAILED' ? '失败' : '待处理'

const loadData = async () => {
  loading.value = true
  try {
    const res: any = await diagnosisList({ ...query, status: query.status || undefined })
    rows.value = res.data?.list || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

const showDetail = async (row: any) => {
  const res: any = await diagnosisDetail(row.id)
  detail.value = res.data
  drawerVisible.value = true
}

const openFeedback = (row: any) => {
  feedbackRecordId.value = row.id
  feedbackForm.verdict = 'WRONG'
  feedbackForm.correctedDiseaseType = ''
  feedbackForm.comment = ''
  feedbackVisible.value = true
}

const onSubmitFeedback = async () => {
  feedbackLoading.value = true
  try {
    await submitFeedback(feedbackRecordId.value, { ...feedbackForm })
    ElMessage.success('反馈已提交，等待专家复核')
    feedbackVisible.value = false
  } finally {
    feedbackLoading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
.detail-image {
  max-width: 100%;
  margin: 16px 0;
}
.source-tag {
  margin-right: 8px;
}
</style>
