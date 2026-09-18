import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      component: () => import('../views/login/index.vue'),
      meta: { title: '登录' }
    },
    {
      path: '/',
      component: () => import('../layout/index.vue'),
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          component: () => import('../views/dashboard/index.vue'),
          meta: { title: '数据看板' }
        },
        {
          path: 'diagnosis/upload',
          component: () => import('../views/diagnosis/upload/index.vue'),
          meta: { title: '病害诊断' }
        },
        {
          path: 'diagnosis/records',
          component: () => import('../views/diagnosis/records/index.vue'),
          meta: { title: '诊断记录' }
        },
        {
          path: 'diagnosis/review',
          component: () => import('../views/diagnosis/review/index.vue'),
          meta: { title: '反馈复核', perm: 'feedback:review' }
        },
        {
          path: 'knowledge',
          component: () => import('../views/knowledge/index.vue'),
          meta: { title: '知识库' }
        },
        {
          path: 'agent/chat',
          component: () => import('../views/agent/chat/index.vue'),
          meta: { title: '智能体对话', perm: 'agent:chat' }
        },
        {
          path: 'agent/monitor',
          component: () => import('../views/agent/monitor/index.vue'),
          meta: { title: '智能体监控', perm: 'agent:monitor' }
        },
        {
          path: 'agent/admin',
          component: () => import('../views/agent/admin/index.vue'),
          meta: { title: '智能体管理', perm: 'agent:skills' }
        },
        {
          path: 'knowledge/admin',
          component: () => import('../views/knowledge/admin.vue'),
          meta: { title: '知识库管理', perm: 'knowledge:manage' }
        },
        {
          path: 'model',
          component: () => import('../views/model/index.vue'),
          meta: { title: '模型版本', perm: 'model:manage' }
        },
        {
          path: 'system/user',
          component: () => import('../views/system/user/index.vue'),
          meta: { title: '用户管理', perm: 'system:user:list' }
        },
        {
          path: 'system/role',
          component: () => import('../views/system/role/index.vue'),
          meta: { title: '角色管理', perm: 'system:role:list' }
        },
        {
          path: 'system/log',
          component: () => import('../views/system/log/index.vue'),
          meta: { title: '操作日志', perm: 'system:log:list' }
        }
      ]
    },
    {
      path: '/:pathMatch(.*)*',
      component: () => import('../views/error/404.vue'),
      meta: { title: '页面不存在' }
    }
  ]
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (to.path !== '/login' && !token) {
    return '/login'
  }
  if (to.path === '/login' && token) {
    return '/'
  }
  document.title = `${to.meta.title || ''} - 黄瓜病害诊断平台`
  return true
})

export default router
