<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="角色名/编码" clearable style="width: 200px"
                @keyup.enter="loadData" />
      <el-button type="primary" @click="loadData">查询</el-button>
      <el-button type="success" @click="openDialog()">新增角色</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="code" label="角色编码" width="130" />
      <el-table-column prop="name" label="角色名称" width="150" />
      <el-table-column prop="remark" label="备注" show-overflow-tooltip />
      <el-table-column prop="create_time" label="创建时间" width="170" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
          <el-button link type="warning" @click="openPerms(row)">分配权限</el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                   :current-page="query.page" :page-size="query.size"
                   @current-change="(p: number) => { query.page = p; loadData() }" />

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑角色' : '新增角色'" width="440px">
      <el-form label-width="90px">
        <el-form-item label="角色编码" required>
          <el-input v-model="form.code" :disabled="!!form.id" placeholder="如 MANAGER" />
        </el-form-item>
        <el-form-item label="角色名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="permsVisible" title="分配权限" width="460px">
      <el-checkbox-group v-model="checkedPerms">
        <div v-for="group in permGroups" :key="group.title" class="perm-group">
          <div class="perm-group-title">{{ group.title }}</div>
          <el-checkbox v-for="perm in group.perms" :key="perm.value" :value="perm.value">
            {{ perm.label }}
          </el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="permsVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onPermsSave">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  roleAssignPerms, roleCreate, roleDelete, roleList, rolePerms, roleUpdate
} from '../../../api/system'

const loading = ref(false)
const saving = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 10, keyword: '' })

const dialogVisible = ref(false)
const emptyForm = () => ({ id: 0, code: '', name: '', remark: '' })
const form = reactive<any>(emptyForm())

const permsVisible = ref(false)
const permsRoleId = ref(0)
const checkedPerms = ref<string[]>([])

const permGroups = [
  {
    title: '用户管理',
    perms: [
      { value: 'system:user:list', label: '用户查询' },
      { value: 'system:user:create', label: '用户新增' },
      { value: 'system:user:update', label: '用户修改' },
      { value: 'system:user:delete', label: '用户删除' },
      { value: 'system:user:reset', label: '重置密码' },
      { value: 'system:user:assign', label: '分配角色' }
    ]
  },
  {
    title: '角色管理',
    perms: [
      { value: 'system:role:list', label: '角色查询' },
      { value: 'system:role:create', label: '角色新增' },
      { value: 'system:role:update', label: '角色修改' },
      { value: 'system:role:delete', label: '角色删除' },
      { value: 'system:role:assign', label: '分配权限' }
    ]
  },
  {
    title: '业务权限',
    perms: [
      { value: 'diagnosis:list:all', label: '查看全部诊断记录' },
      { value: 'knowledge:manage', label: '知识库管理' },
      { value: 'feedback:review', label: '反馈复核' },
      { value: 'model:manage', label: '模型版本管理' }
    ]
  }
]

const loadData = async () => {
  loading.value = true
  try {
    const res: any = await roleList({ ...query, keyword: query.keyword || undefined })
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
  if (!form.code || !form.name) {
    ElMessage.warning('请填写角色编码与名称')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await roleUpdate(form.id, form)
    } else {
      await roleCreate(form)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

const openPerms = async (row: any) => {
  permsRoleId.value = row.id
  const res: any = await rolePerms(row.id)
  checkedPerms.value = res.data || []
  permsVisible.value = true
}

const onPermsSave = async () => {
  saving.value = true
  try {
    await roleAssignPerms(permsRoleId.value, checkedPerms.value)
    ElMessage.success('权限分配成功')
    permsVisible.value = false
  } finally {
    saving.value = false
  }
}

const onDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除角色「${row.name}」？`, '删除确认', { type: 'warning' })
  await roleDelete(row.id)
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
.perm-group {
  margin-bottom: 8px;
}
.perm-group-title {
  font-weight: 600;
  margin-bottom: 4px;
}
</style>
