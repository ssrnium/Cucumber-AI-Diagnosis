import request from '../utils/request'

export const login = (data: { username: string; password: string }) =>
  request.post('/api/v1/auth/login', data)

export const register = (data: { username: string; password: string; nickname?: string }) =>
  request.post('/api/v1/auth/register', data)

export const profile = () => request.get('/api/v1/auth/profile')
