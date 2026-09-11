<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { BrowserMultiFormatReader } from '@zxing/browser'
import { BarcodeFormat, DecodeHintType } from '@zxing/library'
import { acceptRepair, adjustStocktake, beginOperation, changePassword, confirmSale, completeRepair, createBox, createLocation, createOrganization, createPurchaseReceipt, createRepair, createReturn, createRole, createSale, createTray, createUser, dispatchShipment, endOperation, getCurrentUser, getPhone, hasPermission, inspectReceiving, issueTransfer, listAudits, listDocuments, listLocations, listOrganizations, listPhones, listPermissions, listRoles, listUsers, listWorkLocations, loginByPassword, loginBySms, receiveReturn, receiveTransfer, reviewRepair, sendSmsCode, setOperationKey, startReceiving, submitStocktake, type CurrentUser, updateLocation, updateOrganization, updateProfile, updateUser } from './api'
import { ArrowLeftRight, Box, CheckCircle2, ClipboardCheck, FileText, House, PackageOpen, RotateCcw, ScanLine, Search, Send, Settings, ShoppingCart, Warehouse, Wrench } from '@lucide/vue'

type ScanItem = { value: string; time: string; result: '待提交' | '成功' }
type WorkflowKey = 'shenzhen' | 'ghana'
type WorkflowStep = { key: string; label: string; hint: string; action: string; phase: string; permission: string }
type Task = { title: string; hint: string; icon: any; permission: string | string[]; mode: 'imei' | 'container'; action: string; workflow?: WorkflowKey }

const user = ref<CurrentUser | null>(null)
const loading = ref(false)
const error = ref('')
const online = ref(navigator.onLine)
const installPrompt = ref<any>(null)
const loginMode = ref<'password' | 'sms'>('password')
const phone = ref('')
const password = ref('')
const code = ref('')
const smsSent = ref(false)
const activeTask = ref<Task | null>(null)
// A workflow groups the steps that are performed by one physical operator.
// activeTask remains the existing API task so all endpoint payloads and draft
// replay behaviour stay unchanged.
const activeWorkflow = ref<WorkflowKey | null>(null)
const manualValue = ref('')
const scanItems = ref<ScanItem[]>([])
const cameraError = ref('')
const operationMessage = ref('')
const organizationId = ref('')
const locationId = ref('')
const containerCode = ref('')
const capturingContainer = ref(false)
const targetTrayCode = ref('')
const targetBoxCode = ref('')
const containerKind = ref<'PHONE' | 'TRAY' | 'BOX'>('BOX')
const documentNo = ref('')
const destinationOrganizationId = ref('')
const destinationLocationId = ref('')
const logisticsNo = ref('')
const accepted = ref(true)
const salesType = ref<'RETAIL' | 'WHOLESALE'>('RETAIL')
const customerName = ref('')
const salePrices = ref('')
const disposition = ref('AVAILABLE_AGAIN')
const repairResult = ref('REPAIRED')
const adjustmentDecision = ref('IGNORE')
const adjustmentTargetStatus = ref('可再次销售')
const operationPhase = ref('create')
const submitting = ref(false)
const pendingCount = ref(0)
const drafts = ref<any[]>([])
const showDrafts = ref(false)
const showProfileMenu = ref(false)
const showProfileEditor = ref(false)
const profileDisplayName = ref('')
const profileUsername = ref('')
const currentPassword = ref('')
const newPassword = ref('')
const confirmNewPassword = ref('')
const profileSaving = ref(false)
const currentView = ref<'work' | 'inventory' | 'documents' | 'admin'>('work')
const viewLoading = ref(false)
const inventoryItems = ref<Record<string, unknown>[]>([])
const documentItems = ref<Record<string, unknown>[]>([])
const adminData = ref<{ organizations: Record<string, unknown>[]; locations: Record<string, unknown>[]; users: Record<string, unknown>[]; roles: Record<string, unknown>[]; permissions: Record<string, unknown>[]; audits: Record<string, unknown>[] }>({ organizations: [], locations: [], users: [], roles: [], permissions: [], audits: [] })
const adminTab = ref<'users' | 'organizations' | 'locations' | 'roles' | 'audits'>('users')
const orgCode = ref(''); const orgName = ref(''); const orgCountry = ref('')
const locOrganizationId = ref(''); const locCode = ref(''); const locName = ref(''); const locType = ref('store')
const roleCode = ref(''); const roleName = ref(''); const roleWorkGroup = ref(''); const roleDescription = ref(''); const selectedRolePermissions = ref<string[]>([])
const newUserIdentifier = ref(''); const newUserName = ref(''); const newUserPassword = ref(''); const newUserRoleIds = ref<number[]>([]); const newUserScopes = ref('')
// 兼容模板中的旧字段绑定；表单现在同时接受手机号和英文用户名。
const newUserPhone = newUserIdentifier
const editingUserId = ref<number | null>(null); const editingUserRoleIds = ref<number[]>([]); const editingUserScopes = ref('')
const workLocations = ref<Record<string, unknown>[]>([])
// A generated receiving/return number follows the operator when the
// workflow stepper switches to the next underlying task.
const workflowDocuments = ref<Record<string, string>>({})
const roleLabel = computed(() => {
  const first = user.value?.roles?.[0]
  if (typeof first === 'string') return first
  return first?.name || user.value?.work_group || ''
})
const video = ref<HTMLVideoElement | null>(null)
const scanning = ref(false)
let stream: MediaStream | null = null
let scanTimer = 0
let barcodeReader: BrowserMultiFormatReader | null = null
let scannerControls: { stop: () => void } | null = null

