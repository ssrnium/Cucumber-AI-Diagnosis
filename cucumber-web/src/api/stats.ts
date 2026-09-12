import request from '../utils/request'

export const statsOverview = () => request.get('/api/v1/stats/overview')
