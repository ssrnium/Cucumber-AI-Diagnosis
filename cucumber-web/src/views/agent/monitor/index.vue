<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>智能体运行监控</span>
          <el-button size="small" @click="load">刷新</el-button>
        </div>
      </template>

      <div v-if="summary" class="monitor-body">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-statistic title="知识库片段数" :value="knowledgeChunks" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="告警数" :value="(summary.alerts || []).length" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="Agent 总数" :value="Object.keys(agentStats).length" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="工具数" :value="Object.keys(toolStats).length" />
          </el-col>
        </el-row>

        <el-divider>Agent 统计（成功率 / 延迟 / 路由罚分）</el-divider>
        <el-table :data="agentRows" size="small" border>
          <el-table-column prop="key" label="Agent" width="140" />
          <el-table-column prop="role" label="角色" min-width="200" show-overflow-tooltip />
          <el-table-column prop="total" label="调用次数" width="90" />
          <el-table-column label="成功率" width="110">
            <template #default="{ row }">
              <el-progress :percentage="Math.round(row.success_rate * 100)" />
            </template>
          </el-table-column>
          <el-table-column prop="avg_ms" label="平均延迟(ms)" width="110" />
          <el-table-column prop="monitor_penalty" label="监控罚分" width="90" />
          <el-table-column prop="routing_score" label="路由评分" width="90" />
        </el-table>

        <el-divider>工具统计（含熔断状态）</el-divider>
        <el-table :data="toolRows" size="small" border>
          <el-table-column prop="key" label="工具" width="220" />
          <el-table-column prop="total" label="调用次数" width="90" />
          <el-table-column label="成功率" width="110">
            <template #default="{ row }">
              <el-progress :percentage="Math.round(row.success_rate * 100)" />
            </template>
          </el-table-column>
          <el-table-column prop="avg_latency_ms" label="平均延迟(ms)" width="110" />
          <el-table-column prop="consecutive_fails" label="连续失败" width="90" />
          <el-table-column label="熔断器" width="100">
            <template #default="{ row }">
              <el-tag :type="row.circuit_state === 'closed' ? 'success' : row.circuit_state === 'open' ? 'danger' : 'warning'">
                {{ row.circuit_state }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <template v-if="(summary.alerts || []).length">
          <el-divider>告警</el-divider>
          <el-alert v-for="(alert, i) in summary.alerts" :key="i" :title="alert.message || alert"
                    type="warning" :closable="false" style="margin-bottom: 6px" />
        </template>

        <template v-if="(summary.recommendations || []).length">
          <el-divider>优化建议</el-divider>
          <el-alert v-for="(rec, i) in summary.recommendations" :key="i" :title="rec"
                    type="info" :closable="false" style="margin-bottom: 6px" />
        </template>
      </div>
      <el-empty v-else description="监控数据不可用（cucumber-agent 未启动或未配置 ANTHROPIC_API_KEY）" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { agentKnowledgeStats, agentMonitor } from '../../../api/agent'

const summary = ref<any>(null)
const knowledgeChunks = ref(0)

const agentStats = computed(() => summary.value?.agents || {})
const toolStats = computed(() => summary.value?.tools || {})

const agentRows = computed(() =>
  Object.entries(agentStats.value).map(([key, v]: [string, any]) => ({ key, ...v }))
)
const toolRows = computed(() =>
  Object.entries(toolStats.value).map(([key, v]: [string, any]) => ({ key, ...v }))
)

const load = async () => {
  try {
    const res: any = await agentMonitor()
    summary.value = res?.data || null
  } catch {
    summary.value = null
  }
  try {
    const stats: any = await agentKnowledgeStats()
    knowledgeChunks.value = stats?.data?.total_chunks || 0
  } catch {
    knowledgeChunks.value = 0
  }
}

onMounted(load)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.monitor-body {
  min-height: 300px;
}
</style>