const tasks: Task[] = [
  { title: '采购入库', hint: '连续读取手机 IMEI', icon: PackageOpen, permission: 'purchase:create', mode: 'imei', action: 'purchase' },
  { title: '装托盘', hint: '手机归入指定托盘', icon: ClipboardCheck, permission: 'tray:manage', mode: 'imei', action: 'tray' },
  { title: '装箱', hint: '托盘归入指定箱子', icon: Box, permission: 'box:manage', mode: 'container', action: 'box' },
  { title: '发运出库', hint: '按手机、托盘或箱子', icon: Send, permission: 'shipment:dispatch', mode: 'container', action: 'shipment' },
  { title: '接收验收', hint: '逐台核对实际到货', icon: CheckCircle2, permission: ['receiving:unpack', 'receiving:accept'], mode: 'imei', action: 'receiving' },
  { title: '门店调拨', hint: '配送、串货和收货', icon: ArrowLeftRight, permission: ['transfer:create', 'transfer:receive'], mode: 'container', action: 'transfer' },
  { title: '销售', hint: '零售或批发出库', icon: ShoppingCart, permission: ['sales:create', 'sales:approve'], mode: 'container', action: 'sales' },
  { title: '销售退回', hint: '按手机、托盘或箱子运送', icon: RotateCcw, permission: ['return:create', 'return:receive'], mode: 'container', action: 'return' },
  { title: '维修', hint: '支持整批送修，逐台维修复核', icon: Wrench, permission: ['repair:create', 'repair:receive', 'repair:update', 'repair:approve'], mode: 'container', action: 'repair' },
  { title: '盘点核查', hint: '盘点与差异处理', icon: ScanLine, permission: ['stocktake:submit', 'stocktake:adjust'], mode: 'imei', action: 'stocktake' },
  { title: '查询手机', hint: 'IMEI 全程轨迹', icon: Search, permission: 'phone:view', mode: 'imei', action: 'query' }
]
const workflowTasks: Task[] = [
  { title: '深圳收购仓作业', hint: '收购验收 → 装托盘 → 装箱封存', icon: PackageOpen, permission: ['purchase:create', 'tray:manage', 'box:manage'], mode: 'imei', action: 'workflow_shenzhen', workflow: 'shenzhen' },
  { title: '加纳综合仓作业', hint: '到货验收 → 拣货调拨 → 退回分诊 → 维修建单/QA', icon: Warehouse, permission: ['receiving:unpack', 'receiving:accept', 'transfer:create', 'return:receive', 'repair:create', 'repair:approve'], mode: 'imei', action: 'workflow_ghana', workflow: 'ghana' },
]
const workflowDefinitions: Record<WorkflowKey, WorkflowStep[]> = {
  shenzhen: [
    { key: 'purchase', label: '收购验收', hint: '逐台录入 IMEI，生成采购入库单', action: 'purchase', phase: 'create', permission: 'purchase:create' },
    { key: 'tray', label: '装入托盘', hint: '先录托盘编码，再连续扫手机', action: 'tray', phase: 'create', permission: 'tray:manage' },
    { key: 'box', label: '装箱封存', hint: '扫描托盘编码，完成箱内装载', action: 'box', phase: 'create', permission: 'box:manage' },
  ],
  ghana: [
    { key: 'receiving-start', label: '建立到货单', hint: '按发运单开箱登记', action: 'receiving', phase: 'start', permission: 'receiving:unpack' },
    { key: 'receiving-inspect', label: '逐台到货验收', hint: '逐台核对并可重新装托/装箱', action: 'receiving', phase: 'inspect', permission: 'receiving:accept' },
    { key: 'transfer-issue', label: '门店拣货调拨', hint: '按手机、托盘或箱子发往门店', action: 'transfer', phase: 'issue', permission: 'transfer:create' },
    { key: 'transfer-receive', label: '调拨收货', hint: '门店或管理处核对实收', action: 'transfer', phase: 'receive', permission: 'transfer:receive' },
    { key: 'return-create', label: '发起退回', hint: '登记门店待维修手机/托盘', action: 'return', phase: 'create', permission: 'return:create' },
    { key: 'return-receive', label: '退回分诊', hint: '接收退回箱/托盘，逐台登记', action: 'return', phase: 'receive', permission: 'return:receive' },
    { key: 'repair-create', label: '建立维修单', hint: '把待修手机或容器送入维修队列', action: 'repair', phase: 'create', permission: 'repair:create' },
    { key: 'repair-accept', label: '维修接收', hint: '维修人员接收任务（如有授权）', action: 'repair', phase: 'accept', permission: 'repair:receive' },
    { key: 'repair-complete', label: '填写维修结果', hint: '逐台记录维修结果（如有授权）', action: 'repair', phase: 'complete', permission: 'repair:update' },
    { key: 'repair-review', label: '维修 QA 复核', hint: '逐台确认恢复可售、冻结或报损', action: 'repair', phase: 'review', permission: 'repair:approve' },
  ],
}
const underlyingTask = (action: string) => tasks.find((task) => task.action === action) || null
function metadataWorkflow(): WorkflowKey | null {
  const raw = user.value
  if (!raw) return null
  const value = String(raw.work_group || '').trim().toLowerCase()
  if (['shenzhen', 'sz', 'shenzhen_operations', 'sz_operations', 'demo_sz_operations', '深圳综合作业'].includes(value)) return 'shenzhen'
  if (['ghana', 'gh', 'ghana_operations', 'demo_ghana_operations', '加纳综合作业'].includes(value)) return 'ghana'
  const codes = (Array.isArray(raw.role_codes) ? raw.role_codes : [])
    .concat(Array.isArray(raw.roles) ? raw.roles.map((row) => typeof row === 'string' ? row : row.code || '') : [])
    .map((code) => String(code).toLowerCase())
  if (codes.includes('demo_sz_operations')) return 'shenzhen'
  if (codes.includes('demo_ghana_operations')) return 'ghana'
  return null
}
function workflowCapabilityReady(workflow: WorkflowKey) {
  // Require the core capabilities that identify the merged岗位. Partial or
  // legacy roles keep their original granular入口 instead of losing access.
  const required = workflow === 'shenzhen'
    ? ['purchase:create', 'tray:manage', 'box:manage']
    : ['receiving:unpack', 'receiving:accept', 'transfer:create', 'return:receive', 'repair:create', 'repair:approve']
  const hasRequired = required.every((code) => hasPermission(user.value, code))
  const metadata = metadataWorkflow()
  return metadata ? metadata === workflow && hasRequired : hasRequired
}
const workflowSteps = computed(() => activeWorkflow.value ? workflowDefinitions[activeWorkflow.value].filter((step) => hasPermission(user.value, step.permission)) : [])
const currentWorkflowStep = computed(() => workflowSteps.value.find((step) => step.action === activeTask.value?.action && step.phase === operationPhase.value) || null)
const nextWorkflowStep = computed(() => {
  if (!currentWorkflowStep.value) return null
  const index = workflowSteps.value.findIndex((step) => step.key === currentWorkflowStep.value!.key)
  return workflowSteps.value[index + 1] || null
})
// The Ghana综合岗位建立维修单后，维修技师仍是独立执行岗位。  不把
// “建单成功”误显示成可以立即做 QA；技师接单并提交结果后，综合岗位
// 再从步骤条进入 QA。这样既保留了同一账号的连续工作台，也尊重实际
// 的岗位分离和维修状态机。
function repairTechHandoffPending() {
  return activeWorkflow.value === 'ghana'
    && currentWorkflowStep.value?.key === 'repair-create'
    && (!hasPermission(user.value, 'repair:receive') || !hasPermission(user.value, 'repair:update'))
}
function taskVisible(task: Task) { return Array.isArray(task.permission) ? task.permission.some((code) => hasPermission(user.value, code)) : hasPermission(user.value, task.permission) }
function scanMode() {
  if (!activeTask.value) return 'imei'
  if (capturingContainer.value && ['tray', 'box'].includes(activeTask.value.action)) return 'container'
  if (['return', 'repair'].includes(activeTask.value.action) && operationPhase.value !== 'create') return 'imei'
  return activeTask.value.mode
}
function phaseRequiresScan() {
  if (!activeTask.value) return true
  return !(
    (activeTask.value.action === 'receiving' && operationPhase.value === 'start') ||
    (activeTask.value.action === 'sales' && operationPhase.value === 'confirm') ||
    (activeTask.value.action === 'repair' && operationPhase.value === 'accept')
  )
}
watch(operationPhase, async () => {
  if (!activeTask.value) return
  syncTaskLocation()
  scanItems.value = []
  stopCamera()
  if (phaseRequiresScan() && !scannerControls) { await nextTick(); await startCamera() }
})
function roleIdsLabel(item: Record<string, unknown>) {
  const ids = Array.isArray(item.role_ids) ? item.role_ids : []
  return ids.length ? ids.join(', ') : '无'
}
function permissionLabel(code: unknown) {
  const row = adminData.value.permissions.find((item) => item.code === code)
  const labels: Record<string, string> = {
    'audit:view': '查看操作审计', 'box:manage': '管理箱子', 'inventory:issue': '库存出库', 'inventory:receive': '库存入库',
    'phone:edit': '编辑手机资料', 'phone:view': '查询手机', 'purchase:create': '采购入库', 'receiving:accept': '接收验收',
    'receiving:unpack': '拆箱验货', 'repair:approve': '维修复核', 'repair:create': '创建维修单', 'repair:receive': '接收维修',
    'repair:update': '填写维修结果', 'report:view': '查看报表', 'return:create': '发起销售退回', 'return:receive': '接收销售退回',
    'role:manage': '管理角色', 'sales:approve': '确认销售', 'sales:cancel': '取消销售', 'sales:create': '创建销售单',
    'shipment:dispatch': '发运出库', 'shipment:view': '查看发运单', 'stocktake:adjust': '审核盘点差异', 'stocktake:submit': '提交盘点',
    'transfer:create': '发起调拨', 'transfer:receive': '调拨收货', 'tray:manage': '管理托盘', 'user:manage': '管理用户'
  }
  return `${labels[String(code)] || row?.name || String(code)}（${String(code)}）`
}
function roleNameLabel(id: unknown) {
  const row = adminData.value.roles.find((item) => Number(item.id) === Number(id))
  return row ? `${row.name}（${row.code}）` : `角色 ${id}`
}
function documentTypeLabel(type: unknown) {
  return ({ shipment: '发运单', receiving: '接收验收单', transfer: '门店调拨单', sales: '销售单', return: '销售退回单', repair: '维修单', stocktake: '盘点单' } as Record<string, string>)[String(type)] || String(type)
}
const visibleTasks = computed(() => {
  const result: Task[] = []
  const shenzhenMerged = workflowCapabilityReady('shenzhen')
  const ghanaMerged = workflowCapabilityReady('ghana')
  if (shenzhenMerged) result.push(workflowTasks[0])
  if (ghanaMerged) result.push(workflowTasks[1])
  for (const task of tasks) {
    // Once a merged岗位 has the complete capability set, its constituent
    // cards are represented by the single workflow card above.
    if (shenzhenMerged && ['purchase', 'tray', 'box'].includes(task.action)) continue
    if (ghanaMerged && ['receiving', 'transfer', 'return', 'repair'].includes(task.action)) continue
    if (taskVisible(task)) result.push(task)
  }
  return result
})
const hasWorkflowEntry = computed(() => visibleTasks.value.some((task) => Boolean(task.workflow)))
const sourceLocations = computed(() => workLocations.value.filter((item) => item.source_allowed))
const activeLocations = computed(() => workLocations.value)
const destinationLocations = computed(() => {
  const action = activeTask.value?.action
  const current = activeLocations.value.find((item) => String(item.id) === locationId.value)
  const currentOrganizationId = current ? String(current.organization_id) : ''
  const sameOrganization = (item: Record<string, unknown>) => !currentOrganizationId || String(item.organization_id) === currentOrganizationId
  const differentOrganization = (item: Record<string, unknown>) => !currentOrganizationId || String(item.organization_id) !== currentOrganizationId
  if (action === 'transfer') {
    const stores = activeLocations.value.filter((item) => item.location_type === 'store' && String(item.id) !== locationId.value && sameOrganization(item))
    return stores.length ? stores : activeLocations.value
  }
  if (action === 'return') {
    const warehouses = activeLocations.value.filter((item) => ['warehouse', 'receiving'].includes(String(item.location_type)) && String(item.id) !== locationId.value && sameOrganization(item))
    return warehouses.length ? warehouses : activeLocations.value
  }
  if (action === 'shipment') {
    const warehouses = activeLocations.value.filter((item) => ['warehouse', 'receiving'].includes(String(item.location_type)) && String(item.id) !== locationId.value && differentOrganization(item))
    return warehouses.length ? warehouses : activeLocations.value
  }
  return activeLocations.value
})
function scopeAllows(permission: string, locationIdValue: unknown, organizationIdValue: unknown) {
  if (!user.value?.permissions.includes(permission)) return false
  const scopes = user.value.scopes?.[permission] || []
  return scopes.some((scope) => scope.kind === 'all' || (scope.kind === 'location' && scope.values.includes(String(locationIdValue))) || (scope.kind === 'organization' && scope.values.includes(String(organizationIdValue))))
}
const sourceLocationsForTask = computed(() => {
  if (!activeTask.value) return sourceLocations.value
  const codes = Array.isArray(activeTask.value.permission) ? activeTask.value.permission : [activeTask.value.permission]
  return workLocations.value.filter((item) => codes.some((code) => scopeAllows(code, item.id, item.organization_id)))
})
function syncTaskLocation() {
  if (!activeTask.value) return
  if (!phaseRequiresCurrentLocation()) {
    locationId.value = ''
    organizationId.value = ''
    return
  }
  const current = workLocations.value.find((item) => String(item.id) === locationId.value)
  if (current && sourceLocationsForTask.value.some((item) => String(item.id) === locationId.value)) {
    organizationId.value = String(current.organization_id)
    return
  }
  if (sourceLocationsForTask.value.length === 1) {
    locationId.value = String(sourceLocationsForTask.value[0].id)
    syncOrganizationFromLocation()
  } else {
    locationId.value = ''
    organizationId.value = ''
  }
}
function phaseRequiresCurrentLocation() {
  const action = activeTask.value?.action
  return Boolean(action && (
    ['purchase', 'tray', 'box', 'shipment'].includes(action) ||
    (action === 'receiving' && operationPhase.value === 'start') ||
    (action === 'transfer' && operationPhase.value === 'issue') ||
    (action === 'sales' && operationPhase.value === 'create') ||
    (action === 'return' && operationPhase.value === 'create') ||
    (action === 'repair' && operationPhase.value === 'create') ||
    (action === 'stocktake' && operationPhase.value === 'create')
  ))
}
function locationLabel(item: Record<string, unknown>) { return `${item.organization_name} · ${item.name}（${item.code}）` }
function syncOrganizationFromLocation() {
  const row = workLocations.value.find((item) => String(item.id) === locationId.value)
  if (row) organizationId.value = String(row.organization_id)
}
function syncDestinationOrganization() {
  const row = workLocations.value.find((item) => String(item.id) === destinationLocationId.value)
  if (row) destinationOrganizationId.value = String(row.organization_id)
}
async function loadWorkLocations() {
  try { workLocations.value = await listWorkLocations() } catch { workLocations.value = [] }
}
function initialPhase(action: string) {
  const choices: Record<string, [string, string][]> = {
    receiving: [['start', 'receiving:unpack'], ['inspect', 'receiving:accept']],
    transfer: [['issue', 'transfer:create'], ['receive', 'transfer:receive']],
    sales: [['create', 'sales:create'], ['confirm', 'sales:approve']],
    return: [['create', 'return:create'], ['receive', 'return:receive']],
    repair: [['create', 'repair:create'], ['accept', 'repair:receive'], ['complete', 'repair:update'], ['review', 'repair:approve']],
    stocktake: [['create', 'stocktake:submit'], ['adjust', 'stocktake:adjust']],
  }
  return choices[action]?.find(([, permission]) => hasPermission(user.value, permission))?.[0] || 'create'
}
function refreshPendingCount() {
  try { drafts.value = JSON.parse(localStorage.getItem('gh-phone-offline-queue') || '[]'); pendingCount.value = drafts.value.filter((draft) => draft.status !== 'synced').length } catch { drafts.value = []; pendingCount.value = 0 }
}
function saveDrafts() { localStorage.setItem('gh-phone-offline-queue', JSON.stringify(drafts.value)); refreshPendingCount() }
function removeDraft(id: string) { drafts.value = drafts.value.filter((draft) => draft.id !== id); saveDrafts() }
async function switchView(view: 'work' | 'inventory' | 'documents' | 'admin') {
  currentView.value = view; if (view === 'work') return
  viewLoading.value = true; error.value = ''
  try {
    if (view === 'inventory') inventoryItems.value = (await listPhones()).items
    else if (view === 'documents') documentItems.value = (await listDocuments()).items
    else if (view === 'admin') {
      const canUsers = hasPermission(user.value, 'user:manage')
      const canRoles = hasPermission(user.value, 'role:manage')
      const [organizations, locations, users, roles, permissions, audits] = await Promise.all([
        canUsers ? listOrganizations() : Promise.resolve([]),
        canUsers ? listLocations() : Promise.resolve([]),
        canUsers ? listUsers() : Promise.resolve([]),
        canUsers || canRoles ? listRoles() : Promise.resolve([]),
        canRoles ? listPermissions() : Promise.resolve([]),
        hasPermission(user.value, 'audit:view') ? listAudits() : Promise.resolve([]),
      ])
      adminData.value = { organizations, locations, users, roles, permissions, audits }
    }
  } catch (err) { error.value = err instanceof Error ? err.message : '加载失败' }
  finally { viewLoading.value = false }
}
async function toggleUser(item: Record<string, unknown>) {
  const userId = Number(item.id)
  if (!Number.isInteger(userId)) return
  error.value = ''
  try {
    await updateUser(userId, { is_active: !Boolean(item.is_active) })
    await switchView('admin')
  } catch (err) { error.value = err instanceof Error ? err.message : '更新用户失败' }
}
function beginEditUser(item: Record<string, unknown>) {
  editingUserId.value = Number(item.id)
  editingUserRoleIds.value = Array.isArray(item.role_ids) ? item.role_ids.map((id) => Number(id)) : []
  editingUserScopes.value = JSON.stringify(item.scopes || [], null, 2)
}
function cancelEditUser() { editingUserId.value = null; editingUserRoleIds.value = []; editingUserScopes.value = '' }
async function saveUserEdit() {
  if (editingUserId.value === null) return
  error.value = ''
  try {
    let scopes: unknown[] = []
    if (editingUserScopes.value.trim()) {
      scopes = JSON.parse(editingUserScopes.value)
      if (!Array.isArray(scopes)) throw new Error('数据范围必须是 JSON 数组')
    }
    await updateUser(editingUserId.value, { role_ids: editingUserRoleIds.value, scopes })
    cancelEditUser(); operationMessage.value = '用户权限已更新'; await switchView('admin')
  } catch (err) { error.value = err instanceof Error ? err.message : '更新用户权限失败' }
}
async function toggleAdminResource(kind: 'organization' | 'location', item: Record<string, unknown>) {
  const id = Number(item.id)
  if (!Number.isInteger(id)) return
  error.value = ''
  try {
    const payload = { is_active: !Boolean(item.is_active) }
    if (kind === 'organization') await updateOrganization(id, payload)
    else await updateLocation(id, payload)
    await switchView('admin')
  } catch (err) { error.value = err instanceof Error ? err.message : '更新资料失败' }
}
async function createAdminRecord(kind: 'organization' | 'location' | 'role' | 'user') {
  error.value = ''
  try {
    if (kind === 'organization') {
      if (!orgCode.value.trim() || !orgName.value.trim() || !orgCountry.value.trim()) throw new Error('请填写组织代码、名称和国家')
      await createOrganization({ code: orgCode.value.trim(), name: orgName.value.trim(), country: orgCountry.value.trim() })
      orgCode.value = ''; orgName.value = ''; orgCountry.value = ''
    } else if (kind === 'location') {
      const organization_id = numeric(locOrganizationId.value)
      if (!organization_id || !locCode.value.trim() || !locName.value.trim()) throw new Error('请填写组织编号、地点代码和名称')
      await createLocation({ organization_id, code: locCode.value.trim(), name: locName.value.trim(), location_type: locType.value })
      locCode.value = ''; locName.value = ''
    } else if (kind === 'role') {
      if (!roleCode.value.trim() || !roleName.value.trim()) throw new Error('请填写角色代码和名称')
      await createRole({ code: roleCode.value.trim(), name: roleName.value.trim(), work_group: roleWorkGroup.value.trim() || null, description: roleDescription.value.trim() || null, permission_codes: selectedRolePermissions.value })
      roleCode.value = ''; roleName.value = ''; roleWorkGroup.value = ''; roleDescription.value = ''; selectedRolePermissions.value = []
    } else {
      const identifier = newUserIdentifier.value.trim()
      if (!identifier || !newUserName.value.trim() || !newUserPassword.value) throw new Error('请填写手机号或英文用户名、姓名和密码')
      const isUsername = /^[A-Za-z]+$/.test(identifier)
      if (!isUsername && !/^[0-9+()\s-]{6,32}$/.test(identifier)) throw new Error('账号必须是手机号或仅包含英文字母的用户名')
      let scopes: unknown[] = []
      if (newUserScopes.value.trim()) {
        try { scopes = JSON.parse(newUserScopes.value) } catch { throw new Error('数据范围必须是合法 JSON 数组') }
        if (!Array.isArray(scopes)) throw new Error('数据范围必须是 JSON 数组')
      }
      await createUser({ ...(isUsername ? { username: identifier } : { phone: identifier }), display_name: newUserName.value.trim(), password: newUserPassword.value, role_ids: newUserRoleIds.value, scopes })
      newUserIdentifier.value = ''; newUserName.value = ''; newUserPassword.value = ''; newUserRoleIds.value = []; newUserScopes.value = ''
    }
    operationMessage.value = '管理资料已保存'
    await switchView('admin')
  } catch (err) { error.value = err instanceof Error ? err.message : '保存失败' }
}
async function retryDraft(draft: any) {
  if (!online.value) return
  error.value = ''; draft.status = 'syncing'; saveDrafts()
  try {
    setOperationKey(draft.idempotency_key || draft.id)
    const values = draft.values as string[]; const org = numeric(draft.organization_id); const location = numeric(draft.location_id)
    if (!org || !location) throw new Error('草稿缺少当前组织或地点')
    let result: any
    if (draft.action === 'purchase') result = await createPurchaseReceipt({ organization_id: org, location_id: location, items: values.map((imei) => ({ imei })) })
    else if (draft.action === 'tray') result = await createTray({ code: draft.container_code, location_id: location, imeis: values })
    else if (draft.action === 'box') result = await createBox({ code: draft.container_code, location_id: location, tray_codes: values })
    else if (draft.action === 'shipment') result = await dispatchShipment({ origin_organization_id: org, origin_location_id: location, destination_organization_id: numeric(draft.destination_organization_id), destination_location_id: numeric(draft.destination_location_id), logistics_no: draft.logistics_no || null, containers: values.map((code) => ({ kind: draft.container_kind, code })) })
    else if (draft.action === 'receiving') {
      if (draft.phase === 'start') result = await startReceiving({ shipment_no: draft.document_no, organization_id: org, location_id: location })
      else { for (const imei of values) { setOperationKey(`${draft.idempotency_key || draft.id}:${imei}`); result = await inspectReceiving({ receiving_no: draft.document_no, imei, accepted: draft.accepted, note: draft.note || null, target_tray_code: draft.target_tray_code || null, target_box_code: draft.target_box_code || null }) } }
    } else if (draft.action === 'transfer') {
      if (draft.phase === 'issue') result = await issueTransfer({ source_organization_id: org, source_location_id: location, destination_organization_id: numeric(draft.destination_organization_id), destination_location_id: numeric(draft.destination_location_id), containers: values.map((code) => ({ kind: draft.container_kind, code })) })
      else result = await receiveTransfer({ transfer_no: draft.document_no, received_imeis: values, complete: true })
    } else if (draft.action === 'sales') {
      if (draft.phase === 'create') result = await createSale({ organization_id: org, location_id: location, sales_type: draft.sales_type, customer_name: draft.customer_name || null, containers: values.map((code) => ({ kind: draft.container_kind, code })), prices: draft.prices || {} })
      else result = await confirmSale(draft.document_no)
    } else if (draft.action === 'return') {
      if (draft.phase === 'create') result = await createReturn({ sales_no: draft.document_no, source_organization_id: org, source_location_id: location, destination_organization_id: numeric(draft.destination_organization_id), destination_location_id: numeric(draft.destination_location_id), imeis: draft.container_kind === 'PHONE' ? values : [], containers: draft.container_kind === 'PHONE' ? [] : values.map((code) => ({ kind: draft.container_kind, code })), note: draft.note || null })
      else result = await receiveReturn({ return_no: draft.document_no, received_imeis: values })
    } else if (draft.action === 'repair') {
      if (draft.phase === 'create') result = await createRepair({ organization_id: org, location_id: location, imeis: draft.container_kind === 'PHONE' ? values : [], containers: draft.container_kind === 'PHONE' ? [] : values.map((code) => ({ kind: draft.container_kind, code })), return_no: draft.workflow === 'ghana' ? (draft.document_no || null) : null, note: draft.note || null })
      else if (draft.phase === 'accept') result = await acceptRepair(draft.document_no)
      else if (draft.phase === 'complete') { for (const imei of values) { setOperationKey(`${draft.idempotency_key || draft.id}:${imei}`); result = await completeRepair(draft.document_no, { imei, repair_result: draft.repair_result }) } }
      else { for (const imei of values) { setOperationKey(`${draft.idempotency_key || draft.id}:${imei}`); result = await reviewRepair(draft.document_no, { imei, disposition: draft.disposition }) } }
    }
    else if (draft.action === 'stocktake' && draft.phase === 'create') result = await submitStocktake({ organization_id: org, location_id: location, imeis: values, note: draft.note || null })
    else if (draft.action === 'stocktake' && draft.phase === 'adjust') result = await adjustStocktake(draft.document_no, values.map((imei) => ({ imei, decision: draft.adjustment_decision, target_status: draft.adjustment_target_status, note: draft.note || null })))
    else throw new Error('该草稿类型需要回到原任务复核后重试')
    draft.status = 'synced'; draft.result = result
  } catch (err) { draft.status = 'conflict'; draft.error = err instanceof Error ? err.message : '同步失败' }
  finally { endOperation(); saveDrafts() }
}
async function retryAllDrafts() { for (const draft of drafts.value.filter((item) => item.status !== 'synced')) await retryDraft(draft) }

