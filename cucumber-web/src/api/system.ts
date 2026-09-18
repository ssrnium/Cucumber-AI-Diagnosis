import request from '../utils/request'

// ---------- 用户 ----------
export const userList = (params: { page: number; size: number; keyword?: string }) =>
  request.get('/api/v1/system/user', { params })

export const userCreate = (data: any) => request.post('/api/v1/system/user', data)

export const userUpdate = (id: number, data: any) =>
  request.put(`/api/v1/system/user/${id}`, data)

export const userDelete = (id: number) => request.delete(`/api/v1/system/user/${id}`)

export const userResetPassword = (id: number, password: string) =>
  request.put(`/api/v1/system/user/${id}/reset-password`, { password })

export const userRoles = (id: number) => request.get(`/api/v1/system/user/${id}/roles`)

export const userAssignRoles = (id: number, roleIds: number[]) =>
  request.put(`/api/v1/system/user/${id}/roles`, { roleIds })

// ---------- 角色 ----------
export const roleList = (params: { page: number; size: number; keyword?: string }) =>
  request.get('/api/v1/system/role', { params })

export const roleAll = () => request.get('/api/v1/system/role/all')

export const roleCreate = (data: any) => request.post('/api/v1/system/role', data)

export const roleUpdate = (id: number, data: any) =>
  request.put(`/api/v1/system/role/${id}`, data)

export const roleDelete = (id: number) => request.delete(`/api/v1/system/role/${id}`)

export const rolePerms = (id: number) => request.get(`/api/v1/system/role/${id}/perms`)

export const roleAssignPerms = (id: number, perms: string[]) =>
  request.put(`/api/v1/system/role/${id}/perms`, { perms })

// ---------- 操作日志 ----------
export const operationLogList = (params: { page: number; size: number; username?: string }) =>
  request.get('/api/v1/system/log', { params })
