import request from '../utils/request'

export const uploadDiagnosis = (file: File, symptoms: string[] = []) => {
  const formData = new FormData()
  formData.append('file', file)
  // 症状描述作为辅助证据透传（每条一个 symptoms 字段，后端按多值表单参数接收）
  for (const s of symptoms) {
    formData.append('symptoms', s)
  }
  return request.post('/api/v1/diagnosis', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 90000
  })
}

export const diagnosisList = (params: { page: number; size: number; status?: string }) =>
  request.get('/api/v1/diagnosis', { params })

export const diagnosisDetail = (id: number) => request.get(`/api/v1/diagnosis/${id}`)

export const submitFeedback = (id: number, data: {
  verdict: string
  correctedDiseaseType?: string
  comment?: string
}) => request.post(`/api/v1/diagnosis/${id}/feedback`, data)

export const feedbackList = (params: { page: number; size: number; reviewStatus?: string }) =>
  request.get('/api/v1/feedback', { params })

export const reviewFeedback = (id: number) => request.put(`/api/v1/feedback/${id}/review`)
