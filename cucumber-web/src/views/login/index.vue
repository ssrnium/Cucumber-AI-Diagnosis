<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="login-title">黄瓜叶片病害智能识别<br />与可信辅助诊断平台</h2>
      <el-form :model="form" @submit.prevent>
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码"
                    :prefix-icon="Lock" show-password @keyup.enter="onLogin" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="login-btn" :loading="loading" @click="onLogin">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-tip">默认账号：admin/Admin@123、expert/Expert@123、user/User@123</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '../../stores/user'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const onLogin = async () => {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push('/')
  } catch {
    // 错误信息已由响应拦截器提示
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1d5e2a 0%, #0f3d17 100%);
}
.login-card {
  width: 400px;
  padding: 12px 20px;
}
.login-title {
  text-align: center;
  color: #1d5e2a;
  font-size: 20px;
  line-height: 1.6;
}
.login-btn {
  width: 100%;
}
.login-tip {
  text-align: center;
  color: #909399;
  font-size: 12px;
}
</style>
