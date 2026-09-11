<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import * as api from "./api";
import type { CurrentUser } from "./api";

type Task = {
  key: string;
  label: string;
  hint: string;
  permissions: string[];
  mode: "imei" | "container";
  workflow?: WorkflowKey;
};
type WorkflowKey = "shenzhen" | "ghana";
type WorkflowStep = {
  key: string;
  label: string;
  hint: string;
  action: string;
  phase: string;
  permission: string;
};
type Draft = {
  id: string;
  action: string;
  phase: string;
  values: string[];
  organization_id: string;
  location_id: string;
  destination_organization_id: string;
  destination_location_id: string;
  container_kind: string;
  container_code: string;
  document_no: string;
  logistics_no?: string;
  target_tray_code?: string;
  target_box_code?: string;
  sales_type?: "RETAIL" | "WHOLESALE";
  customer_name?: string;
  sale_prices?: string;
  repair_result?: string;
  disposition?: string;
  adjustment_decision?: string;
  adjustment_target_status?: string;
  transfer_receive_complete?: boolean;
  accepted: boolean;
  status: string;
  workflow?: WorkflowKey | null;
  error?: string;
  created_at: string;
};
const tasks: Task[] = [
  {
    key: "purchase",
    label: "采购入库",
    hint: "连续录入手机 IMEI",
    permissions: ["purchase:create"],
    mode: "imei",
  },
  {
    key: "tray",
    label: "装托盘",
    hint: "手机归入指定托盘",
    permissions: ["tray:manage"],
    mode: "imei",
  },
  {
    key: "box",
    label: "装箱",
    hint: "托盘归入指定箱子",
    permissions: ["box:manage"],
    mode: "container",
  },
  {
    key: "shipment",
    label: "发运出库",
    hint: "按手机、托盘或箱子发运",
    permissions: ["shipment:dispatch"],
    mode: "container",
  },
  {
    key: "receiving",
    label: "接收验收",
    hint: "建立接收单并逐台验收",
    permissions: ["receiving:unpack", "receiving:accept"],
    mode: "imei",
  },
  {
    key: "transfer",
    label: "门店调拨",
    hint: "配送、串货和门店收货",
    permissions: ["transfer:create", "transfer:receive"],
    mode: "container",
  },
  {
    key: "sales",
    label: "销售出库",
    hint: "零售或批发销售",
    permissions: ["sales:create", "sales:approve"],
    mode: "container",
  },
  {
    key: "return",
    label: "销售退回",
    hint: "销售退回发起与接收",
    permissions: ["return:create", "return:receive"],
    mode: "container",
  },
  {
    key: "repair",
    label: "维修管理",
    hint: "送修、接收、维修和复核",
    permissions: [
      "repair:create",
      "repair:receive",
      "repair:update",
      "repair:approve",
    ],
    mode: "container",
  },
  {
    key: "stocktake",
    label: "盘点核查",
    hint: "现场盘点与差异处理",
    permissions: ["stocktake:submit", "stocktake:adjust"],
    mode: "imei",
  },
  {
    key: "query",
    label: "IMEI 追踪",
    hint: "输入 IMEI 查看全程轨迹",
    permissions: ["phone:view"],
    mode: "imei",
  },
];
const workflowTasks: Task[] = [
  {
    key: "workflow_shenzhen",
    label: "深圳收购仓作业",
    hint: "收购验收 → 装托盘 → 装箱封存",
    permissions: ["purchase:create", "tray:manage", "box:manage"],
    mode: "imei",
    workflow: "shenzhen",
  },
  {
    key: "workflow_ghana",
    label: "加纳综合仓作业",
    hint: "到货验收 → 拣货调拨 → 退回分诊 → 维修建单/QA",
    permissions: [
      "receiving:unpack",
      "receiving:accept",
      "transfer:create",
      "return:receive",
      "repair:create",
      "repair:approve",
    ],
    mode: "imei",
    workflow: "ghana",
  },
];
const workflowDefinitions: Record<WorkflowKey, WorkflowStep[]> = {
  shenzhen: [
    {
      key: "purchase",
      label: "收购验收",
      hint: "逐台录入 IMEI，生成采购入库单",
      action: "purchase",
      phase: "create",
      permission: "purchase:create",
    },
    {
      key: "tray",
      label: "装入托盘",
      hint: "先录托盘编码，再连续扫手机",
      action: "tray",
      phase: "create",
      permission: "tray:manage",
    },
    {
      key: "box",
      label: "装箱封存",
      hint: "扫描托盘编码，完成箱内装载",
      action: "box",
      phase: "create",
      permission: "box:manage",
    },
  ],
  ghana: [
    {
      key: "receiving-start",
      label: "建立到货单",
      hint: "按发运单开箱登记",
      action: "receiving",
      phase: "start",
      permission: "receiving:unpack",
    },
    {
      key: "receiving-inspect",
      label: "逐台到货验收",
      hint: "逐台核对并可重新装托/装箱",
      action: "receiving",
      phase: "inspect",
      permission: "receiving:accept",
    },
    {
      key: "transfer-issue",
      label: "门店拣货调拨",
      hint: "按手机、托盘或箱子发往门店",
      action: "transfer",
      phase: "issue",
      permission: "transfer:create",
    },
    {
      key: "transfer-receive",
      label: "调拨收货",
      hint: "核对实收并完成交接",
      action: "transfer",
      phase: "receive",
      permission: "transfer:receive",
    },
    {
      key: "return-create",
      label: "发起退回",
      hint: "登记门店待维修手机/托盘",
      action: "return",
      phase: "create",
      permission: "return:create",
    },
    {
      key: "return-receive",
      label: "退回分诊",
      hint: "接收退回箱/托盘，逐台登记",
      action: "return",
      phase: "receive",
      permission: "return:receive",
    },
    {
      key: "repair-create",
      label: "建立维修单",
      hint: "把待修手机或容器送入维修队列",
      action: "repair",
      phase: "create",
      permission: "repair:create",
    },
    {
      key: "repair-accept",
      label: "维修接收",
      hint: "维修人员接收任务（如有授权）",
      action: "repair",
      phase: "accept",
      permission: "repair:receive",
    },
    {
      key: "repair-complete",
      label: "填写维修结果",
      hint: "逐台记录维修结果（如有授权）",
      action: "repair",
      phase: "complete",
      permission: "repair:update",
    },
    {
      key: "repair-review",
      label: "维修 QA 复核",
      hint: "逐台确认恢复可售、冻结或报损",
      action: "repair",
      phase: "review",
      permission: "repair:approve",
    },
  ],
};
const user = ref<CurrentUser | null>(null);
const active = ref("dashboard");
// A composite work card maps one岗位 to several existing API operations.
// The active API task remains granular so backend contracts and offline drafts
// remain compatible while the operator sees one continuous sequence.
const activeWorkflow = ref<WorkflowKey | null>(null);
const error = ref("");
const message = ref("");
const loading = ref(false);
const online = ref(navigator.onLine);
const identifier = ref("");
const password = ref("");
const scanInput = ref("");
const scanned = ref<string[]>([]);
const operationPhase = ref("create");
const organizationId = ref("");
const locationId = ref("");
const destinationOrganizationId = ref("");
const destinationLocationId = ref("");
const containerKind = ref<"PHONE" | "TRAY" | "BOX">("PHONE");
const containerCode = ref("");
const capturingContainer = ref(false);
const documentNo = ref("");
const logisticsNo = ref("");
const accepted = ref(true);
// 收货并不总是一次完成：门店可能先收到一部分，剩余件稍后补录。
// 默认保持“完成”以兼容一次性整批收货，但在表单中要求操作员明确看到
// 短少处理规则后再提交。
const transferReceiveComplete = ref(true);
const targetTrayCode = ref(""); const targetBoxCode = ref("");
const salesType = ref<"RETAIL" | "WHOLESALE">("RETAIL");
const customerName = ref("");
const salePrices = ref("");
const repairResult = ref("REPAIRED");
const disposition = ref("AVAILABLE_AGAIN");
const adjustmentDecision = ref("IGNORE");
const adjustmentTargetStatus = ref("可再次销售");
const workLocations = ref<Record<string, unknown>[]>([]);
const locationsLoaded = ref(false);
const dashboardStats = ref({ phones: 0, documents: 0, pendingDrafts: 0 });
const phoneDetail = ref<Record<string, unknown> | null>(null);
const inventory = ref<Record<string, unknown>[]>([]);
const documents = ref<Record<string, unknown>[]>([]);
const documentLocationLabels = ref<Record<string, string>>({});
const drafts = ref<Draft[]>([]);
const adminData = ref<{
  organizations: any[];
  locations: any[];
  users: any[];
  roles: any[];
  permissions: any[];
  audits: any[];
}>({
  organizations: [],
  locations: [],
  users: [],
  roles: [],
  permissions: [],
  audits: [],
});
const adminTab = ref<
  "users" | "organizations" | "locations" | "roles" | "audits"
>("users");
const newIdentifier = ref("");
const newName = ref("");
const newPassword = ref("");
const newRoleIds = ref<number[]>([]);
const newScopes = ref("");
const orgCode = ref(""); const orgName = ref(""); const orgCountry = ref("GH");
const locOrganizationId = ref(""); const locCode = ref(""); const locName = ref(""); const locType = ref("store");
const roleCode = ref(""); const roleName = ref(""); const roleWorkGroup = ref(""); const roleDescription = ref(""); const rolePermissionsText = ref("");
const profileName = ref(""); const profileUsername = ref(""); const currentPassword = ref(""); const nextPassword = ref("");
const editingUserId = ref<number | null>(null); const editingRoleIds = ref<number[]>([]); const editingScopes = ref("");
const scannerInput = ref<HTMLInputElement | null>(null);
const documentInput = ref<HTMLInputElement | null>(null);
const containerRadioRefs = ref<Record<string, HTMLInputElement | null>>({});
const sidebarRef = ref<HTMLElement | null>(null);
const navGroupsRef = ref<HTMLElement | null>(null);
const menuToggleButton = ref<HTMLButtonElement | null>(null);
const sidebarCloseButton = ref<HTMLButtonElement | null>(null);
const accountToggleButton = ref<HTMLButtonElement | null>(null);
const accountMenu = ref<HTMLElement | null>(null);
const confirmCancelButton = ref<HTMLButtonElement | null>(null);
const confirmDialog = ref<HTMLElement | null>(null);
const helpButton = ref<HTMLButtonElement | null>(null);
const helpDialog = ref<HTMLElement | null>(null);
// UI-only state used by the PC workbench.  Keep it separate from the API
// payload state above so a filter, drawer or help panel never changes a
// warehouse operation that is currently being entered.
const refreshLoading = ref(false);
const sidebarOpen = ref(false);
const sidebarCollapsed = ref(false);
const accountMenuOpen = ref(false);
const navGroupExpanded = ref<Record<string, boolean>>({
  operations: true,
  collaboration: true,
  account: false,
});
const showHelp = ref(false);
const showConfirm = ref(false);
const confirmTitle = ref("");
const confirmDescription = ref("");
const confirmButtonLabel = ref("确认并清空");
const confirmAction = ref<(() => void) | null>(null);
const confirmationReturnFocus = ref<HTMLElement | null>(null);
const scanNotice = ref("");
const lastSubmission = ref<{ no?: string; count?: number; status?: string; text: string; complete?: boolean } | null>(null);
const selectedInventory = ref<Record<string, unknown> | null>(null);
const selectedDocument = ref<Record<string, unknown> | null>(null);
const inventoryDrawer = ref<HTMLElement | null>(null);
const documentDrawer = ref<HTMLElement | null>(null);
const drawerReturnFocus = ref<HTMLElement | null>(null);
const inventorySearch = ref("");
const inventoryStatusFilter = ref("");
const inventoryLocationFilter = ref("");
const inventoryPage = ref(1);
const inventoryPageSize = ref(20);
const documentsSearch = ref("");
const documentsTypeFilter = ref("");
const documentsStatusFilter = ref("");
const documentsPage = ref(1);
const documentsPageSize = ref(15);
const draftsFilter = ref("all");
const userSearch = ref("");
const userStatusFilter = ref("active");
const roleSearch = ref("");
const auditSearch = ref("");
const passwordVisible = ref(false);
const newPasswordVisible = ref(false);
const profileCurrentPasswordVisible = ref(false);
const profileNextPasswordVisible = ref(false);
const selectedRolePermissions = ref<string[]>([]);
const showAdvancedScopes = ref(false);
const selectedUserScopeLocation = ref("");
type ScopeDraft = { permission_code: string; scope_kind: "all" | "organization" | "location" | "country" | "own"; scope_value: string | null };
const newScopeRows = ref<ScopeDraft[]>([]);
const editingScopeRows = ref<ScopeDraft[]>([]);
const scopePermission = ref("");
const scopeKind = ref<ScopeDraft["scope_kind"]>("location");
const scopeValue = ref("");
// Generated document numbers follow the operator through the composite Ghana
// workflow, so the received return can be linked to the repair hand-off.
const workflowDocuments = ref<Record<string, string>>({});
// 只有接口成功提交过的步骤才标记为完成。不能用当前步骤序号推断，
// 因为现场人员可能回看或跳到后面的步骤。
const workflowCompletedSteps = ref<Record<WorkflowKey, string[]>>({
  shenzhen: [],
  ghana: [],
});
type StandaloneProgress = { documentNo: string; completedPhases: string[]; sourcePhase?: string; carryToPhase?: string; phaseComplete?: boolean };
// Standalone岗位可能在同一浏览器会话里连续承接多个阶段（例如“建立到货单”
// 后马上“逐台验收”）。只在阶段提交成功后记录单号，切换阶段时自动带入，
// 避免作业员手抄单号；显式重新进入页面时仍从空白开始，防止误用旧批次。
const standaloneProgress = ref<Record<string, StandaloneProgress>>({});
const standaloneResume = ref<{ taskKey: string; progress: StandaloneProgress } | null>(null);
const roleLabel = computed(() => {
  const first = user.value?.roles?.[0];
  if (typeof first === "string") return first;
  return first?.name || user.value?.work_group || "";
});
function metadataWorkflow(): WorkflowKey | null {
  const raw = user.value as (CurrentUser & { work_group?: string; workGroup?: string; role_codes?: string[]; roles?: unknown[] }) | null;
  if (!raw) return null;
  const value = String(raw.work_group || raw.workGroup || "").trim().toLowerCase();
  if (["shenzhen", "sz", "shenzhen_operations", "sz_operations", "demo_sz_operations"].includes(value)) return "shenzhen";
  if (["ghana", "gh", "ghana_operations", "demo_ghana_operations"].includes(value)) return "ghana";
  const codes = [
    ...(Array.isArray(raw.role_codes) ? raw.role_codes : []),
    ...(Array.isArray(raw.roles) ? raw.roles.map((row: any) => typeof row === "string" ? row : row?.code) : []),
  ].map((code) => String(code || "").toLowerCase());
  if (codes.includes("demo_sz_operations")) return "shenzhen";
  if (codes.includes("demo_ghana_operations")) return "ghana";
  return null;
}
function workflowCapabilityReady(workflow: WorkflowKey) {
  const required = workflow === "shenzhen"
    ? ["purchase:create", "tray:manage", "box:manage"]
    : ["receiving:unpack", "receiving:accept", "transfer:create", "return:receive", "repair:create", "repair:approve"];
  const hasRequired = required.every((code) => has(code));
  const metadata = metadataWorkflow();
  return metadata ? metadata === workflow && hasRequired : hasRequired;
}
const workflowSteps = computed(() => activeWorkflow.value ? workflowDefinitions[activeWorkflow.value].filter((step) => has(step.permission)) : []);
const currentWorkflowStep = computed(() => workflowSteps.value.find((step) => step.action === currentTask.value?.key && step.phase === operationPhase.value) || null);
const nextWorkflowStep = computed(() => {
  if (!currentWorkflowStep.value || !workflowStepDone(currentWorkflowStep.value)) return null;
  const index = workflowSteps.value.findIndex((step) => step.key === currentWorkflowStep.value!.key);
  return workflowSteps.value[index + 1] || null;
});
const workflowCompletedCount = computed(() => activeWorkflow.value ? workflowCompletedSteps.value[activeWorkflow.value].length : 0);
function workflowStepDone(step: WorkflowStep) {
  return Boolean(activeWorkflow.value && workflowCompletedSteps.value[activeWorkflow.value].includes(step.key));
}
const workflowPrerequisites: Record<string, string> = {
  tray: "purchase",
  box: "tray",
  "receiving-inspect": "receiving-start",
  "transfer-issue": "receiving-inspect",
  "transfer-receive": "transfer-issue",
  "return-receive": "return-create",
  "repair-create": "return-receive",
  "repair-accept": "repair-create",
  "repair-complete": "repair-accept",
  "repair-review": "repair-complete",
};
// 同一个 API 动作可能有多个现场阶段（例如维修：建立、接收、完成、QA）。
// 只有“当前阶段需要输入的来源单号”才允许自动承接；首阶段的输入单号
// 与本阶段生成的输出单号不同，绝不能把旧输出单号回填到新的来源字段。
const workflowInputDocumentSources: Record<string, string> = {
  "ghana:receiving:inspect": "ghana:receiving:start",
  "ghana:transfer:receive": "ghana:transfer:issue",
  "ghana:return:receive": "ghana:return:create",
  // 维修建单输入退回单号，而不是上一张维修单号。
  "ghana:repair:create": "ghana:return",
  "ghana:repair:accept": "ghana:repair:create",
  "ghana:repair:complete": "ghana:repair:create",
  "ghana:repair:review": "ghana:repair:create",
};
function workflowDocumentKey(workflow: WorkflowKey, action: string, phase: string) {
  return `${workflow}:${action}:${phase}`;
}
function workflowDocumentFor(workflow: WorkflowKey, action: string, phase: string) {
  const sourceKey = workflowInputDocumentSources[`${workflow}:${action}:${phase}`];
  return sourceKey ? (workflowDocuments.value[sourceKey] || "") : "";
}
function workflowStepBlocked(step: WorkflowStep) {
  if (!activeWorkflow.value) return false;
  const prerequisiteKey = workflowPrerequisites[step.key];
  if (!prerequisiteKey) return false;
  const prerequisite = workflowSteps.value.find((item) => item.key === prerequisiteKey);
  // If a separate岗位 owns the prerequisite (for example the维修技师),
  // do not hide QA from its授权人员; the backend remains the final gate.
  // A locked step remains clickable for cross-shift hand-off: the operator
  // can open it and type an existing document number.  Within this session,
  // however, only an actually completed prerequisite (not merely an output
  // number from a partial scan) may unlock the next step.
  return Boolean(prerequisite && !workflowStepDone(prerequisite));
}
function workflowStepBlockHint(step: WorkflowStep) {
  const prerequisiteKey = workflowPrerequisites[step.key];
  const prerequisite = workflowSteps.value.find((item) => item.key === prerequisiteKey);
  return prerequisite ? `请先完成“${prerequisite.label}”` : step.hint;
}
function resetWorkflowSession(workflow: WorkflowKey) {
  workflowCompletedSteps.value = {
    ...workflowCompletedSteps.value,
    [workflow]: [],
  };
  const prefix = `${workflow}:`;
  workflowDocuments.value = Object.fromEntries(
    Object.entries(workflowDocuments.value).filter(([key]) => !key.startsWith(prefix)),
  );
}
// Ghana综合岗位建单后要等待独立维修技师接单并填写结果。只有在技师
// 权限也被明确授予同一账号时，才允许把“建单成功”直接推进到下一步。
function repairTechHandoffPending() {
  return activeWorkflow.value === "ghana"
    && currentWorkflowStep.value?.key === "repair-create"
    && (!has("repair:receive") || !has("repair:update"));
}
const underlyingTask = (action: string) => tasks.find((task) => task.key === action) || null;
const visibleTasks = computed(() => {
  const result: Task[] = [];
  const shenzhenMerged = workflowCapabilityReady("shenzhen");
  const ghanaMerged = workflowCapabilityReady("ghana");
  if (shenzhenMerged) result.push(workflowTasks[0]);
  if (ghanaMerged) result.push(workflowTasks[1]);
  for (const task of tasks) {
    if (shenzhenMerged && ["purchase", "tray", "box"].includes(task.key)) continue;
    if (ghanaMerged && ["receiving", "transfer", "return", "repair"].includes(task.key)) continue;
    if (task.permissions.some((permission) => user.value?.permissions?.includes(permission))) result.push(task);
  }
  return result;
});
const currentTask = computed(() =>
  tasks.find((task) => task.key === active.value),
);
const canAdmin = computed(() =>
  Boolean(
    user.value?.permissions.includes("user:manage") ||
    user.value?.permissions.includes("role:manage") ||
    user.value?.permissions.includes("audit:view"),
  ),
);
const canUserManagement = computed(() => Boolean(user.value?.permissions.includes("user:manage")));
const canSystemManagement = computed(() => Boolean(user.value?.permissions.includes("role:manage") || user.value?.permissions.includes("audit:view")));
const adminNavLabel = computed(() =>
  user.value?.permissions.includes("user:manage") || user.value?.permissions.includes("role:manage")
    ? "系统管理"
    : "审计记录",
);
const activeLocations = computed(() => workLocations.value);
const authorizedLocationCount = computed(() => workLocations.value.filter((item) => item.source_allowed === true).length);
const countryOptions = computed(() => Array.from(new Set(workLocations.value.map((item) => String(item.country || "")).filter(Boolean))).sort());
const destinationLocations = computed(() => {
  const action = currentTask.value?.key;
  const current = activeLocations.value.find((item) => String(item.id) === locationId.value);
  const currentOrganizationId = current ? String(current.organization_id) : "";
  if (["shipment", "transfer", "return"].includes(String(action)) && !currentOrganizationId) return [];
  const differentOrganization = (item: Record<string, unknown>) =>
    !currentOrganizationId || String(item.organization_id) !== currentOrganizationId;
  const sameOrganization = (item: Record<string, unknown>) =>
    !currentOrganizationId || String(item.organization_id) === currentOrganizationId;
  if (action === "transfer") {
    const stores = activeLocations.value.filter((item) =>
      String(item.location_type) === "store" && String(item.id) !== locationId.value && sameOrganization(item),
    );
    return stores;
  }
  if (action === "return") {
    const warehouses = activeLocations.value.filter((item) =>
      ["warehouse", "receiving"].includes(String(item.location_type)) && String(item.id) !== locationId.value && sameOrganization(item),
    );
    return warehouses;
  }
  if (action === "shipment") {
    const warehouses = activeLocations.value.filter((item) =>
      ["warehouse", "receiving"].includes(String(item.location_type)) && String(item.id) !== locationId.value && differentOrganization(item),
    );
    return warehouses;
  }
  return activeLocations.value;
});
function businessLocationAllowed(item: Record<string, unknown>) {
  const task = currentTask.value?.key;
  const type = String(item.location_type || "");
  // 先按现场物料路径缩小选择范围，再叠加账号的数据权限；这样员工
  // 不会在下拉框里看到“能选但业务上不能作为起点”的地点。
  if (["purchase", "tray", "box", "shipment"].includes(String(task))) {
    return ["warehouse", "receiving"].includes(type);
  }
  if (task === "receiving" && operationPhase.value === "start") {
    return ["warehouse", "receiving"].includes(type);
  }
  if (task === "transfer" && operationPhase.value === "issue") {
    return ["warehouse", "receiving", "store"].includes(type);
  }
  if (task === "return" && operationPhase.value === "create") {
    return type === "store";
  }
  if (task === "repair") {
    return ["repair", "warehouse", "receiving"].includes(type);
  }
  return true;
}
const sourceLocations = computed(() =>
  currentTask.value
    ? workLocations.value.filter((item) => locationAllowed(currentPhasePermission(), item) && businessLocationAllowed(item))
    : workLocations.value,
);