function setOnline() { online.value = navigator.onLine }
async function submitLogin() {
  error.value = ''
  // A browser may retain a key from an interrupted operation.  Login is a
  // new session boundary and must never inherit that business-operation key.
  endOperation()
  if (!phone.value.trim()) return void (error.value = '请输入手机号或用户名')
  if (loginMode.value === 'password' && !password.value) return void (error.value = '请输入密码')
  if (loginMode.value === 'sms' && !code.value) return void (error.value = '请输入验证码')
  loading.value = true
  try {
    const result = loginMode.value === 'password'
      ? await loginByPassword(phone.value.trim(), password.value)
      : await loginBySms(phone.value.trim(), code.value)
    localStorage.setItem('gh-phone-access-token', result.access_token)
    user.value = await getCurrentUser(); await loadWorkLocations()
  } catch (err) { error.value = err instanceof Error ? err.message : '登录失败' }
  finally { loading.value = false }
}
async function requestCode() {
  error.value = ''
  if (!phone.value.trim()) return void (error.value = '请先输入手机号')
  try { await sendSmsCode(phone.value.trim()); smsSent.value = true }
  catch (err) { error.value = err instanceof Error ? err.message : '验证码发送失败' }
}
function logout() {
  showProfileMenu.value = false
  endOperation()
  stopCamera()
  localStorage.removeItem('gh-phone-access-token')
  user.value = null
  activeTask.value = null
  activeWorkflow.value = null
  scanItems.value = []
  operationMessage.value = ''
  error.value = ''
  workflowDocuments.value = {}
  organizationId.value = ''; locationId.value = ''
  destinationOrganizationId.value = ''; destinationLocationId.value = ''
}
function openProfileEditor() {
  if (!user.value) return
  profileDisplayName.value = user.value.display_name
  profileUsername.value = user.value.username || ''
  currentPassword.value = ''; newPassword.value = ''; confirmNewPassword.value = ''
  error.value = ''; operationMessage.value = ''; showProfileMenu.value = false; showProfileEditor.value = true
}
async function saveProfile() {
  if (!profileDisplayName.value.trim()) return void (error.value = '姓名不能为空')
  if (newPassword.value && newPassword.value.length < 8) return void (error.value = '新密码至少 8 位')
  if (newPassword.value && newPassword.value !== confirmNewPassword.value) return void (error.value = '两次输入的新密码不一致')
  if (newPassword.value && !currentPassword.value) return void (error.value = '修改密码时请填写当前密码')
  profileSaving.value = true; error.value = ''
  try {
    const updated = await updateProfile({ display_name: profileDisplayName.value.trim(), username: profileUsername.value.trim() || null })
    if (newPassword.value) await changePassword(currentPassword.value, newPassword.value)
    user.value = { ...user.value!, ...updated }; showProfileEditor.value = false; operationMessage.value = '个人资料已更新'
  } catch (err) { error.value = err instanceof Error ? err.message : '保存个人资料失败' }
  finally { profileSaving.value = false }
}
async function activateTask(task: Task, forcedPhase?: string, preserveLocation = false) {
  if (activeWorkflow.value && activeTask.value?.action && documentNo.value.trim()) {
    workflowDocuments.value[`${activeWorkflow.value}:${activeTask.value.action}`] = documentNo.value.trim()
  }
  beginOperation()
  const previousLocation = preserveLocation ? locationId.value : ''
  const previousOrganization = preserveLocation ? organizationId.value : ''
  activeTask.value = task
  scanItems.value = []
  manualValue.value = ''
  cameraError.value = ''
  operationMessage.value = ''
  if (!preserveLocation) { organizationId.value = ''; locationId.value = '' }
  containerCode.value = ''
  capturingContainer.value = ['tray', 'box'].includes(task.action)
  targetTrayCode.value = ''
  targetBoxCode.value = ''
  containerKind.value = task.action === 'box' ? 'TRAY' : 'BOX'
  const workflowDocumentKey = activeWorkflow.value ? `${activeWorkflow.value}:${task.action}` : ''
  documentNo.value = workflowDocumentKey ? (workflowDocuments.value[workflowDocumentKey] || '') : ''
  destinationOrganizationId.value = ''
  destinationLocationId.value = ''
  logisticsNo.value = ''
  accepted.value = true
  customerName.value = ''
  salePrices.value = ''
  disposition.value = 'AVAILABLE_AGAIN'
  repairResult.value = 'REPAIRED'
  adjustmentDecision.value = 'IGNORE'
  adjustmentTargetStatus.value = '可再次销售'
  operationPhase.value = forcedPhase ?? initialPhase(task.action)
  // Ghana return intake is received at the management office and then
  // physically handed to the repair area.  Default this hand-off to loose
  // IMEI scanning; the source return tray/box is opened before scanning.
  if (task.action === 'repair' && operationPhase.value === 'create') {
    containerKind.value = 'PHONE'
    if (activeWorkflow.value === 'ghana' && !documentNo.value.trim()) {
      documentNo.value = workflowDocuments.value['ghana:return'] || ''
    }
  }
  await nextTick()
  if (phaseRequiresCurrentLocation()) {
    const canKeepLocation = preserveLocation && previousLocation && sourceLocationsForTask.value.some((item) => String(item.id) === previousLocation)
    if (canKeepLocation) {
      locationId.value = previousLocation
      organizationId.value = previousOrganization
    } else if (sourceLocationsForTask.value.length === 1) {
      locationId.value = String(sourceLocationsForTask.value[0].id)
      syncOrganizationFromLocation()
    } else {
      locationId.value = ''
      organizationId.value = ''
    }
  } else {
    locationId.value = ''
    organizationId.value = ''
  }
  if (phaseRequiresScan() && !scannerControls) await startCamera()
}
async function openTask(task: Task) {
  if (task.workflow) {
    activeWorkflow.value = task.workflow
    const first = workflowSteps.value[0]
    if (first) await activateTask(underlyingTask(first.action)!, first.phase)
    else activeWorkflow.value = null
    return
  }
  activeWorkflow.value = null
  await activateTask(task)
}
async function selectWorkflowStep(step: WorkflowStep) {
  if (!activeWorkflow.value || !hasPermission(user.value, step.permission)) return
  const task = underlyingTask(step.action)
  if (!task) return
  await activateTask(task, step.phase, true)
}
async function advanceWorkflow() {
  if (nextWorkflowStep.value) await selectWorkflowStep(nextWorkflowStep.value)
}
function closeTask() {
  try { stopCamera() } finally { activeTask.value = null; activeWorkflow.value = null; cameraError.value = ''; operationMessage.value = '' }
}
async function startCamera() {
  if (!window.isSecureContext) return void (cameraError.value = '当前页面不是 HTTPS 安全连接，iPhone 无法使用摄像头；请打开 HTTPS 地址或手工输入')
  if (!navigator.mediaDevices?.getUserMedia) return void (cameraError.value = '当前浏览器不支持摄像头，请手工输入')
  try {
    scanning.value = true
    cameraError.value = '正在识别条码，请将条码对准取景框'
    // 通过 hints 初始化格式和 TRY_HARDER。仅设置 possibleFormats 在部分
    // iOS Safari/WebKit 版本中不会传递到底层 MultiFormatReader。
    const hints = new Map<DecodeHintType, unknown>([
      [DecodeHintType.TRY_HARDER, true],
      [DecodeHintType.POSSIBLE_FORMATS, [
        BarcodeFormat.CODE_128, BarcodeFormat.CODE_39, BarcodeFormat.CODE_93,
        BarcodeFormat.CODABAR, BarcodeFormat.EAN_8, BarcodeFormat.EAN_13,
        BarcodeFormat.UPC_A, BarcodeFormat.UPC_E, BarcodeFormat.ITF,
      ]],
    ])
    barcodeReader = new BrowserMultiFormatReader(hints, { delayBetweenScanAttempts: 120, delayBetweenScanSuccess: 1000 })
    scannerControls = await barcodeReader.decodeFromConstraints({ video: {
      facingMode: { ideal: 'environment' }, width: { ideal: 1280, min: 640 }, height: { ideal: 720, min: 480 },
      focusMode: { ideal: 'continuous' }, aspectRatio: { ideal: 1.777 },
    }, audio: false }, video.value!, (result) => {
      const text = result?.getText()
      if (text) addScan(text)
    })
  } catch { cameraError.value = '无法访问摄像头，请检查 HTTPS 和浏览器权限' }
}
function stopCamera() {
  scanning.value = false
  window.clearTimeout(scanTimer)
  try { scannerControls?.stop() } catch { /* camera may already be closed */ }
  scannerControls = null
  try { barcodeReader?.reset() } catch { /* reader may already be reset */ }
  barcodeReader = null
  try { stream?.getTracks().forEach((track) => track.stop()) } catch { /* ignore stale stream */ }
  stream = null
}
function isValidImei(value: string) {
  if (!/^\d{15}$/.test(value)) return false
  let total = 0
  for (let index = 0; index < value.length; index += 1) {
    let digit = Number(value[index])
    if (index % 2 === 1) { digit *= 2; if (digit > 9) digit -= 9 }
    total += digit
  }
  return total % 10 === 0
}
function imeiCheckDigit(base: string) {
  let total = 0
  for (let index = 0; index < base.length; index += 1) {
    let digit = Number(base[index])
    if (index % 2 === 1) { digit *= 2; if (digit > 9) digit -= 9 }
    total += digit
  }
  return String((10 - (total % 10)) % 10)
}
function normalizeScanValue(value: string) {
  const clean = value.trim()
  if (scanMode() !== 'imei') return clean
  if (isValidImei(clean)) return clean
  // 二维码常把 IMEI 包在 "IMEI:..."、URL 或 JSON 文本中，不能直接
  // 对整个文本去除非数字，否则会把订单号/时间戳等其他数字混进来。
  const candidates = clean.match(/\d{14,16}/g) || []
  for (const digits of candidates) {
    if (digits.length === 14) return digits + imeiCheckDigit(digits)
    if (digits.length === 15 && isValidImei(digits)) return digits
    if (digits.length === 16) {
      const candidate = digits.slice(0, 14) + imeiCheckDigit(digits.slice(0, 14))
      if (isValidImei(candidate)) return candidate
    }
  }
  return clean
}
function addScan(value: string) {
  const clean = normalizeScanValue(value)
  if (!clean || scanItems.value.some((item) => item.value === clean)) return
  if (capturingContainer.value && activeTask.value && ['tray', 'box'].includes(activeTask.value.action)) {
    containerCode.value = clean
    capturingContainer.value = false
    cameraError.value = `已读取目标${activeTask.value.action === 'tray' ? '托盘' : '箱子'}：${clean}，请继续扫描${activeTask.value.action === 'tray' ? '手机 IMEI' : '托盘编码'}`
    navigator.vibrate?.(35)
    stopCamera()
    nextTick(() => { if (phaseRequiresScan()) startCamera() })
    return
  }
  if (scanMode() === 'imei' && !isValidImei(clean)) {
    cameraError.value = '未识别到有效 IMEI（应为 15 位数字），请将条码完整对准取景框或手工输入'
    navigator.vibrate?.([35, 45, 35])
    return
  }
  scanItems.value.unshift({ value: clean, time: new Date().toLocaleTimeString(), result: '待提交' })
  cameraError.value = '读取成功，可继续扫描下一台'
  navigator.vibrate?.(35)
}
function addManual() { addScan(manualValue.value); manualValue.value = '' }
function containerCodeChanged() {
  if (containerCode.value.trim() && activeTask.value && ['tray', 'box'].includes(activeTask.value.action)) {
    capturingContainer.value = false
    cameraError.value = `目标${activeTask.value.action === 'tray' ? '托盘' : '箱子'}已填写，请继续扫描${activeTask.value.action === 'tray' ? '手机 IMEI' : '托盘编码'}`
    stopCamera()
  }
}
function recaptureContainer() {
  if (!activeTask.value || !['tray', 'box'].includes(activeTask.value.action)) return
  containerCode.value = ''
  capturingContainer.value = true
  scanItems.value = []
  cameraError.value = `请先扫描目标${activeTask.value.action === 'tray' ? '托盘' : '箱子'}编码`
  nextTick(() => { if (!scannerControls) startCamera() })
}
function removeScan(value: string) { scanItems.value = scanItems.value.filter((item) => item.value !== value) }
function numeric(value: string) { const parsed = Number(value); return Number.isInteger(parsed) && parsed > 0 ? parsed : null }
function containers() { return scanItems.value.map((item) => ({ kind: containerKind.value, code: item.value })) }
function idsForDestination() { const org = numeric(destinationOrganizationId.value); const location = numeric(destinationLocationId.value); if (!org || !location) throw new Error('请填写目标组织编号和地点编号'); return { org, location } }
async function submitScans() {
  if (!activeTask.value || (phaseRequiresScan() && !scanItems.value.length)) return
  const task = activeTask.value
  error.value = ''; operationMessage.value = ''; submitting.value = true
  try {
    if (task.action === 'query') {
      const result = await getPhone(scanItems.value[0].value)
      operationMessage.value = `当前位置：${result.box_code || '无箱'} / ${result.tray_code || '无托盘'} · 状态：${result.status || '未知'} · 已记录 ${(result.timeline as unknown[] | undefined)?.length || 0} 条流水`
      scanItems.value[0].result = '成功'
      return
    }
    const org = numeric(organizationId.value); const location = numeric(locationId.value)
    const requireCurrentIds = () => { if (!org || !location) throw new Error('请填写当前组织编号和地点编号'); return { org, location } }
    if (task.action === 'purchase') {
      requireCurrentIds()
      const result = await createPurchaseReceipt({ organization_id: org, location_id: location, items: scanItems.value.map((item) => ({ imei: item.value })) })
      operationMessage.value = `入库成功：${result.order_no} · ${result.total_count} 台`
    } else if (task.action === 'tray') {
      requireCurrentIds()
      if (!containerCode.value.trim()) throw new Error('请填写托盘编号')
      const result = await createTray({ code: containerCode.value.trim(), location_id: location, imeis: scanItems.value.map((item) => item.value) })
      operationMessage.value = `托盘 ${result.code} 已更新 · ${result.phone_count} 台`
    } else if (task.action === 'box') {
      requireCurrentIds()
      if (!containerCode.value.trim()) throw new Error('请填写箱子编号')
      const result = await createBox({ code: containerCode.value.trim(), location_id: location, tray_codes: scanItems.value.map((item) => item.value) })
      operationMessage.value = `箱子 ${result.code} 已更新 · ${result.tray_count} 个托盘 / ${result.phone_count} 台`
    } else if (task.action === 'shipment') {
      requireCurrentIds()
      const destination = idsForDestination()
      const result = await dispatchShipment({ origin_organization_id: org, origin_location_id: location, destination_organization_id: destination.org, destination_location_id: destination.location, logistics_no: logisticsNo.value || null, containers: containers() })
      operationMessage.value = `发运单 ${result.shipment_no} 已创建 · ${result.total_count} 台`
    } else if (task.action === 'receiving') {
      if (!documentNo.value.trim()) throw new Error('请填写发运单号或接收单号')
      if (operationPhase.value === 'start') {
        requireCurrentIds()
        const result = await startReceiving({ shipment_no: documentNo.value.trim(), organization_id: org, location_id: location })
        workflowDocuments.value[`ghana:receiving`] = result.receiving_no
        documentNo.value = result.receiving_no
        operationMessage.value = `接收单 ${result.receiving_no} 已建立 · 待验收 ${result.expected_count} 台`
      } else {
        let result: any = null
        for (const item of scanItems.value) { beginOperation(); result = await inspectReceiving({ receiving_no: documentNo.value.trim(), imei: item.value, accepted: accepted.value, note: null, target_tray_code: targetTrayCode.value.trim() || null, target_box_code: targetBoxCode.value.trim() || null }); endOperation() }
        operationMessage.value = `验收已记录 · 正常 ${result.accepted_count} / 异常 ${result.exception_count}`
      }
    } else if (task.action === 'transfer') {
      if (operationPhase.value === 'issue') {
        requireCurrentIds()
        const destination = idsForDestination()
        const result = await issueTransfer({ source_organization_id: org, source_location_id: location, destination_organization_id: destination.org, destination_location_id: destination.location, containers: containers() })
        operationMessage.value = `调拨单 ${result.transfer_no} 已发出 · ${result.total_count} 台`
      } else {
        if (!documentNo.value.trim()) throw new Error('请填写调拨单号')
        const result = await receiveTransfer({ transfer_no: documentNo.value.trim(), received_imeis: scanItems.value.map((item) => item.value), complete: true })
        operationMessage.value = `收货已登记 · 实收 ${result.received_count} / ${result.total_count} 台`
      }
    } else if (task.action === 'sales') {
      if (operationPhase.value === 'create') {
        requireCurrentIds()
        const prices: Record<string, string> = {}; if (salePrices.value.trim()) scanItems.value.forEach((item, index) => { prices[item.value] = salePrices.value.split(',')[index]?.trim() || salePrices.value.trim() })
        const result = await createSale({ organization_id: org, location_id: location, sales_type: salesType.value, customer_name: customerName.value || null, containers: containers(), prices })
        operationMessage.value = `销售单 ${result.sales_no} 已创建，等待主管确认`
      } else {
        if (!documentNo.value.trim()) throw new Error('请填写销售单号')
        const result = await confirmSale(documentNo.value.trim()); operationMessage.value = `销售单 ${result.sales_no} 已确认`
      }
    } else if (task.action === 'return') {
      if (operationPhase.value === 'create') {
        requireCurrentIds()
        const destination = idsForDestination(); if (!documentNo.value.trim()) throw new Error('请填写原销售单号')
        const values = scanItems.value.map((item) => item.value)
        const asPhones = containerKind.value === 'PHONE'
        const result = await createReturn({ sales_no: documentNo.value.trim(), source_organization_id: org, source_location_id: location, destination_organization_id: destination.org, destination_location_id: destination.location, imeis: asPhones ? values : [], containers: asPhones ? [] : containers(), note: null })
        operationMessage.value = `退回单 ${result.return_no} 已创建 · ${result.total_count} 台`
      } else {
        if (!documentNo.value.trim()) throw new Error('请填写退回单号')
        const result = await receiveReturn({ return_no: documentNo.value.trim(), received_imeis: scanItems.value.map((item) => item.value) }); workflowDocuments.value[`ghana:return`] = documentNo.value.trim(); operationMessage.value = `退回已接收 · ${result.received_count} / ${result.total_count} 台`
      }
    } else if (task.action === 'repair') {
      if (operationPhase.value === 'create') {
        requireCurrentIds()
        const values = scanItems.value.map((item) => item.value)
        const asPhones = containerKind.value === 'PHONE'
        const result = await createRepair({ organization_id: org, location_id: location, imeis: asPhones ? values : [], containers: asPhones ? [] : containers(), return_no: documentNo.value.trim() || null, note: null }); operationMessage.value = `维修单 ${result.repair_no} 已建立`
      } else if (operationPhase.value === 'accept') {
        if (!documentNo.value.trim()) throw new Error('请填写维修单号'); const result = await acceptRepair(documentNo.value.trim()); operationMessage.value = `维修单 ${result.repair_no} 已接收`
      } else if (operationPhase.value === 'complete') {
        if (!documentNo.value.trim()) throw new Error('请填写维修单号'); let result: any = null; for (const item of scanItems.value) { beginOperation(); result = await completeRepair(documentNo.value.trim(), { imei: item.value, repair_result: repairResult.value }); endOperation() } operationMessage.value = `维修结果已提交 · ${result.completed_count} 台完成`
      } else {
        if (!documentNo.value.trim()) throw new Error('请填写维修单号'); let result: any = null; for (const item of scanItems.value) { beginOperation(); result = await reviewRepair(documentNo.value.trim(), { imei: item.value, disposition: disposition.value }); endOperation() } operationMessage.value = `维修复核已完成 · ${result.accepted_count} 台`
      }
    } else if (task.action === 'stocktake') {
      if (operationPhase.value === 'adjust') {
        if (!documentNo.value.trim()) throw new Error('请填写盘点单号')
        const result = await adjustStocktake(documentNo.value.trim(), scanItems.value.map((item) => ({ imei: item.value, decision: adjustmentDecision.value, target_status: adjustmentTargetStatus.value, note: null })))
        operationMessage.value = `盘点差异处理完成：${result.adjustment_status}`
      } else {
        requireCurrentIds()
        const result = await submitStocktake({ organization_id: org, location_id: location, imeis: scanItems.value.map((item) => item.value), note: null })
        operationMessage.value = `盘点单 ${result.stocktake_no}：应有 ${result.expected_count}，实扫 ${result.found_count}，缺失 ${result.missing_count}，多出 ${result.extra_count}`
      }
    } else throw new Error('该任务尚未配置业务提交字段')
    scanItems.value = scanItems.value.map((item) => ({ ...item, result: '成功' }))
    endOperation()
  } catch (err) {
    if (!online.value || err instanceof TypeError) {
      const id = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`
      drafts.value.push({ id, idempotency_key: localStorage.getItem('gh-phone-operation-key') || id, action: task.action, phase: operationPhase.value, workflow: activeWorkflow.value, values: scanItems.value.map((item) => item.value), organization_id: organizationId.value, location_id: locationId.value, destination_organization_id: destinationOrganizationId.value, destination_location_id: destinationLocationId.value, container_code: containerCode.value, target_tray_code: targetTrayCode.value, target_box_code: targetBoxCode.value, container_kind: containerKind.value, logistics_no: logisticsNo.value, document_no: documentNo.value, accepted: accepted.value, sales_type: salesType.value, customer_name: customerName.value, prices: salePrices.value ? Object.fromEntries(scanItems.value.map((item, index) => [item.value, salePrices.value.split(',')[index]?.trim() || salePrices.value.trim()])) : {}, repair_result: repairResult.value, disposition: disposition.value, adjustment_decision: adjustmentDecision.value, adjustment_target_status: adjustmentTargetStatus.value, created_at: new Date().toISOString(), status: 'pending' }); saveDrafts()
      operationMessage.value = '网络不可用，已保存为待同步草稿；联网后请在单据中心复核提交'
      scanItems.value = scanItems.value.map((item) => ({ ...item, result: '待提交' })); error.value = ''
    } else error.value = err instanceof Error ? err.message : '提交失败'
  }
  finally { submitting.value = false }
}
async function installPwa() {
  if (!installPrompt.value) return
  installPrompt.value.prompt(); await installPrompt.value.userChoice; installPrompt.value = null
}

onMounted(async () => {
  window.addEventListener('online', setOnline); window.addEventListener('offline', setOnline)
  window.addEventListener('popstate', closeTask)
  document.addEventListener('click', closeProfileMenu)
  window.addEventListener('beforeinstallprompt', (event) => { event.preventDefault(); installPrompt.value = event })
  refreshPendingCount()
  if (localStorage.getItem('gh-phone-access-token')) {
    try { user.value = await getCurrentUser(); await loadWorkLocations() } catch { logout() }
  }
})
function closeProfileMenu(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (!target.closest('.profile-wrap')) showProfileMenu.value = false
}
onUnmounted(() => { stopCamera(); window.removeEventListener('online', setOnline); window.removeEventListener('offline', setOnline); window.removeEventListener('popstate', closeTask); document.removeEventListener('click', closeProfileMenu) })
</script>

<template>
  <main v-if="!user" class="auth-shell">
    <section class="auth-card">
      <p class="eyebrow">GHANA PHONE MANAGEMENT</p><h1>手机流转管理</h1>
      <p class="auth-subtitle">扫码完成收发货、销售和库存核查</p>
      <div class="login-tabs"><button :class="{ active: loginMode === 'password' }" @click="loginMode = 'password'">密码登录</button><button :class="{ active: loginMode === 'sms' }" @click="loginMode = 'sms'">验证码登录</button></div>
      <label>手机号或用户名<input v-model="phone" autocomplete="username" placeholder="请输入手机号或用户名" /></label>
      <label v-if="loginMode === 'password'">密码<input v-model="password" type="password" autocomplete="current-password" placeholder="请输入密码" @keyup.enter="submitLogin" /></label>
      <label v-else>验证码<div class="code-row"><input v-model="code" inputmode="numeric" placeholder="请输入验证码" /><button class="text-button" @click="requestCode">{{ smsSent ? '重新发送' : '获取验证码' }}</button></div></label>
      <p v-if="loginMode === 'sms' && !smsSent" class="hint">短信服务待接入</p><p v-if="error" class="error">{{ error }}</p>
      <button class="primary wide" :disabled="loading" @click="submitLogin">{{ loading ? '登录中…' : '登录' }}</button>
    </section>
  </main>

  <main v-else class="shell">
    <header class="topbar"><div><p class="eyebrow">GHANA PHONE MANAGEMENT</p><h1>今天要处理什么？</h1><small v-if="roleLabel" class="role-chip">当前岗位：{{ roleLabel }}</small></div><div class="profile-wrap"><button class="profile" aria-label="打开用户菜单" :aria-expanded="showProfileMenu" @click.stop="showProfileMenu = !showProfileMenu">{{ user.display_name.slice(0, 1) }}</button><div v-if="showProfileMenu" class="profile-menu"><div class="profile-menu-card"><span class="muted">当前账号</span><strong>{{ user.display_name }}</strong><small>{{ user.username || user.phone }}</small><small v-if="roleLabel">岗位：{{ roleLabel }}</small><span :class="['online', { offline: !online }]"><i />{{ online ? '在线' : '离线' }}</span></div><button @click="openProfileEditor">个人资料与修改密码</button><button class="logout-menu" @click="logout">退出登录</button></div></div></header>
    <button v-if="pendingCount" class="pending-note pending-button" @click="showDrafts = true">{{ pendingCount }} 条待同步草稿 · 打开单据中心</button>
    <button v-if="installPrompt" class="install-banner" @click="installPwa">＋ 添加到手机桌面</button>
    <p v-if="currentView === 'work' && hasWorkflowEntry" class="workflow-home-note">当前岗位已合并为连续作业入口：进入一张卡片后按现场顺序完成每个步骤，系统仍会为每一步保留独立单据和审计记录。</p>
    <section v-if="currentView === 'work'" class="action-grid"><button v-for="task in visibleTasks" :key="task.title" class="action-card" @click="openTask(task)"><span class="action-main"><component :is="task.icon" class="action-icon" :size="22" :stroke-width="1.8" /><span class="action-title">{{ task.title }}</span></span><span class="muted action-hint">{{ task.hint }}</span></button></section>
    <section v-if="currentView === 'inventory'" class="data-section"><div class="section-title"><h2>当前库存</h2><button class="text-button" @click="switchView('inventory')">刷新</button></div><p v-if="viewLoading" class="empty-note">加载中…</p><div v-for="item in inventoryItems" :key="String(item.imei)" class="data-row"><div><strong>{{ item.imei }}</strong><small>{{ item.brand || '' }} {{ item.model || '' }}</small></div><span class="status-text">{{ item.status }}</span></div><p v-if="!viewLoading && !inventoryItems.length" class="empty-note">暂无可见库存</p></section>
    <section v-if="currentView === 'documents'" class="data-section"><div class="section-title"><h2>业务单据</h2><button class="text-button" @click="switchView('documents')">刷新</button></div><p v-if="viewLoading" class="empty-note">加载中…</p><div v-for="item in documentItems" :key="`${item.type}-${item.no}`" class="data-row"><div><strong>{{ item.no }}</strong><small>{{ documentTypeLabel(item.type) }} · {{ item.total_count }} 台</small></div><span class="status-text">{{ item.status }}</span></div><p v-if="!viewLoading && !documentItems.length" class="empty-note">暂无可见单据</p></section>
    <section v-if="currentView === 'admin'" class="data-section"><div class="section-title"><h2>权限与组织</h2><button class="text-button" @click="switchView('admin')">刷新</button></div><p v-if="viewLoading" class="empty-note">加载中…</p><div class="admin-summary"><strong>{{ adminData.users.length }} 个用户</strong><strong>{{ adminData.roles.length }} 个角色</strong><strong>{{ adminData.organizations.length }} 个组织</strong><strong>{{ adminData.locations.length }} 个地点</strong></div><div class="admin-tabs"><button v-if="hasPermission(user, 'user:manage')" :class="{ active: adminTab === 'users' }" @click="adminTab = 'users'">用户</button><button v-if="hasPermission(user, 'user:manage')" :class="{ active: adminTab === 'organizations' }" @click="adminTab = 'organizations'">组织</button><button v-if="hasPermission(user, 'user:manage')" :class="{ active: adminTab === 'locations' }" @click="adminTab = 'locations'">地点</button><button v-if="hasPermission(user, 'role:manage')" :class="{ active: adminTab === 'roles' }" @click="adminTab = 'roles'">角色</button></div><div v-if="adminTab === 'users' && hasPermission(user, 'user:manage')" class="admin-panel"><div class="admin-form"><input v-model="newUserPhone" inputmode="tel" placeholder="手机号或英文用户名" /><input v-model="newUserName" placeholder="姓名" /><input v-model="newUserPassword" type="password" placeholder="初始密码" /><select v-model="newUserRoleIds" multiple><option v-for="role in adminData.roles" :key="String(role.id)" :value="Number(role.id)">{{ roleNameLabel(role.id) }}</option></select><textarea v-model="newUserScopes" placeholder='数据范围 JSON，例如 [{"permission_code":"phone:view","scope_kind":"location","scope_value":"20"}]'></textarea><button class="secondary" @click="createAdminRecord('user')">创建用户</button></div><p class="hint">系统遵循“无范围即拒绝”；角色只赋予功能权限，地点/组织范围仍需单独配置。</p><div v-for="item in adminData.users" :key="String(item.id)" class="data-row"><div><strong>{{ item.display_name }}</strong><small>{{ item.phone }} · 角色 {{ roleIdsLabel(item) }}</small></div><div class="row-actions"><span class="status-text">{{ item.is_active ? '启用' : '停用' }}</span><button class="text-button" @click="beginEditUser(item)">权限</button><button class="text-button" @click="toggleUser(item)">{{ item.is_active ? '停用' : '启用' }}</button></div></div><div v-if="editingUserId !== null" class="admin-edit"><strong>编辑用户权限 #{{ editingUserId }}</strong><select v-model="editingUserRoleIds" multiple><option v-for="role in adminData.roles" :key="String(role.id)" :value="Number(role.id)">{{ roleNameLabel(role.id) }}</option></select><textarea v-model="editingUserScopes" placeholder="数据范围 JSON 数组"></textarea><div class="row-actions"><button class="secondary" @click="saveUserEdit">保存权限</button><button class="text-button" @click="cancelEditUser">取消</button></div></div></div><div v-if="adminTab === 'organizations' && hasPermission(user, 'user:manage')" class="admin-panel"><div class="admin-form"><input v-model="orgCode" placeholder="组织代码" /><input v-model="orgName" placeholder="组织名称" /><input v-model="orgCountry" placeholder="国家代码" /><button class="secondary" @click="createAdminRecord('organization')">创建组织</button></div><div v-for="item in adminData.organizations" :key="String(item.id)" class="data-row"><div><strong>{{ item.name }}</strong><small>{{ item.id }} · {{ item.code }} · {{ item.country }}</small></div><span class="status-text">{{ item.is_active ? '启用' : '停用' }}</span></div></div><div v-if="adminTab === 'locations' && hasPermission(user, 'user:manage')" class="admin-panel"><div class="admin-form"><input v-model="locOrganizationId" inputmode="numeric" placeholder="所属组织 ID" /><input v-model="locCode" placeholder="地点代码" /><input v-model="locName" placeholder="地点名称" /><select v-model="locType"><option value="store">门店</option><option value="warehouse">仓库</option><option value="repair">维修区</option><option value="receiving">接收区</option></select><button class="secondary" @click="createAdminRecord('location')">创建地点</button></div><div v-for="item in adminData.locations" :key="String(item.id)" class="data-row"><div><strong>{{ item.name }}</strong><small>{{ item.id }} · 组织 {{ item.organization_id }} · {{ item.code }}</small></div><span class="status-text">{{ item.location_type }}</span></div></div><div v-if="adminTab === 'roles' && hasPermission(user, 'role:manage')" class="admin-panel"><div class="admin-form"><input v-model="roleCode" placeholder="角色代码" /><input v-model="roleName" placeholder="角色名称" /><input v-model="roleWorkGroup" placeholder="工作组（如 GHANA_OPERATIONS）" /><input v-model="roleDescription" placeholder="岗位职责说明（可选）" /><div class="permission-grid"><label v-for="permission in adminData.permissions" :key="String(permission.code)"><input v-model="selectedRolePermissions" type="checkbox" :value="String(permission.code)" />{{ permissionLabel(permission.code) }}</label></div><button class="secondary" @click="createAdminRecord('role')">创建角色</button></div></div></section>
    <section v-if="currentView === 'admin' && adminTab === 'roles' && hasPermission(user, 'role:manage')" class="admin-actions"><p class="hint">当前列表只显示启用角色；历史拆分角色保留在数据库中但不可重新分配。</p><div v-for="item in adminData.roles" :key="`role-action-${item.id}`" class="data-row"><div><strong>{{ item.name }}</strong><small>{{ item.code }} · {{ item.work_group || '未分组' }} · {{ Array.isArray(item.permission_codes) ? item.permission_codes.length : 0 }} 项权限</small><small v-if="item.description">{{ item.description }}</small></div><span class="status-text">{{ item.is_active ? '启用' : '停用' }}</span></div></section>
    <section v-if="currentView === 'admin' && adminTab === 'organizations' && hasPermission(user, 'user:manage')" class="admin-actions"><p class="hint">停用不会删除历史单据，只会阻止后续业务使用该组织。</p><div v-for="item in adminData.organizations" :key="`org-action-${item.id}`" class="data-row"><strong>{{ item.name }}</strong><button class="text-button" @click="toggleAdminResource('organization', item)">{{ item.is_active ? '停用' : '启用' }}</button></div></section>
    <section v-if="currentView === 'admin' && adminTab === 'locations' && hasPermission(user, 'user:manage')" class="admin-actions"><p class="hint">停用不会删除历史单据，只会阻止后续业务使用该地点。</p><div v-for="item in adminData.locations" :key="`location-action-${item.id}`" class="data-row"><strong>{{ item.name }}</strong><button class="text-button" @click="toggleAdminResource('location', item)">{{ item.is_active ? '停用' : '启用' }}</button></div></section>
    <button v-if="currentView === 'admin' && hasPermission(user, 'audit:view')" class="secondary audit-switch" @click="adminTab = 'audits'">查看操作审计</button>
    <section v-if="currentView === 'admin' && adminTab === 'audits'" class="data-section"><div class="section-title"><h2>操作审计</h2><button class="text-button" @click="switchView('admin')">刷新</button></div><p class="hint">只读记录：包含后台操作人、资源、时间和提交摘要。</p><div v-for="item in adminData.audits" :key="String(item.id)" class="data-row audit-row"><div><strong>{{ item.action }} · {{ item.resource_type }} #{{ item.resource_id }}</strong><small>用户 {{ item.user_id || '系统' }} · {{ item.created_at }}</small></div><span class="muted">{{ item.payload ? '有参数' : '无参数' }}</span></div><p v-if="!adminData.audits.length" class="empty-note">暂无可见审计记录</p></section>
    <section v-if="currentView === 'work' && !visibleTasks.length" class="work-section"><p class="empty-note">当前账号没有现场操作权限</p></section>
    <nav class="bottom-nav"><div class="bottom-nav-pill"><button :class="{ active: currentView === 'work' }" @click="switchView('work')"><House :size="17" />工作台</button><button :class="{ active: currentView === 'inventory' }" @click="switchView('inventory')"><Warehouse :size="17" />库存</button><button :class="{ active: currentView === 'documents' }" @click="switchView('documents')"><FileText :size="17" />单据</button><button v-if="hasPermission(user, 'user:manage') || hasPermission(user, 'role:manage')" :class="{ active: currentView === 'admin' }" @click="switchView('admin')"><Settings :size="17" />管理</button></div></nav>

    <div v-if="showProfileEditor" class="modal-backdrop" @click.self="showProfileEditor = false"><section class="scan-modal profile-modal"><header class="modal-header"><div><p class="eyebrow">个人中心</p><h2>个人资料与安全</h2></div><button class="close" @click="showProfileEditor = false">×</button></header><label>显示名称<input v-model="profileDisplayName" maxlength="128" /></label><label>用户名<input v-model="profileUsername" maxlength="64" placeholder="可选，用于登录" /></label><div class="profile-divider">修改密码（不修改可留空）</div><label>当前密码<input v-model="currentPassword" type="password" autocomplete="current-password" /></label><label>新密码<input v-model="newPassword" type="password" autocomplete="new-password" /></label><label>确认新密码<input v-model="confirmNewPassword" type="password" autocomplete="new-password" @keyup.enter="saveProfile" /></label><p v-if="error" class="error">{{ error }}</p><button class="primary wide" :disabled="profileSaving" @click="saveProfile">{{ profileSaving ? '保存中…' : '保存修改' }}</button></section></div>

    <div v-if="showDrafts" class="modal-backdrop" @click.self="showDrafts = false"><section class="scan-modal draft-modal">
      <header class="modal-header"><div><p class="eyebrow">单据中心</p><h2>待同步草稿</h2></div><button class="close" @click="showDrafts = false">×</button></header>
      <div class="draft-actions"><button class="secondary" :disabled="!online || !pendingCount" @click="retryAllDrafts">联网重试全部</button><span class="muted">冲突草稿不会自动删除</span></div>
      <div v-for="draft in drafts" :key="draft.id" class="draft-item"><div><strong>{{ draft.action }} · {{ draft.values.length }} 项</strong><small>{{ draft.created_at }} · {{ draft.status }}<template v-if="draft.error"> · {{ draft.error }}</template></small></div><div class="draft-buttons"><button v-if="draft.status !== 'synced'" class="secondary" :disabled="!online || draft.status === 'syncing'" @click="retryDraft(draft)">重试</button><button class="text-button" @click="removeDraft(draft.id)">删除</button></div></div>
      <p v-if="!drafts.length" class="empty-note">暂无草稿</p>
    </section></div>
    <div v-if="activeTask" class="modal-backdrop" @click.self="closeTask"><section class="scan-modal">
      <header class="modal-header"><div><p class="eyebrow">{{ activeWorkflow ? (activeWorkflow === 'shenzhen' ? '深圳收购仓作业' : '加纳综合仓作业') : activeTask.title }}</p><h2>{{ activeTask.action === 'query' ? '查询 IMEI' : (currentWorkflowStep?.label || '连续扫描') }}</h2></div><button class="close" @click="closeTask">×</button></header>
      <section v-if="activeWorkflow" class="workflow-strip" aria-label="岗位作业步骤">
        <p class="workflow-guide">同一岗位按现场顺序完成，已完成后可切换下一步；每一步仍保留独立的提交记录。</p>
        <div class="workflow-steps">
          <button v-for="(step, index) in workflowSteps" :key="step.key" :class="['workflow-step', { active: currentWorkflowStep?.key === step.key }]" @click="selectWorkflowStep(step)">
            <span>{{ index + 1 }}</span><strong>{{ step.label }}</strong><small>{{ step.hint }}</small>
          </button>
        </div>
        <p v-if="repairTechHandoffPending() && operationMessage" class="workflow-wait">维修单已建立，等待维修技师接单并提交结果；完成后再进入“维修 QA”。</p>
        <button v-if="nextWorkflowStep && operationMessage && !repairTechHandoffPending()" class="workflow-next" @click="advanceWorkflow">下一步：{{ nextWorkflowStep.label }} →</button>
      </section>
      <div v-if="phaseRequiresScan()" class="camera-box"><video ref="video" muted playsinline /><span v-if="scanning" class="scan-line" /><p class="camera-message">{{ cameraError || '将条码放入框内' }}</p></div>
      <div v-if="activeTask.action !== 'query'" class="task-fields">
        <template v-if="phaseRequiresCurrentLocation()"><select v-model="locationId" @change="syncOrganizationFromLocation"><option value="">选择当前地点</option><option v-for="item in sourceLocationsForTask" :key="String(item.id)" :value="String(item.id)">{{ locationLabel(item) }}</option></select>
        <input v-model="organizationId" inputmode="numeric" placeholder="当前组织编号（自动）" readonly /></template>
        <div v-if="['tray', 'box'].includes(activeTask.action)" class="container-capture">
          <input v-model="containerCode" :placeholder="capturingContainer ? `请先扫描目标${activeTask.action === 'tray' ? '托盘' : '箱子'}编码` : `目标${activeTask.action === 'tray' ? '托盘' : '箱子'}编号`" @change="containerCodeChanged" @keyup.enter="containerCodeChanged" />
          <button class="text-button" type="button" @click="recaptureContainer">重扫</button>
        </div>
        <template v-if="['shipment', 'transfer', 'sales'].includes(activeTask.action)">
          <select v-model="containerKind"><option value="PHONE">手机 IMEI</option><option value="TRAY">托盘编号</option><option value="BOX">箱子编号</option></select>
        </template>
        <template v-if="['return', 'repair'].includes(activeTask.action) && operationPhase === 'create'">
          <select v-model="containerKind"><option value="PHONE">手机 IMEI</option><option value="TRAY">托盘编号</option><option value="BOX">箱子编号</option></select>
        </template>
        <template v-if="activeTask.action === 'shipment' || (activeTask.action === 'transfer' && operationPhase === 'issue') || (activeTask.action === 'return' && operationPhase === 'create')">
          <select v-model="destinationLocationId" @change="syncDestinationOrganization"><option value="">选择目标地点</option><option v-for="item in destinationLocations" :key="`destination-${item.id}`" :value="String(item.id)">{{ locationLabel(item) }}</option></select>
          <input v-model="destinationOrganizationId" inputmode="numeric" placeholder="目标组织编号（自动）" readonly />
        </template>
        <select v-if="!activeWorkflow && activeTask.action === 'receiving'" v-model="operationPhase"><option v-if="hasPermission(user, 'receiving:unpack')" value="start">建立接收单</option><option v-if="hasPermission(user, 'receiving:accept')" value="inspect">逐台验收</option></select>
        <select v-if="!activeWorkflow && activeTask.action === 'transfer'" v-model="operationPhase"><option v-if="hasPermission(user, 'transfer:create')" value="issue">发起出库/串货</option><option v-if="hasPermission(user, 'transfer:receive')" value="receive">门店收货</option></select>
        <select v-if="!activeWorkflow && activeTask.action === 'sales'" v-model="operationPhase"><option v-if="hasPermission(user, 'sales:create')" value="create">制销售单</option><option v-if="hasPermission(user, 'sales:approve')" value="confirm">主管确认</option></select>
        <select v-if="!activeWorkflow && activeTask.action === 'return'" v-model="operationPhase"><option v-if="hasPermission(user, 'return:create')" value="create">发起退回</option><option v-if="hasPermission(user, 'return:receive')" value="receive">管理处接收</option></select>
        <select v-if="!activeWorkflow && activeTask.action === 'repair'" v-model="operationPhase"><option v-if="hasPermission(user, 'repair:create')" value="create">建立送修单</option><option v-if="hasPermission(user, 'repair:receive')" value="accept">维修人员接收</option><option v-if="hasPermission(user, 'repair:update')" value="complete">填写维修结果</option><option v-if="hasPermission(user, 'repair:approve')" value="review">管理处复核</option></select>
        <select v-if="!activeWorkflow && activeTask.action === 'stocktake'" v-model="operationPhase"><option v-if="hasPermission(user, 'stocktake:submit')" value="create">提交现场盘点</option><option v-if="hasPermission(user, 'stocktake:adjust')" value="adjust">审核盘点差异</option></select>
        <input v-if="activeTask.action === 'shipment'" v-model="logisticsNo" placeholder="物流单号（可选）" />
        <input v-if="['receiving', 'transfer', 'sales', 'return', 'repair', 'stocktake'].includes(activeTask.action)" v-model="documentNo" :placeholder="activeTask.action === 'repair' && operationPhase === 'create' && activeWorkflow === 'ghana' ? '已接收退回单号（用于分诊，可选）' : activeTask.action === 'receiving' && operationPhase === 'start' ? '深圳发运单号' : '业务单号（收货/审核/维修/盘点时填写）'" />
        <p v-if="activeTask.action === 'repair' && operationPhase === 'create' && activeWorkflow === 'ghana' && documentNo" class="hint">已接收退回单将从管理处转入维修区；请逐台扫描 IMEI，原退回箱/托盘不要直接搬入。</p>
        <select v-if="activeTask.action === 'receiving'" v-model="accepted"><option :value="true">验收正常</option><option :value="false">异常/待核查</option></select>
        <template v-if="activeTask.action === 'receiving' && operationPhase === 'inspect' && accepted"><input v-model="targetTrayCode" placeholder="重新装入托盘编号（可选）" /><input v-model="targetBoxCode" placeholder="重新装入箱子编号（需填托盘）" /></template>
        <template v-if="activeTask.action === 'sales'">
          <select v-model="salesType"><option value="RETAIL">零售</option><option value="WHOLESALE">批发</option></select><input v-model="customerName" placeholder="客户名称（可选）" /><input v-model="salePrices" placeholder="价格：逐台逗号分隔（可选）" />
        </template>
        <select v-if="activeTask.action === 'repair' && hasPermission(user, 'repair:update')" v-model="repairResult"><option value="REPAIRED">已修复</option><option value="NO_REPAIR">无需维修</option><option value="UNREPAIRABLE">不可维修</option></select>
        <select v-if="activeTask.action === 'repair' && hasPermission(user, 'repair:approve')" v-model="disposition"><option value="AVAILABLE_AGAIN">恢复可售</option><option value="FROZEN">冻结待核查</option><option value="SCRAPPED">报损</option></select>
        <template v-if="activeTask.action === 'stocktake' && operationPhase === 'adjust'"><select v-model="adjustmentDecision"><option value="IGNORE">忽略差异</option><option value="CONFIRM_MISSING">确认缺失</option><option value="ACCEPT_EXTRA">接收多出</option></select><select v-if="adjustmentDecision === 'ACCEPT_EXTRA'" v-model="adjustmentTargetStatus"><option value="加纳管理处库存">加纳管理处库存</option><option value="门店库存">门店库存</option><option value="可再次销售">可再次销售</option></select></template>
      </div>
      <div v-if="phaseRequiresScan()" class="manual-row"><input v-model="manualValue" :placeholder="capturingContainer ? `手工输入目标${activeTask?.action === 'tray' ? '托盘' : '箱子'}编码` : scanMode() === 'imei' ? '手工输入 IMEI' : '输入手机/托盘/箱子编号'" @keyup.enter="addManual" /><button class="secondary" @click="addManual">加入</button></div>
      <div v-if="phaseRequiresScan()" class="scan-summary"><strong>已读取 {{ scanItems.length }} 项</strong><button class="text-button" @click="scanItems = []">清空</button></div>
      <div v-if="phaseRequiresScan()" class="scan-list"><div v-for="item in scanItems" :key="item.value" class="scan-item"><span><strong>{{ item.value }}</strong><small>{{ item.time }} · {{ item.result }}</small></span><button class="remove" @click="removeScan(item.value)">×</button></div><p v-if="!scanItems.length" class="empty-note">暂无扫描结果</p></div>
      <p v-if="operationMessage" class="success">{{ operationMessage }}</p><p v-if="error" class="error">{{ error }}</p>
      <button class="primary wide" :disabled="(phaseRequiresScan() && !scanItems.length) || submitting" @click="submitScans">{{ submitting ? '提交中…' : `确认提交（${scanItems.length}）` }}</button>
    </section></div>
  </main>
</template>
