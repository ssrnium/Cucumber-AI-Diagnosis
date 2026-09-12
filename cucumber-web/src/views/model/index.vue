<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-button type="primary" @click="openDialog">注册模型版本</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" border>
      <el-table-column prop="name" label="模型名称" width="160" />
      <el-table-column prop="version" label="版本" width="100" />
      <el-table-column prop="model_type" label="类型" width="110">
        <template #default="{ row }">
          <el-tag :type="row.model_type === 'DETECTION' ? 'primary' : 'warning'">
            {{ row.model_type === 'DETECTION' ? '检测模型' : 'LLM' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="weights_path" label="权重路径" show-overflow-tooltip />
      <el-table-column label="评测指标" width="220">
        <template #default="{ row }">
          <span v-if="row.metrics">{{ JSON.stringify(row.metrics) }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'">
            {{ row.status === 'ACTIVE' ? '使用中' : '已归档' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" label="登记时间" width="170" />
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link type="success" :disabled="row.status === 'ACTIVE'"
                     @click="onActivate(row)">激活</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="注册模型版本" width="520px">
      <el-form label-width="90px">
        <el-form-item label="模型名称" required>
          <el-input v-model="form.name" placeholder="如 YOLO11n-E2_gfix" />
        </el-form-item>
        <el-form-item label="版本" required>
          <el-input v-model="form.version" placeholder="如 v1.0.0" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.model_type">
            <el-radio value="DETECTION">检测模型</el-radio>
            <el-radio value="LLM">LLM</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="权重路径">
          <el-input v-model="form.weights_path" placeholder="如 weights/E2_gfix.pt" />
        </el-form-item>
        <el-form-item label="SHA256">
          <el-input v-model="form.sha256" />
        </el-form-item>
        <el-form-item label="指标 JSON">
          <el-input v-model="metricsText" placeholder='如 {"mAP50": 0.93}' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { modelActivate, modelList, modelRegister } from '../../api/model'

const loading = ref(false)
const saving = ref(false)
const rows = ref<any[]>([])
const dialogVisible = ref(false)
const metricsText = ref('')
const form = reactive<any>({
  name: '', version: '', model_type: 'DETECTION', weights_path: '', sha256: ''
})

const loadData = async () => {
  loading.value = true
  try {
    const res: any = await modelList()
    rows.value = res.data || []
  } finally {
    loading.value = false
  }
}

const openDialog = () => {
  Object.assign(form, { name: '', version: '', model_type: 'DETECTION', weights_path: '', sha256: '' })
  metricsText.value = ''
  dialogVisible.value = true
}

const onSave = async () => {
  if (!form.name || !form.version) {
    ElMessage.warning('请填写模型名称与版本')
    return
  }
  let metrics: any = null
  if (metricsText.value.trim()) {
    try {
      metrics = JSON.parse(metricsText.value)
    } catch {
      ElMessage.warning('指标 JSON 格式不正确')
      return
    }
  }
  saving.value = true
  try {
    await modelRegister({ ...form, metrics })
    ElMessage.success('注册成功')
    dialogVisible.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

const onActivate = async (row: any) => {
  await ElMessageBox.confirm(
    `激活「${row.name} ${row.version}」？同类型其它模型将自动归档。`,
    '激活确认',
    { type: 'warning' }
  )
  await modelActivate(row.id)
  ElMessage.success('已激活')
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.toolbar {
  margin-bottom: 16px;
}
</style>