const permissionLabels: Record<string, string> = {
  "phone:view": "查看手机与轨迹",
  "phone:edit": "修改手机资料",
  "purchase:create": "收购验收入库",
  "tray:manage": "装托盘 / 拆托盘",
  "box:manage": "装箱 / 拆箱",
  "shipment:view": "查看发运单",
  "shipment:dispatch": "发运出库",
  "receiving:unpack": "建立到货单 / 开箱",
  "receiving:accept": "逐台到货验收",
  "transfer:create": "发起门店调拨",
  "transfer:receive": "门店调拨收货",
  "inventory:issue": "库存出库",
  "inventory:receive": "库存入库",
  "sales:create": "创建销售单",
  "sales:approve": "销售单复核",
  "sales:cancel": "撤销销售单",
  "return:create": "发起销售退回",
  "return:receive": "接收退回 / 分诊",
  "repair:create": "建立维修单",
  "repair:receive": "维修接收",
  "repair:update": "填写维修结果",
  "repair:approve": "维修 QA 复核",
  "stocktake:submit": "提交盘点",
  "stocktake:adjust": "审核盘点差异",
  "report:view": "查看报表",
  "audit:view": "查看审计记录",
  "user:manage": "管理用户与组织",
  "role:manage": "管理角色与权限",
};
const permissionGroups = [
  { label: "库存与容器", codes: ["phone:view", "phone:edit", "tray:manage", "box:manage", "inventory:issue", "inventory:receive"] },
  { label: "收发货与调拨", codes: ["purchase:create", "shipment:view", "shipment:dispatch", "receiving:unpack", "receiving:accept", "transfer:create", "transfer:receive"] },
  { label: "销售、退回与维修", codes: ["sales:create", "sales:approve", "sales:cancel", "return:create", "return:receive", "repair:create", "repair:receive", "repair:update", "repair:approve"] },
  { label: "盘点、报表与管理", codes: ["stocktake:submit", "stocktake:adjust", "report:view", "audit:view", "user:manage", "role:manage"] },
];
const actionLabels: Record<string, string> = {
  purchase: "收购验收",
  tray: "装托盘",
  box: "装箱封存",
  shipment: "发运出库",
  receiving: "到货接收",
  transfer: "门店调拨",
  sales: "销售出库",
  return: "销售退回",
  repair: "维修管理",
  stocktake: "盘点核查",
  query: "IMEI 追踪",
};
const timelineActionLabels: Record<string, string> = {
  purchase_receipt: "采购入库", purchase: "采购入库", tray_pack: "装入托盘", tray_unpack: "取出托盘",
  box_pack: "装入箱子", box_unpack: "拆出箱子", shipment_dispatch: "发运出库", shipment_receive: "到货接收",
  receiving_start: "建立到货单", receiving_inspect: "逐台到货验收", transfer_issue: "调拨出库",
  transfer_receive: "调拨收货", sale_create: "创建销售单", sale_confirm: "销售确认", return_create: "发起销售退回",
  return_receive: "退回分诊", repair_create: "创建维修单", repair_accept: "维修接收", repair_complete: "维修完成",
  repair_review: "维修 QA 复核", stocktake_submit: "提交盘点", stocktake_adjust: "处理盘点差异",
};
const documentTypeLabels: Record<string, string> = {
  purchase: "采购入库",
  shipment: "发运单",
  receiving: "到货单",
  transfer: "调拨单",
  sales: "销售单",
  return: "退回单",
  repair: "维修单",
  stocktake: "盘点单",
};
const locationTypeLabels: Record<string, string> = {
  warehouse: "仓库",
  receiving: "接收区",
  store: "门店",
  repair: "维修区",
};
const phaseLabels: Record<string, string> = {
  create: "新建",
  start: "建立单据",
  inspect: "逐台验收",
  issue: "发起出库",
  receive: "现场收货",
  confirm: "主管复核",
  accept: "接收维修",
  complete: "填写结果",
  review: "QA 复核",
  adjust: "审核差异",
};
const pageMeta = computed(() => {
  if (active.value === "dashboard") return { eyebrow: "工作台", title: "今天要完成什么？", subtitle: "按现场顺序选择作业入口，系统会在每一步提示应扫描的物料和交接对象。" };
  if (currentTask.value) return { eyebrow: activeWorkflow.value ? (activeWorkflow.value === "shenzhen" ? "深圳收购仓作业" : "加纳综合仓作业") : actionLabels[currentTask.value.key], title: activeWorkflow.value ? (currentWorkflowStep.value?.hint || currentTask.value.hint) : currentTask.value.hint, subtitle: operationInstruction() };
  const pages: Record<string, { eyebrow: string; title: string; subtitle: string }> = {
    inventory: { eyebrow: "查询与追溯", title: "库存列表", subtitle: "按 IMEI、状态或地点查找手机，点击一行可查看当前保管位置。" },
    documents: { eyebrow: "查询与追溯", title: "业务单据", subtitle: "查看发运、接收、调拨、销售、退回和维修单的当前状态。" },
    drafts: { eyebrow: "作业保障", title: "离线草稿", subtitle: "网络中断时先保存在本机；恢复联网后逐条核对并同步。" },
    profile: { eyebrow: "账户", title: "个人资料与安全", subtitle: "维护显示名称、用户名和登录密码。" },
    system: { eyebrow: "系统管理", title: "系统业务配置", subtitle: "配置组织、地点、角色与权限等系统业务基础信息。" },
    users: { eyebrow: "用户管理", title: "用户管理", subtitle: "创建用户并为工作人员分配岗位和数据范围。" },
    admin: { eyebrow: adminNavLabel.value, title: adminNavLabel.value === "系统管理" ? "用户、地点与权限" : "审计记录", subtitle: adminNavLabel.value === "系统管理" ? "只有管理员可见。变更权限前请确认岗位职责和数据范围。" : "只读查看关键业务与权限变更记录。" },
  };
  return pages[active.value] || { eyebrow: "工作台", title: "进销存业务控制台", subtitle: "" };
});
const activeLocation = computed(() => workLocations.value.find((item) => String(item.id) === locationId.value) || null);
const activeDestinationLocation = computed(() => workLocations.value.find((item) => String(item.id) === destinationLocationId.value) || null);
const operationStepNumber = computed(() => {
  if (!activeWorkflow.value || !currentWorkflowStep.value) return 0;
  return workflowSteps.value.findIndex((step) => step.key === currentWorkflowStep.value!.key) + 1;
});
const operationInstruction = () => {
  const key = currentTask.value?.key;
  const phase = operationPhase.value;
  const map: Record<string, string> = {
    "purchase:create": "先选择深圳收货地点，再连续扫描每台手机的 IMEI；同一批可一次提交。",
    "tray:create": "先扫描一个空托盘编码，再连续扫描手机 IMEI；扫描完成后一次提交装托。",
    "box:create": "先扫描箱子编码，再连续扫描箱内托盘编码；封箱前请核对托盘数量。",
    "shipment:create": "选择起运地和目的地，按实际装载单位扫描手机、托盘或箱子。提交后由收货方继续验收。",
    "receiving:start": "先输入深圳发运单号并选择加纳接收地点，开箱后再进入逐台验收。",
    "receiving:inspect": "每拿出一台就扫描一次 IMEI；异常机选择“异常/待核查”，不要用正常状态代替。",
    "transfer:issue": "按门店拣货清单扫描实际发出的手机、托盘或箱子，提交后形成待收货调拨单。",
    "transfer:receive": "输入调拨单号，再逐台扫描实收手机；箱子未到齐时先暂存，清点结束后再完成交接。",
    "sales:create": "先选择零售/批发，再扫描实际售出的手机或容器；价格可按扫描顺序填写。",
    "sales:confirm": "只需输入待确认销售单号。确认前请由主管核对金额和手机数量。",
    "return:create": "输入原销售单号，扫描门店退回的手机或容器；提交后交给加纳管理处分诊。",
    "return:receive": "输入退回单号，开箱/拆托后逐台扫描；异常机保留在待核查状态。",
    "repair:create": "逐台扫描待修 IMEI；如来自退回分诊，填写已接收退回单号以保留来源链路。",
    "repair:accept": "输入维修单号，确认维修技师已实际接收设备。",
    "repair:complete": "输入维修单号并逐台扫描，选择每台手机的维修结果。",
    "repair:review": "输入维修单号并逐台扫描，选择 QA 处理结论后再移交库存。",
    "stocktake:create": "选择盘点地点，现场逐台扫描看到的 IMEI；不要凭记忆补录。",
    "stocktake:adjust": "输入盘点单号，确认差异原因后再选择忽略、确认缺失或接收多出。",
    "query:create": "扫描或输入一台手机的 IMEI，查看它的状态、地点和流转轨迹。",
  };
  return map[`${key}:${phase}`] || "按页面提示完成当前作业，并在提交前核对数量和地点。";
};
const operationHandoff = computed(() => {
  const key = currentTask.value?.key;
  const phase = operationPhase.value;
  const map: Record<string, string> = {
    "purchase:create": "下一步：装托人员使用生成的入库记录，把手机装入托盘。",
    "tray:create": "下一步：装箱人员扫描托盘，把已装托盘放入箱子。",
    "box:create": "下一步：深圳发运员复核箱内托盘并登记物流。",
    "shipment:create": "下一步：目的地岗位按发运单开箱、拆托并逐台验收。",
    "receiving:start": "下一步：同一岗位进入逐台到货验收，逐台留下正常/异常结果。",
    "receiving:inspect": "下一步：合格手机进入加纳库存，异常手机进入待核查或维修分诊。",
    "transfer:issue": "下一步：门店收货员按调拨单逐台清点并确认实收。",
    "transfer:receive": "完成收货后：调拨单进入已完成/部分差异，库存归属目的门店；未到货明细会单独留痕。",
    "return:create": "下一步：加纳管理处按退回单开箱、拆托、逐台分诊。",
    "return:receive": "下一步：对待维修手机建立维修单，再交给维修技师接收。",
    "repair:create": "下一步：维修技师在维修队列接收并填写维修结果。",
    "repair:review": "交接完成：QA 结论决定恢复可售、冻结待核查或报损。",
    "query:create": "只读查询：不会修改库存、生成单据或触发岗位交接。",
  };
  return map[`${key}:${phase}`] || "提交后请按单号和状态与下一岗位交接。";
});
const scanKindLabel = computed(() => containerKind.value === "PHONE" ? "手机 IMEI" : containerKind.value === "TRAY" ? "托盘编号" : "箱子编号");
const scanPlaceholder = computed(() => {
  if (phaseRequiresCurrentLocation() && !locationId.value) return "先选择当前作业地点，再开始扫描";
  if (phaseRequiresDestination() && !destinationLocationId.value) return "先选择目标地点，再开始扫描";
  if (phaseRequiresDocumentInput() && !documentNo.value.trim()) return `先填写${documentFieldLabel()}，再开始扫描`;
  if (capturingContainer.value) return `第一步：扫描目标${currentTask.value?.key === "tray" ? "托盘" : "箱子"}编码`;
  return scanMode() === "imei" ? "扫描 IMEI（15 位数字，扫码后自动加入）" : `扫描${scanKindLabel.value}，扫码后自动加入`;
});
const submitDisabledReason = computed(() => {
  const task = currentTask.value;
  if (!task) return "";
  if (loading.value) return "正在提交，请稍候";
  if (lastSubmission.value && !phaseRequiresScan() && !canCloseTransferAfterPartial()) return "本阶段已完成，请点击下一阶段或开始新批次";
  if (phaseRequiresCurrentLocation() && !sourceLocations.value.length) return locationsLoaded.value ? "当前岗位没有授权的可用作业地点，请联系管理员" : "正在加载作业地点，请稍候";
  if (phaseRequiresCurrentLocation() && !locationId.value) return "先选择当前地点";
  if (phaseRequiresDestination() && locationId.value && !destinationLocations.value.length) return "当前没有符合业务规则的目标地点，请联系管理员配置门店或仓库";
  if (phaseRequiresDestination() && destinationLocationId.value
    && !destinationLocations.value.some((item) => String(item.id) === destinationLocationId.value)) return "目标地点已随当前地点变化，请重新选择";
  if (phaseRequiresDestination() && !destinationLocationId.value) return "先选择目标地点";
  if ((task.key === "tray" || task.key === "box") && !containerCode.value.trim()) return `先填写目标${task.key === "tray" ? "托盘" : "箱子"}编号`;
  const needsDocument = phaseRequiresDocumentInput();
  if (needsDocument && !documentNo.value.trim()) return "先填写业务单号";
  if (task.key === "receiving" && operationPhase.value === "inspect") {
    if (targetBoxCode.value.trim() && !targetTrayCode.value.trim()) return "填写箱子编码前，请先填写托盘编码";
    if (targetTrayCode.value.trim() && !isValidContainerCode(targetTrayCode.value.trim())) return "托盘编码格式不正确，请检查标签";
    if (targetBoxCode.value.trim() && !isValidContainerCode(targetBoxCode.value.trim())) return "箱子编码格式不正确，请检查标签";
  }
  if (task.key === "sales" && operationPhase.value === "create" && containerKind.value === "PHONE" && salePrices.value.trim()) {
    const prices = salePrices.value.split(",").map((value) => value.trim()).filter(Boolean);
    if (prices.some((value) => !/^\d+(?:\.\d{1,2})?$/.test(value))) return "销售价格请填写数字，多个价格用逗号分隔";
    if (prices.length > 1 && prices.length !== scanned.value.length) return `销售价格有 ${prices.length} 个，但清单有 ${scanned.value.length} 项；请按扫描顺序一一对应`;
  }
  if (phaseRequiresScan() && !scanned.value.length && !canCloseTransferAfterPartial()) return "至少扫描或输入一项";
  if (task.key === "query" && scanned.value.length > 1) return "查询一次只能输入一台手机";
  return "";
});
const canSubmit = computed(() => Boolean(currentTask.value && !submitDisabledReason.value));
const submitSummary = computed(() => {
  const task = currentTask.value;
  if (!task) return "";
  const count = scanned.value.length;
  const target = activeDestinationLocation.value ? ` → ${locationLabel(activeDestinationLocation.value)}` : "";
  const source = activeLocation.value ? locationLabel(activeLocation.value) : "";
  if (!count && !documentNo.value) return "完成必填项后，这里会显示提交摘要";
  return `${phaseLabels[operationPhase.value] || "提交"} · ${count ? `${count} 项` : "按单号操作"}${source ? ` · ${source}` : ""}${target}`;
});
function phaseNeedsDocument() {
  const task = currentTask.value?.key;
  return task === "receiving" || task === "return" || (task === "transfer" && operationPhase.value === "receive") || (task === "sales" && operationPhase.value === "confirm") || (task === "repair" && (operationPhase.value !== "create" || activeWorkflow.value === "ghana")) || (task === "stocktake" && operationPhase.value === "adjust");
}
function phaseRequiresDocumentInput() {
  const task = currentTask.value?.key;
  // 维修建单的关联退回单号是可选的：仍显示字段以保留来源链路，
  // 但没有退回单时也必须允许直接扫描 IMEI 建立维修单。
  return task === "receiving"
    || task === "return"
    || (task === "transfer" && operationPhase.value === "receive")
    || (task === "sales" && operationPhase.value === "confirm")
    || (task === "repair" && operationPhase.value !== "create")
    || (task === "stocktake" && operationPhase.value === "adjust");
}
function operationResultComplete(taskKey: string, phase: string, result: any, requestedTransferCompletion = transferReceiveComplete.value) {
  const rawStatus = String(result?.status || "").trim().toLowerCase();
  const isStatus = (...values: string[]) => values.some((value) => rawStatus === value.toLowerCase());
  if (taskKey === "receiving" && phase === "inspect") {
    const expected = Number(result?.expected_count);
    const checked = Number(result?.accepted_count || 0) + Number(result?.exception_count || 0);
    return (expected > 0 && checked >= expected) || isStatus("completed", "complete", "partial", "已完成", "部分差异");
  }
  if ((taskKey === "return" && phase === "receive")) {
    const total = Number(result?.total_count);
    const received = Number(result?.received_count);
    return (total > 0 && received >= total) || isStatus("completed", "complete", "已完成");
  }
  if (taskKey === "transfer" && phase === "receive") {
    // 调拨接口只有在 complete=true 时才会把未收到的明细记为短少并关单。
    // “暂存已收”返回 receiving，不能让工作流误认为已经完成。
    const total = Number(result?.total_count);
    const received = Number(result?.received_count || 0);
    return requestedTransferCompletion && (
      (total > 0 && received >= total)
      || isStatus("completed", "complete", "partial", "已完成", "部分差异")
    );
  }
  if (taskKey === "repair" && phase === "complete") {
    // The repair endpoint exposes no total_count; PENDING_ACCEPTANCE is
    // emitted only after every repair item has a technician result.
    return isStatus("pending_acceptance", "待验收", "completed", "complete", "已完成");
  }
  if (taskKey === "repair" && phase === "review") {
    return isStatus("completed", "complete", "已完成");
  }
  return true;
}
function phaseCanChooseContainerKind() {
  const task = currentTask.value?.key;
  // Receiving/return receiving and repair acceptance/results are deliberately
  // phone-by-phone. Their APIs need an IMEI so a box/tray code would create a
  // false handoff; only the create side of return/repair accepts containers.
  return (task === "shipment")
    || (task === "transfer" && operationPhase.value === "issue")
    || (task === "sales" && operationPhase.value === "create")
    || (task === "return" && operationPhase.value === "create")
    || (task === "repair" && operationPhase.value === "create");
}
function containerChoiceHint() {
  const task = currentTask.value?.key;
  if (task === "shipment") return "深圳发运可按散台、整托或整箱；请选择与实际装车方式一致的单位，提交后由目的地拆箱验收。";
  if (task === "transfer") return "门店串货支持单台手机、整托或整箱；选择与拣货清单一致的单位，收货方仍会逐台核对。";
  if (task === "sales") return "销售可按单台、整托或整箱出库；整托/整箱销售会按容器内手机生成销售明细。";
  if (task === "return") return "门店可按单台、整托或整箱退回；加纳管理处收到后仍需拆箱/拆托逐台分诊。";
  if (task === "repair") return "送修可按单台、整托或整箱交接；维修 QA 阶段会回到逐台 IMEI。";
  return "门店收货和到货验收必须拆箱/拆托后逐台扫描，系统会自动使用手机 IMEI 模式。";
}
function documentFieldLabel() {
  const task = currentTask.value?.key;
  if (task === "receiving") return operationPhase.value === "start" ? "深圳发运单号" : "加纳到货单号";
  if (task === "transfer") return "调拨单号";
  if (task === "sales") return "待确认销售单号";
  if (task === "return") return operationPhase.value === "create" ? "原销售单号" : "退回单号";
  if (task === "repair" && operationPhase.value === "create" && activeWorkflow.value === "ghana") return "关联退回单号";
  if (task === "repair") return "维修单号";
  if (task === "stocktake") return "盘点单号";
  return "业务单号";
}
function documentFieldHint() {
  const task = currentTask.value?.key;
  if (task === "receiving" && operationPhase.value === "start") return "从深圳发运单或交接单上抄录，不要输入物流单号。";
  if (task === "receiving") return "建立到货单后系统会自动带出，请使用页面显示的到货单号。";
  if (task === "return" && operationPhase.value === "create") return "用于关联原销售记录，退回单建立后再交给加纳管理处。";
  if (task === "repair" && operationPhase.value === "create") return "系统会带出本岗位刚完成的退回单；确认来源一致后再建立维修单，没有来源单时可留空。";
  return "请核对单号后再提交，单号决定这批物料归属哪一次交接。";
}
function taskIcon(task: Task) {
  const icons: Record<string, string> = { workflow_shenzhen: "▣", workflow_ghana: "◎", shipment: "➜", sales: "◆", stocktake: "✓", query: "⌕", inventory: "▤", documents: "▤", drafts: "↥", profile: "●", admin: "⚙" };
  return icons[task.key] || "•";
}
function roleScopeSummary() {
  // The endpoint returns all active locations for destination selectors. Only
  // locations usable by at least one of this operator's permissions belong in
  // the scope summary shown to staff.
  if (!locationsLoaded.value) return "地点范围加载中";
  const count = authorizedLocationCount.value;
  return count ? `授权作业地点 ${count} 个` : "暂无授权作业地点";
}
function permissionLabel(code: string) { return permissionLabels[code] || code; }
function timelineActionLabel(action: unknown) {
  const raw = String(action || "").trim();
  return timelineActionLabels[raw.toLowerCase()] || raw || "业务操作";
}
function documentTypeLabel(type: unknown) {
  const raw = String(type || "").trim();
  return documentTypeLabels[raw.toLowerCase()] || raw || "业务单据";
}
function locationTypeLabel(type: unknown) {
  const raw = String(type || "").trim();
  return locationTypeLabels[raw.toLowerCase()] || raw || "地点";
}
const statusLabels: Record<string, string> = {
  completed: "已完成", complete: "已完成", cancelled: "已取消", canceled: "已取消",
  draft: "草稿", submitted: "待审核", approved: "已审核", in_transit: "运输中",
  receiving: "接收中", partial: "部分差异", pending_confirmation: "待确认",
  pending_acceptance: "待验收", in_progress: "处理中", pending_receipt: "待入库",
  shenzhen_stock: "深圳库存", in_tray: "已装托盘", in_box: "已装箱待发运",
  ghana_pending_inspection: "加纳待验收", ghana_stock: "加纳管理处库存",
  store_stock: "门店库存", transferring: "调拨中", sold: "已售出",
  sale_pending: "销售待确认", return_pending_check: "销售退回待检测",
  waiting_repair: "待送修", repairing: "维修中", repair_pending_acceptance: "维修完成待验收",
  available_again: "可再次销售", frozen: "冻结待核查", lost_or_scrapped: "报损/遗失",
  conflict: "冲突待处理", syncing: "同步中", pending: "待同步", failed: "失败",
};
function statusText(status: unknown) {
  const raw = String(status || "").trim();
  if (!raw) return "未标记";
  return statusLabels[raw.toLowerCase()] || raw;
}
function statusClass(status: unknown) {
  const raw = String(status || "").toLowerCase();
  const value = statusText(status);
  if (/(completed|complete|可再次销售|正常|启用|已售出|available_again|sold)/.test(raw) || /(完成|可再次销售|正常|启用|已售出)/.test(value)) return "success";
  if (/(stock|in_tray|in_box|库存|装托|装箱|在库)/.test(raw) || /(库存|装托|装箱|在库)/.test(value)) return "info";
  if (/(运输|处理中|接收中|待|审核|维修|transit|receiving|pending|progress|review|repair|submitted|approved|draft|syncing)/.test(raw) || /(运输|处理中|接收中|待|审核|维修|草稿|同步中)/.test(value)) return "warning";
  if (/(异常|缺失|冻结|报损|停用|失败|冲突|cancel|canceled|lost|scrap|frozen|conflict|failed)/.test(raw) || /(异常|缺失|冻结|报损|停用|失败|冲突|取消)/.test(value)) return "danger";
  return "neutral";
}
function formatDate(value: unknown) {
  if (!value) return "—";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
function locationNameById(id: unknown) {
  const row = workLocations.value.find((item) => String(item.id) === String(id));
  if (row) return String(row.name || row.code || id);
  const cached = documentLocationLabels.value[String(id ?? "")];
  return cached || (id ? `地点 ${id}` : "—");
}
function locationDisplay(id: unknown, label: unknown) {
  return label ? String(label) : locationNameById(id);
}
function rememberDocumentLocations(items: Record<string, unknown>[]) {
  const next = { ...documentLocationLabels.value };
  for (const item of items) {
    if (item.location_id && item.location_name) next[String(item.location_id)] = String(item.location_name);
    if (item.destination_location_id && item.destination_location_name) next[String(item.destination_location_id)] = String(item.destination_location_name);
  }
  documentLocationLabels.value = next;
}
function userRoleLabel(item: any) { return roleIdsLabel(item); }
const inventoryStatuses = computed(() => Array.from(new Set(inventory.value.map((item) => String(item.status || "")).filter(Boolean))).sort());
const inventoryLocations = computed(() => {
  const ids = new Set(inventory.value.map((item) => String(item.location_id || "")).filter(Boolean));
  return Array.from(ids).map((id) => ({ id, name: locationNameById(id) }));
});
const filteredInventory = computed(() => {
  const query = inventorySearch.value.trim().toLowerCase();
  return inventory.value.filter((item) => {
    const haystack = [item.imei, item.imei2, item.brand, item.model, item.status, locationNameById(item.location_id), item.tray_id].map((v) => String(v || "").toLowerCase()).join(" ");
    return (!query || haystack.includes(query)) && (!inventoryStatusFilter.value || String(item.status || "") === inventoryStatusFilter.value) && (!inventoryLocationFilter.value || String(item.location_id || "") === inventoryLocationFilter.value);
  });
});
const inventoryTotalPages = computed(() => Math.max(1, Math.ceil(filteredInventory.value.length / inventoryPageSize.value)));
const pagedInventory = computed(() => filteredInventory.value.slice((inventoryPage.value - 1) * inventoryPageSize.value, inventoryPage.value * inventoryPageSize.value));
const documentTypes = computed(() => Array.from(new Set(documents.value.map((item) => String(item.type || "")).filter(Boolean))).sort());
const documentStatuses = computed(() => Array.from(new Set(documents.value.map((item) => String(item.status || "")).filter(Boolean))).sort());
const filteredDocuments = computed(() => {
  const query = documentsSearch.value.trim().toLowerCase();
  return documents.value.filter((item) => {
    const haystack = [item.no, item.type, item.status, locationDisplay(item.location_id, item.location_name), locationDisplay(item.destination_location_id, item.destination_location_name)].map((v) => String(v || "").toLowerCase()).join(" ");
    return (!query || haystack.includes(query)) && (!documentsTypeFilter.value || String(item.type || "") === documentsTypeFilter.value) && (!documentsStatusFilter.value || String(item.status || "") === documentsStatusFilter.value);
  });
});
const documentsTotalPages = computed(() => Math.max(1, Math.ceil(filteredDocuments.value.length / documentsPageSize.value)));
const pagedDocuments = computed(() => filteredDocuments.value.slice((documentsPage.value - 1) * documentsPageSize.value, documentsPage.value * documentsPageSize.value));
const filteredDrafts = computed(() => drafts.value.filter((draft) => draftsFilter.value === "all" || draft.status === draftsFilter.value));
const filteredAdminUsers = computed(() => {
  const query = userSearch.value.trim().toLowerCase();
  return adminData.value.users.filter((item) => (!query || [item.username, item.phone, item.display_name, roleIdsLabel(item)].join(" ").toLowerCase().includes(query)) && (userStatusFilter.value === "all" || (userStatusFilter.value === "active" ? item.is_active : !item.is_active)));
});
const filteredAdminRoles = computed(() => {
  const query = roleSearch.value.trim().toLowerCase();
  return adminData.value.roles.filter((item) => !query || [item.code, item.name, item.work_group, item.description].join(" ").toLowerCase().includes(query));
});
const filteredAudits = computed(() => {
  const query = auditSearch.value.trim().toLowerCase();
  return adminData.value.audits.filter((item) => !query || [item.action, item.resource_type, item.resource_id, item.created_at].join(" ").toLowerCase().includes(query));
});
function toggleRolePermission(code: string, target: "new" = "new") {
  if (target !== "new") return;
  const manuallyEntered = rolePermissionsText.value.split(",").map((item) => item.trim()).filter(Boolean).filter((item) => !selectedRolePermissions.value.includes(item));
  selectedRolePermissions.value = selectedRolePermissions.value.includes(code) ? selectedRolePermissions.value.filter((item) => item !== code) : [...selectedRolePermissions.value, code];
  rolePermissionsText.value = Array.from(new Set([...manuallyEntered, ...selectedRolePermissions.value])).join(", ");
}
function clearInventoryFilters() { inventorySearch.value = ""; inventoryStatusFilter.value = ""; inventoryLocationFilter.value = ""; inventoryPage.value = 1; }
function clearDocumentFilters() { documentsSearch.value = ""; documentsTypeFilter.value = ""; documentsStatusFilter.value = ""; documentsPage.value = 1; }
function selectInventory(item: Record<string, unknown>) {
  drawerReturnFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  selectedInventory.value = item;
  nextTick(() => inventoryDrawer.value?.querySelector<HTMLElement>("button")?.focus());
}
function selectDocument(item: Record<string, unknown>) {
  drawerReturnFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  selectedDocument.value = item;
  nextTick(() => documentDrawer.value?.querySelector<HTMLElement>("button")?.focus());
}
function closeInventoryDrawer() {
  const returnFocus = drawerReturnFocus.value;
  selectedInventory.value = null;
  nextTick(() => returnFocus?.focus({ preventScroll: true }));
  drawerReturnFocus.value = null;
}
function closeDocumentDrawer() {
  const returnFocus = drawerReturnFocus.value;
  selectedDocument.value = null;
  nextTick(() => returnFocus?.focus({ preventScroll: true }));
  drawerReturnFocus.value = null;
}
function handleDrawerKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    event.preventDefault();
    if (selectedInventory.value) closeInventoryDrawer();
    else if (selectedDocument.value) closeDocumentDrawer();
    return;
  }
  if (event.key !== "Tab") return;
  const root = selectedInventory.value ? inventoryDrawer.value : documentDrawer.value;
  if (!root) return;
  const focusable = Array.from(root.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ));
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
async function copyValue(value: unknown) {
  if (!value) return;
  try {
    if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText(String(value));
    message.value = `已复制：${value}`;
  } catch {
    message.value = "复制失败，请手动选择文本";
  }
}
function scopeValueLabel(row: ScopeDraft) {
  if (row.scope_kind === "all") return "全部范围";
  if (row.scope_kind === "own") return "本人创建或负责的记录";
  if (row.scope_kind === "location") return locationNameById(row.scope_value);
  if (row.scope_kind === "organization") {
    const org = adminData.value.organizations.find((item) => String(item.id) === String(row.scope_value));
    return org ? String(org.name || org.code) : `组织 ${row.scope_value || "—"}`;
  }
  return row.scope_value || "国家 / 地区未填写";
}
function syncScopeJson(rows: ScopeDraft[], target: "new" | "editing" = "new") {
  const json = JSON.stringify(rows, null, 2);
  if (target === "new") newScopes.value = json;
  else editingScopes.value = json;
}
function addScopeRow(target: "new" | "editing" = "new") {
  if (!scopePermission.value) return void (error.value = "请选择要限定范围的权限");
  const locationScopedPermissions = [
    "phone:view", "report:view", "purchase:create", "tray:manage", "box:manage", "shipment:dispatch",
    "receiving:unpack", "receiving:accept", "transfer:create", "transfer:receive",
    "inventory:issue", "inventory:receive", "sales:create", "sales:approve",
    "return:create", "return:receive", "repair:create", "repair:receive",
    "repair:update", "repair:approve", "stocktake:submit", "stocktake:adjust",
  ];
  if (scopeKind.value === "own" && locationScopedPermissions.includes(scopePermission.value)) return void (error.value = "该作业权限按组织/地点授权，不能使用“本人负责”范围");
  if (!["all", "own"].includes(scopeKind.value) && !scopeValue.value) return void (error.value = "请选择范围对象");
  if (scopeKind.value === "location" && !workLocations.value.some((item) => String(item.id) === scopeValue.value)) return void (error.value = "请选择有效的地点");
  if (scopeKind.value === "organization" && !adminData.value.organizations.some((item) => String(item.id) === scopeValue.value)) return void (error.value = "请选择有效的组织");
  if (scopeKind.value === "country" && !countryOptions.value.includes(scopeValue.value)) return void (error.value = "请选择有效的国家 / 地区");
  const row: ScopeDraft = { permission_code: scopePermission.value, scope_kind: scopeKind.value, scope_value: ["all", "own"].includes(scopeKind.value) ? null : scopeValue.value };
  const rows = target === "new" ? newScopeRows.value : editingScopeRows.value;
  if (rows.some((item) => item.permission_code === row.permission_code && item.scope_kind === row.scope_kind && item.scope_value === row.scope_value)) return void (error.value = "相同的数据范围已存在");
  rows.push(row);
  syncScopeJson(rows, target);
  error.value = "";
  scopePermission.value = "";
  scopeValue.value = "";
}
function removeScopeRow(index: number, target: "new" | "editing" = "new") {
  const rows = target === "new" ? newScopeRows.value : editingScopeRows.value;
  rows.splice(index, 1);
  syncScopeJson(rows, target);
}
function resetScopeBuilder() { scopePermission.value = ""; scopeKind.value = "location"; scopeValue.value = ""; }
function scopeRowsFromUnknown(value: unknown): ScopeDraft[] {
  if (!Array.isArray(value)) return [];
  return value.map((row: any) => {
    const rawKind = String(row.scope_kind || "location");
    return {
      permission_code: String(row.permission_code || ""),
      scope_kind: (rawKind === "owner" ? "own" : rawKind) as ScopeDraft["scope_kind"],
      scope_value: row.scope_value == null ? null : String(row.scope_value),
    };
  }).filter((row) => row.permission_code);
}
function has(permission: string) {
  return Boolean(user.value?.permissions?.includes(permission));
}
function currentPhasePermission() {
  const key = currentTask.value?.key;
  const map: Record<string, string> = {
    purchase: "purchase:create", tray: "tray:manage", box: "box:manage", shipment: "shipment:dispatch", query: "phone:view",
    [`receiving:${operationPhase.value}`]: operationPhase.value === "start" ? "receiving:unpack" : "receiving:accept",
    [`transfer:${operationPhase.value}`]: operationPhase.value === "issue" ? "transfer:create" : "transfer:receive",
    [`sales:${operationPhase.value}`]: operationPhase.value === "create" ? "sales:create" : "sales:approve",
    [`return:${operationPhase.value}`]: operationPhase.value === "create" ? "return:create" : "return:receive",
    [`repair:${operationPhase.value}`]: operationPhase.value === "create" ? "repair:create" : operationPhase.value === "accept" ? "repair:receive" : operationPhase.value === "complete" ? "repair:update" : "repair:approve",
    [`stocktake:${operationPhase.value}`]: operationPhase.value === "create" ? "stocktake:submit" : "stocktake:adjust",
  };
  return map[`${key}:${operationPhase.value}`] || map[key || ""] || "phone:view";
}
function locationAllowed(permission: string, item: Record<string, unknown>) {
  const scopes = user.value?.scopes?.[permission] || [];
  return scopes.some(
    (scope) =>
      scope.kind === "all" ||
      (scope.kind === "organization" &&
        scope.values.includes(String(item.organization_id))) ||
      (scope.kind === "location" && scope.values.includes(String(item.id))) ||
      (scope.kind === "country" && scope.values.includes(String(item.country || ""))),
  );
}
function locationLabel(item: Record<string, unknown>) {
  return `${item.organization_name || item.organization_id} · ${item.name || item.code}（${item.code || item.id}）`;
}
function roleIdsLabel(item: Record<string, unknown>) {
  const ids = Array.isArray(item.role_ids) ? item.role_ids : [];
  if (!ids.length) return "无";
  return ids.map((id) => {
    const role = adminData.value.roles.find((row) => Number(row.id) === Number(id));
    return role ? `${role.name}` : `角色 ${id}`;
  }).join("、");
}
function resetOperationViewport() {
  // The page and its card are independent scroll containers.  When Vue
  // reuses the operation layout while switching jobs/phases, a previous
  // review-at-bottom position otherwise hides the first fields of the next
  // job beneath the workflow header.
  nextTick(() => {
    document.querySelector<HTMLElement>(".operation-page")?.scrollTo(0, 0);
    document.querySelector<HTMLElement>(".operation-card")?.scrollTo(0, 0);
  });
}
function activateTask(task: Task, forcedPhase?: string, options: { carryStandalone?: boolean } = {}) {
  // The shared API helper stores an idempotency key in localStorage.  Start a
  // fresh key whenever the operator opens a new physical operation; otherwise
  // the next unrelated PC submit would be mistaken for a replay of the first
  // endpoint used in this browser session.
  api.beginOperation();
  active.value = task.key;
  error.value = "";
  message.value = "";
  scanNotice.value = "";
  lastSubmission.value = null;
  scanned.value = [];
  scanInput.value = "";
  phoneDetail.value = null;
  selectedInventory.value = null;
  selectedDocument.value = null;
  operationPhase.value = forcedPhase ?? phaseFor(task);
  // A phase change starts a new physical batch. Keep only the explicit
  // hand-off document that is restored below; never let a previous shipment,
  // destination, target container or sales/repair conclusion leak into the
  // next phase and become an accidental API payload.
  logisticsNo.value = "";
  destinationOrganizationId.value = "";
  destinationLocationId.value = "";
  targetTrayCode.value = "";
  targetBoxCode.value = "";
  accepted.value = true;
  salePrices.value = "";
  customerName.value = "";
  repairResult.value = "REPAIRED";
  disposition.value = "AVAILABLE_AGAIN";
  adjustmentDecision.value = "IGNORE";
  adjustmentTargetStatus.value = "可再次销售";
  transferReceiveComplete.value = true;
  containerKind.value = task.key === "box" ? "TRAY" : task.mode === "imei" ? "PHONE" : "PHONE";
  capturingContainer.value = ["tray", "box"].includes(task.key);
  containerCode.value = "";
  if (phaseRequiresCurrentLocation()) {
    const current = workLocations.value.find((item) => String(item.id) === locationId.value);
    if (!current || !locationAllowed(currentPhasePermission(), current) || !businessLocationAllowed(current)) {
      locationId.value = "";
      organizationId.value = "";
      const allowed = workLocations.value.filter((item) => locationAllowed(currentPhasePermission(), item) && businessLocationAllowed(item));
      if (allowed.length === 1) {
        locationId.value = String(allowed[0].id);
        syncOrganization();
      }
    }
  }
  documentNo.value = activeWorkflow.value ? workflowDocumentFor(activeWorkflow.value, task.key, operationPhase.value) : "";
  if (!activeWorkflow.value && options.carryStandalone && phaseCanCarryStandaloneDocument(task.key, operationPhase.value) && phaseNeedsDocument()) {
    documentNo.value = standaloneProgress.value[task.key]?.documentNo || "";
    if (documentNo.value) message.value = `已带入上一阶段单号：${documentNo.value}`;
  }
  if (task.key === "repair" && operationPhase.value === "create") {
    containerKind.value = "PHONE";
    if (activeWorkflow.value === "ghana" && !documentNo.value.trim()) {
      documentNo.value = workflowDocuments.value["ghana:return"] || "";
    }
  }
  window.scrollTo(0, 0);
  resetOperationViewport();
  focusOperationEntry();
}
function performWorkflowStep(step: WorkflowStep) {
  const task = underlyingTask(step.action);
  if (!task) return;
  activateTask(task, step.phase);
  refresh();
}
function selectWorkflowStep(step: WorkflowStep) {
  if (!activeWorkflow.value || !has(step.permission)) return;
  if (workflowStepBlocked(step)) {
    requestLeave(() => {
      performWorkflowStep(step);
      message.value = workflowStepBlockHint(step) + "未在本次会话中完成；如果是跨班次承接，请输入已有单号后提交。";
    });
    return;
  }
  if (currentWorkflowStep.value?.key === step.key) return;
  requestLeave(() => performWorkflowStep(step));
}
function selectWorkflow(workflow: WorkflowKey) {
  // Resolve the first permitted step before changing activeWorkflow.  This is
  // important when the operator has an unfinished scan: cancelling the
  // confirmation must leave the old workflow and its context untouched.
  const first = workflowDefinitions[workflow].find((step) => has(step.permission));
  if (!first) return;
  requestLeave(() => {
    activeWorkflow.value = workflow;
    resetWorkflowSession(workflow);
    // The workflow may expose the same phase key as the previous standalone
    // page; activate directly so the physical-operation context is always
    // reset and the new workflow's data is refreshed.
    performWorkflowStep(first);
  });
}
function isTaskActive(task: Task) {
  return task.workflow ? activeWorkflow.value === task.workflow : active.value === task.key;
}
function hasPendingOperationEntry() {
  if (!currentTask.value) return false;
  // IMEI 追踪是只读查询；已输入的号码不会形成待提交批次，也不应在
  // 切换页面时弹出“确认离开当前批次”的交接提示。
  if (currentTask.value.key === "query") return false;
  if (scanned.value.length || scanInput.value.trim()) return true;
  if (containerCode.value.trim() && !lastSubmission.value) return true;
  return Boolean(documentNo.value.trim() && !lastSubmission.value && phaseNeedsDocument());
}
function pendingEntryDescription() {
  const parts: string[] = [];
  if (scanned.value.length) parts.push(`${scanned.value.length} 项扫描记录`);
  if (containerCode.value.trim()) parts.push("已锁定容器");
  if (documentNo.value.trim()) parts.push("已填写单号");
  if (scanInput.value.trim()) parts.push("未加入清单的输入");
  return parts.join("、") || "当前页面输入";
}
function openConfirmation(action: () => void, title: string, description: string, buttonLabel = "确认并清空") {
  confirmationReturnFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  confirmTitle.value = title;
  confirmDescription.value = description;
  confirmButtonLabel.value = buttonLabel;
  confirmAction.value = action;
  showConfirm.value = true;
  nextTick(() => confirmCancelButton.value?.focus());
}
function requestLeave(action: () => void) {
  if (!hasPendingOperationEntry()) {
    action();
    return;
  }
  openConfirmation(action, "确认离开当前批次？", `离开后将清空${pendingEntryDescription()}，尚未提交的内容不会形成业务记录。`);
}
function cancelConfirmation() {
  const returnFocus = confirmationReturnFocus.value;
  showConfirm.value = false;
  confirmAction.value = null;
  confirmButtonLabel.value = "确认并清空";
  nextTick(() => returnFocus?.focus({ preventScroll: true }));
  confirmationReturnFocus.value = null;
}
function confirmPendingAction() {
  const action = confirmAction.value;
  showConfirm.value = false;
  confirmAction.value = null;
  confirmButtonLabel.value = "确认并清空";
  confirmationReturnFocus.value = null;
  action?.();
}
function handleConfirmKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    event.preventDefault();
    cancelConfirmation();
    return;
  }
  if (event.key !== "Tab") return;
  const root = confirmDialog.value;
  if (!root) return;
  const focusable = Array.from(root.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ));
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
function handleHelpKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    event.preventDefault();
    showHelp.value = false;
    return;
  }
  if (event.key !== "Tab") return;
  const root = helpDialog.value;
  if (!root) return;
  const focusable = Array.from(root.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ));
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
watch(showHelp, (open) => {
  nextTick(() => {
    if (open) helpDialog.value?.querySelector<HTMLElement>("button")?.focus();
    else helpButton.value?.focus();
  });
});
function canOpenPage(key: string) {
  if (["dashboard", "drafts", "profile"].includes(key)) return true;
  if (["inventory", "query"].includes(key)) return has("phone:view");
  if (key === "documents") return has("phone:view") || has("report:view");
  if (key === "system") return canSystemManagement.value;
  if (key === "users") return canUserManagement.value;
  if (key === "admin") return canAdmin.value;
  return visibleTasks.value.some((task) => task.key === key);
}
function resetOperationEntry() {
  documentNo.value = "";
  logisticsNo.value = "";
  destinationOrganizationId.value = "";
  destinationLocationId.value = "";
  targetTrayCode.value = "";
  targetBoxCode.value = "";
  containerCode.value = "";
  scanInput.value = "";
  capturingContainer.value = false;
  accepted.value = true;
  salePrices.value = "";
  customerName.value = "";
  repairResult.value = "REPAIRED";
  disposition.value = "AVAILABLE_AGAIN";
  adjustmentDecision.value = "IGNORE";
  adjustmentTargetStatus.value = "可再次销售";
  transferReceiveComplete.value = true;
}
function startNewBatch() {
  const task = currentTask.value;
  if (!task) return;
  if (task.key === "query") {
    resetOperationEntry();
    scanned.value = [];
    lastSubmission.value = null;
    phoneDetail.value = null;
    error.value = "";
    message.value = "";
    scanNotice.value = "";
    api.beginOperation();
    focusScannerInput();
    return;
  }
  const workflow = activeWorkflow.value;
  // “开始新批次” means a genuinely new physical hand-off.  Clear the
  // workflow completion ledger and generated numbers together; otherwise an
  // old receiving/repair step could make a new batch look partially done.
  if (workflow) {
    resetWorkflowSession(workflow);
    const first = workflowDefinitions[workflow].find((step) => has(step.permission));
    if (first) {
      performWorkflowStep(first);
      message.value = "已开始新的批次，请从第一步按现场顺序作业";
    } else {
      resetOperationEntry();
      scanned.value = [];
      lastSubmission.value = null;
      message.value = "已清空上一批，可以开始新的作业";
    }
    return;
  }
  resetOperationEntry();
  scanned.value = [];
  lastSubmission.value = null;
  error.value = "";
  message.value = "已清空上一批，可以开始新的作业";
  api.beginOperation();
  if (!activeWorkflow.value && standalonePhaseDefinitions[task.key]) {
    standaloneProgress.value = { ...standaloneProgress.value, [task.key]: { documentNo: "", completedPhases: [] } };
  }
  focusOperationEntry();
}
function performSelect(key: string) {
  api.endOperation();
  resetSidebarScroll();
  ensureNavGroupVisible(["inventory", "documents", "drafts", "query"].includes(key) ? "collaboration" : ["profile", "admin", "system", "users"].includes(key) ? "account" : "operations");
  const menuTask = workflowTasks.find((task) => task.key === key);
  if (menuTask?.workflow) {
    if (activeWorkflow.value === menuTask.workflow && currentTask.value && !hasPendingOperationEntry()) return;
    resetOperationEntry();
    standaloneResume.value = null;
    activeWorkflow.value = menuTask.workflow;
    resetWorkflowSession(menuTask.workflow);
    const first = workflowDefinitions[menuTask.workflow].find((step) => has(step.permission));
    if (first) performWorkflowStep(first);
    else activeWorkflow.value = null;
    return;
  }
  activeWorkflow.value = null;
  standaloneResume.value = null;
  // Switching to a different standalone task must not carry a previous
  // shipment/return/repair number or destination into the next submission.
  resetOperationEntry();
  active.value = key;
  error.value = "";
  message.value = "";
  scanNotice.value = "";
  lastSubmission.value = null;
  scanned.value = [];
  phoneDetail.value = null;
  selectedInventory.value = null;
  selectedDocument.value = null;
  if (key === "profile" && user.value) { profileName.value = user.value.display_name; profileUsername.value = user.value.username || ""; currentPassword.value = ""; nextPassword.value = ""; }
  if (key === "users") adminTab.value = "users";
  if (key === "system") adminTab.value = has("role:manage") ? "roles" : has("user:manage") ? "organizations" : "audits";
  if (key === "admin") adminTab.value = has("user:manage") ? "users" : has("role:manage") ? "roles" : "audits";
  if (tasks.some((task) => task.key === key)) {
    const task = tasks.find((row) => row.key === key)!;
    const previousProgress = standaloneProgress.value[task.key];
    // Do not silently reuse a previous hand-off. Offer an explicit choice so
    // a worker can continue an interrupted batch without risking cross-batch
    // contamination.
    standaloneResume.value = previousProgress?.documentNo && previousProgress.carryToPhase
      ? { taskKey: task.key, progress: { ...previousProgress } }
      : null;
    if (!standaloneResume.value) {
      standaloneProgress.value = { ...standaloneProgress.value, [task.key]: { documentNo: "", completedPhases: [] } };
    }
    api.beginOperation();
    operationPhase.value = phaseFor(task);
    containerKind.value =
      task.key === "box" ? "TRAY" : task.mode === "imei" ? "PHONE" : "PHONE";
    capturingContainer.value = ["tray", "box"].includes(task.key);
    containerCode.value = "";
    syncTaskLocation();
  }
  window.scrollTo(0, 0);
  refresh();
  focusOperationEntry();
}
function select(key: string) {
  if (!canOpenPage(key)) {
    error.value = "当前账号没有访问此页面的权限，请联系管理员。";
    return;
  }
  requestLeave(() => performSelect(key));
}
function phaseFor(task: Task) {
  const choices: Record<string, [string, string][]> = {
    receiving: [
      ["start", "receiving:unpack"],
      ["inspect", "receiving:accept"],
    ],
    transfer: [
      ["issue", "transfer:create"],
      ["receive", "transfer:receive"],
    ],
    sales: [
      ["create", "sales:create"],
      ["confirm", "sales:approve"],
    ],
    return: [
      ["create", "return:create"],
      ["receive", "return:receive"],
    ],
    repair: [
      ["create", "repair:create"],
      ["accept", "repair:receive"],
      ["complete", "repair:update"],
      ["review", "repair:approve"],
    ],
    stocktake: [
      ["create", "stocktake:submit"],
      ["adjust", "stocktake:adjust"],
    ],
  };
  return (
    choices[task.key]?.find(([, permission]) => has(permission))?.[0] ||
    "create"
  );
}
function phaseCanCarryStandaloneDocument(taskKey: string, phase: string) {
  // 只把“上一阶段生成的单号”带入真正的后续承接阶段；回到新建/建立
  // 阶段必须重新录入来源单号，避免把旧单号误当成新批次。
  return (taskKey === "receiving" && phase === "inspect")
    || (taskKey === "transfer" && phase === "receive")
    || (taskKey === "sales" && phase === "confirm")
    || (taskKey === "return" && phase === "receive")
    || (taskKey === "repair" && ["accept", "complete", "review"].includes(phase))
    || (taskKey === "stocktake" && phase === "adjust");
}
function isStandaloneStartPhase(taskKey: string, phase: string) {
  return (taskKey === "receiving" && phase === "start")
    || (["transfer", "sales", "return", "repair", "stocktake"].includes(taskKey) && phase === "create")
    || (taskKey === "transfer" && phase === "issue");
}
type StandalonePhase = { phase: string; label: string; hint: string; permission: string };
const standalonePhaseDefinitions: Record<string, StandalonePhase[]> = {
  receiving: [
    { phase: "start", label: "建立到货单", hint: "按发运单开箱登记", permission: "receiving:unpack" },
    { phase: "inspect", label: "逐台验收", hint: "扫描 IMEI，记录正常/异常", permission: "receiving:accept" },
  ],
  transfer: [
    { phase: "issue", label: "发起调拨", hint: "按手机、托盘或箱子发出", permission: "transfer:create" },
    { phase: "receive", label: "调拨收货", hint: "按单号核对实收手机", permission: "transfer:receive" },
  ],
  sales: [
    { phase: "create", label: "创建销售单", hint: "扫描售出手机或容器", permission: "sales:create" },
    { phase: "confirm", label: "主管复核", hint: "输入销售单号确认金额", permission: "sales:approve" },
  ],
  return: [
    { phase: "create", label: "发起退回", hint: "门店整理后登记退回", permission: "return:create" },
    { phase: "receive", label: "接收分诊", hint: "拆箱拆托，逐台清点", permission: "return:receive" },
  ],
  repair: [
    { phase: "create", label: "建立维修单", hint: "把待修手机送入队列", permission: "repair:create" },
    { phase: "accept", label: "维修接收", hint: "确认技师接收设备", permission: "repair:receive" },
    { phase: "complete", label: "填写维修结果", hint: "逐台记录维修结论", permission: "repair:update" },
    { phase: "review", label: "QA 复核", hint: "决定恢复可售/冻结/报损", permission: "repair:approve" },
  ],
  stocktake: [
    { phase: "create", label: "现场盘点", hint: "扫描现场看到的 IMEI", permission: "stocktake:submit" },
    { phase: "adjust", label: "审核差异", hint: "确认缺失或接收多出", permission: "stocktake:adjust" },
  ],
};
const standalonePhaseSteps = computed(() => {
  const task = currentTask.value;
  if (!task || activeWorkflow.value) return [];
  return (standalonePhaseDefinitions[task.key] || []).filter((step) => has(step.permission));
});
const nextStandalonePhase = computed(() => {
  if (activeWorkflow.value || !currentTask.value || !lastSubmission.value || !standalonePhaseDone(operationPhase.value)) return null;
  const index = standalonePhaseSteps.value.findIndex((step) => step.phase === operationPhase.value);
  return index >= 0 ? standalonePhaseSteps.value[index + 1] || null : null;
});
function selectStandalonePhase(step: StandalonePhase) {
  const task = currentTask.value;
  if (!task || !has(step.permission) || step.phase === operationPhase.value) return;
  const progress = standaloneProgress.value[task.key];
  const carryStandalone = Boolean(
    lastSubmission.value
      && progress?.sourcePhase === operationPhase.value
      && progress?.carryToPhase === step.phase
      && ((lastSubmission.value.no && lastSubmission.value.no === progress.documentNo)
        || (!lastSubmission.value.no && documentNo.value.trim() === progress.documentNo)),
  );
  requestLeave(() => {
    activeWorkflow.value = null;
    standaloneResume.value = null;
    if (isStandaloneStartPhase(task.key, step.phase) && !carryStandalone) {
      standaloneProgress.value = { ...standaloneProgress.value, [task.key]: { documentNo: "", completedPhases: [] } };
    }
    activateTask(task, step.phase, { carryStandalone });
    refresh();
  });
}
function resumeStandaloneBatch() {
  const task = currentTask.value;
  const prompt = standaloneResume.value;
  if (!task || !prompt || prompt.taskKey !== task.key) return;
  standaloneResume.value = null;
  const phase = prompt.progress.carryToPhase || standalonePhaseSteps.value.find((step) => !prompt.progress.completedPhases.includes(step.phase))?.phase || phaseFor(task);
  activateTask(task, phase, { carryStandalone: Boolean(prompt.progress.carryToPhase) });
  refresh();
}
function discardStandaloneBatch() {
  const task = currentTask.value;
  if (!task || !standaloneResume.value || standaloneResume.value.taskKey !== task.key) return;
  standaloneProgress.value = { ...standaloneProgress.value, [task.key]: { documentNo: "", completedPhases: [] } };
  standaloneResume.value = null;
  activateTask(task, phaseFor(task));
  refresh();
}
function standalonePhaseDone(phase: string) {
  const task = currentTask.value?.key;
  return Boolean(task && standaloneProgress.value[task]?.completedPhases.includes(phase));
}
function standaloneResumeComplete(progress: StandaloneProgress) {
  return Boolean(progress.phaseComplete !== false
    && progress.sourcePhase
    && progress.completedPhases.includes(progress.sourcePhase));
}
function isValidImei(value: string) { if (!/^\d{15}$/.test(value)) return false; let total = 0; for (let index = 0; index < value.length; index += 1) { let digit = Number(value[index]); if (index % 2 === 1) { digit *= 2; if (digit > 9) digit -= 9; } total += digit; } return total % 10 === 0; }
function phaseRequiresScan() {
  const task = currentTask.value;
  if (!task) return true;
  return !((task.key === "receiving" && operationPhase.value === "start") || (task.key === "sales" && operationPhase.value === "confirm") || (task.key === "repair" && operationPhase.value === "accept"));
}
function scanInputDisabled() {
  if (!currentTask.value || !phaseRequiresScan()) return true;
  if (phaseRequiresCurrentLocation() && !locationId.value) return true;
  if (phaseRequiresDestination() && !destinationLocationId.value) return true;
  if (phaseRequiresDocumentInput() && !documentNo.value.trim()) return true;
  return false;
}
function canCloseTransferAfterPartial() {
  return currentTask.value?.key === "transfer"
    && operationPhase.value === "receive"
    && transferReceiveComplete.value
    && lastSubmission.value?.complete === false;
}
function scanMode() {
  const task = currentTask.value;
  if (!task) return "imei";
  if (capturingContainer.value && ["tray", "box"].includes(task.key)) return "container";
  // Shipment/transfer/sales/return/repair let the operator choose whether
  // to scan individual phones or a tray/box.  Respect that choice so a
  // malformed value cannot pass client validation merely because the task's
  // default mode is container-level.
  if (["shipment", "transfer", "sales", "return", "repair"].includes(task.key)) {
    return containerKind.value === "PHONE" ? "imei" : "container";
  }
  return task.mode;
}
function phaseRequiresCurrentLocation() { const key = currentTask.value?.key; return Boolean(key && (["purchase", "tray", "box", "shipment"].includes(key) || (key === "receiving" && operationPhase.value === "start") || (key === "transfer" && operationPhase.value === "issue") || (key === "sales" && operationPhase.value === "create") || (key === "return" && operationPhase.value === "create") || (key === "repair") || (key === "stocktake" && operationPhase.value === "create"))); }
function phaseRequiresDestination() { const key = currentTask.value?.key; return key === "shipment" || (key === "transfer" && operationPhase.value === "issue") || (key === "return" && operationPhase.value === "create"); }
function syncTaskLocation() {
  if (!phaseRequiresCurrentLocation()) {
    locationId.value = "";
    organizationId.value = "";
    return;
  }
  const current = workLocations.value.find((item) => String(item.id) === locationId.value);
  if (current && locationAllowed(currentPhasePermission(), current) && businessLocationAllowed(current)) {
    organizationId.value = String(current.organization_id);
    return;
  }
  const allowed = workLocations.value.filter((item) => locationAllowed(currentPhasePermission(), item) && businessLocationAllowed(item));
  if (allowed.length === 1) {
    locationId.value = String(allowed[0].id);
    syncOrganization();
  } else {
    locationId.value = "";
    organizationId.value = "";
  }
}
watch(operationPhase, () => {
  if (currentTask.value) syncTaskLocation();
  if (currentTask.value?.key === "transfer" && operationPhase.value === "receive") containerKind.value = "PHONE";
});
watch(locationId, (next, previous) => {
  if (next === previous) return;
  syncOrganization();
  if (phaseRequiresDestination() && destinationLocationId.value
    && !destinationLocations.value.some((item) => String(item.id) === destinationLocationId.value)) {
    destinationLocationId.value = "";
    destinationOrganizationId.value = "";
    message.value = "当前地点已改变，请重新选择目标地点";
  }
  // Location is the first context gate. Once it is selected, put the cursor
  // on the next actionable field so a scanner-station operator can continue
  // without an extra mouse click (required document, destination, or IMEI).
  if (next) nextTick(() => focusOperationEntry());
});
watch(destinationLocationId, (next, previous) => {
  if (next === previous || !next) return;
  nextTick(() => focusOperationEntry());
});
watch(accepted, (next) => {
  if (!next) {
    // An abnormal arrival must never carry a previously entered destination
    // tray/box into the API payload by accident.
    targetTrayCode.value = "";
    targetBoxCode.value = "";
  }
});
function setContainerRadioRef(value: string, element: unknown) {
  containerRadioRefs.value[value] = element instanceof HTMLInputElement ? element : null;
}
function focusContainerRadio(value: string) {
  nextTick(() => containerRadioRefs.value[value]?.focus({ preventScroll: true }));
}
function selectContainerKind(nextValue: string, keepRadioFocus = false) {
  if (!currentTask.value || !phaseCanChooseContainerKind()) return;
  if (!(nextValue === "PHONE" || nextValue === "TRAY" || nextValue === "BOX")) return;
  const next = nextValue as "PHONE" | "TRAY" | "BOX";
  if (next === containerKind.value) return;
  if (!scanned.value.length) {
    containerKind.value = next;
    if (currentTask.value.key === "sales" && operationPhase.value === "create" && next !== "PHONE") salePrices.value = "";
    scanInput.value = "";
    if (keepRadioFocus) focusContainerRadio(next);
    else focusScannerInput();
    return;
  }
  // Never reinterpret already captured IMEIs as tray/box codes (or the
  // reverse). Ask before clearing the batch; the radio remains on the old
  // value until the operator confirms.
  openConfirmation(
    () => {
      containerKind.value = next;
      if (currentTask.value?.key === "sales" && operationPhase.value === "create" && next !== "PHONE") salePrices.value = "";
      scanned.value = [];
      scanInput.value = "";
      scanNotice.value = "已切换装载单位，请从新单位开始扫描";
      lastSubmission.value = null;
      if (keepRadioFocus) focusContainerRadio(next);
      else focusScannerInput();
    },
    "切换本次装载单位？",
    `当前清单已有 ${scanned.value.length} 项。切换后会清空清单，避免把手机编码误当成${next === "PHONE" ? "手机" : next === "TRAY" ? "托盘" : "箱子"}之外的编码。`,
  );
}
function handleContainerKindKeydown(event: KeyboardEvent, currentValue: string) {
  // The browser's native radio arrow behavior is not consistent when the
  // checked state is controlled by Vue. Keep an explicit roving focus model
  // so scanner-station operators can move PHONE → TRAY → BOX without a mouse.
  if ([" ", "Spacebar", "Space", "Enter"].includes(event.key)) {
    event.preventDefault();
    selectContainerKind(currentValue, true);
    return;
  }
  const order = ["PHONE", "TRAY", "BOX"];
  const index = order.indexOf(currentValue);
  if (index < 0) return;
  const delta = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 0;
  if (!delta) return;
  event.preventDefault();
  selectContainerKind(order[(index + delta + order.length) % order.length], true);
}
watch([inventorySearch, inventoryStatusFilter, inventoryLocationFilter, inventoryPageSize], () => { inventoryPage.value = 1; });
watch([documentsSearch, documentsTypeFilter, documentsStatusFilter, documentsPageSize], () => { documentsPage.value = 1; });
watch(scopeKind, () => {
  // 地点、组织、国家共用一个选择值；切换类型时必须清空旧值，
  // 防止把地点 ID 误提交成组织或国家范围。
  scopeValue.value = "";
});
function focusScannerInput() {
  nextTick(() => {
    if (!scanInputDisabled()) scannerInput.value?.focus({ preventScroll: true });
  });
}
function focusOperationEntry() {
  nextTick(() => {
    // Follow the same order shown on screen: current location → destination
    // → required document → scanner.  Focusing a document first while the
    // location is still empty made new operators skip the most important
    // context check on multi-location accounts.
    if (phaseRequiresCurrentLocation() && !locationId.value) {
      document.getElementById("current-location")?.focus({ preventScroll: true });
      return;
    }
    if (phaseRequiresDestination() && !destinationLocationId.value) {
      document.getElementById("destination-location")?.focus({ preventScroll: true });
      return;
    }
    if (phaseRequiresDocumentInput() && !documentNo.value.trim()) {
      documentInput.value?.focus({ preventScroll: true });
      return;
    }
    if (!scanInputDisabled()) scannerInput.value?.focus({ preventScroll: true });
  });
}
function resetSidebarScroll() {
  // Only the navigation list scrolls. Returning it to the top keeps the
  // account control anchored at the bottom and makes every page start from
  // the same visible set of actions.
  nextTick(() => {
    if (navGroupsRef.value) navGroupsRef.value.scrollTop = 0;
  });
}
function toggleNavGroup(group: string) {
  navGroupExpanded.value[group] = !navGroupExpanded.value[group];
}
function toggleSidebarCollapsed() {
  closeAccountMenu(false);
  sidebarCollapsed.value = !sidebarCollapsed.value;
}
function ensureNavGroupVisible(group: string) {
  if (group in navGroupExpanded.value) navGroupExpanded.value[group] = true;
}
function toggleAccountMenu() {
  accountMenuOpen.value = !accountMenuOpen.value;
  if (accountMenuOpen.value) {
    nextTick(() => accountMenu.value?.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true }));
  }
}
function closeAccountMenu(restoreFocus = true) {
  const wasOpen = accountMenuOpen.value;
  accountMenuOpen.value = false;
  if (wasOpen && restoreFocus) {
    nextTick(() => accountToggleButton.value?.focus({ preventScroll: true }));
  }
}
function closeAccountAfterNavigation() {
  // If a warehouse batch is pending, requestLeave() opens a confirmation
  // dialog. The menu item is removed immediately afterwards, so return focus
  // to the persistent account trigger instead of a detached menu button.
  if (showConfirm.value) confirmationReturnFocus.value = accountToggleButton.value;
  closeAccountMenu(false);
}
function openProfileFromAccount() {
  select("profile");
  closeAccountAfterNavigation();
}
function openAdminFromAccount() {
  select(canSystemManagement.value ? "system" : canUserManagement.value ? "users" : "admin");
  closeAccountAfterNavigation();
}
function logoutFromAccount() {
  logout();
  closeAccountAfterNavigation();
}
function handleAccountMenuKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    event.preventDefault();
    // Keep the event inside the menu.  Otherwise the document-level handler
    // sees the same Escape after the menu closes and also dismisses the
    // off-canvas sidebar on narrow screens.
    event.stopPropagation();
    closeAccountMenu();
    return;
  }
  if (event.key !== "Tab" || !accountMenu.value) return;
  const items = Array.from(accountMenu.value.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"));
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
function handleAccountOutsidePointerdown(event: PointerEvent) {
  if (!accountMenuOpen.value) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (accountMenu.value?.contains(target) || accountToggleButton.value?.contains(target)) return;
  closeAccountMenu(false);
}
function openSidebar() {
  closeAccountMenu(false);
  if (window.innerWidth <= 1080) sidebarCollapsed.value = false;
  sidebarOpen.value = true;
  nextTick(() => sidebarCloseButton.value?.focus({ preventScroll: true }));
}
function closeSidebar() {
  const wasOpen = sidebarOpen.value;
  sidebarOpen.value = false;
  closeAccountMenu(false);
  // On a narrow screen the menu toggle is the logical return point.  Avoid
  // moving focus on desktop, where the sidebar is permanently visible and
  // selecting a page should leave focus in the new page's first control.
  if (wasOpen && window.innerWidth <= 1080 && !showConfirm.value && !showHelp.value) {
    nextTick(() => menuToggleButton.value?.focus({ preventScroll: true }));
  }
}
function handleWindowKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && accountMenuOpen.value && !showConfirm.value && !showHelp.value) {
    event.preventDefault();
    closeAccountMenu();
    return;
  }
  if (event.key === "Escape" && sidebarOpen.value && !showConfirm.value && !showHelp.value) {
    event.preventDefault();
    closeSidebar();
  }
}
function isValidContainerCode(value: string) {
  return /^[A-Za-z0-9][A-Za-z0-9._/-]{2,63}$/.test(value);
}
function addScan() {
  const rawValue = scanInput.value.trim();
  const value = scanMode() === "imei" ? rawValue.replace(/\s+/g, "") : rawValue;
  if (!value) return;
  const task = currentTask.value;
  if (capturingContainer.value && task && ["tray", "box"].includes(task.key)) {
    if (!isValidContainerCode(value) || /^\d{15}$/.test(value)) {
      error.value = `请输入有效的${task.key === "tray" ? "托盘" : "箱子"}编码（3-64 位字母、数字或 -/_/.）`;
      scanNotice.value = "目标容器还未确认";
      scanInput.value = "";
      focusScannerInput();
      return;
    }
    containerCode.value = value;
    capturingContainer.value = false;
    scanInput.value = "";
    error.value = "";
    scanNotice.value = `目标${task.key === "tray" ? "托盘" : "箱子"}已锁定：${value}`;
    message.value = "";
    focusScannerInput();
    return;
  }
  if (scanMode() === "imei" && !isValidImei(value)) {
    error.value = "IMEI 必须是通过校验的 15 位数字";
    scanNotice.value = "本次输入未加入清单，请重新扫描";
    // 丢弃本次无效输入，避免下一次扫码与旧内容拼接
    scanInput.value = "";
    focusScannerInput();
    return;
  }
  if (scanMode() !== "imei" && !isValidContainerCode(value)) {
    error.value = "容器编码格式不正确，请检查标签后重试";
    scanNotice.value = "本次输入未加入清单，请重新扫描";
    scanInput.value = "";
    focusScannerInput();
    return;
  }
  if (scanned.value.includes(value)) {
    error.value = `重复扫描：${value}`;
    scanNotice.value = "重复项不会再次加入，请核对手边物料";
    scanInput.value = "";
    focusScannerInput();
    return;
  }
  lastSubmission.value = null;
  if (task?.key === "query") phoneDetail.value = null;
  scanned.value.push(value);
  error.value = "";
  scanNotice.value = `已加入第 ${scanned.value.length} 项`;
  scanInput.value = "";
  focusScannerInput();
}
async function submitQuery() {
  if (currentTask.value?.key !== "query") {
    addScan();
    return;
  }
  const rawValue = scanInput.value.trim().replace(/\s+/g, "");
  if (rawValue) {
    if (!isValidImei(rawValue)) {
      error.value = "IMEI 必须是通过校验的 15 位数字";
      scanNotice.value = "本次输入未开始查询，请重新输入";
      scanInput.value = "";
      focusScannerInput();
      return;
    }
    scanned.value = [rawValue];
    scanInput.value = "";
  }
  if (!scanned.value.length) {
    error.value = "请输入或扫描一台手机的 IMEI";
    scanNotice.value = "还没有可查询的 IMEI";
    focusScannerInput();
    return;
  }
  await submit();
}
function onScanInput() {
  // 部分扫码枪配置为仅输出字符、不追加回车；IMEI 满 15 位时自动加入
  if (scanMode() === "imei" && /^\d{15}$/.test(scanInput.value)) addScan();
}
function performRecaptureContainer() {
  const task = currentTask.value;
  if (!task || !["tray", "box"].includes(task.key)) return;
  containerCode.value = "";
  capturingContainer.value = true;
  scanned.value = [];
  error.value = "";
  message.value = "";
  scanNotice.value = `请先扫描目标${task.key === "tray" ? "托盘" : "箱子"}编码`;
  nextTick(() => scannerInput.value?.focus({ preventScroll: true }));
}
function recaptureContainer() {
  const task = currentTask.value;
  if (!task || !["tray", "box"].includes(task.key)) return;
  if (hasPendingOperationEntry()) {
    openConfirmation(
      performRecaptureContainer,
      `重新扫描目标${task.key === "tray" ? "托盘" : "箱子"}？`,
      `当前批次已有${pendingEntryDescription()}。重新扫描会清空这些内容，请确认手边实物已经换批。`,
    );
    return;
  }
  performRecaptureContainer();
}
function clearScanned() {
  if (!scanned.value.length) return;
  openConfirmation(
    () => {
      scanned.value = [];
      scanNotice.value = "";
      lastSubmission.value = null;
      focusScannerInput();
    },
    "清空本批扫描？",
    `将移除已读取的 ${scanned.value.length} 项，清空后不能自动恢复。`,
  );
}
function syncOrganization() {
  const row = workLocations.value.find(
    (item) => String(item.id) === locationId.value,
  );
  organizationId.value = row ? String(row.organization_id) : "";
}
function syncDestinationOrganization() {
  const row = workLocations.value.find(
    (item) => String(item.id) === destinationLocationId.value,
  );
  destinationOrganizationId.value = row ? String(row.organization_id) : "";
}
function containers() {
  return scanned.value.map((code) => ({ kind: containerKind.value, code }));
}
function clientId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
// Offline work belongs to the signed-in operator.  Keeping the queue scoped
// by user prevents a shared PC/browser from showing another operator's draft
// shipments or IMEI lists after a logout/login switch.
function offlineQueueKey() {
  const identity = user.value?.id ?? user.value?.username ?? user.value?.phone ?? "anonymous";
  return `gh-phone-offline-queue:${identity}`;
}
function readOfflineDrafts(): Draft[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(offlineQueueKey()) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}
function persistOfflineDrafts() {
  localStorage.setItem(offlineQueueKey(), JSON.stringify(drafts.value));
  dashboardStats.value = {
    ...dashboardStats.value,
    pendingDrafts: drafts.value.filter((item) => item.status !== "synced").length,
  };
}
function saveDraft(task: Task) {
  const draft: Draft = {
    id: clientId(),
    action: task.key,
    phase: operationPhase.value,
    values: [...scanned.value],
    organization_id: organizationId.value,
    location_id: locationId.value,
    destination_organization_id: destinationOrganizationId.value,
    destination_location_id: destinationLocationId.value,
    container_kind: containerKind.value,
    container_code: containerCode.value,
    document_no: documentNo.value,
    logistics_no: logisticsNo.value,
    target_tray_code: targetTrayCode.value,
    target_box_code: targetBoxCode.value,
    sales_type: salesType.value,
    customer_name: customerName.value,
    sale_prices: salePrices.value,
    repair_result: repairResult.value,
    disposition: disposition.value,
    adjustment_decision: adjustmentDecision.value,
    adjustment_target_status: adjustmentTargetStatus.value,
    transfer_receive_complete: transferReceiveComplete.value,
    workflow: activeWorkflow.value,
    accepted: accepted.value,
    status: "pending",
    created_at: new Date().toISOString(),
  };
  drafts.value.unshift(draft);
  persistOfflineDrafts();
  return draft;
}
async function submit() {
  const task = currentTask.value;
  if (!task) return;
  if (submitDisabledReason.value) {
    error.value = submitDisabledReason.value;
    return;
  }
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    const org = Number(organizationId.value);
    const loc = Number(locationId.value);
    let result: any;
    if (task.key === "query") { result = await api.getPhone(scanned.value[0]); phoneDetail.value = result; }
    else if (task.key === "purchase")
      result = await api.createPurchaseReceipt({
        organization_id: org,
        location_id: loc,
        items: scanned.value.map((imei) => ({ imei })),
      });
    else if (task.key === "tray")
      result = await api.createTray({
        code: containerCode.value.trim(),
        location_id: loc,
        imeis: scanned.value,
      });
    else if (task.key === "box")
      result = await api.createBox({
        code: containerCode.value.trim(),
        location_id: loc,
        tray_codes: scanned.value,
      });
    else if (task.key === "shipment")
      result = await api.dispatchShipment({
        origin_organization_id: org,
        origin_location_id: loc,
        destination_organization_id: Number(destinationOrganizationId.value),
        destination_location_id: Number(destinationLocationId.value),
        logistics_no: logisticsNo.value || null,
        containers: containers(),
      });
    else if (task.key === "receiving") {
      if (operationPhase.value === "start") {
        result = await api.startReceiving({ shipment_no: documentNo.value.trim(), organization_id: org, location_id: loc });
        documentNo.value = String(result.receiving_no);
        if (activeWorkflow.value === "ghana") workflowDocuments.value[workflowDocumentKey("ghana", "receiving", "start")] = String(result.receiving_no);
      }
      else for (const imei of scanned.value) {
        api.endOperation(); api.beginOperation();
        result = await api.inspectReceiving({ receiving_no: documentNo.value.trim(), imei, accepted: accepted.value, note: null, target_tray_code: accepted.value ? (targetTrayCode.value.trim() || null) : null, target_box_code: accepted.value ? (targetBoxCode.value.trim() || null) : null });
      }
    }
    else if (task.key === "transfer")
      result =
        operationPhase.value === "issue"
          ? await api.issueTransfer({
              source_organization_id: org,
              source_location_id: loc,
              destination_organization_id: Number(
                destinationOrganizationId.value,
              ),
              destination_location_id: Number(destinationLocationId.value),
              containers: containers(),
            })
          : await api.receiveTransfer({
              transfer_no: documentNo.value.trim(),
              received_imeis: scanned.value,
              complete: transferReceiveComplete.value,
            });
    else if (task.key === "sales")
      result =
        operationPhase.value === "create"
          ? await api.createSale({
              organization_id: org,
              location_id: loc,
              sales_type: salesType.value,
              customer_name: customerName.value || null,
              containers: containers(),
              prices: containerKind.value === "PHONE" && salePrices.value
                ? Object.fromEntries(
                    scanned.value.map((imei, index) => [
                      imei,
                      salePrices.value.split(",")[index]?.trim() ||
                        salePrices.value.trim(),
                    ]),
                  )
                : {},
            })
          : await api.confirmSale(documentNo.value.trim());
    else if (task.key === "return")
      result =
        operationPhase.value === "create"
          ? await api.createReturn({
              sales_no: documentNo.value.trim(),
              source_organization_id: org,
              source_location_id: loc,
              destination_organization_id: Number(
                destinationOrganizationId.value,
              ),
              destination_location_id: Number(destinationLocationId.value),
              imeis: containerKind.value === "PHONE" ? scanned.value : [],
              containers: containerKind.value === "PHONE" ? [] : containers(),
            })
          : await api.receiveReturn({
              return_no: documentNo.value.trim(),
              received_imeis: scanned.value,
            });
    else if (task.key === "repair")
      result =
        operationPhase.value === "create"
          ? await api.createRepair({
              organization_id: org,
              location_id: loc,
              imeis: containerKind.value === "PHONE" ? scanned.value : [],
              containers: containerKind.value === "PHONE" ? [] : containers(),
              return_no: activeWorkflow.value === "ghana" ? (documentNo.value.trim() || null) : null,
            })
          : operationPhase.value === "accept"
            ? await api.acceptRepair(documentNo.value.trim())
              : operationPhase.value === "complete"
                ? await (async () => { for (const imei of scanned.value) { api.endOperation(); api.beginOperation(); result = await api.completeRepair(documentNo.value.trim(), { imei, repair_result: repairResult.value }); } return result; })()
                : await (async () => { for (const imei of scanned.value) { api.endOperation(); api.beginOperation(); result = await api.reviewRepair(documentNo.value.trim(), { imei, disposition: disposition.value }); } return result; })();
    else if (task.key === "stocktake")
      result =
        operationPhase.value === "adjust"
          ? await api.adjustStocktake(
              documentNo.value.trim(),
              scanned.value.map((imei) => ({
                imei,
                decision: adjustmentDecision.value,
                target_status: adjustmentTargetStatus.value,
              })),
            )
          : await api.submitStocktake({
              organization_id: org,
              location_id: loc,
              imeis: scanned.value,
            });
    const resultNo = result && typeof result === "object"
      ? (result.order_no || result.shipment_no || result.receiving_no || result.transfer_no || result.sales_no || result.return_no || result.repair_no || result.stocktake_no)
      : null;
    const resultCount = result && typeof result === "object"
      ? (task.key === "receiving" && operationPhase.value === "inspect"
          ? Number(result.accepted_count || 0) + Number(result.exception_count || 0)
          : result.total_count ?? result.accepted_count ?? result.received_count ?? result.completed_count ?? result.found_count ?? scanned.value.length)
      : scanned.value.length;
    const resultComplete = operationResultComplete(task.key, operationPhase.value, result);
    // Keep every generated number under the workflow's task key.  The next
    // phase can then receive it without asking the operator to retype it.
    if (activeWorkflow.value && resultNo) {
      workflowDocuments.value[workflowDocumentKey(activeWorkflow.value, task.key, operationPhase.value)] = String(resultNo);
    }
    if (task.key === "return" && operationPhase.value === "receive" && activeWorkflow.value === "ghana") {
      workflowDocuments.value["ghana:return"] = String(resultNo || documentNo.value.trim());
    }
    if (activeWorkflow.value && currentWorkflowStep.value && resultComplete) {
      const workflow = activeWorkflow.value;
      workflowCompletedSteps.value = {
        ...workflowCompletedSteps.value,
        [workflow]: Array.from(new Set([
          ...workflowCompletedSteps.value[workflow],
          currentWorkflowStep.value.key,
        ])),
      };
    }
    // Keep the generated business number available for the next standalone
    // phase (issue → receive, create → review, etc.).  It is recorded only
    // after the API call succeeds, so an unfinished/failed batch is never
    // shown as completed in the phase switcher.
    if (!activeWorkflow.value && standalonePhaseDefinitions[task.key]) {
      const handoffNo = resultNo ? String(resultNo) : documentNo.value.trim();
      if (handoffNo) {
        const previous = standaloneProgress.value[task.key];
        const nextPhase = resultComplete
          ? standalonePhaseDefinitions[task.key]
              ?.filter((step) => has(step.permission))
              .find((step) => {
                const currentIndex = standalonePhaseDefinitions[task.key].findIndex((item) => item.phase === operationPhase.value);
                const candidateIndex = standalonePhaseDefinitions[task.key].findIndex((item) => item.phase === step.phase);
                return candidateIndex > currentIndex;
              })?.phase || ""
          : operationPhase.value;
        standaloneProgress.value = {
          ...standaloneProgress.value,
          [task.key]: {
            documentNo: handoffNo,
            completedPhases: resultComplete
              ? Array.from(new Set([...(previous?.completedPhases || []), operationPhase.value]))
              : (previous?.completedPhases || []).filter((phase) => phase !== operationPhase.value),
            sourcePhase: operationPhase.value,
            carryToPhase: nextPhase,
            phaseComplete: resultComplete,
          },
        };
      }
    }
    message.value =
      task.key === "query"
        ? ""
        : resultComplete
          ? `${task.label}已完成${resultNo ? `，单号：${resultNo}` : ""}`
          : `${task.label}本次已记录${resultNo ? `，单号：${resultNo}` : ""}；当前单据尚未完成，请继续扫描剩余明细`;
    lastSubmission.value = {
      no: resultNo ? String(resultNo) : undefined,
      count: Number(resultCount || 0),
      status: result?.status ? String(result.status) : "已完成",
      complete: resultComplete,
      text: task.key === "query"
        ? "查询完成"
        : resultComplete
          ? `${task.label}已成功提交，可按下方提示交接。`
          : `${task.label}已记录本次明细，请继续处理当前单据。`,
    };
    if (task.key !== "query") {
      scanned.value = [];
      // The key protects a double-click/retry of this physical submission,
      // but must not leak into the next batch entered on the same page.  Keep
      // the key on failed/offline requests so a queued retry remains safe.
      api.endOperation();
      api.beginOperation();
    }
  } catch (e) {
    if (!online.value || e instanceof TypeError) {
      saveDraft(task);
      message.value = "网络不可用，已保存为待同步草稿";
      error.value = "";
    } else error.value = e instanceof Error ? e.message : "提交失败";
  } finally {
    loading.value = false;
    if (task.key === "query" && phoneDetail.value) {
      // 查询结果与输入区共用一张卡片。不要调用 scrollIntoView：它会把
      // 整张卡片滚到最底部，导致标题和查询框被顶到页头下面。结果已
      // 进入卡片后保持当前位置，用户仍可在卡片内继续查看完整轨迹。
      nextTick(() => {
        const card = document.querySelector<HTMLElement>(".query-operation-card");
        if (card) card.scrollTop = Math.min(card.scrollTop, Math.max(0, card.scrollHeight - card.clientHeight));
      });
    } else focusScannerInput();
  }
}
function continueCurrentPhase() {
  if (!lastSubmission.value || lastSubmission.value.complete !== false) return;
  lastSubmission.value = null;
  message.value = "请继续扫描当前单据的剩余明细，全部处理后再交接";
  scanNotice.value = "当前单据尚未完成，请继续扫描";
  focusScannerInput();
}
async function refresh() {
  if (!user.value) return;
  refreshLoading.value = true;
  try {
    if (active.value === "dashboard") {
      const phoneResult = has("phone:view") ? await api.listPhones({ limit: 500 }) : { items: [], count: 0 };
      const documentResult = has("phone:view") || has("report:view") ? await api.listDocuments({ limit: 500 }) : { items: [], count: 0 };
      rememberDocumentLocations(documentResult.items);
      const localDrafts = readOfflineDrafts();
      dashboardStats.value = { phones: phoneResult.count, documents: documentResult.count, pendingDrafts: localDrafts.filter((item: any) => item.status !== "synced").length };
    } else if (active.value === "inventory")
      inventory.value = (await api.listPhones({ limit: 500 })).items;
    else if (active.value === "documents") {
      documents.value = (await api.listDocuments({ limit: 500 })).items;
      rememberDocumentLocations(documents.value);
    }
    else if (active.value === "drafts") {
      drafts.value = readOfflineDrafts();
      dashboardStats.value = {
        ...dashboardStats.value,
        pendingDrafts: drafts.value.filter((item) => item.status !== "synced").length,
      };
    }
    else if (["admin", "system", "users"].includes(active.value)) await loadAdmin();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  } finally {
    refreshLoading.value = false;
  }
}
async function loadAdmin() {
  const canUsers = has("user:manage");
  const canRoles = has("role:manage");
  const [organizations, locations, users, roles, permissions, audits] =
    await Promise.all([
      canUsers ? api.listOrganizations() : Promise.resolve([]),
      canUsers ? api.listLocations() : Promise.resolve([]),
      canUsers ? api.listUsers() : Promise.resolve([]),
      canUsers || canRoles ? api.listRoles() : Promise.resolve([]),
      canRoles ? api.listPermissions() : Promise.resolve([]),
      has("audit:view") ? api.listAudits() : Promise.resolve([]),
    ]);
  adminData.value = {
    organizations,
    locations,
    users,
    roles,
    permissions,
    audits,
  };
}
function handleAdminTabKeydown(event: KeyboardEvent) {
  if (!['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
  const target = event.target;
  if (!(target instanceof HTMLButtonElement) || target.getAttribute('role') !== 'tab') return;
  const tabs = Array.from((target.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]') || []));
  if (!tabs.length) return;
  const currentIndex = tabs.indexOf(target);
  if (currentIndex < 0) return;
  const nextIndex = event.key === 'Home'
    ? 0
    : event.key === 'End'
      ? tabs.length - 1
      : (currentIndex + (['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1) + tabs.length) % tabs.length;
  const next = tabs[nextIndex];
  const tabById: Record<string, "users" | "organizations" | "locations" | "roles" | "audits"> = {
    'admin-tab-users': 'users',
    'admin-tab-organizations': 'organizations',
    'admin-tab-locations': 'locations',
    'admin-tab-roles': 'roles',
    'admin-tab-audits': 'audits',
  };
  const nextValue = tabById[next.id];
  if (!nextValue) return;
  event.preventDefault();
  adminTab.value = nextValue;
  next.focus();
}
async function retryDraft(draft: Draft) {
  if (!online.value) return;
  draft.status = "syncing";
  draft.error = "";
  const processedValues: string[] = [];
  let result: any = null;
  try {
    api.setOperationKey(draft.id);
    const task = tasks.find((item) => item.key === draft.action);
    if (!task) throw new Error("未知草稿类型");
    const org = Number(draft.organization_id);
    const loc = Number(draft.location_id);
    const destination = {
      destination_organization_id: Number(draft.destination_organization_id),
      destination_location_id: Number(draft.destination_location_id),
    };
    if (draft.action === "purchase") {
      result = await api.createPurchaseReceipt({ organization_id: org, location_id: loc, items: draft.values.map((imei) => ({ imei })) });
    } else if (draft.action === "tray") {
      result = await api.createTray({ code: draft.container_code, location_id: loc, imeis: draft.values });
    } else if (draft.action === "box") {
      result = await api.createBox({ code: draft.container_code, location_id: loc, tray_codes: draft.values });
    } else if (draft.action === "shipment") {
      result = await api.dispatchShipment({ origin_organization_id: org, origin_location_id: loc, ...destination, logistics_no: draft.logistics_no || null, containers: draft.values.map((code) => ({ kind: draft.container_kind, code })) });
    } else if (draft.action === "receiving") {
      if (draft.phase === "start") {
        result = await api.startReceiving({ shipment_no: draft.document_no, organization_id: org, location_id: loc });
        draft.document_no = String(result.receiving_no);
      } else {
        for (const [index, imei] of draft.values.entries()) {
          api.setOperationKey(`${draft.id}:${index}`);
          result = await api.inspectReceiving({ receiving_no: draft.document_no, imei, accepted: draft.accepted, note: null, target_tray_code: draft.accepted ? (draft.target_tray_code || null) : null, target_box_code: draft.accepted ? (draft.target_box_code || null) : null });
          processedValues.push(imei);
        }
      }
    } else if (draft.action === "transfer") {
      result = draft.phase === "issue"
        ? await api.issueTransfer({ source_organization_id: org, source_location_id: loc, ...destination, containers: draft.values.map((code) => ({ kind: draft.container_kind, code })) })
        : await api.receiveTransfer({ transfer_no: draft.document_no, received_imeis: draft.values, complete: draft.transfer_receive_complete !== false });
    } else if (draft.action === "sales") {
      result = draft.phase === "create"
        ? await api.createSale({
            organization_id: org,
            location_id: loc,
            sales_type: draft.sales_type || "RETAIL",
            customer_name: draft.customer_name || null,
            containers: draft.values.map((code) => ({ kind: draft.container_kind, code })),
            prices: draft.container_kind === "PHONE" && draft.sale_prices
              ? Object.fromEntries(draft.values.map((imei, index) => [imei, draft.sale_prices!.split(",")[index]?.trim() || draft.sale_prices!.trim()]))
              : {},
          })
        : await api.confirmSale(draft.document_no);
    } else if (draft.action === "return") {
      result = draft.phase === "create"
        ? await api.createReturn({ sales_no: draft.document_no, source_organization_id: org, source_location_id: loc, ...destination, imeis: draft.container_kind === "PHONE" ? draft.values : [], containers: draft.container_kind === "PHONE" ? [] : draft.values.map((code) => ({ kind: draft.container_kind, code })) })
        : await api.receiveReturn({ return_no: draft.document_no, received_imeis: draft.values });
    } else if (draft.action === "repair") {
      if (draft.phase === "create") {
        result = await api.createRepair({ organization_id: org, location_id: loc, imeis: draft.container_kind === "PHONE" ? draft.values : [], containers: draft.container_kind === "PHONE" ? [] : draft.values.map((code) => ({ kind: draft.container_kind, code })), return_no: draft.workflow === "ghana" ? (draft.document_no || null) : null });
      } else if (draft.phase === "accept") {
        result = await api.acceptRepair(draft.document_no);
      } else if (draft.phase === "complete") {
        for (const [index, imei] of draft.values.entries()) {
          api.setOperationKey(`${draft.id}:${index}`);
          result = await api.completeRepair(draft.document_no, { imei, repair_result: draft.repair_result || "REPAIRED" });
          processedValues.push(imei);
        }
      } else {
        for (const [index, imei] of draft.values.entries()) {
          api.setOperationKey(`${draft.id}:${index}`);
          result = await api.reviewRepair(draft.document_no, { imei, disposition: draft.disposition || "AVAILABLE_AGAIN" });
          processedValues.push(imei);
        }
      }
    } else if (draft.action === "stocktake" && draft.phase === "create") {
      result = await api.submitStocktake({ organization_id: org, location_id: loc, imeis: draft.values });
    } else if (draft.action === "stocktake" && draft.phase === "adjust") {
      result = await api.adjustStocktake(draft.document_no, draft.values.map((imei) => ({ imei, decision: draft.adjustment_decision || "IGNORE", target_status: draft.adjustment_target_status || "可再次销售" })));
    } else {
      throw new Error("该草稿类型不支持重试");
    }

    const resultNo = result && typeof result === "object"
      ? (result.order_no || result.shipment_no || result.receiving_no || result.transfer_no || result.sales_no || result.return_no || result.repair_no || result.stocktake_no)
      : null;
    const resultComplete = operationResultComplete(
      draft.action,
      draft.phase,
      result,
      draft.transfer_receive_complete !== false,
    );
    if (draft.workflow && resultNo) {
      workflowDocuments.value[workflowDocumentKey(draft.workflow, draft.action, draft.phase)] = String(resultNo);
      const step = workflowDefinitions[draft.workflow].find((item) => item.action === draft.action && item.phase === draft.phase);
      if (step && resultComplete) {
        workflowCompletedSteps.value = {
          ...workflowCompletedSteps.value,
          [draft.workflow]: Array.from(new Set([...workflowCompletedSteps.value[draft.workflow], step.key])),
        };
      }
      if (draft.action === "return" && draft.phase === "receive" && draft.workflow === "ghana") {
        workflowDocuments.value["ghana:return"] = String(resultNo);
      }
    }
    if (!draft.workflow && standalonePhaseDefinitions[draft.action]) {
      const handoffNo = resultNo ? String(resultNo) : draft.document_no.trim();
      if (handoffNo) {
        const previous = standaloneProgress.value[draft.action];
        const currentIndex = standalonePhaseDefinitions[draft.action].findIndex((item) => item.phase === draft.phase);
        const nextPhase = resultComplete
          ? standalonePhaseDefinitions[draft.action]
              .filter((step) => has(step.permission))
              .find((step) => standalonePhaseDefinitions[draft.action].findIndex((item) => item.phase === step.phase) > currentIndex)?.phase || ""
          : draft.phase;
        standaloneProgress.value = {
          ...standaloneProgress.value,
          [draft.action]: {
            documentNo: handoffNo,
            completedPhases: resultComplete
              ? Array.from(new Set([...(previous?.completedPhases || []), draft.phase]))
              : (previous?.completedPhases || []).filter((phase) => phase !== draft.phase),
            sourcePhase: draft.phase,
            carryToPhase: nextPhase,
            phaseComplete: resultComplete,
          },
        };
      }
    }
    draft.status = "synced";
    draft.error = "";
    message.value = resultComplete
      ? `${task.label}离线草稿已同步${resultNo ? `，单号：${resultNo}` : ""}`
      : `${task.label}离线草稿已同步本次明细；当前单据尚未完成，请继续扫描剩余明细`;
  } catch (e) {
    // A partial batch keeps only the not-yet-processed items, so retrying
    // cannot submit already accepted IMEIs a second time.
    if (processedValues.length) draft.values = draft.values.filter((value) => !processedValues.includes(value));
    const networkError = !online.value || e instanceof TypeError || (e instanceof Error && /failed to fetch|networkerror|网络|超时/i.test(e.message));
    draft.status = networkError ? "pending" : "conflict";
    draft.error = networkError ? "网络仍不可用，恢复联网后可重试" : (e instanceof Error ? e.message : "同步失败，请核对单据后处理");
  } finally {
    api.endOperation();
    persistOfflineDrafts();
  }
}
function isDraftRetryable(status: string) { return status === "pending" || status === "failed"; }
async function retryAllDrafts() {
  // Business conflicts need a human to inspect the单号/物料 first.  Bulk
  // retry is reserved for drafts that only failed because the network was
  // unavailable, so one bad record cannot repeatedly interrupt a whole shift.
  for (const draft of drafts.value.filter((item) => isDraftRetryable(item.status))) await retryDraft(draft);
}
async function createAdminUser() {
  const value = newIdentifier.value.trim();
  if (!value || !newName.value.trim() || newPassword.value.length < 8)
    return void (error.value = "请填写账号、姓名和至少 8 位密码");
  try {
    let scopes: unknown[] = [];
    if (newScopes.value.trim()) { scopes = JSON.parse(newScopes.value); if (!Array.isArray(scopes)) throw new Error("数据范围必须是 JSON 数组"); }
    await api.createUser(
      /^[A-Za-z]+$/.test(value)
        ? {
            username: value,
            display_name: newName.value.trim(),
            password: newPassword.value,
            role_ids: newRoleIds.value, scopes,
          }
        : {
            phone: value,
            display_name: newName.value.trim(),
            password: newPassword.value,
            role_ids: newRoleIds.value, scopes,
          },
    );
    message.value = "用户创建成功";
    newIdentifier.value = "";
    newName.value = "";
    newPassword.value = "";
    newRoleIds.value = []; newScopes.value = ""; newScopeRows.value = []; resetScopeBuilder();
    await refresh();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "创建失败";
  }
}
async function createOrganization() { if (!orgCode.value || !orgName.value || !orgCountry.value) return void (error.value = "请填写组织代码、名称和国家"); try { await api.createOrganization({ code: orgCode.value.trim(), name: orgName.value.trim(), country: orgCountry.value.trim() }); orgCode.value = ""; orgName.value = ""; message.value = "组织创建成功"; await loadAdmin() } catch (e) { error.value = e instanceof Error ? e.message : "创建失败" } }
async function createLocation() { if (!locOrganizationId.value || !locCode.value || !locName.value) return void (error.value = "请填写组织、地点代码和名称"); try { await api.createLocation({ organization_id: Number(locOrganizationId.value), code: locCode.value.trim(), name: locName.value.trim(), location_type: locType.value }); locCode.value = ""; locName.value = ""; message.value = "地点创建成功"; await loadAdmin() } catch (e) { error.value = e instanceof Error ? e.message : "创建失败" } }
async function createRole() {
  if (!roleCode.value.trim() || !roleName.value.trim()) return void (error.value = "请填写角色代码和名称");
  const manualPermissionCodes = rolePermissionsText.value.split(",").map((value) => value.trim()).filter(Boolean);
  const permissionCodes = Array.from(new Set([...selectedRolePermissions.value, ...manualPermissionCodes]));
  try {
    await api.createRole({ code: roleCode.value.trim(), name: roleName.value.trim(), work_group: roleWorkGroup.value.trim() || null, description: roleDescription.value.trim() || null, permission_codes: permissionCodes });
    roleCode.value = ""; roleName.value = ""; roleWorkGroup.value = ""; roleDescription.value = ""; rolePermissionsText.value = ""; selectedRolePermissions.value = [];
    message.value = "角色创建成功";
    await loadAdmin();
  } catch (e) { error.value = e instanceof Error ? e.message : "创建失败"; }
}
function toggleUser(item: any) {
  const nextState = !item.is_active;
  openConfirmation(
    () => { void (async () => { try { await api.updateUser(Number(item.id), { is_active: nextState }); message.value = `用户“${item.display_name || item.username || item.id}”已${nextState ? "启用" : "停用"}`; await loadAdmin(); } catch (e) { error.value = e instanceof Error ? e.message : "更新失败"; } })(); },
    `${nextState ? "启用" : "停用"}用户？`,
    `${nextState ? "恢复" : "停用"}后，${nextState ? "该账号可以" : "该账号将不能"}登录并进行新的现场操作。`,
    `确认${nextState ? "启用" : "停用"}`,
  );
}
function editUser(item: any) {
  editingUserId.value = Number(item.id);
  editingRoleIds.value = Array.isArray(item.role_ids) ? item.role_ids.map(Number) : [];
  editingScopeRows.value = scopeRowsFromUnknown(item.scopes);
  editingScopes.value = JSON.stringify(editingScopeRows.value, null, 2);
  resetScopeBuilder();
}
async function saveUserPermissions() {
  if (editingUserId.value === null) return;
  try {
    const scopes = editingScopeRows.value.length || !editingScopes.value.trim()
      ? editingScopeRows.value
      : JSON.parse(editingScopes.value);
    if (!Array.isArray(scopes)) throw new Error("数据范围必须是数组");
    await api.updateUser(editingUserId.value, { role_ids: editingRoleIds.value, scopes });
    editingUserId.value = null; editingScopeRows.value = [];
    message.value = "用户权限已更新";
    await loadAdmin();
  } catch (e) { error.value = e instanceof Error ? e.message : "更新失败"; }
}
function toggleOrganization(item: any) {
  const nextState = !item.is_active;
  openConfirmation(
    () => { void (async () => { try { await api.updateOrganization(Number(item.id), { is_active: nextState }); message.value = `组织“${item.name || item.code || item.id}”已${nextState ? "启用" : "停用"}`; await loadAdmin(); } catch (e) { error.value = e instanceof Error ? e.message : "更新失败"; } })(); },
    `${nextState ? "启用" : "停用"}组织？`,
    `${nextState ? "恢复" : "停用"}后，该组织下的地点和业务数据${nextState ? "可以继续使用" : "将不能用于新的现场作业"}。`,
    `确认${nextState ? "启用" : "停用"}`,
  );
}
function toggleLocation(item: any) {
  const nextState = !item.is_active;
  openConfirmation(
    () => { void (async () => { try { await api.updateLocation(Number(item.id), { is_active: nextState }); message.value = `地点“${item.name || item.code || item.id}”已${nextState ? "启用" : "停用"}`; await loadAdmin(); } catch (e) { error.value = e instanceof Error ? e.message : "更新失败"; } })(); },
    `${nextState ? "启用" : "停用"}地点？`,
    `${nextState ? "恢复" : "停用"}后，现场人员${nextState ? "可以在作业表单中选择该地点" : "将不能把该地点作为新的作业地点"}。`,
    `确认${nextState ? "启用" : "停用"}`,
  );
}
async function login() {
  loading.value = true;
  error.value = "";
  // Login starts a fresh session; do not reuse a key left by an interrupted
  // warehouse operation in this browser.
  api.endOperation();
  try {
    const result = await api.loginByPassword(
      identifier.value.trim(),
      password.value,
    );
    localStorage.setItem("gh-phone-access-token", result.access_token);
    user.value = await api.getCurrentUser();
    workLocations.value = await api.listWorkLocations();
    locationsLoaded.value = true;
    active.value = "dashboard";
    await refresh();
  } catch (e) {
    localStorage.removeItem("gh-phone-access-token");
    error.value = e instanceof Error ? e.message : "登录失败";
  } finally {
    loading.value = false;
  }
}
function performLogout() {
  api.endOperation();
  closeAccountMenu(false);
  localStorage.removeItem("gh-phone-access-token");
  user.value = null;
  active.value = "dashboard";
  activeWorkflow.value = null;
  scanned.value = [];
  phoneDetail.value = null;
  error.value = "";
  message.value = "";
  workflowDocuments.value = {};
  workflowCompletedSteps.value = { shenzhen: [], ghana: [] };
  standaloneProgress.value = {};
  standaloneResume.value = null;
  locationsLoaded.value = false;
  drafts.value = [];
  dashboardStats.value = { phones: 0, documents: 0, pendingDrafts: 0 };
  organizationId.value = "";
  locationId.value = "";
  destinationOrganizationId.value = "";
  destinationLocationId.value = "";
  identifier.value = "";
  password.value = "";
  scanInput.value = "";
  scanNotice.value = "";
  lastSubmission.value = null;
  transferReceiveComplete.value = true;
}
function logout() {
  requestLeave(performLogout);
}
async function saveBasicProfile() {
  if (!profileName.value.trim()) return void (error.value = "姓名不能为空");
  if (profileUsername.value && !/^[A-Za-z]+$/.test(profileUsername.value)) return void (error.value = "用户名只能包含英文字母");
  try {
    const updated = await api.updateProfile({ display_name: profileName.value.trim(), username: profileUsername.value.trim() || null });
    user.value = { ...user.value!, ...updated };
    message.value = "个人资料已更新";
  } catch (e) { error.value = e instanceof Error ? e.message : "保存失败"; }
}
async function savePassword() {
  if (!currentPassword.value || nextPassword.value.length < 8) return void (error.value = "修改密码需填写当前密码，且新密码至少 8 位");
  try {
    await api.changePassword(currentPassword.value, nextPassword.value);
    currentPassword.value = "";
    nextPassword.value = "";
    message.value = "密码已更新，当前会话仍有效；下次登录请使用新密码";
  } catch (e) { error.value = e instanceof Error ? e.message : "保存失败"; }
}
onMounted(async () => {
  window.addEventListener("online", () => {
    online.value = true;
  });
  window.addEventListener("offline", () => {
    online.value = false;
  });
  window.addEventListener("keydown", handleWindowKeydown);
  document.addEventListener("pointerdown", handleAccountOutsidePointerdown);
  if (localStorage.getItem("gh-phone-access-token")) {
    try {
      user.value = await api.getCurrentUser();
      workLocations.value = await api.listWorkLocations();
      locationsLoaded.value = true;
      await refresh();
    } catch (e) {
      localStorage.removeItem("gh-phone-access-token");
      locationsLoaded.value = false;
      error.value = e instanceof TypeError ? "无法连接服务器，请检查网络后重新登录" : "登录已过期，请重新登录";
    }
  }
});
onUnmounted(() => {
  window.removeEventListener("keydown", handleWindowKeydown);
  document.removeEventListener("pointerdown", handleAccountOutsidePointerdown);
});
</script>

<template>
  <main v-if="!user" class="login-page">
    <section class="login-hero" aria-label="系统介绍">
      <div class="brand brand-large">GHANA PHONE <span>MANAGEMENT</span></div>
      <p class="eyebrow">仓库作业 · 跨境流转 · 全程追溯</p>
      <h1>每一步都清楚，<br />交接不丢失。</h1>
      <p class="hero-copy">为深圳仓、加纳管理处和门店设计的手机流转工作台。按现场顺序扫码，系统自动留下单号、地点和交接记录。</p>
      <div class="login-flow"><span><b>1</b> 收购入库</span><i>→</i><span><b>2</b> 装托 / 装箱</span><i>→</i><span><b>3</b> 发运接收</span><i>→</i><span><b>4</b> 门店 / 维修</span></div>
      <div class="login-benefits"><span>✓ 扫码枪连续录入</span><span>✓ 托盘、箱、手机可追溯</span><span>✓ 断网可保存草稿</span></div>
    </section>
    <section class="login-card">
      <p class="eyebrow">工作人员登录</p>
      <h2>进入 PC 工作台</h2>
      <p class="login-muted">使用管理员分配的岗位账号登录，系统只显示你有权限的作业。</p>
      <form class="login-form" @submit.prevent="login">
        <div class="field-group"><label for="login-identifier">账号</label><input id="login-identifier" v-model="identifier" autocomplete="username" placeholder="手机号或英文用户名" required /></div>
        <div class="field-group"><label for="login-password">密码</label><div class="input-with-action"><input id="login-password" v-model="password" :type="passwordVisible ? 'text' : 'password'" autocomplete="current-password" placeholder="请输入密码" required /><button type="button" class="input-action" :aria-label="passwordVisible ? '隐藏密码' : '显示密码'" :aria-pressed="passwordVisible" @click="passwordVisible = !passwordVisible">{{ passwordVisible ? '隐藏' : '显示' }}</button></div></div>
        <button class="primary primary-large" type="submit" :disabled="loading"><span v-if="loading" class="spinner" aria-hidden="true"></span>{{ loading ? '正在登录…' : '登录工作台' }}</button>
      </form>
      <p class="login-footnote">连接扫码枪后，将光标放在扫描框即可连续作业；也可直接手工输入编码。</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </section>
  </main>

  <main v-else class="app-shell">
    <aside id="pc-sidebar" ref="sidebarRef" class="sidebar" :class="{ open: sidebarOpen, collapsed: sidebarCollapsed }" aria-label="主导航">
      <div class="sidebar-head"><div class="brand">GHANA PHONE<br /><span>MANAGEMENT</span></div><div class="sidebar-head-actions"><button class="sidebar-collapse" type="button" :aria-label="sidebarCollapsed ? '展开侧栏' : '收起侧栏'" :title="sidebarCollapsed ? '展开侧栏' : '收起侧栏'" @click="toggleSidebarCollapsed">{{ sidebarCollapsed ? '›' : '‹' }}</button><button ref="sidebarCloseButton" class="sidebar-close" type="button" aria-label="关闭菜单" @click="closeSidebar">×</button></div></div>
      <nav ref="navGroupsRef" class="nav-groups" aria-label="页面分组">
        <section class="nav-group" :class="{ collapsed: !navGroupExpanded.operations }">
          <button class="nav-group-toggle" type="button" title="折叠或展开现场作业" aria-controls="nav-group-operations" :aria-expanded="navGroupExpanded.operations" @click="toggleNavGroup('operations')"><span class="nav-group-label"><span class="nav-group-marker" aria-hidden="true">01</span><span class="nav-group-title">现场作业</span></span><span class="nav-group-chevron" aria-hidden="true">{{ navGroupExpanded.operations ? '⌃' : '⌄' }}</span></button>
          <div id="nav-group-operations" v-show="navGroupExpanded.operations" class="nav-group-items">
            <button class="nav-item" type="button" title="工作台" :class="{ active: active === 'dashboard' }" :aria-current="active === 'dashboard' ? 'page' : undefined" @click="select('dashboard'); closeSidebar()"><span class="nav-icon" aria-hidden="true">⌂</span><span><strong>工作台</strong><small>业务总览与待办</small></span></button>
            <button v-for="task in visibleTasks.filter((item) => item.workflow)" :key="task.key" class="nav-item" type="button" :title="task.label + '：' + task.hint" :class="{ active: isTaskActive(task) }" :aria-current="isTaskActive(task) ? 'page' : undefined" @click="select(task.key); closeSidebar()"><span class="nav-icon" aria-hidden="true">{{ taskIcon(task) }}</span><span><strong>{{ task.label }}</strong><small>{{ task.hint }}</small></span></button>
            <button v-for="task in visibleTasks.filter((item) => !item.workflow && item.key !== 'query')" :key="task.key" class="nav-item" type="button" :title="task.label + '：' + task.hint" :class="{ active: isTaskActive(task) }" :aria-current="isTaskActive(task) ? 'page' : undefined" @click="select(task.key); closeSidebar()"><span class="nav-icon" aria-hidden="true">{{ taskIcon(task) }}</span><span><strong>{{ task.label }}</strong><small>{{ task.hint }}</small></span></button>
          </div>
        </section>
        <section class="nav-group" :class="{ collapsed: !navGroupExpanded.collaboration }">
          <button class="nav-group-toggle" type="button" title="折叠或展开查询与协同" aria-controls="nav-group-collaboration" :aria-expanded="navGroupExpanded.collaboration" @click="toggleNavGroup('collaboration')"><span class="nav-group-label"><span class="nav-group-marker" aria-hidden="true">02</span><span class="nav-group-title">查询与协同</span></span><span class="nav-group-chevron" aria-hidden="true">{{ navGroupExpanded.collaboration ? '⌃' : '⌄' }}</span></button>
          <div id="nav-group-collaboration" v-show="navGroupExpanded.collaboration" class="nav-group-items">
            <button v-if="has('phone:view')" class="nav-item" type="button" title="库存列表：按 IMEI 或地点查询" :class="{ active: active === 'inventory' }" :aria-current="active === 'inventory' ? 'page' : undefined" @click="select('inventory'); closeSidebar()"><span class="nav-icon" aria-hidden="true">▤</span><span><strong>库存列表</strong><small>按 IMEI / 地点查库存</small></span></button>
            <button v-if="has('phone:view') || has('report:view')" class="nav-item" type="button" title="业务单据：查看状态、数量与交接" :class="{ active: active === 'documents' }" :aria-current="active === 'documents' ? 'page' : undefined" @click="select('documents'); closeSidebar()"><span class="nav-icon" aria-hidden="true">▧</span><span><strong>业务单据</strong><small>状态、数量与交接</small></span></button>
            <button class="nav-item" type="button" title="离线草稿：处理断网时待同步的作业" :class="{ active: active === 'drafts' }" :aria-current="active === 'drafts' ? 'page' : undefined" @click="select('drafts'); closeSidebar()"><span class="nav-icon" aria-hidden="true">↥</span><span><strong>离线草稿</strong><small>断网时待同步</small></span><em v-if="dashboardStats.pendingDrafts">{{ dashboardStats.pendingDrafts }}</em></button>
            <button v-if="has('phone:view')" class="nav-item" type="button" title="IMEI 追踪：查看单台手机全程轨迹" :class="{ active: active === 'query' }" :aria-current="active === 'query' ? 'page' : undefined" @click="select('query'); closeSidebar()"><span class="nav-icon" aria-hidden="true">⌕</span><span><strong>IMEI 追踪</strong><small>查看单台全程轨迹</small></span></button>
          </div>
        </section>
        <section v-if="canAdmin" class="nav-group" :class="{ collapsed: !navGroupExpanded.account }">
          <button class="nav-group-toggle" type="button" :title="'折叠或展开' + adminNavLabel" aria-controls="nav-group-account" :aria-expanded="navGroupExpanded.account" @click="toggleNavGroup('account')"><span class="nav-group-label"><span class="nav-group-marker" aria-hidden="true">03</span><span class="nav-group-title">{{ adminNavLabel }}</span></span><span class="nav-group-chevron" aria-hidden="true">{{ navGroupExpanded.account ? '⌃' : '⌄' }}</span></button>
          <div id="nav-group-account" v-show="navGroupExpanded.account" class="nav-group-items">
            <button v-if="canSystemManagement" class="nav-item" type="button" title="系统管理：配置系统业务" :class="{ active: active === 'system' }" :aria-current="active === 'system' ? 'page' : undefined" @click="select('system'); closeSidebar()"><span class="nav-icon" aria-hidden="true">⚙</span><span><strong>系统管理</strong><small>系统业务配置</small></span></button>
            <button v-if="canUserManagement" class="nav-item" type="button" title="用户管理：创建用户并分配岗位" :class="{ active: active === 'users' }" :aria-current="active === 'users' ? 'page' : undefined" @click="select('users'); closeSidebar()"><span class="nav-icon" aria-hidden="true">♙</span><span><strong>用户管理</strong><small>创建用户与分配岗位</small></span></button>
            <button v-if="!canSystemManagement && !canUserManagement" class="nav-item" type="button" title="审计记录" :class="{ active: active === 'admin' }" :aria-current="active === 'admin' ? 'page' : undefined" @click="select('admin'); closeSidebar()"><span class="nav-icon" aria-hidden="true">▤</span><span><strong>审计记录</strong><small>只读查看变更记录</small></span></button>
          </div>
        </section>
      </nav>
      <div class="sidebar-bottom">
        <div class="sidebar-account">
          <button ref="accountToggleButton" id="account-toggle" class="account-trigger" type="button" :aria-label="'我的账号：' + user.display_name" title="账户菜单" aria-haspopup="menu" aria-controls="account-menu" :aria-expanded="accountMenuOpen" @click="toggleAccountMenu"><span class="avatar" aria-hidden="true">{{ String(user.display_name || '员').slice(0, 1) }}</span><span class="account-trigger-copy"><strong>{{ user.display_name }}</strong><small>{{ roleLabel || '我的账号' }}</small></span><span class="account-chevron" aria-hidden="true">{{ accountMenuOpen ? '⌃' : '⌄' }}</span></button>
          <div v-if="accountMenuOpen" ref="accountMenu" id="account-menu" class="account-menu" role="menu" aria-label="账户菜单" @keydown="handleAccountMenuKeydown">
            <div class="account-summary"><strong>{{ user.display_name }}</strong><small>{{ user.username || user.phone || '—' }}</small><span v-if="roleLabel" class="role-chip">{{ roleLabel }}</span><span class="account-scope"><span class="scope-dot"></span>{{ roleScopeSummary() }}</span></div>
            <button class="account-menu-item" type="button" role="menuitem" @click="openProfileFromAccount">个人设置</button>
            <button v-if="canAdmin" class="account-menu-item" type="button" role="menuitem" @click="openAdminFromAccount">{{ adminNavLabel }}</button>
            <button class="account-menu-item danger-account" type="button" role="menuitem" @click="logoutFromAccount">退出登录</button>
          </div>
        </div>
        <div class="sidebar-footer"><span :class="['online-dot', { offline: !online }]" aria-hidden="true"></span><span>{{ online ? '在线' : '离线 · 草稿保存在本机' }}</span></div>
      </div>
    </aside>
    <div v-if="sidebarOpen" class="sidebar-backdrop" @click="closeSidebar()"></div>

    <section class="main-area" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
      <header class="topbar"><div class="topbar-left"><button ref="menuToggleButton" id="pc-menu-toggle" class="menu-toggle" type="button" aria-label="打开菜单" aria-controls="pc-sidebar" :aria-expanded="sidebarOpen" @click="openSidebar">☰</button><div class="breadcrumb"><span>{{ pageMeta.eyebrow }}</span><b>/</b><strong>{{ pageMeta.title }}</strong></div></div><div class="topbar-tools"><span :class="['scanner-status', { offline: !online }]" role="status"><i></i>{{ online ? (currentTask ? '扫码输入已就绪' : '系统在线') : '离线模式' }}</span><button ref="helpButton" class="help-button" type="button" @click="showHelp = true">? <span>操作帮助</span></button></div></header>
      <section class="page-heading"><div><p class="eyebrow">{{ pageMeta.eyebrow }}</p><h1>{{ pageMeta.title }}</h1><p class="page-subtitle">{{ pageMeta.subtitle }}</p></div></section>
      <div class="alerts" aria-live="polite"><p v-if="message" class="message"><span class="alert-icon">✓</span>{{ message }}</p><p v-if="error" class="error" role="alert"><span class="alert-icon">!</span>{{ error }}</p><p v-if="refreshLoading" class="loading-banner" role="status"><span class="spinner" aria-hidden="true"></span>正在加载最新数据，请稍候…</p></div>

      <section v-if="active === 'dashboard'" class="dashboard-page">
        <article class="welcome-card"><div><p class="eyebrow">今日作业</p><h2>你好，{{ user.display_name }}。先处理哪一批？</h2><p>扫描前确认手边的单据和容器，提交后按系统生成的单号与下一岗位交接。</p><div class="welcome-actions"><button v-if="visibleTasks.length" class="primary" type="button" @click="select(visibleTasks[0].key)">开始 {{ visibleTasks[0].label }} <span>→</span></button><button v-if="has('phone:view') || has('report:view')" class="secondary" type="button" @click="select('documents')">查看待办单据</button></div></div><div class="welcome-illustration" aria-hidden="true"><div class="illustration-box"><span>IMEI</span><b>→</b><span>托盘</span><b>→</b><span>箱</span></div><small>扫码 · 核对 · 交接</small></div></article>
        <section class="metric-grid" aria-label="业务概览"><article v-if="has('phone:view')" class="metric-card"><span class="metric-icon teal">▣</span><div><strong>{{ dashboardStats.phones }}</strong><small>当前可见手机</small></div><button class="metric-link" type="button" @click="select('inventory')">查看库存 →</button></article><article v-if="has('phone:view') || has('report:view')" class="metric-card"><span class="metric-icon blue">▧</span><div><strong>{{ dashboardStats.documents }}</strong><small>当前可见业务单据</small></div><button class="metric-link" type="button" @click="select('documents')">查看单据 →</button></article><article class="metric-card"><span class="metric-icon amber">↥</span><div><strong>{{ dashboardStats.pendingDrafts }}</strong><small>待同步离线草稿</small></div><button class="metric-link" type="button" @click="select('drafts')">处理草稿 →</button></article></section>
        <details class="flow-card flow-details"><summary><span><strong>完整流转路径</strong><small>不熟悉流程时展开查看，日常作业无需重复阅读。</small></span><b aria-hidden="true"></b></summary><div class="flow-map"><div class="flow-node"><span class="flow-number">1</span><strong>深圳收购仓</strong><small>收购验收 · 装托 · 装箱</small></div><span class="flow-arrow">→</span><div class="flow-node"><span class="flow-number">2</span><strong>跨境发运</strong><small>整箱 / 整托 / 散台</small></div><span class="flow-arrow">→</span><div class="flow-node"><span class="flow-number">3</span><strong>加纳管理处</strong><small>到货验收 · 拣货调拨</small></div><span class="flow-arrow">→</span><div class="flow-node"><span class="flow-number">4</span><strong>门店与维修</strong><small>销售 · 退回 · QA</small></div></div></details>
        <section class="dashboard-columns"><article class="quick-actions"><div class="section-heading"><div><h2>我的作业入口</h2><p>只显示当前账号有权限的岗位任务。</p></div></div><div class="quick-grid"><button v-for="task in visibleTasks" :key="'quick-' + task.key" type="button" class="quick-action" @click="select(task.key)"><span class="quick-icon">{{ taskIcon(task) }}</span><span><strong>{{ task.label }}</strong><small>{{ task.hint }}</small></span><b>→</b></button></div><p v-if="!visibleTasks.length" class="empty-state compact"><span>□</span>当前账号暂无可用作业权限，请联系管理员。</p></article><article class="rules-card"><div class="section-heading"><div><h2>现场三条提醒</h2><p>给第一次使用系统的同事</p></div></div><ol class="rule-list"><li><b>先容器，后手机</b><span>装托盘/装箱时先锁定托盘或箱码，再连续扫描内容物。</span></li><li><b>一批一提交</b><span>确认清单数量和地点后提交；提交成功会生成可交接单号。</span></li><li><b>异常要留痕</b><span>验收异常、维修和盘点差异都要选择真实结果，不能用正常代替。</span></li></ol></article></section>
      </section>

      <section v-else-if="currentTask" class="operation-page" :class="{ 'query-page': currentTask.key === 'query' }">
        <section v-if="activeWorkflow" class="workflow-panel" aria-label="岗位作业步骤"><div class="workflow-panel-head"><div><p class="eyebrow">{{ activeWorkflow === 'shenzhen' ? '深圳收购仓岗位' : '加纳管理处综合岗位' }}</p><h2>{{ activeWorkflow === 'shenzhen' ? '一人连续完成收购、装托、装箱' : '一人承接到货、调拨、退回分诊与维修 QA' }}</h2></div><span class="step-counter">已完成 {{ workflowCompletedCount }} / {{ workflowSteps.length }} 步</span></div><p class="workflow-guide">按现场顺序处理，每一步提交后才会形成下一步可承接的记录；发运、销售和门店收货仍由对应岗位完成。</p><div class="workflow-progress"><span :style="{ width: (workflowSteps.length ? workflowCompletedCount / workflowSteps.length * 100 : 0) + '%' }"></span></div><div class="workflow-steps-viewport" :class="{ 'is-scrollable': workflowSteps.length > 4 }" role="region" :aria-label="workflowSteps.length > 4 ? '岗位步骤，可左右滚动查看全部步骤' : '岗位作业步骤'"><div class="workflow-steps" :class="{ 'workflow-steps-scrollable': workflowSteps.length > 4 }"><button v-for="(step, index) in workflowSteps" :key="step.key" type="button" :class="['workflow-step', { active: currentWorkflowStep && currentWorkflowStep.key === step.key, done: workflowStepDone(step), locked: workflowStepBlocked(step) }]" :title="workflowStepBlocked(step) ? workflowStepBlockHint(step) + '；点击后可输入跨班次已有单号' : step.hint" :aria-current="currentWorkflowStep && currentWorkflowStep.key === step.key ? 'step' : undefined" @click="selectWorkflowStep(step)"><span>{{ index + 1 }}</span><strong>{{ step.label }}</strong><small>{{ workflowStepBlocked(step) ? workflowStepBlockHint(step) : step.hint }}</small></button></div></div><p v-if="workflowSteps.length > 4" class="workflow-scroll-hint" aria-hidden="true"><span>↔</span> 左右滑动查看全部步骤</p><p class="workflow-cross-shift">跨班次承接：虚线步骤仍可点击；按提示输入已有单号或重新扫描实物，系统不会把上一步未提交的输入带过来。</p><p v-if="repairTechHandoffPending()" class="workflow-wait">维修单建立后会交给独立维修技师接单并填写结果；技师完成后，再进入“维修 QA”。</p></section>
        <section v-if="standaloneResume && standaloneResume.taskKey === currentTask.key" class="resume-banner" role="status"><div><strong>{{ standaloneResumeComplete(standaloneResume.progress) ? '发现上一批未完成交接' : '发现上一批尚未完成' }}</strong><p v-if="standaloneResumeComplete(standaloneResume.progress)">单号 <code>{{ standaloneResume.progress.documentNo }}</code> 已完成“{{ phaseLabels[standaloneResume.progress.sourcePhase || ''] || '上一阶段' }}”，可以继续下一阶段。</p><p v-else>单号 <code>{{ standaloneResume.progress.documentNo }}</code> 仍在“{{ phaseLabels[standaloneResume.progress.sourcePhase || ''] || '当前阶段' }}”，可以继续扫描剩余明细。</p></div><div class="resume-actions"><button class="primary" type="button" @click="resumeStandaloneBatch">继续上一批</button><button class="secondary" type="button" @click="discardStandaloneBatch">开始新批次</button></div></section>
        <section v-if="!activeWorkflow && standalonePhaseSteps.length > 1" class="phase-switcher" aria-label="当前作业阶段"><div><p class="eyebrow">同一岗位的多个阶段</p><h2>选择现在要做的步骤</h2><p>如果你同时负责多个阶段，先完成当前阶段，再点下一阶段继续；提交成功的单号会自动带到下一阶段。</p></div><div class="phase-switch-steps"><button v-for="(step, index) in standalonePhaseSteps" :key="step.phase" type="button" :class="['phase-switch-step', { active: step.phase === operationPhase, done: standalonePhaseDone(step.phase) }]" @click="selectStandalonePhase(step)"><span>{{ index + 1 }}</span><strong>{{ step.label }}</strong><small>{{ step.hint }}</small></button></div></section>
        <div class="operation-layout"><article class="operation-card" :class="{ 'query-operation-card': currentTask.key === 'query', 'has-query-result': currentTask.key === 'query' && phoneDetail }"><div class="operation-card-head"><div><span class="step-kicker">{{ currentTask.key === 'query' ? '只读查询' : activeWorkflow ? '步骤 ' + operationStepNumber + ' · ' + (phaseLabels[operationPhase] || '') : (phaseLabels[operationPhase] || '现场作业') }}</span><h2>{{ activeWorkflow ? (currentWorkflowStep?.label || currentTask.label) : currentTask.label }}</h2></div><span class="operation-badge">{{ currentTask.key === 'query' ? '只读查询' : online ? '可提交' : '离线草稿' }}</span></div><p class="operation-purpose">{{ operationInstruction() }}</p><div v-if="currentTask.key === 'query' && !phoneDetail" class="query-guide" role="note">输入或扫描一台 IMEI，点击“查询 IMEI”查看当前状态与全程轨迹；查询不会修改库存或生成业务单据。</div><div v-else-if="currentTask.key !== 'query'" class="sequence-tip"><span class="tip-number">1</span><div><strong>先确认上下文</strong><small>地点、单号和容器决定这批手机归属哪一次交接。</small></div><span class="tip-arrow">→</span><span class="tip-number">2</span><div><strong>{{ phaseRequiresScan() ? '再连续扫码' : '最后核对并提交' }}</strong><small>{{ phaseRequiresScan() ? '扫码枪每扫一台，清单会立即增加。' : '没有逐台扫描的阶段，只需输入业务单号。' }}</small></div></div>
          <form class="operation-form" @submit.prevent="currentTask.key === 'query' ? submitQuery() : submit()">
            <fieldset v-if="currentTask.key === 'shipment'" class="field-section"><legend>运输信息</legend><div class="field-group"><label for="logistics-number">物流单号 <span class="optional">可选</span></label><input id="logistics-number" v-model="logisticsNo" autocomplete="off" placeholder="承运商或物流追踪号" /><small>可填写提单号、运单号或承运商追踪号，便于加纳管理处查询运输状态。</small></div></fieldset>
            <fieldset v-if="phaseRequiresCurrentLocation() || phaseRequiresDestination()" class="field-section"><legend>作业地点</legend><div class="field-grid"><div v-if="phaseRequiresCurrentLocation()" class="field-group"><label for="current-location">当前作业地点 <em>必填</em></label><select id="current-location" v-model="locationId" @change="syncOrganization" :disabled="!sourceLocations.length" required><option value="">{{ sourceLocations.length ? "请选择当前地点" : "没有符合规则的作业地点" }}</option><option v-for="item in sourceLocations" :key="String(item.id)" :value="String(item.id)">{{ locationLabel(item) }}</option></select><small v-if="activeLocation">组织自动带出：{{ activeLocation.organization_name || activeLocation.organization_id }}</small><small v-else-if="!sourceLocations.length" class="field-warning">当前岗位没有符合本业务规则的作业地点，请联系管理员检查地点类型和权限范围。</small><small v-else>只显示当前岗位授权的地点。</small></div><div v-if="phaseRequiresDestination()" class="field-group"><label for="destination-location">目标地点 <em>必填</em></label><select id="destination-location" v-model="destinationLocationId" @change="syncDestinationOrganization" :disabled="!locationId || !destinationLocations.length" required><option value="">{{ !locationId ? '先选择当前地点' : destinationLocations.length ? '请选择目标地点' : '没有符合规则的目标地点' }}</option><option v-for="item in destinationLocations" :key="'dest-' + item.id" :value="String(item.id)">{{ locationLabel(item) }}</option></select><small v-if="activeDestinationLocation">目标组织：{{ activeDestinationLocation.organization_name || activeDestinationLocation.organization_id }}</small><small v-else-if="locationId && !destinationLocations.length" class="field-warning">没有符合当前业务规则的目标地点，请联系管理员检查地点类型。</small><small v-else>系统会按发运 / 调拨 / 退回规则筛选可去地点。</small></div></div></fieldset>
            <fieldset v-if="phaseNeedsDocument()" class="field-section"><legend>关联单据</legend><div class="field-grid"><div class="field-group"><label for="document-number">{{ documentFieldLabel() }} <em v-if="!(currentTask.key === 'repair' && operationPhase === 'create')">必填</em><span v-else class="optional">可选</span></label><input id="document-number" ref="documentInput" v-model="documentNo" autocomplete="off" :placeholder="documentFieldLabel()" :required="!(currentTask.key === 'repair' && operationPhase === 'create')" /><small>{{ documentFieldHint() }}</small></div></div></fieldset>
            <fieldset v-if="currentTask.key === 'transfer' && operationPhase === 'receive'" class="field-section"><legend>收货完成方式</legend><div class="choice-row compact-choice"><label class="choice-card" :class="{ selected: transferReceiveComplete }"><input v-model="transferReceiveComplete" name="transfer-receive-complete" type="radio" :value="true" /><span><strong>完成本次收货</strong><small>未扫到的明细会记为短少并冻结</small></span></label><label class="choice-card warning-choice" :class="{ selected: !transferReceiveComplete }"><input v-model="transferReceiveComplete" name="transfer-receive-complete" type="radio" :value="false" /><span><strong>暂存已收，稍后继续</strong><small>只登记本次实收，不处理未到货明细</small></span></label></div><small class="section-help">如果箱子尚未全部到齐，请选择“暂存已收”；确认实物清点结束后再选择“完成本次收货”。</small></fieldset>
            <fieldset v-if="phaseCanChooseContainerKind()" class="field-section"><legend>本次装载单位</legend><div class="choice-row"><label v-for="option in [{ value: 'PHONE', label: '手机 IMEI', hint: '逐台扫描' }, { value: 'TRAY', label: '托盘', hint: '整托发运' }, { value: 'BOX', label: '箱子', hint: '整箱发运' }]" :key="option.value" class="choice-card" :class="{ selected: containerKind === option.value }"><input :ref="(element) => setContainerRadioRef(option.value, element)" :checked="containerKind === option.value" name="container-kind" type="radio" :value="option.value" @change="selectContainerKind(option.value)" @keydown="handleContainerKindKeydown($event, option.value)" /><span><strong>{{ option.label }}</strong><small>{{ option.hint }}</small></span></label></div><small class="section-help">{{ containerChoiceHint() }}</small></fieldset>
            <fieldset v-if="['tray', 'box'].includes(currentTask.key)" class="field-section"><legend>{{ currentTask.key === 'tray' ? '目标托盘' : '目标箱子' }}</legend><div class="container-lock" :class="{ locked: !capturingContainer && containerCode }"><span class="lock-icon">{{ capturingContainer ? '1' : '✓' }}</span><div><strong>{{ capturingContainer ? '请先扫描目标' + (currentTask.key === 'tray' ? '托盘' : '箱子') + '编码' : '已锁定目标' + (currentTask.key === 'tray' ? '托盘' : '箱子') }}</strong><small>{{ containerCode || '扫描后会固定在本批作业中' }}</small></div><button v-if="!capturingContainer && containerCode" type="button" class="secondary small-button" @click="recaptureContainer">重新扫描</button></div></fieldset>
            <fieldset v-if="currentTask.key === 'receiving' && operationPhase === 'inspect'" class="field-section"><legend>本批验收结论</legend><div class="choice-row compact-choice"><label class="choice-card" :class="{ selected: accepted }"><input v-model="accepted" name="acceptance-result" type="radio" :value="true" /><span><strong>验收正常</strong><small>可进入库存或重新装托</small></span></label><label class="choice-card danger-choice" :class="{ selected: !accepted }"><input v-model="accepted" name="acceptance-result" type="radio" :value="false" /><span><strong>异常 / 待核查</strong><small>保留问题记录，不要强行入库</small></span></label></div><small class="section-help">清单中的每台手机都会使用同一结论；正常机与异常机请分批提交。</small><div v-if="accepted" class="field-grid nested-fields"><div class="field-group"><label for="target-tray">重新装入托盘 <span class="optional">可选</span></label><input id="target-tray" v-model="targetTrayCode" placeholder="托盘编码" /></div><div class="field-group"><label for="target-box">重新装入箱子 <span class="optional">可选</span></label><input id="target-box" v-model="targetBoxCode" placeholder="箱子编码（需先填托盘）" /></div></div></fieldset>
            <fieldset v-if="currentTask.key === 'sales' && operationPhase === 'create'" class="field-section"><legend>销售资料</legend><div class="field-grid"><div class="field-group"><label for="sales-type">销售类型 <em>必填</em></label><select id="sales-type" v-model="salesType"><option value="RETAIL">零售</option><option value="WHOLESALE">批发</option></select></div><div class="field-group"><label for="customer-name">客户名称 <span class="optional">可选</span></label><input id="customer-name" v-model="customerName" placeholder="客户或门店名称" /></div><div class="field-group full-field" v-if="containerKind === 'PHONE'"><label for="sale-prices">销售价格 <span class="optional">可选</span></label><input id="sale-prices" v-model="salePrices" inputmode="decimal" autocomplete="off" placeholder="按扫描顺序填写，如 120,150,120" /><small>不填写时由后续财务流程补录；填写多个价格请用逗号分隔。</small></div><div v-else class="field-group full-field"><label>销售价格</label><p class="form-help">整托/整箱先按容器明细出库，金额由财务后补；如需逐台定价，请选择“手机 IMEI”。</p></div></div></fieldset>
            <fieldset v-if="currentTask.key === 'repair' && operationPhase === 'complete'" class="field-section"><legend>维修结果</legend><div class="field-group"><label for="repair-result">本批维修结论 <em>必填</em></label><select id="repair-result" v-model="repairResult"><option value="REPAIRED">已修复</option><option value="NO_REPAIR">无需维修</option><option value="UNREPAIRABLE">不可维修</option></select><small>扫描清单中的每台手机都会写入同一结论，如结论不同请分批提交。</small></div><small class="section-help">不同维修结果请分批扫描提交，避免同一批被写成相同结论。</small></fieldset>
            <fieldset v-if="currentTask.key === 'repair' && operationPhase === 'review'" class="field-section"><legend>QA 处理结论</legend><div class="choice-row compact-choice"><label v-for="option in [{ value: 'AVAILABLE_AGAIN', label: '恢复可售', hint: '回到可销售库存' }, { value: 'FROZEN', label: '冻结待核查', hint: '暂不流转' }, { value: 'SCRAPPED', label: '报损', hint: '停止销售' }]" :key="option.value" class="choice-card" :class="{ selected: disposition === option.value, danger: option.value === 'SCRAPPED' }"><input v-model="disposition" name="repair-disposition" type="radio" :value="option.value" /><span><strong>{{ option.label }}</strong><small>{{ option.hint }}</small></span></label></div><small class="section-help">同一清单中的手机会使用同一 QA 结论；结论不同请分批提交。</small></fieldset>
            <fieldset v-if="currentTask.key === 'stocktake' && operationPhase === 'adjust'" class="field-section"><legend>差异处理</legend><div class="field-grid"><div class="field-group"><label for="adjustment-decision">处理决定 <em>必填</em></label><select id="adjustment-decision" v-model="adjustmentDecision"><option value="IGNORE">忽略差异</option><option value="CONFIRM_MISSING">确认缺失</option><option value="ACCEPT_EXTRA">接收多出</option></select></div><div v-if="adjustmentDecision === 'ACCEPT_EXTRA'" class="field-group"><label for="adjustment-status">多出手机记入状态</label><select id="adjustment-status" v-model="adjustmentTargetStatus"><option value="加纳管理处库存">加纳管理处库存</option><option value="门店库存">门店库存</option><option value="可再次销售">可再次销售</option></select></div></div><small class="section-help">同一批差异会使用同一个处理决定；缺失和多出情况请分开提交。</small></fieldset>
            <fieldset v-if="phaseRequiresScan()" class="scan-section"><legend>{{ currentTask.key === 'query' ? '查询 IMEI' : capturingContainer ? '第一步：扫描容器' : '连续扫描清单' }}</legend><div class="scan-instruction"><span class="scan-icon">⌁</span><div><strong>{{ currentTask.key === 'query' ? '输入或扫描 IMEI' : capturingContainer ? '扫描目标' + (currentTask.key === 'tray' ? '托盘' : '箱子') + '，再扫描内容物' : '扫描' + scanKindLabel }}</strong><small>{{ currentTask.key === 'query' ? '输入或扫描通过校验的 15 位 IMEI，点击“查询 IMEI”查看详情。' : scanMode() === 'imei' ? 'IMEI 必须是通过校验的 15 位数字；扫码枪回车只会加入清单，不会直接提交。' : '扫码枪需带回车才会自动加入；没有回车请点击“加入清单”，编码不能包含空格。' }}</small></div><span class="scan-count">{{ scanned.length }} 项</span></div><div class="scanbar"><input ref="scannerInput" v-model="scanInput" :disabled="scanInputDisabled()" :inputmode="scanMode() === 'imei' ? 'numeric' : 'text'" :maxlength="scanMode() === 'imei' ? 15 : 64" :placeholder="scanPlaceholder" :aria-label="currentTask.key === 'query' ? 'IMEI 查询输入框' : '扫码输入框'" autocomplete="off" autocapitalize="off" spellcheck="false" @input="onScanInput" @keydown.enter.prevent.stop="currentTask.key === 'query' ? submitQuery() : addScan()" /><button class="secondary add-button" type="button" :disabled="scanInputDisabled()" @click="currentTask.key === 'query' ? submitQuery() : addScan()">{{ currentTask.key === 'query' ? '查询 IMEI' : '加入清单' }}</button></div><p v-if="scanNotice" class="scan-notice" role="status">{{ scanNotice }}</p><div class="scan-toolbar"><span>{{ currentTask.key === 'query' ? (phoneDetail ? '查询完成，可查看下方详情' : '输入 1 台手机后查询详情') : '已读取 ' + scanned.length + ' 项' + (scanned.length ? '，提交前可检查并移除' : '') }}</span><button v-if="currentTask.key === 'query' && phoneDetail" class="link" type="button" @click="startNewBatch">查询下一台</button><button v-else-if="scanned.length" class="link" type="button" @click="currentTask.key === 'query' ? startNewBatch() : clearScanned()">{{ currentTask.key === 'query' ? '清除' : '清空本批' }}</button></div><div v-if="scanned.length && currentTask.key !== 'query'" class="scan-list"><div v-for="(value, index) in scanned" :key="value" class="scan-row"><span class="scan-index">{{ index + 1 }}</span><code>{{ value }}</code><span class="scan-row-state">待提交</span><button class="link remove-button" type="button" aria-label="移除这一项" @click="scanned.splice(index, 1)">移除</button></div></div><div v-else-if="!scanned.length" class="empty-scan"><span>⌁</span><strong>{{ currentTask.key === 'query' ? '尚未输入 IMEI' : '还没有扫描记录' }}</strong><small>{{ currentTask.key === 'query' ? '输入或扫描一台手机的 IMEI，再点击“查询 IMEI”。' : '把光标留在上方输入框，拿起扫码枪开始。' }}</small></div></fieldset>
            <div v-else class="no-scan-card"><span class="no-scan-icon">№</span><div><strong>本阶段按单号处理</strong><p>不需要逐台扫描。输入正确的{{ documentFieldLabel() }}后，系统会按单据中的明细完成交接。</p></div></div>
            <div v-if="currentTask.key !== 'query' || !phoneDetail" class="submit-footer" :class="{ 'query-submit-footer': currentTask.key === 'query' }"><div><strong>{{ currentTask.key === 'query' ? '查询操作' : '提交前确认' }}</strong><span>{{ currentTask.key === 'query' ? (scanned.length ? '将查询这台手机的当前状态与流转轨迹' : '输入 IMEI 后点击查询') : submitSummary }}</span><small v-if="submitDisabledReason" class="submit-reason">{{ submitDisabledReason }}</small></div><button class="primary submit-button" type="submit" :disabled="!canSubmit || loading"><span v-if="loading" class="spinner" aria-hidden="true"></span>{{ loading ? (currentTask.key === 'query' ? '正在查询…' : '正在提交…') : currentTask.key === 'query' ? '查询 IMEI' : '确认提交' + (activeWorkflow ? (currentWorkflowStep?.label || currentTask.label) : currentTask.label) }}<template v-if="phaseRequiresScan() && currentTask.key !== 'query'">（{{ scanned.length }}）</template></button></div>
          </form>
          <div v-if="lastSubmission && !(currentTask.key === 'query' && phoneDetail)" :class="['success-card', { 'partial-card': lastSubmission.complete === false, 'query-success-card': currentTask.key === 'query' }]" role="status"><span class="success-mark">{{ lastSubmission.complete === false ? '!' : '✓' }}</span><div><strong>{{ lastSubmission.text }}</strong><p v-if="lastSubmission.no">单号：<code>{{ lastSubmission.no }}</code><button type="button" class="link" @click="copyValue(lastSubmission.no)">复制</button></p><p>数量：{{ lastSubmission.count || 0 }} 项　状态：{{ lastSubmission.status || '已完成' }}</p></div><button v-if="lastSubmission.complete === false && phaseRequiresScan()" class="secondary" type="button" @click="continueCurrentPhase">继续扫描剩余明细</button><button v-else-if="nextWorkflowStep && !repairTechHandoffPending()" class="secondary" type="button" @click="selectWorkflowStep(nextWorkflowStep)">下一步：{{ nextWorkflowStep.label }} →</button><button v-else-if="nextStandalonePhase" class="secondary" type="button" @click="selectStandalonePhase(nextStandalonePhase)">下一步：{{ nextStandalonePhase.label }} →</button><button v-if="!phaseRequiresScan()" class="link" type="button" @click="startNewBatch">开始新批次</button><button v-if="lastSubmission.complete !== false && phaseRequiresScan() && !nextWorkflowStep && !nextStandalonePhase" class="secondary" type="button" @click="startNewBatch">{{ currentTask.key === 'query' ? '查询下一台' : '开始下一批' }}</button></div>
          <div v-if="currentTask.key === 'query' && phoneDetail" class="phone-detail-card"><div class="detail-head"><div><p class="eyebrow">手机详情</p><h3>{{ phoneDetail.brand || '' }} {{ phoneDetail.model || '未知型号' }}</h3></div><span :class="['status-badge', statusClass(phoneDetail.status)]">{{ statusText(phoneDetail.status) }}</span></div><div class="detail-grid"><div><small>IMEI 1</small><code>{{ phoneDetail.imei || '—' }}</code></div><div><small>IMEI 2</small><code>{{ phoneDetail.imei2 || '—' }}</code></div><div><small>当前组织</small><span>{{ phoneDetail.organization_id || '—' }}</span></div><div><small>当前地点</small><span>{{ locationNameById(phoneDetail.location_id) }}</span></div></div><div v-if="Array.isArray(phoneDetail.timeline) && phoneDetail.timeline.length" class="timeline"><div v-for="(event, index) in phoneDetail.timeline" :key="String(event.created_at) + '-' + index" class="timeline-item"><span class="timeline-dot"></span><div><strong>{{ timelineActionLabel(event.action) }}</strong><small>{{ formatDate(event.created_at) }} · {{ event.document_id || '无单据' }}</small><p v-if="event.note">{{ event.note }}</p></div></div></div></div>
        </article><aside v-if="currentTask.key !== 'query'" class="operation-aside"><section class="aside-card"><div class="aside-title"><span class="aside-icon">✓</span><h3>现场操作口诀</h3></div><ol><li :class="{ current: phaseRequiresCurrentLocation() }"><b>确认地点</b><span>当前地点和目标地点不能选错</span></li><li :class="{ current: phaseRequiresScan() }"><b>{{ phaseRequiresScan() ? '扫码清单' : '输入单号' }}</b><span>{{ phaseRequiresScan() ? '一台一项，重复项会提示' : '按单号承接上一工序' }}</span></li><li><b>核对后提交</b><span>看到成功单号再移交实物</span></li></ol></section><section class="aside-card handoff-card"><div class="aside-title"><span class="aside-icon">↗</span><h3>交给下一岗位</h3></div><p>{{ operationHandoff }}</p><div v-if="activeLocation" class="handoff-location"><small>当前地点</small><strong>{{ activeLocation.name || activeLocation.code }}</strong><small v-if="activeDestinationLocation">目标：{{ activeDestinationLocation.name || activeDestinationLocation.code }}</small></div></section><section v-if="activeWorkflow" class="aside-card workflow-summary"><div class="aside-title"><span class="aside-icon">◎</span><h3>本岗位范围</h3></div><p>{{ activeWorkflow === 'shenzhen' ? '深圳收购仓：收购验收、装托盘、装箱封存。' : '加纳管理处：到货验收、拣货调拨、退回分诊、维修建单与 QA。' }}</p></section></aside>
        </div>
      </section>

      <section v-else-if="active === 'inventory'" class="page-panel data-page inventory-page"><div class="panel-heading compact-panel-heading"><div><h2 class="sr-only">库存明细</h2><p class="panel-summary">当前加载 {{ filteredInventory.length }} 台符合条件；点击一行查看 IMEI 详情。</p></div><button class="secondary" type="button" :disabled="refreshLoading" @click="refresh">{{ refreshLoading ? '刷新中…' : '刷新库存' }}</button></div><div class="filter-bar"><div class="search-field"><label for="inventory-search">关键词</label><span>⌕</span><input id="inventory-search" v-model="inventorySearch" placeholder="IMEI、品牌、型号或地点" aria-label="搜索库存" /></div><label class="filter-control" for="inventory-status">状态<select id="inventory-status" v-model="inventoryStatusFilter" aria-label="按状态筛选"><option value="">全部状态</option><option v-for="status in inventoryStatuses" :key="status" :value="status">{{ statusText(status) }}</option></select></label><label class="filter-control" for="inventory-location">地点<select id="inventory-location" v-model="inventoryLocationFilter" aria-label="按地点筛选"><option value="">全部地点</option><option v-for="item in inventoryLocations" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><button class="link" type="button" @click="clearInventoryFilters">清除筛选</button></div><div class="table-meta"><span>显示 {{ filteredInventory.length ? (inventoryPage - 1) * inventoryPageSize + 1 : 0 }}–{{ Math.min(inventoryPage * inventoryPageSize, filteredInventory.length) }} / {{ filteredInventory.length }}</span><label>每页 <select v-model.number="inventoryPageSize" aria-label="库存每页数量"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label></div><div class="table-wrap"><table class="data-table"><thead><tr><th>手机 / IMEI</th><th>品牌型号</th><th>状态</th><th>所在地点</th><th>托盘</th><th></th></tr></thead><tbody><tr v-for="item in pagedInventory" :key="String(item.imei)" tabindex="0" @click="selectInventory(item)" @keyup.enter="selectInventory(item)"><td><code>{{ item.imei }}</code><small v-if="item.imei2">IMEI2：{{ item.imei2 }}</small></td><td>{{ item.brand || '—' }} {{ item.model || '' }}</td><td><span :class="['status-badge', statusClass(item.status)]">{{ statusText(item.status) }}</span></td><td>{{ locationNameById(item.location_id) }}</td><td>{{ item.tray_id || '散台' }}</td><td><button class="link" type="button" @click.stop="selectInventory(item)">查看</button></td></tr></tbody></table></div><div v-if="!refreshLoading && !pagedInventory.length" class="empty-state"><span>□</span><strong>没有找到库存手机</strong><small>尝试清除筛选，或确认手机已在当前账号的数据范围内。</small><button class="secondary" type="button" @click="clearInventoryFilters">清除筛选</button></div><div v-if="filteredInventory.length" class="pager"><button class="secondary small-button" type="button" :disabled="inventoryPage <= 1" @click="inventoryPage--">上一页</button><span>第 {{ inventoryPage }} / {{ inventoryTotalPages }} 页</span><button class="secondary small-button" type="button" :disabled="inventoryPage >= inventoryTotalPages" @click="inventoryPage++">下一页</button></div><aside v-if="selectedInventory" ref="inventoryDrawer" class="detail-drawer" role="dialog" aria-modal="true" aria-labelledby="inventory-detail-title" tabindex="-1" @keydown="handleDrawerKeydown"><button class="drawer-close" type="button" aria-label="关闭库存详情" @click="closeInventoryDrawer">×</button><p class="eyebrow">手机详情</p><h3 id="inventory-detail-title">{{ selectedInventory.brand || '' }} {{ selectedInventory.model || '未知型号' }}</h3><span :class="['status-badge', statusClass(selectedInventory.status)]">{{ statusText(selectedInventory.status) }}</span><dl><div><dt>IMEI 1</dt><dd><code>{{ selectedInventory.imei || '—' }}</code><button class="link" type="button" @click="copyValue(selectedInventory.imei)">复制</button></dd></div><div><dt>IMEI 2</dt><dd><code>{{ selectedInventory.imei2 || '—' }}</code></dd></div><div><dt>地点</dt><dd>{{ locationNameById(selectedInventory.location_id) }}</dd></div><div><dt>托盘</dt><dd>{{ selectedInventory.tray_id || '散台' }}</dd></div></dl></aside></section>

      <section v-else-if="active === 'documents'" class="page-panel data-page documents-page"><div class="panel-heading compact-panel-heading"><div><h2 class="sr-only">业务单据</h2><p class="panel-summary">当前加载 {{ filteredDocuments.length }} 张单据；状态代表当前交接位置。</p></div><button class="secondary" type="button" :disabled="refreshLoading" @click="refresh">{{ refreshLoading ? '刷新中…' : '刷新单据' }}</button></div><div class="filter-bar"><div class="search-field"><label for="documents-search">关键词</label><span>⌕</span><input id="documents-search" v-model="documentsSearch" placeholder="单号、状态或地点" aria-label="搜索业务单据" /></div><label class="filter-control" for="documents-type">类型<select id="documents-type" v-model="documentsTypeFilter" aria-label="按单据类型筛选"><option value="">全部类型</option><option v-for="type in documentTypes" :key="type" :value="type">{{ documentTypeLabel(type) }}</option></select></label><label class="filter-control" for="documents-status">状态<select id="documents-status" v-model="documentsStatusFilter" aria-label="按单据状态筛选"><option value="">全部状态</option><option v-for="status in documentStatuses" :key="status" :value="status">{{ statusText(status) }}</option></select></label><button class="link" type="button" @click="clearDocumentFilters">清除筛选</button></div><div class="table-meta"><span>显示 {{ filteredDocuments.length ? (documentsPage - 1) * documentsPageSize + 1 : 0 }}–{{ Math.min(documentsPage * documentsPageSize, filteredDocuments.length) }} / {{ filteredDocuments.length }}</span><label>每页 <select v-model.number="documentsPageSize" aria-label="单据每页数量"><option :value="15">15</option><option :value="30">30</option><option :value="50">50</option></select></label></div><div class="table-wrap"><table class="data-table"><thead><tr><th>单号</th><th>类型</th><th>状态</th><th>来源地点</th><th>目标地点</th><th>数量</th><th></th></tr></thead><tbody><tr v-for="item in pagedDocuments" :key="String(item.no)" tabindex="0" @click="selectDocument(item)" @keyup.enter="selectDocument(item)"><td><code>{{ item.no }}</code></td><td><span class="type-badge">{{ documentTypeLabel(item.type) }}</span></td><td><span :class="['status-badge', statusClass(item.status)]">{{ statusText(item.status) }}</span></td><td>{{ locationNameById(item.location_id) }}</td><td>{{ locationNameById(item.destination_location_id) }}</td><td>{{ item.received_count != null ? item.received_count + ' / ' + (item.total_count || 0) : (item.total_count || 0) }}</td><td><button class="link" type="button" @click.stop="selectDocument(item)">详情</button></td></tr></tbody></table></div><div v-if="!refreshLoading && !pagedDocuments.length" class="empty-state"><span>□</span><strong>没有找到业务单据</strong><small>尝试清除筛选，或刷新后再查看。</small><button class="secondary" type="button" @click="clearDocumentFilters">清除筛选</button></div><div v-if="filteredDocuments.length" class="pager"><button class="secondary small-button" type="button" :disabled="documentsPage <= 1" @click="documentsPage--">上一页</button><span>第 {{ documentsPage }} / {{ documentsTotalPages }} 页</span><button class="secondary small-button" type="button" :disabled="documentsPage >= documentsTotalPages" @click="documentsPage++">下一页</button></div><aside v-if="selectedDocument" ref="documentDrawer" class="detail-drawer" role="dialog" aria-modal="true" aria-labelledby="document-detail-title" tabindex="-1" @keydown="handleDrawerKeydown"><button class="drawer-close" type="button" aria-label="关闭单据详情" @click="closeDocumentDrawer">×</button><p class="eyebrow">{{ documentTypeLabel(selectedDocument.type) }}</p><h3 id="document-detail-title"><code>{{ selectedDocument.no }}</code></h3><span :class="['status-badge', statusClass(selectedDocument.status)]">{{ statusText(selectedDocument.status) }}</span><dl><div><dt>来源地点</dt><dd>{{ locationNameById(selectedDocument.location_id) }}</dd></div><div><dt>目标地点</dt><dd>{{ locationNameById(selectedDocument.destination_location_id) }}</dd></div><div><dt>数量</dt><dd>{{ selectedDocument.total_count || 0 }} 项</dd></div><div><dt>已接收</dt><dd>{{ selectedDocument.received_count == null ? '—' : selectedDocument.received_count + ' 项' }}</dd></div></dl></aside></section>

      <section v-else-if="active === 'drafts'" class="page-panel data-page drafts-page"><div class="panel-heading compact-panel-heading"><div><h2 class="sr-only">离线草稿</h2><p class="panel-summary">本机暂存的操作</p></div><div class="panel-actions"><button class="secondary" type="button" @click="refresh">刷新</button><button class="primary" type="button" :disabled="!online || !filteredDrafts.some((item) => isDraftRetryable(item.status))" @click="retryAllDrafts">{{ online ? '重试待同步草稿' : '等待联网' }}</button></div></div><div class="draft-summary"><button type="button" :class="['summary-pill', { active: draftsFilter === 'all' }]" @click="draftsFilter = 'all'">全部 <b>{{ drafts.length }}</b></button><button type="button" :class="['summary-pill', { active: draftsFilter === 'pending' }]" @click="draftsFilter = 'pending'">待同步 <b>{{ drafts.filter((item) => item.status === 'pending').length }}</b></button><button type="button" :class="['summary-pill', { active: draftsFilter === 'conflict' }]" @click="draftsFilter = 'conflict'">有冲突 <b>{{ drafts.filter((item) => item.status === 'conflict').length }}</b></button><button type="button" :class="['summary-pill', { active: draftsFilter === 'synced' }]" @click="draftsFilter = 'synced'">已同步 <b>{{ drafts.filter((item) => item.status === 'synced').length }}</b></button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>作业</th><th>阶段</th><th>数量</th><th>创建时间</th><th>状态 / 原因</th><th></th></tr></thead><tbody><tr v-for="draft in filteredDrafts" :key="draft.id"><td><strong>{{ actionLabels[draft.action] || draft.action }}</strong><small>{{ draft.workflow === 'ghana' ? '加纳综合岗位' : draft.workflow === 'shenzhen' ? '深圳综合岗位' : '单项作业' }}</small></td><td>{{ phaseLabels[draft.phase] || draft.phase }}</td><td>{{ draft.values.length }} 项</td><td>{{ formatDate(draft.created_at) }}</td><td><span :class="['status-badge', statusClass(draft.status)]">{{ draft.status === 'pending' ? '待同步' : draft.status === 'syncing' ? '同步中' : draft.status === 'synced' ? '已同步' : draft.status === 'conflict' ? '冲突待处理' : draft.status }}</span><small v-if="draft.error" class="row-error">{{ draft.error }}</small></td><td><button v-if="draft.status !== 'synced'" class="secondary small-button" type="button" :disabled="!online || draft.status === 'syncing'" @click="retryDraft(draft)">{{ draft.status === 'conflict' ? '核对后重试' : '重试' }}</button></td></tr></tbody></table></div><div v-if="!filteredDrafts.length" class="empty-state"><span>✓</span><strong>{{ drafts.length ? '当前筛选没有草稿' : '暂无离线草稿' }}</strong><small>{{ drafts.length ? '切换上方状态筛选查看其他记录。' : '网络正常时直接提交；断网后系统会在这里保留待同步操作。' }}</small></div></section>

      <section v-else-if="active === 'profile'" class="page-panel data-page profile-page" aria-label="个人资料与安全"><div class="profile-grid"><section class="form-card"><h3>基本资料</h3><div class="field-group"><label for="profile-name">显示名称 <em>必填</em></label><input id="profile-name" v-model="profileName" autocomplete="name" placeholder="例如：张三" required /></div><div class="field-group"><label for="profile-username">英文用户名</label><input id="profile-username" v-model="profileUsername" autocomplete="username" placeholder="仅英文字母，可留空" /><small>登录账号：{{ user.username || user.phone || '—' }}</small></div><button class="primary" type="button" @click="saveBasicProfile">保存资料</button></section><section class="form-card"><h3>修改密码</h3><p class="form-help">至少 8 位。若不修改密码，下面两项保持为空即可。</p><div class="field-group"><label for="profile-current-password">当前密码</label><div class="input-with-action"><input id="profile-current-password" v-model="currentPassword" :type="profileCurrentPasswordVisible ? 'text' : 'password'" autocomplete="current-password" placeholder="输入当前密码" /><button class="input-action" type="button" :aria-label="profileCurrentPasswordVisible ? '隐藏当前密码' : '显示当前密码'" @click="profileCurrentPasswordVisible = !profileCurrentPasswordVisible">{{ profileCurrentPasswordVisible ? '隐藏' : '显示' }}</button></div></div><div class="field-group"><label for="profile-next-password">新密码</label><div class="input-with-action"><input id="profile-next-password" v-model="nextPassword" :type="profileNextPasswordVisible ? 'text' : 'password'" autocomplete="new-password" minlength="8" placeholder="至少 8 位" /><button class="input-action" type="button" :aria-label="profileNextPasswordVisible ? '隐藏新密码' : '显示新密码'" @click="profileNextPasswordVisible = !profileNextPasswordVisible">{{ profileNextPasswordVisible ? '隐藏' : '显示' }}</button></div></div><button class="secondary" type="button" @click="savePassword">保存密码</button></section></div><section class="account-context"><div><span>当前岗位</span><strong>{{ roleLabel || '—' }}</strong></div><div><span>授权地点</span><strong>{{ !locationsLoaded ? '加载中' : authorizedLocationCount ? authorizedLocationCount + ' 个' : '暂无授权' }}</strong></div><div><span>权限数量</span><strong>{{ user.permissions.length }} 项</strong></div></section></section>

      <section v-else-if="['admin', 'system', 'users'].includes(active)" class="page-panel admin-page"><div class="admin-tabs" role="tablist" aria-label="系统管理分类" @keydown="handleAdminTabKeydown"><button v-if="has('user:manage')" type="button" role="tab" id="admin-tab-users" :aria-controls="adminTab === 'users' ? 'admin-panel-users' : undefined" :aria-selected="adminTab === 'users'" :class="{ active: adminTab === 'users' }" @click="adminTab = 'users'">用户 <b>{{ adminData.users.length }}</b></button><button v-if="has('user:manage')" type="button" role="tab" id="admin-tab-organizations" :aria-controls="adminTab === 'organizations' ? 'admin-panel-organizations' : undefined" :aria-selected="adminTab === 'organizations'" :class="{ active: adminTab === 'organizations' }" @click="adminTab = 'organizations'">组织 <b>{{ adminData.organizations.length }}</b></button><button v-if="has('user:manage')" type="button" role="tab" id="admin-tab-locations" :aria-controls="adminTab === 'locations' ? 'admin-panel-locations' : undefined" :aria-selected="adminTab === 'locations'" :class="{ active: adminTab === 'locations' }" @click="adminTab = 'locations'">地点 <b>{{ adminData.locations.length }}</b></button><button v-if="has('role:manage')" type="button" role="tab" id="admin-tab-roles" :aria-controls="adminTab === 'roles' ? 'admin-panel-roles' : undefined" :aria-selected="adminTab === 'roles'" :class="{ active: adminTab === 'roles' }" @click="adminTab = 'roles'">角色 <b>{{ adminData.roles.length }}</b></button><button v-if="has('audit:view')" type="button" role="tab" id="admin-tab-audits" :aria-controls="adminTab === 'audits' ? 'admin-panel-audits' : undefined" :aria-selected="adminTab === 'audits'" :class="{ active: adminTab === 'audits' }" @click="adminTab = 'audits'">审计 <b>{{ adminData.audits.length }}</b></button></div>
        <section v-if="adminTab === 'users'" class="admin-section" role="tabpanel" id="admin-panel-users" aria-labelledby="admin-tab-users" tabindex="0"><div class="panel-heading compact-heading"><div><h2>用户与岗位</h2><p>岗位决定能看到的页面；数据范围决定能看到的地点。</p></div></div><details class="admin-create-details"><summary><strong>新建用户</strong><small>填写账号并分配岗位</small></summary><form class="admin-form" @submit.prevent="createAdminUser"><div class="form-card"><div class="field-grid"><div class="field-group"><label for="new-identifier">登录账号 <em>必填</em></label><input id="new-identifier" v-model="newIdentifier" placeholder="手机号或英文用户名" required /></div><div class="field-group"><label for="new-name">显示姓名 <em>必填</em></label><input id="new-name" v-model="newName" placeholder="工作人员姓名" required /></div><div class="field-group"><label for="new-password">初始密码 <em>至少 8 位</em></label><div class="input-with-action"><input id="new-password" v-model="newPassword" :type="newPasswordVisible ? 'text' : 'password'" autocomplete="new-password" minlength="8" placeholder="请设置初始密码" required /><button type="button" class="input-action" :aria-label="newPasswordVisible ? '隐藏初始密码' : '显示初始密码'" :aria-pressed="newPasswordVisible" @click="newPasswordVisible = !newPasswordVisible">{{ newPasswordVisible ? '隐藏' : '显示' }}</button></div></div></div><h4>分配岗位 <span>可多选</span></h4><div class="role-choice-grid"><label v-for="role in adminData.roles" :key="role.id" class="role-choice" :class="{ selected: newRoleIds.includes(Number(role.id)) }"><input v-model="newRoleIds" type="checkbox" :value="Number(role.id)" /><span><strong>{{ role.name }}</strong><small>{{ role.work_group || role.code }}</small></span></label></div><p class="form-help">通常一个工作人员只分配一个岗位；只有确有兼岗时才多选。</p><details class="advanced-details"><summary>高级：限制数据范围（可选）</summary><p>角色给出操作权限；这里进一步限制组织、地点、国家或本人负责的记录。</p><div class="scope-builder"><select v-model="scopePermission" aria-label="范围权限"><option value="">选择权限</option><option v-for="code in Object.keys(permissionLabels)" :key="code" :value="code">{{ permissionLabel(code) }}</option></select><select v-model="scopeKind" aria-label="范围类型"><option value="location">地点</option><option value="organization">组织</option><option value="country">国家 / 地区</option><option value="own">本人负责</option><option value="all">全部</option></select><select v-if="scopeKind === 'location'" v-model="scopeValue" aria-label="选择地点"><option value="">选择地点</option><option v-for="item in workLocations" :key="'scope-loc-' + item.id" :value="String(item.id)">{{ locationLabel(item) }}</option></select><select v-else-if="scopeKind === 'organization'" v-model="scopeValue" aria-label="选择组织"><option value="">选择组织</option><option v-for="item in adminData.organizations" :key="'scope-org-' + item.id" :value="String(item.id)">{{ item.name }}（{{ item.code }}）</option></select><select v-else-if="scopeKind === 'country'" v-model="scopeValue" aria-label="选择国家 / 地区"><option value="">选择国家 / 地区</option><option v-for="country in countryOptions" :key="'scope-country-' + country" :value="country">{{ country }}</option></select><span v-else-if="scopeKind === 'own'" class="scope-all-label">本人创建或负责的记录</span><span v-else class="scope-all-label">全部范围</span><button class="secondary" type="button" @click="addScopeRow('new')">添加范围</button></div><div v-if="newScopeRows.length" class="scope-list"><div v-for="(row, index) in newScopeRows" :key="row.permission_code + '-' + index"><span>{{ permissionLabel(row.permission_code) }}</span><small>{{ scopeValueLabel(row) }}</small><button class="link" type="button" @click="removeScopeRow(index, 'new')">移除</button></div></div><textarea v-model="newScopes" aria-label="高级范围 JSON" placeholder="需要导入已有配置时，可直接粘贴 JSON 数组"></textarea></details><button class="primary" type="submit">创建用户</button></div></form></details><div class="table-toolbar"><span>显示 {{ filteredAdminUsers.length }} 位用户</span><div><input v-model="userSearch" placeholder="搜索用户" aria-label="再次搜索用户" /><select v-model="userStatusFilter" aria-label="筛选用户状态"><option value="active">启用</option><option value="inactive">停用</option><option value="all">全部</option></select></div></div><div class="table-wrap"><table class="data-table admin-table"><thead><tr><th>账号</th><th>姓名</th><th>岗位</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="item in filteredAdminUsers" :key="item.id"><td><code>{{ item.username || item.phone || '—' }}</code><small v-if="item.phone && item.username">手机：{{ item.phone }}</small></td><td>{{ item.display_name }}</td><td>{{ userRoleLabel(item) }}</td><td><span :class="['status-badge', item.is_active ? 'success' : 'danger']">{{ item.is_active ? '启用' : '停用' }}</span></td><td class="row-actions"><button class="link" type="button" @click="toggleUser(item)">{{ item.is_active ? '停用' : '启用' }}</button><button class="link" type="button" @click="editUser(item)">编辑权限</button></td></tr></tbody></table></div><div v-if="!filteredAdminUsers.length" class="empty-state"><span>□</span><strong>没有符合条件的用户</strong><small>切换状态筛选或清除搜索。</small></div><div v-if="editingUserId !== null" class="edit-card"><div class="edit-card-head"><div><p class="eyebrow">权限编辑</p><h3>用户 #{{ editingUserId }}</h3></div><button class="link" type="button" @click="editingUserId = null">关闭</button></div><h4>岗位</h4><div class="role-choice-grid"><label v-for="role in adminData.roles" :key="'edit-' + role.id" class="role-choice" :class="{ selected: editingRoleIds.includes(Number(role.id)) }"><input v-model="editingRoleIds" type="checkbox" :value="Number(role.id)" /><span><strong>{{ role.name }}</strong><small>{{ role.work_group || role.code }}</small></span></label></div><details class="advanced-details" open><summary>数据范围</summary><div class="scope-builder"><select v-model="scopePermission" aria-label="编辑范围权限"><option value="">选择权限</option><option v-for="code in Object.keys(permissionLabels)" :key="'edit-' + code" :value="code">{{ permissionLabel(code) }}</option></select><select v-model="scopeKind" aria-label="编辑范围类型"><option value="location">地点</option><option value="organization">组织</option><option value="country">国家 / 地区</option><option value="own">本人负责</option><option value="all">全部</option></select><select v-if="scopeKind === 'location'" v-model="scopeValue" aria-label="编辑范围地点"><option value="">选择地点</option><option v-for="item in workLocations" :key="'edit-loc-' + item.id" :value="String(item.id)">{{ locationLabel(item) }}</option></select><select v-else-if="scopeKind === 'organization'" v-model="scopeValue" aria-label="编辑范围组织"><option value="">选择组织</option><option v-for="item in adminData.organizations" :key="'edit-org-' + item.id" :value="String(item.id)">{{ item.name }}</option></select><select v-else-if="scopeKind === 'country'" v-model="scopeValue" aria-label="编辑范围国家 / 地区"><option value="">选择国家 / 地区</option><option v-for="country in countryOptions" :key="'edit-country-' + country" :value="country">{{ country }}</option></select><span v-else-if="scopeKind === 'own'" class="scope-all-label">本人创建或负责的记录</span><span v-else class="scope-all-label">全部范围</span><button class="secondary" type="button" @click="addScopeRow('editing')">添加范围</button></div><div v-if="editingScopeRows.length" class="scope-list"><div v-for="(row, index) in editingScopeRows" :key="'editing-' + row.permission_code + '-' + index"><span>{{ permissionLabel(row.permission_code) }}</span><small>{{ scopeValueLabel(row) }}</small><button class="link" type="button" @click="removeScopeRow(index, 'editing')">移除</button></div></div><textarea v-model="editingScopes" aria-label="编辑范围 JSON"></textarea></details><div class="edit-actions"><button class="primary" type="button" @click="saveUserPermissions">保存权限</button><button class="secondary" type="button" @click="editingUserId = null">取消</button></div></div></section>
        <section v-else-if="adminTab === 'organizations'" class="admin-section" role="tabpanel" id="admin-panel-organizations" aria-labelledby="admin-tab-organizations" tabindex="0"><div class="panel-heading compact-heading"><div><h2>组织</h2><p>跨境业务的公司、办公室和门店所属组织。</p></div></div><form class="form-card inline-admin-form" @submit.prevent="createOrganization"><div class="field-grid"><div class="field-group"><label for="org-code">组织代码 <em>必填</em></label><input id="org-code" v-model="orgCode" placeholder="如 GH-STORE" required /></div><div class="field-group"><label for="org-name">组织名称 <em>必填</em></label><input id="org-name" v-model="orgName" placeholder="组织显示名称" required /></div><div class="field-group"><label for="org-country">国家 / 地区 <em>必填</em></label><input id="org-country" v-model="orgCountry" placeholder="如 GH" required /></div></div><button class="primary" type="submit">创建组织</button></form><div class="table-wrap"><table class="data-table"><thead><tr><th>代码</th><th>组织名称</th><th>国家</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="item in adminData.organizations" :key="item.id"><td><code>{{ item.code }}</code></td><td>{{ item.name }}</td><td>{{ item.country || '—' }}</td><td><span :class="['status-badge', item.is_active ? 'success' : 'danger']">{{ item.is_active ? '启用' : '停用' }}</span></td><td><button class="link" type="button" @click="toggleOrganization(item)">{{ item.is_active ? '停用' : '启用' }}</button></td></tr></tbody></table></div></section>
        <section v-else-if="adminTab === 'locations'" class="admin-section" role="tabpanel" id="admin-panel-locations" aria-labelledby="admin-tab-locations" tabindex="0"><div class="panel-heading compact-heading"><div><h2>作业地点</h2><p>地点类型会影响调拨、发运和维修的可选范围。</p></div></div><form class="form-card inline-admin-form" @submit.prevent="createLocation"><div class="field-grid"><div class="field-group"><label for="loc-org">所属组织 <em>必填</em></label><select id="loc-org" v-model="locOrganizationId" required><option value="">选择组织</option><option v-for="item in adminData.organizations.filter((row) => row.is_active)" :key="item.id" :value="String(item.id)">{{ item.name }}（{{ item.code }}）</option></select></div><div class="field-group"><label for="loc-code">地点代码 <em>必填</em></label><input id="loc-code" v-model="locCode" placeholder="如 GH-MGMT" required /></div><div class="field-group"><label for="loc-name">地点名称 <em>必填</em></label><input id="loc-name" v-model="locName" placeholder="例如：加纳管理处仓库" required /></div><div class="field-group"><label for="loc-type">地点类型 <em>必填</em></label><select id="loc-type" v-model="locType"><option value="warehouse">仓库</option><option value="receiving">接收区</option><option value="store">门店</option><option value="repair">维修区</option></select></div></div><button class="primary" type="submit">创建地点</button></form><div class="table-wrap"><table class="data-table"><thead><tr><th>代码 / 名称</th><th>所属组织</th><th>类型</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="item in adminData.locations" :key="item.id"><td><code>{{ item.code }}</code><strong>{{ item.name }}</strong></td><td>{{ item.organization_name || item.organization_id }}</td><td>{{ locationTypeLabel(item.location_type) }}</td><td><span :class="['status-badge', item.is_active ? 'success' : 'danger']">{{ item.is_active ? '启用' : '停用' }}</span></td><td><button class="link" type="button" @click="toggleLocation(item)">{{ item.is_active ? '停用' : '启用' }}</button></td></tr></tbody></table></div></section>
        <section v-else-if="adminTab === 'roles'" class="admin-section" role="tabpanel" id="admin-panel-roles" aria-labelledby="admin-tab-roles" tabindex="0"><div class="panel-heading compact-heading"><div><h2>角色与权限</h2><p>用岗位职责组织权限；旧的已合并岗位保持停用，不要重新启用。</p></div><input v-model="roleSearch" class="compact-search" placeholder="搜索角色" aria-label="搜索角色" /></div><details class="admin-create-details role-create-details"><summary><strong>新建角色</strong><small>填写职责并选择权限</small></summary><form class="form-card role-form" @submit.prevent="createRole"><h3>新建角色</h3><div class="field-grid"><div class="field-group"><label for="role-code">角色代码 <em>必填</em></label><input id="role-code" v-model="roleCode" placeholder="如 store_ops" required /></div><div class="field-group"><label for="role-name">角色名称 <em>必填</em></label><input id="role-name" v-model="roleName" placeholder="面向工作人员的名称" required /></div><div class="field-group"><label for="role-work-group">工作组</label><input id="role-work-group" v-model="roleWorkGroup" placeholder="如 GHANA_OPERATIONS" /></div><div class="field-group full-field"><label for="role-description">岗位职责</label><textarea id="role-description" v-model="roleDescription" placeholder="写清楚谁承接什么、完成什么、交给谁"></textarea></div></div><h4>选择权限 <span>{{ selectedRolePermissions.length }} 项已选</span></h4><div class="permission-groups"><div v-for="group in permissionGroups" :key="group.label" class="permission-group"><strong>{{ group.label }}</strong><label v-for="code in group.codes" :key="code" class="permission-check"><input type="checkbox" :checked="selectedRolePermissions.includes(code)" @change="toggleRolePermission(code)" /><span>{{ permissionLabel(code) }}</span><small>{{ code }}</small></label></div></div><details class="advanced-details"><summary>高级：直接输入权限代码</summary><input v-model="rolePermissionsText" aria-label="直接输入权限代码" placeholder="用逗号分隔，例如 phone:view,report:view" /></details><button class="primary" type="submit">创建角色</button></form></details><div class="table-wrap"><table class="data-table roles-table"><thead><tr><th>角色</th><th>工作组</th><th>职责</th><th>权限</th><th>状态</th></tr></thead><tbody><tr v-for="item in filteredAdminRoles" :key="item.id"><td><code>{{ item.code }}</code><strong>{{ item.name }}</strong></td><td>{{ item.work_group || '未分组' }}</td><td>{{ item.description || '—' }}</td><td><span class="count-badge">{{ Array.isArray(item.permission_codes) ? item.permission_codes.length : 0 }} 项</span></td><td><span :class="['status-badge', item.is_active ? 'success' : 'danger']">{{ item.is_active ? '启用' : '停用' }}</span></td></tr></tbody></table></div><div v-if="!filteredAdminRoles.length" class="empty-state"><span>□</span><strong>没有符合条件的角色</strong><small>尝试清除搜索。</small></div></section>
        <section v-else class="admin-section" role="tabpanel" id="admin-panel-audits" aria-labelledby="admin-tab-audits" tabindex="0"><div class="panel-heading compact-heading"><div><h2>审计记录</h2><p>记录账号、权限和业务操作的变更，便于追责和复盘。</p></div><input v-model="auditSearch" class="compact-search" placeholder="搜索动作或资源" aria-label="搜索审计记录" /></div><div class="table-wrap"><table class="data-table"><thead><tr><th>时间</th><th>操作</th><th>资源</th><th>操作人</th></tr></thead><tbody><tr v-for="item in filteredAudits" :key="item.id"><td>{{ formatDate(item.created_at) }}</td><td>{{ item.action }}</td><td>{{ item.resource_type }} #{{ item.resource_id }}</td><td>{{ item.user_id || '—' }}</td></tr></tbody></table></div><div v-if="!filteredAudits.length" class="empty-state"><span>✓</span><strong>暂无审计记录</strong><small>发生管理变更后会在这里显示。</small></div></section>
      </section>
    </section>
    <div v-if="showConfirm" class="confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title" @keydown="handleConfirmKeydown" @click.self="cancelConfirmation"><section ref="confirmDialog" class="confirm-dialog"><span class="confirm-icon">!</span><div><p class="eyebrow">请确认</p><h2 id="confirm-title">{{ confirmTitle }}</h2><p>{{ confirmDescription }}</p></div><div class="confirm-actions"><button ref="confirmCancelButton" class="secondary" type="button" @click="cancelConfirmation">继续作业</button><button class="danger-button" type="button" @click="confirmPendingAction">{{ confirmButtonLabel }}</button></div></section></div>
    <div v-if="showHelp" class="help-overlay" role="dialog" aria-modal="true" aria-labelledby="help-title" tabindex="-1" @keydown="handleHelpKeydown" @click.self="showHelp = false"><section ref="helpDialog" class="help-dialog"><button class="drawer-close" type="button" aria-label="关闭帮助" @click="showHelp = false">×</button><p class="eyebrow">快速帮助</p><h2 id="help-title">第一次作业看这里</h2><div class="help-grid"><div><span>1</span><strong>先选地点</strong><p>当前地点是实物现在所在的位置；目标地点是下一站。</p></div><div><span>2</span><strong>容器优先</strong><p>装托盘或装箱先锁定容器，再连续扫描里面的手机或托盘。</p></div><div><span>3</span><strong>看到成功单号</strong><p>只有出现绿色成功卡和单号，才把实物交给下一岗位。</p></div><div><span>4</span><strong>断网不用停工</strong><p>提交失败会保存为离线草稿，联网后在“离线草稿”里重试。</p></div></div><button class="primary" type="button" @click="showHelp = false">知道了</button></section></div>
  </main>
</template>
