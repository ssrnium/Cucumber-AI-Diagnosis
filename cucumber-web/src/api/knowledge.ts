import request from '../utils/request'

export const knowledgeList = (params: {
  page: number
  size: number
  diseaseType?: string
  keyword?: string
}) => request.get('/api/v1/knowledge', { params })

export const knowledgeDetail = (id: number) => request.get(`/api/v1/knowledge/${id}`)

export const knowledgeCreate = (data: any) => request.post('/api/v1/knowledge', data)

export const knowledgeUpdate = (id: number, data: any) =>
  request.put(`/api/v1/knowledge/${id}`, data)

export const knowledgeDelete = (id: number) => request.delete(`/api/v1/knowledge/${id}`)
