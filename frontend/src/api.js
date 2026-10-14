// 统一 API 封装：严格按 PLAN.md API 契约 v1 调用后端（http://localhost:8000，路由前缀 /api）
// dev 模式下通过 vite proxy 同源 /api → localhost:8000
//
// 管理口令（可选）：后端设置 GUARD_ADMIN_TOKEN 后，管理/审批接口要求
// X-Admin-Token 头。前端从 localStorage('guard_admin_token') 读取并自动附带；
// 未设置时行为与之前完全一致（本机演示零负担）。

function adminToken() {
  try { return localStorage.getItem('guard_admin_token') || '' } catch { return '' }
}

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  const token = adminToken()
  if (token) opts.headers['X-Admin-Token'] = token
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(path, opts)
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = { _raw: text } }
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status} ${method} ${path}`)
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

const get = (path) => request('GET', path)
const post = (path, body) => request('POST', path, body)

export const api = {
  health: () => get('/api/health'),
  status: () => get('/api/admin/status'),
  stop: (by = 'admin') => post('/api/admin/stop', { by }),
  resume: (by = 'admin') => post('/api/admin/resume', { by }),
  reset: () => post('/api/admin/reset', {}),

  listTasks: () => get('/api/tasks'),
  createTask: (title, scenario) => post('/api/tasks', { title, scenario }),
  getTask: (id) => get(`/api/tasks/${id}`),
  planTask: (id) => post(`/api/tasks/${id}/plan`, {}),
  advanceTask: (id) => post(`/api/tasks/${id}/advance`, {}),

  executeAction: (actionId) => post(`/api/actions/${actionId}/execute`, {}),

  pendingApprovals: () => get('/api/approvals?status=pending'),
  createApproval: (actionId) => post('/api/approvals', { action_id: actionId }),
  decideApproval: (id, decision, approver = 'admin', note = '') =>
    post(`/api/approvals/${id}/decide`, { decision, approver, note }),

  auditList: (taskId, limit = 200) =>
    get(`/api/audit?limit=${limit}${taskId ? `&task_id=${taskId}` : ''}`),
  auditVerify: () => get('/api/audit/verify'),

  customers: () => get('/api/customers'),
  outbox: () => get('/api/outbox'),

  llmStatus: () => get('/api/llm/status'),
  runLlm: (taskId, goal) => post(`/api/tasks/${taskId}/run-llm`, { goal }),
}

export function apiErrorMessage(e) {
  if (e && e.data) {
    if (typeof e.data.detail === 'string') return e.data.detail
    return JSON.stringify(e.data)
  }
  return e && e.message ? e.message : '未知错误'
}
