import { defineStore } from 'pinia'
import { login as loginApi } from '../api/auth'

interface UserInfo {
  id?: number
  username?: string
  nickname?: string
  avatar?: string
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    userInfo: JSON.parse(localStorage.getItem('userInfo') || '{}') as UserInfo,
    perms: JSON.parse(localStorage.getItem('perms') || '[]') as string[]
  }),
  actions: {
    async login(username: string, password: string) {
      const res: any = await loginApi({ username, password })
      this.token = res.data.token
      this.userInfo = res.data.userInfo || {}
      this.perms = res.data.perms || []
      localStorage.setItem('token', this.token)
      localStorage.setItem('userInfo', JSON.stringify(this.userInfo))
      localStorage.setItem('perms', JSON.stringify(this.perms))
    },
    logout() {
      this.token = ''
      this.userInfo = {}
      this.perms = []
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      localStorage.removeItem('perms')
    },
    hasPerm(perm: string) {
      return this.perms.includes(perm)
    }
  }
})
