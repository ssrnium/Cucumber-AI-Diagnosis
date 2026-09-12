<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value">{{ overview.totalCount ?? '-' }}</div>
            <div class="stat-label">累计诊断数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value">{{ overview.todayCount ?? '-' }}</div>
            <div class="stat-label">今日诊断数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value">{{ overview.feedbackAccuracy ?? '-' }}%</div>
            <div class="stat-label">反馈准确率</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value">{{ diseaseTypeCount }}</div>
            <div class="stat-label">近30天病害类型数</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-card class="chart-card" shadow="never">
      <template #header>近 30 天病害类型分布</template>
      <div ref="chartRef" class="chart-container"></div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { statsOverview } from '../../api/stats'

const overview = ref<any>({})
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

const diseaseTypeCount = computed(
  () => (overview.value.diseaseDistribution || []).length
)

onMounted(async () => {
  const res: any = await statsOverview()
  overview.value = res.data || {}
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    chart.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          label: { formatter: '{b}: {c}' },
          data: (overview.value.diseaseDistribution || []).map((item: any) => ({
            name: item.disease_type || '未知',
            value: Number(item.count)
          }))
        }
      ]
    })
  }
})
</script>

<style scoped>
.stat-card {
  text-align: center;
  padding: 12px 0;
}
.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #1d5e2a;
}
.stat-label {
  color: #909399;
  margin-top: 8px;
}
.chart-card {
  margin-top: 16px;
}
.chart-container {
  height: 360px;
}
</style>
