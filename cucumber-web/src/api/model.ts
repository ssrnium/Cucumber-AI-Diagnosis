import request from '../utils/request'

export const modelList = () => request.get('/api/v1/model')

export const modelRegister = (data: any) => request.post('/api/v1/model', data)

export const modelActivate = (id: number) => request.put(`/api/v1/model/${id}/activate`)
