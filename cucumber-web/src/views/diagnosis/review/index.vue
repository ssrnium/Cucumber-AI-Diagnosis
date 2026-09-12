<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="query.reviewStatus" placeholder="按复核状态筛选" clearable
                 style="width: 160px" @change="loadData">
        <el-option label="待复核" value="PENDING" />
        <el-option label="已复核" value="REVIEWED" />
      </el-select>
      <el-button type="primary" @click="loadData">查询</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="record_id" label="诊断记录" width="100" />
      <el-table-column label="用户判定" width="100">
        <template #default="{ row }">
          <el-tag :type="row.verdict === 'CORRECT' ? 'success' : row.verdict === 'UNCERTAIN' ? 'warning' : 'danger'">
            {{ row.verdict === 'CORRECT' ? '诊断正确' : row.verdict === 'UNCERTAIN' ? '低置信复核' : '诊断有误' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="corrected_disease_type" label="修正病害" width="110">
        <template #default="{ row }">{{ row.corrected_disease_type || '-' }}</template>
      </el-table-column>
      <el-table-column prop="comment" label="备注" show-overflow-tooltip />
      <el-table-column label="复核状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.review_status === 'REVIEWED' ? 'success' : 'warning'">
            {{ row.review_status === 'REVIEWED' ? '已复核' : '待复核' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" label="提交时间" width="170" />
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :disabled="row.review_status === 'REVIEWED'"
                     @click="onReview(row)">复核处理</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                   :current-page="query.page" :page-size="query.size"
                   @current-change="(p: number) => { query.page = p; loadData() }" />
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { feedbackList, reviewFeedback } from '../../../api/diagnosis'

const loading = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 10, reviewStatus: 'PENDING' })

const loadData = async () => {
  loading.value = true
  try {
    const res: any = await feedbackList({
      ...query,
      reviewStatus: query.reviewStatus || undefined
    })
    rows.value = res.data?.list || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

const onReview = async (row: any) => {
  await ElMessageBox.confirm(
    `确认完成对该反馈（记录 #${row.record_id}）的复核处理？`,
    '复核确认',
    { type: 'warning' }
  )
  await reviewFeedback(row.id)
  ElMessage.success('已标记为已复核')
  loadData()
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
</style>
