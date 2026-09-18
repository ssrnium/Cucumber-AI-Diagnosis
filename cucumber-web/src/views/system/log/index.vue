<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-input v-model="query.username" placeholder="按操作人筛选" clearable
                style="width: 200px" @keyup.enter="loadData" />
      <el-button type="primary" @click="loadData">查询</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="操作人" width="110" />
      <el-table-column prop="operation" label="操作" width="160" />
      <el-table-column prop="method" label="方法" show-overflow-tooltip />
      <el-table-column prop="uri" label="接口" width="220" show-overflow-tooltip />
      <el-table-column prop="ip" label="IP" width="120" />
      <el-table-column prop="cost_ms" label="耗时" width="90">
        <template #default="{ row }">{{ row.cost_ms }} ms</template>
      </el-table-column>
      <el-table-column label="结果" width="90">
        <template #default="{ row }">
          <el-tag :type="row.result === 'SUCCESS' ? 'success' : 'danger'">{{ row.result }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" label="时间" width="180" />
    </el-table>
    <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                   :current-page="query.page" :page-size="query.size"
                   @current-change="(p: number) => { query.page = p; loadData() }" />
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { operationLogList } from '../../../api/system'

const loading = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 15, username: '' })

const loadData = async () => {
  loading.value = true
  try {
    const res: any = await operationLogList({ ...query, username: query.username || undefined })
    rows.value = res.data?.list || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
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
</style>
