const API_BASE = (
  import.meta.env.VITE_API_BASE_URL
  || `${window.location.origin}/api/v1`
).replace(/\/$/, '')

export type CurrentUser = {
  id: number
  username?: string | null
  phone?: string | null
  display_name: string
  permissions: string[]
  scopes: Record<string, { kind: string; values: string[] }[]>
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('gh-phone-access-token')
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if ((init.method || 'GET').toUpperCase() === 'POST' && !headers.has('X-Idempotency-Key')) {
    let key = localStorage.getItem('gh-phone-operation-key')
    if (!key) { key = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`; localStorage.setItem('gh-phone-operation-key', key) }
    headers.set('X-Idempotency-Key', key)
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = body.detail ?? body.message
    const message = Array.isArray(detail)
      ? detail.map((item) => typeof item === 'string' ? item : item?.msg || JSON.stringify(item)).join('；')
      : typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : '请求失败'
    throw new Error(message)
  }
  return body as T
}

export function loginByPassword(identifier: string, password: string) {
  return request<{ access_token: string; token_type: string; user: CurrentUser }>('/auth/password', { method: 'POST', body: JSON.stringify({ identifier, password }) })
}
export function sendSmsCode(phone: string) {
  return request<{ status: string; provider: string }>('/auth/sms/send', { method: 'POST', body: JSON.stringify({ phone }) })
}
export function loginBySms(phone: string, code: string) {
  return request<{ access_token: string; token_type: string; user: CurrentUser }>('/auth/sms', { method: 'POST', body: JSON.stringify({ phone, code }) })
}
export function getCurrentUser() { return request<CurrentUser>('/auth/me') }
export function updateProfile(payload: { display_name?: string; username?: string | null }) { return request<CurrentUser>('/auth/profile', { method: 'PATCH', body: JSON.stringify(payload) }) }
export function changePassword(current_password: string, new_password: string) { return request<void>('/auth/password', { method: 'PATCH', body: JSON.stringify({ current_password, new_password }) }) }
export function listWorkLocations() { return request<Record<string, unknown>[]>('/auth/work-locations') }
export function hasPermission(user: CurrentUser | null, code: string) { return Boolean(user?.permissions.includes(code)) }
export function beginOperation() { const key = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`; localStorage.setItem('gh-phone-operation-key', key); return key }
export function endOperation() { localStorage.removeItem('gh-phone-operation-key') }
export function setOperationKey(key: string) { localStorage.setItem('gh-phone-operation-key', key) }

export function createPurchaseReceipt(payload: unknown) {
  return request<{ order_no: string; total_count: number; status: string }>('/inventory/purchase-receipts', { method: 'POST', body: JSON.stringify(payload) })
}
export function createTray(payload: unknown) {
  return request<{ code: string; phone_count: number }>('/inventory/trays', { method: 'POST', body: JSON.stringify(payload) })
}
export function createBox(payload: unknown) {
  return request<{ code: string; phone_count: number; tray_count: number }>('/inventory/boxes', { method: 'POST', body: JSON.stringify(payload) })
}
export function getPhone(imei: string) { return request<Record<string, unknown>>(`/inventory/phones/${encodeURIComponent(imei)}`) }
export function dispatchShipment(payload: unknown) { return request<{ shipment_no: string; total_count: number; status: string }>('/shipments/dispatch', { method: 'POST', body: JSON.stringify(payload) }) }
export function startReceiving(payload: unknown) { return request<{ receiving_no: string; expected_count: number; status: string }>('/shipments/receiving/start', { method: 'POST', body: JSON.stringify(payload) }) }
export function inspectReceiving(payload: unknown) { return request<{ receiving_no: string; accepted_count: number; exception_count: number; expected_count: number; status: string }>('/shipments/receiving/inspect', { method: 'POST', body: JSON.stringify(payload) }) }
export function issueTransfer(payload: unknown) { return request<{ transfer_no: string; total_count: number; status: string }>('/transfers/issue', { method: 'POST', body: JSON.stringify(payload) }) }
export function receiveTransfer(payload: unknown) { return request<{ transfer_no: string; total_count: number; received_count: number; exception_count: number; status: string }>('/transfers/receive', { method: 'POST', body: JSON.stringify(payload) }) }
export function createSale(payload: unknown) { return request<{ sales_no: string; total_count: number; status: string; total_amount: string | null }>('/sales', { method: 'POST', body: JSON.stringify(payload) }) }
export function confirmSale(salesNo: string) { return request<{ sales_no: string; status: string; total_count: number }>(`/sales/${encodeURIComponent(salesNo)}/confirm`, { method: 'POST', body: JSON.stringify({}) }) }
export function createReturn(payload: unknown) { return request<{ return_no: string; total_count: number; status: string }>('/returns', { method: 'POST', body: JSON.stringify(payload) }) }
export function receiveReturn(payload: unknown) { return request<{ return_no: string; received_count: number; total_count: number; status: string }>('/returns/receive', { method: 'POST', body: JSON.stringify(payload) }) }
export function createRepair(payload: unknown) { return request<{ repair_no: string; total_count: number; status: string }>('/repairs', { method: 'POST', body: JSON.stringify(payload) }) }
export function acceptRepair(repairNo: string) { return request<{ repair_no: string; status: string }>(`/repairs/${encodeURIComponent(repairNo)}/accept`, { method: 'POST', body: JSON.stringify({}) }) }
export function completeRepair(repairNo: string, payload: unknown) { return request<{ repair_no: string; completed_count: number; status: string }>(`/repairs/${encodeURIComponent(repairNo)}/complete`, { method: 'POST', body: JSON.stringify({ repair_no: repairNo, ...payload }) }) }
export function reviewRepair(repairNo: string, payload: unknown) { return request<{ repair_no: string; accepted_count: number; status: string }>(`/repairs/${encodeURIComponent(repairNo)}/review`, { method: 'POST', body: JSON.stringify({ repair_no: repairNo, ...payload }) }) }
export function submitStocktake(payload: unknown) { return request<{ stocktake_no: string; expected_count: number; found_count: number; missing_count: number; extra_count: number; status: string }>('/stocktakes', { method: 'POST', body: JSON.stringify(payload) }) }
export function adjustStocktake(stocktakeNo: string, payload: unknown) { return request<{ stocktake_no: string; adjustment_status: string; reviewer_id: number | null }>(`/stocktakes/${encodeURIComponent(stocktakeNo)}/adjust`, { method: 'POST', body: JSON.stringify(payload) }) }
export function listPhones(params: Record<string, string | number | undefined> = {}) { const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)])); return request<{ items: Record<string, unknown>[]; count: number }>(`/inventory/phones?${query}`) }
export function listDocuments(params: Record<string, string | number | undefined> = {}) { const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)])); return request<{ items: Record<string, unknown>[]; count: number }>(`/documents?${query}`) }
export function listOrganizations() { return request<Record<string, unknown>[]>('/admin/organizations') }
export function listLocations() { return request<Record<string, unknown>[]>('/admin/locations') }
export function listUsers() { return request<Record<string, unknown>[]>('/admin/users') }
export function listRoles() { return request<Record<string, unknown>[]>('/admin/roles') }
export function listPermissions() { return request<Record<string, unknown>[]>('/admin/permissions') }
export function listAudits(params: Record<string, string | number | undefined> = {}) { const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)])); return request<Record<string, unknown>[]>(`/admin/audits?${query}`) }
export function createOrganization(payload: unknown) { return request<Record<string, unknown>>('/admin/organizations', { method: 'POST', body: JSON.stringify(payload) }) }
export function createLocation(payload: unknown) { return request<Record<string, unknown>>('/admin/locations', { method: 'POST', body: JSON.stringify(payload) }) }
export function createRole(payload: unknown) { return request<Record<string, unknown>>('/admin/roles', { method: 'POST', body: JSON.stringify(payload) }) }
export function createUser(payload: unknown) { return request<Record<string, unknown>>('/admin/users', { method: 'POST', body: JSON.stringify(payload) }) }
export function updateOrganization(id: number, payload: unknown) { return request<Record<string, unknown>>(`/admin/organizations/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }) }
export function updateLocation(id: number, payload: unknown) { return request<Record<string, unknown>>(`/admin/locations/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }) }
export function updateUser(userId: number, payload: unknown) { return request<Record<string, unknown>>(`/admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(payload) }) }
