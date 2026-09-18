<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="layout-aside">
      <div class="logo">黄瓜病害诊断平台</div>
      <el-menu :default-active="$route.path" router background-color="#001529"
               text-color="#a6adb4" active-text-color="#ffffff">
        <template v-for="menu in visibleMenus" :key="menu.path">
          <el-menu-item :index="menu.path">
            <el-icon><component :is="menu.icon" /></el-icon>
            <span>{{ menu.title }}</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="layout-header">
        <span class="header-title">{{ $route.meta.title }}</span>
        <el-dropdown @command="onCommand">
          <span class="user-info">
            {{ userStore.userInfo.nickname || userStore.userInfo.username }}
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()

const menus = [
  { path: '/dashboard', title: '数据看板', icon: 'DataAnalysis' },
  { path: '/diagnosis/upload', title: '病害诊断', icon: 'Upload' },
  { path: '/diagnosis/records', title: '诊断记录', icon: 'Document' },
  { path: '/diagnosis/review', title: '反馈复核', icon: 'Stamp', perm: 'feedback:review' },
  { path: '/knowledge', title: '知识库', icon: 'Collection' },
  { path: '/agent/chat', title: '智能体对话', icon: 'ChatDotRound', perm: 'agent:chat' },
  { path: '/agent/monitor', title: '智能体监控', icon: 'Monitor', perm: 'agent:monitor' },
  { path: '/agent/admin', title: '智能体管理', icon: 'MagicStick', perm: 'agent:skills' },
  { path: '/knowledge/admin', title: '知识库管理', icon: 'EditPen', perm: 'knowledge:manage' },
  { path: '/model', title: '模型版本', icon: 'Cpu', perm: 'model:manage' },
  { path: '/system/user', title: '用户管理', icon: 'User', perm: 'system:user:list' },
  { path: '/system/role', title: '角色管理', icon: 'UserFilled', perm: 'system:role:list' },
  { path: '/system/log', title: '操作日志', icon: 'Tickets', perm: 'system:log:list' }
]

const visibleMenus = computed(() =>
  menus.filter((menu) => !menu.perm || userStore.hasPerm(menu.perm))
)

const onCommand = (command: string) => {
  if (command === 'logout') {
    userStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
}
.layout-aside {
  background-color: #001529;
}
.logo {
  color: #fff;
  font-size: 16px;
  font-weight: bold;
  text-align: center;
  line-height: 60px;
  border-bottom: 1px solid #1f2d3d;
}
.layout-aside :deep(.el-menu) {
  border-right: none;
}
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
  background: #fff;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
}
.user-info {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}
.layout-main {
  background: #f5f7fa;
}
</style>
