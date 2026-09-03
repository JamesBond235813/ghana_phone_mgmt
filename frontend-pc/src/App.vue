<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import * as api from "./api";
import type { CurrentUser } from "./api";

type Task = {
  key: string;
  label: string;
  hint: string;
  permissions: string[];
  mode: "imei" | "container";
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
  accepted: boolean;
  status: string;
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
    label: "查询手机",
    hint: "查看 IMEI 全程轨迹",
    permissions: ["phone:view"],
    mode: "imei",
  },
];
const user = ref<CurrentUser | null>(null);
const active = ref("dashboard");
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
const documentNo = ref("");
const logisticsNo = ref("");
const accepted = ref(true);
const targetTrayCode = ref(""); const targetBoxCode = ref("");
const salesType = ref<"RETAIL" | "WHOLESALE">("RETAIL");
const customerName = ref("");
const salePrices = ref("");
const repairResult = ref("REPAIRED");
const disposition = ref("AVAILABLE_AGAIN");
const adjustmentDecision = ref("IGNORE");
const adjustmentTargetStatus = ref("可再次销售");
const workLocations = ref<Record<string, unknown>[]>([]);
const dashboardStats = ref({ phones: 0, documents: 0, pendingDrafts: 0 });
const phoneDetail = ref<Record<string, unknown> | null>(null);
const inventory = ref<Record<string, unknown>[]>([]);
const documents = ref<Record<string, unknown>[]>([]);
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
const roleCode = ref(""); const roleName = ref(""); const rolePermissionsText = ref("");
const profileName = ref(""); const profileUsername = ref(""); const currentPassword = ref(""); const nextPassword = ref("");
const editingUserId = ref<number | null>(null); const editingRoleIds = ref<number[]>([]); const editingScopes = ref("");
const scannerInput = ref<HTMLInputElement | null>(null);
const visibleTasks = computed(() =>
  tasks.filter((task) =>
    task.permissions.some((permission) =>
      user.value?.permissions?.includes(permission),
    ),
  ),
);
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
const activeLocations = computed(() => workLocations.value);
const sourceLocations = computed(() =>
  currentTask.value
    ? workLocations.value.filter((item) => locationAllowed(currentPhasePermission(), item))
    : workLocations.value,
);
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
      (scope.kind === "location" && scope.values.includes(String(item.id))),
  );
}
function locationLabel(item: Record<string, unknown>) {
  return `${item.organization_name || item.organization_id} · ${item.name || item.code}（${item.code || item.id}）`;
}
function select(key: string) {
  active.value = key;
  error.value = "";
  message.value = "";
  scanned.value = [];
  phoneDetail.value = null;
  if (key === "profile" && user.value) { profileName.value = user.value.display_name; profileUsername.value = user.value.username || ""; currentPassword.value = ""; nextPassword.value = ""; }
  if (key === "admin") adminTab.value = has("user:manage") ? "users" : has("role:manage") ? "roles" : "audits";
  if (tasks.some((task) => task.key === key)) {
    const task = tasks.find((row) => row.key === key)!;
    operationPhase.value = phaseFor(task);
    containerKind.value =
      task.key === "box" ? "TRAY" : task.mode === "imei" ? "PHONE" : "PHONE";
  }
  refresh();
  nextTick(() => scannerInput.value?.focus());
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
function isValidImei(value: string) { if (!/^\d{15}$/.test(value)) return false; let total = 0; for (let index = 0; index < value.length; index += 1) { let digit = Number(value[index]); if (index % 2 === 1) { digit *= 2; if (digit > 9) digit -= 9; } total += digit; } return total % 10 === 0; }
function phaseRequiresScan() {
  const task = currentTask.value;
  if (!task) return true;
  return !((task.key === "receiving" && operationPhase.value === "start") || (task.key === "sales" && operationPhase.value === "confirm") || (task.key === "repair" && operationPhase.value === "accept"));
}
function scanMode() { const task = currentTask.value; if (!task) return "imei"; if (["return", "repair"].includes(task.key) && operationPhase.value !== "create") return "imei"; return task.mode; }
function phaseRequiresCurrentLocation() { const key = currentTask.value?.key; return Boolean(key && (["purchase", "tray", "box", "shipment"].includes(key) || (key === "receiving" && operationPhase.value === "start") || (key === "transfer" && operationPhase.value === "issue") || (key === "sales" && operationPhase.value === "create") || (key === "return" && operationPhase.value === "create") || (key === "repair" && operationPhase.value === "create") || (key === "stocktake" && operationPhase.value === "create"))); }
function phaseRequiresDestination() { const key = currentTask.value?.key; return key === "shipment" || (key === "transfer" && operationPhase.value === "issue") || (key === "return" && operationPhase.value === "create"); }
function focusScannerInput() {
  nextTick(() => {
    if (phaseRequiresScan()) scannerInput.value?.focus();
  });
}
function addScan() {
  const value = scanInput.value.trim();
  if (!value) return;
  if (scanMode() === "imei" && !isValidImei(value)) {
    error.value = "IMEI 必须是通过校验的 15 位数字";
    // 丢弃本次无效输入，避免下一次扫码与旧内容拼接
    scanInput.value = "";
    focusScannerInput();
    return;
  }
  if (!scanned.value.includes(value)) scanned.value.push(value);
  scanInput.value = "";
  focusScannerInput();
}
function onScanInput() {
  // 部分扫码枪配置为仅输出字符、不追加回车；IMEI 满 15 位时自动加入
  if (scanMode() === "imei" && /^\d{15}$/.test(scanInput.value)) addScan();
}
function syncOrganization() {
  const row = workLocations.value.find(
    (item) => String(item.id) === locationId.value,
  );
  if (row) organizationId.value = String(row.organization_id);
}
function syncDestinationOrganization() {
  const row = workLocations.value.find(
    (item) => String(item.id) === destinationLocationId.value,
  );
  if (row) destinationOrganizationId.value = String(row.organization_id);
}
function containers() {
  return scanned.value.map((code) => ({ kind: containerKind.value, code }));
}
function saveDraft(task: Task) {
  const draft: Draft = {
    id: crypto.randomUUID(),
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
    accepted: accepted.value,
    status: "pending",
    created_at: new Date().toISOString(),
  };
  drafts.value.unshift(draft);
  localStorage.setItem("gh-phone-offline-queue", JSON.stringify(drafts.value));
  return draft;
}
async function submit() {
  const task = currentTask.value;
  if (!task || (phaseRequiresScan() && !scanned.value.length)) return;
  if (phaseRequiresCurrentLocation() && (!organizationId.value || !locationId.value)) return void (error.value = "请选择当前组织和地点");
  if (phaseRequiresDestination() && (!destinationOrganizationId.value || !destinationLocationId.value)) return void (error.value = "请选择目标组织和地点");
  if (["tray", "box"].includes(task.key) && !containerCode.value.trim()) return void (error.value = "请填写目标容器编号");
  const needsDocument = task.key === "receiving" || task.key === "return" || (task.key === "transfer" && operationPhase.value === "receive") || (task.key === "sales" && operationPhase.value === "confirm") || (task.key === "repair" && operationPhase.value !== "create") || (task.key === "stocktake" && operationPhase.value === "adjust");
  if (needsDocument && !documentNo.value.trim()) return void (error.value = "请填写业务单号");
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
      if (operationPhase.value === "start") result = await api.startReceiving({ shipment_no: documentNo.value.trim(), organization_id: org, location_id: loc });
      else for (const imei of scanned.value) result = await api.inspectReceiving({ receiving_no: documentNo.value.trim(), imei, accepted: accepted.value, note: null, target_tray_code: targetTrayCode.value.trim() || null, target_box_code: targetBoxCode.value.trim() || null });
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
              complete: true,
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
              prices: salePrices.value
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
            })
          : operationPhase.value === "accept"
            ? await api.acceptRepair(documentNo.value.trim())
              : operationPhase.value === "complete"
                ? await (async () => { for (const imei of scanned.value) result = await api.completeRepair(documentNo.value.trim(), { imei, repair_result: repairResult.value }); return result; })()
                : await (async () => { for (const imei of scanned.value) result = await api.reviewRepair(documentNo.value.trim(), { imei, disposition: disposition.value }); return result; })();
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
    message.value =
      task.key === "query"
        ? `查询成功：${result.status || "未知状态"}`
        : `${task.label}已完成`;
    if (task.key !== "query") scanned.value = [];
  } catch (e) {
    if (!online.value || e instanceof TypeError) {
      saveDraft(task);
      message.value = "网络不可用，已保存为待同步草稿";
      error.value = "";
    } else error.value = e instanceof Error ? e.message : "提交失败";
  } finally {
    loading.value = false;
    focusScannerInput();
  }
}
async function refresh() {
  if (!user.value) return;
  try {
    if (active.value === "dashboard") {
      const phoneResult = has("phone:view") ? await api.listPhones({ limit: 500 }) : { items: [], count: 0 };
      const documentResult = has("phone:view") || has("report:view") ? await api.listDocuments({ limit: 500 }) : { items: [], count: 0 };
      const localDrafts = JSON.parse(localStorage.getItem("gh-phone-offline-queue") || "[]");
      dashboardStats.value = { phones: phoneResult.count, documents: documentResult.count, pendingDrafts: localDrafts.filter((item: any) => item.status !== "synced").length };
    } else if (active.value === "inventory")
      inventory.value = (await api.listPhones({ limit: 500 })).items;
    else if (active.value === "documents")
      documents.value = (await api.listDocuments({ limit: 500 })).items;
    else if (active.value === "drafts")
      drafts.value = JSON.parse(
        localStorage.getItem("gh-phone-offline-queue") || "[]",
      );
    else if (active.value === "admin") await loadAdmin();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
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
async function retryDraft(draft: Draft) {
  if (!online.value) return;
  draft.status = "syncing";
  try {
    api.setOperationKey(draft.id);
    const task = tasks.find((item) => item.key === draft.action);
    if (!task) throw new Error("未知草稿类型");
    const org = Number(draft.organization_id), loc = Number(draft.location_id);
    const destination = { destination_organization_id: Number(draft.destination_organization_id), destination_location_id: Number(draft.destination_location_id) };
    if (draft.action === "purchase") await api.createPurchaseReceipt({ organization_id: org, location_id: loc, items: draft.values.map((imei) => ({ imei })) });
    else if (draft.action === "tray") await api.createTray({ code: draft.container_code, location_id: loc, imeis: draft.values });
    else if (draft.action === "box") await api.createBox({ code: draft.container_code, location_id: loc, tray_codes: draft.values });
    else if (draft.action === "shipment") await api.dispatchShipment({ origin_organization_id: org, origin_location_id: loc, ...destination, logistics_no: null, containers: draft.values.map((code) => ({ kind: draft.container_kind, code })) });
    else if (draft.action === "receiving") { if (draft.phase === "start") await api.startReceiving({ shipment_no: draft.document_no, organization_id: org, location_id: loc }); else for (const imei of draft.values) await api.inspectReceiving({ receiving_no: draft.document_no, imei, accepted: draft.accepted, note: null }); }
    else if (draft.action === "transfer") { if (draft.phase === "issue") await api.issueTransfer({ source_organization_id: org, source_location_id: loc, ...destination, containers: draft.values.map((code) => ({ kind: draft.container_kind, code })) }); else await api.receiveTransfer({ transfer_no: draft.document_no, received_imeis: draft.values, complete: true }); }
    else if (draft.action === "sales") { if (draft.phase === "create") await api.createSale({ organization_id: org, location_id: loc, sales_type: "RETAIL", customer_name: null, containers: draft.values.map((code) => ({ kind: draft.container_kind, code })), prices: {} }); else await api.confirmSale(draft.document_no); }
    else if (draft.action === "return") { if (draft.phase === "create") await api.createReturn({ sales_no: draft.document_no, source_organization_id: org, source_location_id: loc, ...destination, imeis: draft.container_kind === "PHONE" ? draft.values : [], containers: draft.container_kind === "PHONE" ? [] : draft.values.map((code) => ({ kind: draft.container_kind, code })) }); else await api.receiveReturn({ return_no: draft.document_no, received_imeis: draft.values }); }
    else if (draft.action === "repair") { if (draft.phase === "create") await api.createRepair({ organization_id: org, location_id: loc, imeis: draft.container_kind === "PHONE" ? draft.values : [], containers: draft.container_kind === "PHONE" ? [] : draft.values.map((code) => ({ kind: draft.container_kind, code })) }); else if (draft.phase === "accept") await api.acceptRepair(draft.document_no); else if (draft.phase === "complete") for (const imei of draft.values) await api.completeRepair(draft.document_no, { imei, repair_result: "REPAIRED" }); else for (const imei of draft.values) await api.reviewRepair(draft.document_no, { imei, disposition: "AVAILABLE_AGAIN" }); }
    else if (draft.action === "stocktake" && draft.phase === "create") await api.submitStocktake({ organization_id: org, location_id: loc, imeis: draft.values });
    else if (draft.action === "stocktake" && draft.phase === "adjust") await api.adjustStocktake(draft.document_no, draft.values.map((imei) => ({ imei, decision: "IGNORE", target_status: "可再次销售" })));
    else throw new Error("该草稿类型不支持重试");
    draft.status = "synced";
    draft.error = "";
  } catch (e) {
    draft.status = "conflict";
    draft.error = e instanceof Error ? e.message : "同步失败";
  } finally {
    api.endOperation();
    localStorage.setItem(
      "gh-phone-offline-queue",
      JSON.stringify(drafts.value),
    );
  }
}
async function retryAllDrafts() { for (const draft of drafts.value.filter((item) => item.status !== 'synced')) await retryDraft(draft); }
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
    newRoleIds.value = []; newScopes.value = "";
    await refresh();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "创建失败";
  }
}
async function createOrganization() { if (!orgCode.value || !orgName.value || !orgCountry.value) return void (error.value = "请填写组织代码、名称和国家"); try { await api.createOrganization({ code: orgCode.value.trim(), name: orgName.value.trim(), country: orgCountry.value.trim() }); orgCode.value = ""; orgName.value = ""; message.value = "组织创建成功"; await loadAdmin() } catch (e) { error.value = e instanceof Error ? e.message : "创建失败" } }
async function createLocation() { if (!locOrganizationId.value || !locCode.value || !locName.value) return void (error.value = "请填写组织、地点代码和名称"); try { await api.createLocation({ organization_id: Number(locOrganizationId.value), code: locCode.value.trim(), name: locName.value.trim(), location_type: locType.value }); locCode.value = ""; locName.value = ""; message.value = "地点创建成功"; await loadAdmin() } catch (e) { error.value = e instanceof Error ? e.message : "创建失败" } }
async function createRole() { if (!roleCode.value || !roleName.value) return void (error.value = "请填写角色代码和名称"); try { await api.createRole({ code: roleCode.value.trim(), name: roleName.value.trim(), permission_codes: rolePermissionsText.value.split(",").map((value) => value.trim()).filter(Boolean) }); roleCode.value = ""; roleName.value = ""; rolePermissionsText.value = ""; message.value = "角色创建成功"; await loadAdmin() } catch (e) { error.value = e instanceof Error ? e.message : "创建失败" } }
async function toggleUser(item: any) { try { await api.updateUser(Number(item.id), { is_active: !item.is_active }); await loadAdmin() } catch (e) { error.value = e instanceof Error ? e.message : "更新失败" } }
function editUser(item: any) { editingUserId.value = Number(item.id); editingRoleIds.value = Array.isArray(item.role_ids) ? item.role_ids.map(Number) : []; editingScopes.value = JSON.stringify(item.scopes || [], null, 2); }
async function saveUserPermissions() { if (editingUserId.value === null) return; try { const scopes = editingScopes.value.trim() ? JSON.parse(editingScopes.value) : []; if (!Array.isArray(scopes)) throw new Error("数据范围必须是 JSON 数组"); await api.updateUser(editingUserId.value, { role_ids: editingRoleIds.value, scopes }); editingUserId.value = null; message.value = "用户权限已更新"; await loadAdmin() } catch (e) { error.value = e instanceof Error ? e.message : "更新失败" } }
async function toggleOrganization(item: any) { try { await api.updateOrganization(Number(item.id), { is_active: !item.is_active }); await loadAdmin() } catch (e) { error.value = e instanceof Error ? e.message : "更新失败" } }
async function toggleLocation(item: any) { try { await api.updateLocation(Number(item.id), { is_active: !item.is_active }); await loadAdmin() } catch (e) { error.value = e instanceof Error ? e.message : "更新失败" } }
async function login() {
  loading.value = true;
  error.value = "";
  try {
    const result = await api.loginByPassword(
      identifier.value.trim(),
      password.value,
    );
    localStorage.setItem("gh-phone-access-token", result.access_token);
    user.value = await api.getCurrentUser();
    workLocations.value = await api.listWorkLocations();
    active.value = "dashboard";
    await refresh();
  } catch (e) {
    localStorage.removeItem("gh-phone-access-token");
    error.value = e instanceof Error ? e.message : "登录失败";
  } finally {
    loading.value = false;
  }
}
function logout() {
  localStorage.removeItem("gh-phone-access-token");
  user.value = null;
  active.value = "dashboard";
}
async function saveProfile() {
  if (!profileName.value.trim()) return void (error.value = "姓名不能为空");
  if (profileUsername.value && !/^[A-Za-z]+$/.test(profileUsername.value)) return void (error.value = "用户名只能包含英文字母");
  if (nextPassword.value && (!currentPassword.value || nextPassword.value.length < 8)) return void (error.value = "修改密码需填写当前密码，且新密码至少 8 位");
  try {
    const updated = await api.updateProfile({ display_name: profileName.value.trim(), username: profileUsername.value.trim() || null });
    if (nextPassword.value) await api.changePassword(currentPassword.value, nextPassword.value);
    user.value = { ...user.value!, ...updated }; currentPassword.value = ""; nextPassword.value = ""; message.value = "个人资料已更新";
  } catch (e) { error.value = e instanceof Error ? e.message : "保存失败"; }
}
onMounted(async () => {
  window.addEventListener("online", () => {
    online.value = true;
  });
  window.addEventListener("offline", () => {
    online.value = false;
  });
  if (localStorage.getItem("gh-phone-access-token")) {
    try {
      user.value = await api.getCurrentUser();
      workLocations.value = await api.listWorkLocations();
      await refresh();
    } catch {
      localStorage.removeItem("gh-phone-access-token");
    }
  }
});
</script>

