<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-button type="primary" @click="openDialog()">新增条目</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" border>
      <el-table-column prop="source_id" label="来源编号" width="120" />
      <el-table-column prop="disease_type" label="病害类型" width="110" />
      <el-table-column prop="title" label="标题" width="180" />
      <el-table-column prop="level" label="等级" width="70" />
      <el-table-column prop="category" label="分类" width="80" />
      <el-table-column prop="content" label="内容" show-overflow-tooltip />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                   :current-page="query.page" :page-size="query.size"
                   @current-change="(p: number) => { query.page = p; loadData() }" />

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑知识条目' : '新增知识条目'" width="560px">
      <el-form label-width="90px">
        <el-form-item label="来源编号" required>
          <el-input v-model="form.source_id" :disabled="!!form.id" placeholder="格式 KB-XXX-NNN，如 KB-JC-006" />
        </el-form-item>
        <el-form-item label="病害类型" required>
          <el-select v-model="form.disease_type" style="width: 100%">
            <el-option v-for="d in diseaseTypes" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="form.title" />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input v-model="form.content" type="textarea" :rows="5" />
        </el-form-item>
        <el-form-item label="证据等级">
          <el-radio-group v-model="form.level">
            <el-radio value="A">A 级</el-radio>
            <el-radio value="B">B 级</el-radio>
            <el-radio value="C">C 级</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="分类">
          <el-radio-group v-model="form.category">
            <el-radio value="症状">症状</el-radio>
            <el-radio value="防治">防治</el-radio>
            <el-radio value="药剂">药剂</el-radio>
          </el-radio-group>
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
import { knowledgeCreate, knowledgeDelete, knowledgeList, knowledgeUpdate } from '../../api/knowledge'

const loading = ref(false)
const saving = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 10 })
const dialogVisible = ref(false)
const emptyForm = () => ({
  id: 0, source_id: '', disease_type: '', title: '', content: '', level: 'B', category: '症状'
})
const form = reactive<any>(emptyForm())

const diseaseTypes = ['炭疽病', '霜霉病', '蔓枯病', '白粉病', '健康叶']

const loadData = async () => {
  loading.value = true
  try {
    const res: any = await knowledgeList({ ...query })
    rows.value = res.data?.list || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

const openDialog = (row?: any) => {
  Object.assign(form, emptyForm(), row || {})
  dialogVisible.value = true
}

const onSave = async () => {
  if (!form.source_id || !form.disease_type || !form.title || !form.content) {
    ElMessage.warning('请填写完整信息')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await knowledgeUpdate(form.id, form)
    } else {
      await knowledgeCreate(form)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

const onDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除知识条目「${row.title}」？`, '删除确认', { type: 'warning' })
  await knowledgeDelete(row.id)
  ElMessage.success('删除成功')
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.toolbar {
  margin-bottom: 16px;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
