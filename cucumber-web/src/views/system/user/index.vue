<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="用户名/昵称" clearable style="width: 200px"
                @keyup.enter="loadData" />
      <el-button type="primary" @click="loadData">查询</el-button>
      <el-button type="success" @click="openDialog()">新增用户</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" width="130" />
      <el-table-column prop="nickname" label="昵称" width="130" />
      <el-table-column prop="email" label="邮箱" show-overflow-tooltip />
      <el-table-column prop="phone" label="手机号" width="130" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'danger'">
            {{ row.status === 1 ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" label="创建时间" width="170" />
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
          <el-button link type="warning" @click="openAssign(row)">分配角色</el-button>
          <el-button link type="warning" @click="onResetPassword(row)">重置密码</el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                   :current-page="query.page" :page-size="query.size"
                   @current-change="(p: number) => { query.page = p; loadData() }" />

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑用户' : '新增用户'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" :disabled="!!form.id" />
        </el-form-item>
        <el-form-item v-if="!form.id" label="密码">
          <el-input v-model="form.password" type="password" placeholder="留空默认 123456" show-password />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="form.nickname" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="assignVisible" title="分配角色" width="420px">
      <el-checkbox-group v-model="assignRoleIds">
        <el-checkbox v-for="role in allRoles" :key="role.id" :value="role.id">
          {{ role.name }}（{{ role.code }}）
        </el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onAssignSave">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  roleAll, userAssignRoles, userCreate, userDelete, userList,
  userResetPassword, userRoles, userUpdate
} from '../../../api/system'

const loading = ref(false)
const saving = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 10, keyword: '' })

const dialogVisible = ref(false)
const emptyForm = () => ({
  id: 0, username: '', password: '', nickname: '', email: '', phone: '', status: 1
})
const form = reactive<any>(emptyForm())

const assignVisible = ref(false)
const assignUserId = ref(0)
const assignRoleIds = ref<number[]>([])
const allRoles = ref<any[]>([])

const loadData = async () => {
  loading.value = true
  try {
    const res: any = await userList({ ...query, keyword: query.keyword || undefined })
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
  if (!form.username) {
    ElMessage.warning('请填写用户名')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await userUpdate(form.id, form)
    } else {
      await userCreate(form)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

const openAssign = async (row: any) => {
  assignUserId.value = row.id
  const [rolesRes, userRolesRes]: any[] = await Promise.all([roleAll(), userRoles(row.id)])
  allRoles.value = rolesRes.data || []
  assignRoleIds.value = userRolesRes.data || []
  assignVisible.value = true
}

const onAssignSave = async () => {
  saving.value = true
  try {
    await userAssignRoles(assignUserId.value, assignRoleIds.value)
    ElMessage.success('角色分配成功')
    assignVisible.value = false
  } finally {
    saving.value = false
  }
}

const onResetPassword = async (row: any) => {
  const { value } = await ElMessageBox.prompt(
    `为用户「${row.username}」设置新密码`, '重置密码',
    { inputValue: '123456', inputPattern: /^.{6,32}$/, inputErrorMessage: '密码长度 6-32 位' }
  )
  await userResetPassword(row.id, value)
  ElMessage.success('密码已重置')
}

const onDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除用户「${row.username}」？`, '删除确认', { type: 'warning' })
  await userDelete(row.id)
  ElMessage.success('删除成功')
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