<template>
  <main v-if="!user" class="login">
    <section>
      <p class="brand">GHANA PHONE MANAGEMENT</p>
      <h1>PC 进销存工作台</h1>
      <p>连接扫码枪后，将光标放在扫码输入框即可作业。</p>
      <input
        v-model="identifier"
        placeholder="手机号或用户名"
        @keyup.enter="login"
      /><input
        v-model="password"
        type="password"
        placeholder="密码"
        @keyup.enter="login"
      /><button class="primary" :disabled="loading" @click="login">登录</button>
      <p v-if="error" class="error">{{ error }}</p>
    </section>
  </main>
  <main v-else class="layout">
    <aside>
      <div class="brand">GHANA PHONE<br /><span>MANAGEMENT</span></div>
      <div class="operator">
        {{ user.display_name }}<small>{{ user.username || user.phone }}</small
        ><button class="logout" @click="logout">退出登录</button>
      </div>
      <nav>
        <button
          :class="{ active: active === 'dashboard' }"
          @click="select('dashboard')"
        >
          <strong>工作台</strong><small>业务总览</small></button
        ><button
          v-for="task in visibleTasks"
          :key="task.key"
          :class="{ active: active === task.key }"
          @click="select(task.key)"
        >
          <strong>{{ task.label }}</strong
          ><small>{{ task.hint }}</small></button
        ><button
          v-if="has('phone:view')"
          :class="{ active: active === 'inventory' }"
          @click="select('inventory')"
        >
          <strong>库存查询</strong><small>库存与 IMEI 轨迹</small></button
        ><button
          v-if="has('phone:view') || has('report:view')"
          :class="{ active: active === 'documents' }"
          @click="select('documents')"
        >
          <strong>业务单据</strong><small>状态与数量</small></button
        ><button
          :class="{ active: active === 'drafts' }"
          @click="select('drafts')"
        >
          <strong>离线草稿</strong><small>待同步任务</small></button
        ><button :class="{ active: active === 'profile' }" @click="select('profile')">
          <strong>个人设置</strong><small>资料与密码</small></button
        ><button
          v-if="canAdmin"
          :class="{ active: active === 'admin' }"
          @click="select('admin')"
        >
          <strong>系统管理</strong><small>用户与组织</small>
        </button>
      </nav>
    </aside>
    <section class="content">
      <header>
        <div>
          <p class="eyebrow">
            {{
              currentTask?.label ||
              (active === "dashboard"
                ? "工作台"
                : active === "inventory"
                  ? "库存查询"
                  : active === "documents"
                    ? "业务单据"
                    : active === "drafts"
                      ? "离线草稿"
                      : active === "profile"
                        ? "个人设置"
                      : "系统管理")
            }}
          </p>
          <h1>{{ currentTask?.hint || "进销存业务控制台" }}</h1>
        </div>
        <span :class="['scanner-status', { offline: !online }]"
          >● {{ online ? "扫码枪就绪" : "离线模式" }}</span
        >
      </header>
      <p v-if="message" class="message">{{ message }}</p>
      <p v-if="error" class="error">{{ error }}</p>
      <section v-if="active === 'dashboard'" class="cards">
        <div>
          <b>业务工作台</b
          ><span
            >左侧选择业务，右侧完成字段录入、扫码枪录入、提交和结果确认。</span
          >
        </div>
        <div>
          <b>权限驱动</b><span>没有权限的任务、阶段和管理入口不会显示。</span>
        </div>
        <div>
          <b>数据范围</b
          ><span>工作地点按当前账号授权范围加载，不使用固定组织或地点。</span>
        </div>
        <div><b>{{ dashboardStats.phones }}</b><span>当前可见手机</span></div>
        <div><b>{{ dashboardStats.documents }}</b><span>当前可见业务单据</span></div>
        <div><b>{{ dashboardStats.pendingDrafts }}</b><span>待同步离线草稿</span></div>
      </section>
      <section v-else-if="currentTask" class="panel">
        <div class="toolbar">
          <h2>{{ currentTask.label }}</h2>
          <select
            v-if="
              [
                'receiving',
                'transfer',
                'sales',
                'return',
                'repair',
                'stocktake',
              ].includes(currentTask.key)
            "
            v-model="operationPhase"
          >
            <option
              v-if="has('receiving:unpack') && currentTask.key === 'receiving'"
              value="start"
            >
              建立接收单
            </option>
            <option
              v-if="has('receiving:accept') && currentTask.key === 'receiving'"
              value="inspect"
            >
              逐台验收
            </option>
            <option
              v-if="has('transfer:create') && currentTask.key === 'transfer'"
              value="issue"
            >
              发起调拨
            </option>
            <option
              v-if="has('transfer:receive') && currentTask.key === 'transfer'"
              value="receive"
            >
              门店收货
            </option>
            <option
              v-if="has('sales:create') && currentTask.key === 'sales'"
              value="create"
            >
              创建销售单
            </option>
            <option
              v-if="has('sales:approve') && currentTask.key === 'sales'"
              value="confirm"
            >
              主管确认
            </option>
            <option
              v-if="has('return:create') && currentTask.key === 'return'"
              value="create"
            >
              发起退回
            </option>
            <option
              v-if="has('return:receive') && currentTask.key === 'return'"
              value="receive"
            >
              管理处接收
            </option>
            <option
              v-if="has('repair:create') && currentTask.key === 'repair'"
              value="create"
            >
              建立维修单
            </option>
            <option
              v-if="has('repair:receive') && currentTask.key === 'repair'"
              value="accept"
            >
              维修接收
            </option>
            <option
              v-if="has('repair:update') && currentTask.key === 'repair'"
              value="complete"
            >
              填写维修结果
            </option>
            <option
              v-if="has('repair:approve') && currentTask.key === 'repair'"
              value="review"
            >
              维修复核
            </option>
            <option
              v-if="has('stocktake:submit') && currentTask.key === 'stocktake'"
              value="create"
            >
              提交盘点
            </option>
            <option
              v-if="has('stocktake:adjust') && currentTask.key === 'stocktake'"
              value="adjust"
            >
              审核差异
            </option>
          </select>
        </div>
        <div class="fields">
          <select
            v-if="phaseRequiresCurrentLocation()"
            v-model="locationId"
            @change="syncOrganization"
          >
            <option value="">选择当前地点</option>
            <option
              v-for="item in sourceLocations"
              :key="String(item.id)"
              :value="String(item.id)"
            >
              {{ locationLabel(item) }}
            </option></select
          ><input
            v-if="phaseRequiresCurrentLocation()"
            v-model="organizationId"
            placeholder="当前组织（自动）"
            readonly
          /><select
            v-if="phaseRequiresDestination()"
            v-model="destinationLocationId"
            @change="syncDestinationOrganization"
          >
            <option value="">选择目标地点</option>
            <option
              v-for="item in activeLocations"
              :key="`dest-${item.id}`"
              :value="String(item.id)"
            >
              {{ locationLabel(item) }}
            </option></select
          ><input
            v-if="phaseRequiresDestination()"
            v-model="destinationOrganizationId"
            placeholder="目标组织（自动）"
            readonly
          /><input
            v-if="['tray', 'box'].includes(currentTask.key)"
            v-model="containerCode"
            placeholder="目标容器编号"
          /><input
            v-if="
              [
                'receiving',
                'transfer',
                'sales',
                'return',
                'repair',
                'stocktake',
              ].includes(currentTask.key)
            "
            v-model="documentNo"
            placeholder="业务单号"
          /><select
            v-if="
              ['shipment', 'transfer', 'sales'].includes(currentTask.key) ||
              (['return', 'repair'].includes(currentTask.key) && operationPhase === 'create')
            "
            v-model="containerKind"
          >
            <option value="PHONE">手机 IMEI</option>
            <option value="TRAY">托盘编号</option>
            <option value="BOX">箱子编号</option></select
          ><input
            v-if="currentTask.key === 'shipment'"
            v-model="logisticsNo"
            placeholder="物流单号（可选）"
          /><select
            v-if="
              currentTask.key === 'receiving' && operationPhase === 'inspect'
            "
            v-model="accepted"
          >
            <option :value="true">验收正常</option>
            <option :value="false">异常/待核查</option></select
          ><input v-if="currentTask.key === 'receiving' && operationPhase === 'inspect' && accepted" v-model="targetTrayCode" placeholder="重新装入托盘编号（可选）" />
          <input v-if="currentTask.key === 'receiving' && operationPhase === 'inspect' && accepted" v-model="targetBoxCode" placeholder="重新装入箱子编号（需填托盘）" />
          <select
            v-if="currentTask.key === 'sales' && operationPhase === 'create'"
            v-model="salesType"
          >
            <option value="RETAIL">零售</option>
            <option value="WHOLESALE">批发</option></select
          ><input
            v-if="currentTask.key === 'sales' && operationPhase === 'create'"
            v-model="customerName"
            placeholder="客户名称（可选）"
          /><input
            v-if="currentTask.key === 'sales' && operationPhase === 'create'"
            v-model="salePrices"
            placeholder="价格（逐台逗号分隔，可选）"
          />
          <select v-if="currentTask.key === 'repair' && operationPhase === 'complete'" v-model="repairResult"><option value="REPAIRED">已修复</option><option value="NO_REPAIR">无需维修</option><option value="UNREPAIRABLE">不可维修</option></select>
          <select v-if="currentTask.key === 'repair' && operationPhase === 'review'" v-model="disposition"><option value="AVAILABLE_AGAIN">恢复可售</option><option value="FROZEN">冻结待核查</option><option value="SCRAPPED">报损</option></select>
          <select v-if="currentTask.key === 'stocktake' && operationPhase === 'adjust'" v-model="adjustmentDecision"><option value="IGNORE">忽略差异</option><option value="CONFIRM_MISSING">确认缺失</option><option value="ACCEPT_EXTRA">接收多出</option></select>
          <select v-if="currentTask.key === 'stocktake' && operationPhase === 'adjust' && adjustmentDecision === 'ACCEPT_EXTRA'" v-model="adjustmentTargetStatus"><option value="加纳管理处库存">加纳管理处库存</option><option value="门店库存">门店库存</option><option value="可再次销售">可再次销售</option></select>
        </div>
        <div v-if="phaseRequiresScan()" class="scanbar">
          <input
            ref="scannerInput"
            v-model="scanInput"
            autofocus
            :placeholder="
              scanMode() === 'imei'
                ? '扫码枪扫描 IMEI，自动回车'
                : '扫码枪扫描手机/托盘/箱子编号，自动回车'
            "
            @input="onScanInput"
            @keyup.enter="addScan"
          /><button class="secondary" @click="addScan">加入</button>
        </div>
        <div v-if="phaseRequiresScan()" class="count">
          已读取 {{ scanned.length }} 项
          <button class="link" @click="scanned = []">清空</button>
        </div>
        <table v-if="phaseRequiresScan()">
          <thead>
            <tr>
              <th>#</th>
              <th>编码</th>
              <th>状态</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(value, index) in scanned" :key="value">
              <td>{{ index + 1 }}</td>
              <td>{{ value }}</td>
              <td>待提交</td>
              <td>
                <button class="link" @click="scanned.splice(index, 1)">
                  移除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <button
          class="primary"
          :disabled="(phaseRequiresScan() && !scanned.length) || loading"
          @click="submit"
        >
          提交{{ currentTask.label }}<template v-if="phaseRequiresScan()">（{{ scanned.length }}）</template>
        </button>
        <div v-if="currentTask.key === 'query' && phoneDetail" class="detail-card"><strong>{{ phoneDetail.imei }}</strong><span>{{ phoneDetail.brand || '' }} {{ phoneDetail.model || '' }}</span><span>状态：{{ phoneDetail.status || '未知' }}</span><span>组织：{{ phoneDetail.organization_id || '无' }} · 地点：{{ phoneDetail.location_id || '无' }}</span></div>
      </section>
      <section
        v-else-if="active === 'inventory' || active === 'documents'"
        class="panel"
      >
        <h2>{{ active === "inventory" ? "库存查询" : "业务单据" }}</h2>
        <button class="secondary" @click="refresh">刷新</button>
        <table>
          <tbody>
            <tr
              v-for="item in active === 'inventory' ? inventory : documents"
              :key="String(item.imei || item.no)"
            >
              <td>{{ item.imei || item.no }}</td>
              <td>
                {{ item.brand || item.type || "" }} {{ item.model || "" }}
              </td>
              <td>{{ item.status }}</td>
              <td>{{ item.location_id || item.total_count || "" }}</td>
            </tr>
          </tbody>
        </table>
      </section>
      <section v-else-if="active === 'drafts'" class="panel">
        <h2>离线草稿</h2>
        <button class="secondary" @click="refresh">刷新</button><button class="secondary" :disabled="!online" @click="retryAllDrafts">联网重试全部</button>
        <table>
          <tbody>
            <tr v-for="draft in drafts" :key="draft.id">
              <td>{{ draft.action }}</td>
              <td>{{ draft.values.length }} 项</td>
              <td>
                {{ draft.status
                }}<small v-if="draft.error"> · {{ draft.error }}</small>
              </td>
              <td>
                <button
                  v-if="draft.status !== 'synced'"
                  class="link"
                  @click="retryDraft(draft)"
                >
                  重试
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
      <section v-else-if="active === 'profile'" class="panel"><h2>个人资料与安全</h2><div class="form-grid"><input v-model="profileName" placeholder="显示名称"/><input v-model="profileUsername" placeholder="英文用户名"/><input v-model="currentPassword" type="password" placeholder="当前密码（修改密码时填写）"/><input v-model="nextPassword" type="password" placeholder="新密码（至少 8 位）"/><button class="primary" @click="saveProfile">保存修改</button></div></section>
      <section v-else class="panel">
        <div class="admin-tabs">
          <button
            v-for="tab in [
              'users',
              'organizations',
              'locations',
              'roles',
              'audits',
            ] as const"
            :key="tab"
            :class="{ active: adminTab === tab }"
            v-if="(tab === 'users' || tab === 'organizations' || tab === 'locations') ? has('user:manage') : tab === 'roles' ? has('role:manage') : has('audit:view')"
            @click="adminTab = tab"
          >
            {{
              tab === "users"
                ? "用户"
                : tab === "organizations"
                  ? "组织"
                  : tab === "locations"
                    ? "地点"
                    : tab === "roles"
                      ? "角色"
                      : "审计"
            }}
          </button>
        </div>
        <div v-if="adminTab === 'users'" class="form-grid">
          <input
            v-model="newIdentifier"
            placeholder="手机号或英文用户名"
          /><input v-model="newName" placeholder="姓名" /><input
            v-model="newPassword"
            type="password"
            placeholder="初始密码（至少 8 位）"
          /><button class="primary" @click="createAdminUser">创建用户</button>
          <select v-model="newRoleIds" multiple><option v-for="role in adminData.roles" :key="role.id" :value="Number(role.id)">{{ role.name }}（{{ role.code }}）</option></select>
          <textarea v-model="newScopes" placeholder='数据范围 JSON，例如 [{"permission_code":"phone:view","scope_kind":"location","scope_value":"20"}]'></textarea>
        </div>
        <div v-if="adminTab === 'organizations'" class="form-grid"><input v-model="orgCode" placeholder="组织代码"/><input v-model="orgName" placeholder="组织名称"/><input v-model="orgCountry" placeholder="国家代码"/><button class="primary" @click="createOrganization">创建组织</button></div>
        <div v-if="adminTab === 'locations'" class="form-grid"><input v-model="locOrganizationId" placeholder="所属组织 ID"/><input v-model="locCode" placeholder="地点代码"/><input v-model="locName" placeholder="地点名称"/><select v-model="locType"><option value="store">门店</option><option value="warehouse">仓库</option><option value="repair">维修区</option><option value="receiving">接收区</option></select><button class="primary" @click="createLocation">创建地点</button></div>
        <div v-if="adminTab === 'roles'" class="form-grid"><input v-model="roleCode" placeholder="角色代码"/><input v-model="roleName" placeholder="角色名称"/><input v-model="rolePermissionsText" placeholder="权限代码（逗号分隔）"/><button class="primary" @click="createRole">创建角色</button></div>
        <table v-if="adminTab === 'users'">
          <tbody>
            <tr v-for="item in adminData.users" :key="item.id">
              <td>{{ item.username || item.phone }}</td>
              <td>{{ item.display_name }}</td>
              <td>{{ item.is_active ? "启用" : "停用" }}</td>
              <td><button class="link" @click="toggleUser(item)">{{ item.is_active ? "停用" : "启用" }}</button></td>
              <td><button class="link" @click="editUser(item)">编辑权限</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="adminTab === 'users' && editingUserId !== null" class="edit-card"><h3>编辑用户 #{{ editingUserId }}</h3><select v-model="editingRoleIds" multiple><option v-for="role in adminData.roles" :key="role.id" :value="Number(role.id)">{{ role.name }}（{{ role.code }}）</option></select><textarea v-model="editingScopes" placeholder="数据范围 JSON"></textarea><div><button class="primary" @click="saveUserPermissions">保存权限</button><button class="secondary" @click="editingUserId=null">取消</button></div></div>
        <table v-else-if="adminTab === 'organizations'">
          <tbody>
            <tr v-for="item in adminData.organizations" :key="item.id">
              <td>{{ item.code }}</td>
              <td>{{ item.name }}</td>
              <td>{{ item.is_active ? "启用" : "停用" }}</td>
              <td><button class="link" @click="toggleOrganization(item)">{{ item.is_active ? "停用" : "启用" }}</button></td>
            </tr>
          </tbody>
        </table>
        <table v-else-if="adminTab === 'locations'">
          <tbody>
            <tr v-for="item in adminData.locations" :key="item.id">
              <td>{{ item.code }}</td>
              <td>{{ item.name }}</td>
              <td>{{ item.location_type }}</td>
              <td><button class="link" @click="toggleLocation(item)">{{ item.is_active ? "停用" : "启用" }}</button></td>
            </tr>
          </tbody>
        </table>
        <table v-else-if="adminTab === 'roles'">
          <tbody>
            <tr v-for="item in adminData.roles" :key="item.id">
              <td>{{ item.code }}</td>
              <td>{{ item.name }}</td>
            </tr>
          </tbody>
        </table>
        <table v-else>
          <tbody>
            <tr v-for="item in adminData.audits" :key="item.id">
              <td>{{ item.action }}</td>
              <td>{{ item.resource_type }} #{{ item.resource_id }}</td>
              <td>{{ item.created_at }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </section>
  </main>
</template>
