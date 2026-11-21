import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api', withCredentials: true })

// CSRF credentials are kept only in memory and refreshed when the session changes.
let csrfToken = null
let csrfRequest = null
let csrfGeneration = 0
function clearCsrf() {
  csrfGeneration += 1
  csrfToken = null
  csrfRequest = null
}
async function ensureCsrf() {
  if (csrfToken) return csrfToken
  if (!csrfRequest) {
    const generation = csrfGeneration
    csrfRequest = api.get('/auth/csrf').then(response => {
      if (generation !== csrfGeneration) return ensureCsrf()
      csrfToken = response.data.csrf_token
      if (!csrfToken) throw new Error('Missing CSRF token')
      return csrfToken
    }).finally(() => { if (generation === csrfGeneration) csrfRequest = null })
  }
  return csrfRequest
}
api.interceptors.request.use(async config => {
  if (['post', 'put', 'patch', 'delete'].includes(config.method?.toLowerCase())) {
    config.headers['X-CSRF-Token'] = await ensureCsrf()
  }
  return config
})
api.interceptors.response.use(response => response, error => {
  if ([401, 403].includes(error.response?.status)) clearCsrf()
  return Promise.reject(error)
})

export async function register(email, password) {
  const user = (await api.post('/auth/register', { email, password })).data
  clearCsrf()
  return user
}
export async function login(email, password) {
  const user = (await api.post('/auth/login', { email, password })).data
  clearCsrf()
  return user
}
export async function logout() {
  await api.post('/auth/logout')
  clearCsrf()
}
export async function getCurrentUser() {
  return (await api.get('/auth/me')).data
}
export async function deleteReading(id) {
  await api.delete(`/readings/${encodeURIComponent(id)}`)
}

export async function getCategories() {
  return (await api.get('/categories')).data
}

export async function getQuestions(categoryId) {
  return (await api.get('/questions', { params: { category_id: categoryId } })).data
}

export async function getSpreads() {
  return (await api.get('/spreads')).data
}

export async function getCards() {
  return (await api.get('/cards')).data
}

export async function getCard(id) {
  return (await api.get(`/cards/${encodeURIComponent(id)}`)).data
}

export async function createReading(payload, key) {
  return (await api.post('/readings', payload, { headers: { 'Idempotency-Key': key } })).data
}

export async function getReading(id) {
  return (await api.get(`/readings/${encodeURIComponent(id)}`)).data
}

export async function drawReading(id, selectedIndices) {
  return (await api.post(`/readings/${encodeURIComponent(id)}/draw`, { selected_indices: selectedIndices })).data
}

export async function revealReading(id, positionNumber) {
  return (await api.post(`/readings/${encodeURIComponent(id)}/reveal`, { position_number: positionNumber })).data
}

export async function interpretReading(id) {
  return (await api.post(`/readings/${encodeURIComponent(id)}/interpret`)).data
}

export async function getHistory() {
  return (await api.get('/history')).data
}
