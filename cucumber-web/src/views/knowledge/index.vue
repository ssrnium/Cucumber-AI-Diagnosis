<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="query.diseaseType" placeholder="按病害类型筛选" clearable
                 style="width: 160px" @change="loadData">
        <el-option v-for="d in diseaseTypes" :key="d" :label="d" :value="d" />
      </el-select>
      <el-input v-model="query.keyword" placeholder="关键词（标题/内容/编号）" clearable
                style="width: 240px" @keyup.enter="loadData" />
      <el-button type="primary" @click="loadData">查询</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" border>
      <el-table-column prop="source_id" label="来源编号" width="120" />
      <el-table-column prop="disease_type" label="病害类型" width="110" />
      <el-table-column prop="title" label="标题" width="200" />
      <el-table-column prop="content" label="内容" show-overflow-tooltip />
      <el-table-column prop="level" label="证据等级" width="90">
        <template #default="{ row }">
          <el-tag :type="row.level === 'A' ? 'success' : row.level === 'B' ? 'warning' : 'info'">
            {{ row.level }} 级
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="80" />
    </el-table>
    <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                   :current-page="query.page" :page-size="query.size"
                   @current-change="(p: number) => { query.page = p; loadData() }" />
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { knowledgeList } from '../../api/knowledge'

const loading = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 10, diseaseType: '', keyword: '' })

const diseaseTypes = ['炭疽病', '霜霉病', '蔓枯病', '白粉病', '健康叶']

const loadData = async () => {
  loading.value = true
  try {
    const res: any = await knowledgeList({
      ...query,
      diseaseType: query.diseaseType || undefined,
      keyword: query.keyword || undefined
    })
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
