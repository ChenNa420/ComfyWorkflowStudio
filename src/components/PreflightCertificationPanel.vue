<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, BadgeCheck, Braces, CircleX, Filter, Play, RefreshCcw, Search, ShieldCheck, TriangleAlert, X } from 'lucide-vue-next'

type Issue = {
  code: string
  message: string
  severity: string
}

type PreflightItem = {
  workflowId: string
  name: string
  category: string
  capabilities: string[]
  dependencyStatus: string
  status: 'CERTIFIED' | 'NEEDS_REVIEW' | 'BLOCKED_DEPENDENCIES' | 'COMFY_OFFLINE'
  sourceFormat?: string | null
  sourcePath?: string | null
  promptNodes: number
  detectedOutputNodes: string[]
  errors: Issue[]
  warnings: Issue[]
  writeMode: boolean
  submitsPrompt: boolean
}

type PreflightReport = {
  connected: boolean
  comfyUiUrl?: string
  error?: string | null
  summary: {
    workflows: number
    certified: number
    needsReview: number
    blockedDependencies: number
    offline: number
    errorCodes: Array<{ key: string; count: number }>
    warningCodes: Array<{ key: string; count: number }>
  }
  items: PreflightItem[]
  rules: string[]
}

const report = ref<PreflightReport | null>(null)
const loading = ref(false)
const error = ref('')
const q = ref('')
const status = ref('')
const capability = ref('')
const selected = ref<PreflightItem | null>(null)
const pilotOpen = ref(false)
const pilotBusy = ref(false)
const pilotInputs = ref('{}')
const pilotParameters = ref('{}')
const pilotError = ref('')
const pilotResult = ref<Record<string, any> | null>(null)

const capabilities = computed(() => {
  const counts = new Map<string, number>()
  for (const item of report.value?.items || []) {
    for (const cap of item.capabilities || []) counts.set(cap, (counts.get(cap) || 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
})

const items = computed(() => {
  const key = q.value.trim().toLowerCase()
  return (report.value?.items || []).filter(item => {
    if (status.value && item.status !== status.value) return false
    if (capability.value && !item.capabilities.includes(capability.value)) return false
    if (key && !`${item.name} ${item.workflowId} ${item.category} ${item.capabilities.join(' ')} ${item.errors.map(x => x.code).join(' ')}`.toLowerCase().includes(key)) return false
    return true
  })
})

async function load(forceRefresh = false) {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ limit: '1000' })
    if (forceRefresh) params.set('forceRefresh', 'true')
    const response = await fetch(`/api/readiness/preflight?${params}`)
    if (!response.ok) throw new Error(`Preflight HTTP ${response.status}`)
    report.value = await response.json()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法加载预检认证'
  } finally {
    loading.value = false
  }
}

function statusLabel(value: string) {
  return ({
    CERTIFIED: '静态预检通过',
    NEEDS_REVIEW: '需要人工复核',
    BLOCKED_DEPENDENCIES: '依赖阻塞',
    COMFY_OFFLINE: 'ComfyUI 离线',
  } as Record<string, string>)[value] || value
}

function openPilot() { pilotError.value = ''; pilotResult.value = null; pilotOpen.value = true }
async function pollPilot(taskId: string) {
  const response = await fetch(`/api/workflows/pilot-runs/${taskId}`)
  if (!response.ok) return
  pilotResult.value = await response.json()
  if (!['SUCCEEDED', 'FAILED', 'UNKNOWN', 'NEEDS_REVIEW'].includes(String(pilotResult.value?.status))) window.setTimeout(() => void pollPilot(taskId), 1500)
}
async function runPilot() {
  if (!selected.value || pilotBusy.value) return
  pilotBusy.value = true; pilotError.value = ''
  try {
    const response = await fetch(`/api/workflows/${selected.value.workflowId}/pilot-run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ workflowId: selected.value.workflowId, clientApp: 'ComfyWorkflowStudio-Pilot', inputs: JSON.parse(pilotInputs.value), parameters: JSON.parse(pilotParameters.value) }) })
    const data = await response.json()
    if (!response.ok) throw new Error(data?.detail?.message || `Pilot HTTP ${response.status}`)
    pilotResult.value = data; await pollPilot(data.taskId)
  } catch (value) { pilotError.value = value instanceof Error ? value.message : 'Pilot 提交失败' }
  finally { pilotBusy.value = false }
}

onMounted(() => void load(true))
</script>

<template>
  <section class="preflight-shell">
    <div class="preflight-head">
      <div>
        <span class="eyebrow">PHASE 1G-4 · CERTIFIED RUNTIME PILOT</span>
        <h2><ShieldCheck :size="23"/>Runtime 预检认证</h2>
        <p>在真正生成之前，使用当前 ComfyUI object_info 和 Runtime Converter 对 Workflow 做只读结构预检：依赖、UI→API 转换、必填输入映射、参数映射、输出节点和 UNKNOWN 安全规则。不会提交 Prompt，也不会消耗 GPU。</p>
      </div>
      <button class="refresh" :disabled="loading" @click="load(true)"><RefreshCcw :size="15" :class="{ spin: loading }"/>重新预检</button>
    </div>

    <p v-if="error" class="alert"><AlertTriangle :size="15"/>{{ error }}</p>
    <div v-if="report && !report.connected" class="offline"><AlertTriangle :size="18"/><div><b>ComfyUI 当前离线</b><span>离线时不发放 CERTIFIED，避免把未知环境当成已通过。</span></div></div>

    <div v-if="report" class="stats">
      <article class="good"><BadgeCheck :size="18"/><div><b>{{ report.summary.certified }}</b><span>静态预检通过</span></div></article>
      <article class="review"><TriangleAlert :size="18"/><div><b>{{ report.summary.needsReview }}</b><span>需要人工复核</span></div></article>
      <article class="blocked"><CircleX :size="18"/><div><b>{{ report.summary.blockedDependencies }}</b><span>依赖阻塞</span></div></article>
      <article><Braces :size="18"/><div><b>{{ report.summary.workflows }}</b><span>本轮 Workflow</span></div></article>
    </div>

    <section class="definition">
      <BadgeCheck :size="16"/>
      <p><b>CERTIFIED 不是“已经真实生成成功”。</b> 它只表示当前依赖已满足、Runtime Prompt 可以构建、Manifest 的关键映射和输出结构可确认，并且不会违反 UNKNOWN/原始 Workflow 保护规则。下一阶段才做少量真实运行认证。</p>
    </section>

    <div class="toolbar">
      <label><Search :size="14"/><input v-model="q" placeholder="搜索工作流、ID、分类或错误码..."/></label>
      <label><Filter :size="14"/><select v-model="status"><option value="">全部状态</option><option value="CERTIFIED">静态预检通过</option><option value="NEEDS_REVIEW">需要人工复核</option><option value="BLOCKED_DEPENDENCIES">依赖阻塞</option><option value="COMFY_OFFLINE">ComfyUI 离线</option></select></label>
      <select v-model="capability"><option value="">全部 Capability</option><option v-for="entry in capabilities" :key="entry[0]" :value="entry[0]">{{ entry[0] }} · {{ entry[1] }}</option></select>
    </div>

    <div v-if="report" class="content-grid">
      <section class="list-panel">
        <div class="section-title"><div><span>PREFLIGHT RESULTS</span><h3>认证结果</h3></div><small>{{ items.length }} 项</small></div>
        <div class="workflow-list">
          <button v-for="item in items" :key="item.workflowId" :class="['workflow-row', { active: selected?.workflowId === item.workflowId }]" @click="selected=item">
            <div class="row-main"><strong>{{ item.name }}</strong><span>{{ item.category }} · {{ item.capabilities.join(', ') }}</span><code>{{ item.workflowId }}</code></div>
            <div class="row-side"><b :class="['status', item.status.toLowerCase()]">{{ statusLabel(item.status) }}</b><span>{{ item.promptNodes }} Runtime Nodes</span><span v-if="item.errors.length">错误 {{ item.errors.length }}</span><span v-else-if="item.warnings.length">提醒 {{ item.warnings.length }}</span></div>
          </button>
          <p v-if="!items.length" class="empty">当前筛选下没有结果。</p>
        </div>
      </section>

      <section class="detail-panel">
        <template v-if="selected">
          <div class="detail-head"><div><span>WORKFLOW PREFLIGHT</span><h3>{{ selected.name }}</h3></div><b :class="['status', selected.status.toLowerCase()]">{{ statusLabel(selected.status) }}</b></div>
          <div class="meta-grid"><span><b>依赖</b>{{ selected.dependencyStatus }}</span><span><b>来源</b>{{ selected.sourceFormat || '-' }}</span><span><b>Prompt Nodes</b>{{ selected.promptNodes }}</span><span><b>Output Nodes</b>{{ selected.detectedOutputNodes.length }}</span></div>

          <div v-if="selected.errors.length" class="issue-block errors"><h4>必须处理</h4><article v-for="issue in selected.errors" :key="`${issue.code}-${issue.message}`"><code>{{ issue.code }}</code><p>{{ issue.message }}</p></article></div>
          <div v-if="selected.warnings.length" class="issue-block warnings"><h4>提醒</h4><article v-for="issue in selected.warnings" :key="`${issue.code}-${issue.message}`"><code>{{ issue.code }}</code><p>{{ issue.message }}</p></article></div>
          <div v-if="!selected.errors.length && !selected.warnings.length" class="clean"><BadgeCheck :size="18"/><div><b>结构预检无异常</b><span>可以进入后续真实运行认证候选集。</span></div></div>

          <section class="read-only"><b>只读保证</b><span>writeMode = {{ selected.writeMode }}</span><span>submitsPrompt = {{ selected.submitsPrompt }}</span><span>不会创建 Generation Task</span><span>不会上传素材</span></section>
          <button v-if="selected.status === 'CERTIFIED'" class="pilot-button" @click="openPilot"><Play :size="14"/>试运行</button>
          <p v-else class="pilot-disabled">{{ selected.status === 'COMFY_OFFLINE' ? 'ComfyUI 当前离线，无法执行 Runtime Pilot。' : '当前 Workflow 尚未通过 Runtime Preflight Certification。' }}</p>
        </template>
        <div v-else class="empty detail-empty"><ShieldCheck :size="34"/><b>选择一个 Workflow 查看详情</b><span>重点查看 NEEDS_REVIEW 的错误码与失效映射。</span></div>
      </section>
    </div>

    <section v-if="report?.summary.errorCodes?.length" class="codes">
      <div class="section-title"><div><span>TOP PREFLIGHT ISSUES</span><h3>主要阻塞原因</h3></div></div>
      <div class="code-chips"><span v-for="item in report.summary.errorCodes" :key="item.key"><code>{{ item.key }}</code><b>{{ item.count }}</b></span></div>
    </section>
    <div v-if="pilotOpen && selected" class="modal-backdrop"><section class="pilot-modal">
      <button class="modal-close" @click="pilotOpen=false"><X :size="16"/></button><span class="eyebrow">REAL COMFYUI SUBMISSION</span><h3>{{ selected.name }}</h3>
      <div class="meta-grid"><span><b>Workflow ID</b>{{ selected.workflowId }}</span><span><b>Capability</b>{{ selected.capabilities.join(', ') }}</span><span><b>Preflight</b>{{ selected.status }}</span><span><b>Dependency</b>{{ selected.dependencyStatus }}</span><span><b>ComfyUI</b>{{ report?.connected ? 'Connected' : 'Offline' }}</span><span><b>Source</b>{{ selected.sourceFormat }}</span><span><b>Prompt Nodes</b>{{ selected.promptNodes }}</span><span><b>Output Nodes</b>{{ selected.detectedOutputNodes.join(', ') }}</span></div>
      <div class="safety"><b>Pilot 会真实向 ComfyUI 提交任务。</b><span>Runtime Clone：Enabled · Original Protection：Enabled · Strict Serial：Enabled</span></div>
      <label class="json-field">Inputs JSON<textarea v-model="pilotInputs" rows="4"/></label><label class="json-field">Parameters JSON<textarea v-model="pilotParameters" rows="4"/></label>
      <p v-if="pilotError" class="alert">{{ pilotError }}</p><button class="pilot-button" :disabled="pilotBusy || !!pilotResult?.taskId" @click="runPilot"><Play :size="14"/>{{ pilotBusy ? '提交中…' : '开始试运行' }}</button>
      <div v-if="pilotResult" class="pilot-result"><b>Generation Task</b><code>{{ pilotResult.id || pilotResult.taskId }}</code><span>Status: {{ pilotResult.status }}</span><span>Prompt ID: {{ pilotResult.prompt_id || '-' }}</span><span>Started: {{ pilotResult.started_at || '-' }}</span><span>Finished: {{ pilotResult.finished_at || '-' }}</span><span>Outputs: {{ pilotResult.outputs?.length || 0 }}</span><span v-if="pilotResult.error">Error: {{ pilotResult.error }}</span></div>
    </section></div>
  </section>
</template>

<style scoped>
.pilot-button{margin-top:10px;border:0;border-radius:8px;background:#5b56d8;color:#fff;padding:9px 13px;display:flex;gap:6px;align-items:center;justify-content:center;cursor:pointer}.pilot-button:disabled{opacity:.55;cursor:not-allowed}.pilot-disabled{font-size:8px;color:#9b5961;background:#fff3f3;padding:9px;border-radius:8px}.modal-backdrop{position:fixed;inset:0;background:rgba(24,31,48,.48);display:grid;place-items:center;z-index:50;padding:16px}.pilot-modal{position:relative;background:#fff;border-radius:14px;padding:18px;width:min(680px,100%);max-height:92vh;overflow:auto;display:grid;gap:10px}.pilot-modal h3{margin:0;color:#34496d}.modal-close{position:absolute;right:10px;top:10px;border:0;background:#f0f2f7;border-radius:7px;padding:6px}.safety{display:flex;flex-direction:column;background:#fff6df;color:#85601b;padding:10px;border-radius:8px;font-size:9px}.json-field{display:grid;gap:4px;color:#65738a;font-size:9px}.json-field textarea{width:100%;box-sizing:border-box;border:1px solid #dfe4ef;border-radius:8px;padding:8px;font:10px monospace}.pilot-result{display:grid;gap:4px;background:#f5f7fc;padding:10px;border-radius:8px;font-size:9px;overflow-wrap:anywhere}
.preflight-shell{display:grid;gap:15px}.preflight-head{display:flex;justify-content:space-between;gap:18px}.preflight-head h2{margin:5px 0;color:#263a61;display:flex;align-items:center;gap:8px}.preflight-head p{margin:0;color:#76849d;font-size:11px;line-height:1.6;max-width:900px}.eyebrow{font-size:9px;letter-spacing:.12em;color:#5269da;font-weight:800}.refresh{border:0;background:#edf1ff;color:#5065d0;border-radius:8px;padding:9px 12px;height:max-content;display:flex;gap:6px;align-items:center}.alert,.offline{display:flex;align-items:center;gap:8px;border-radius:9px;padding:10px;font-size:10px}.alert{background:#fff1f1;color:#a74953}.offline{background:#f4f5f8;color:#6f7b91}.offline div{display:flex;flex-direction:column}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.stats article{padding:12px;border:1px solid #e4e8f1;border-radius:10px;background:#fff;display:flex;gap:9px;align-items:center;color:#627089}.stats .good{color:#298161}.stats .review{color:#b7792d}.stats .blocked{color:#b75259}.stats div{display:flex;flex-direction:column}.stats b{font-size:18px;color:#2f4267}.stats span{font-size:8px;color:#8996aa}.definition{display:flex;gap:8px;align-items:flex-start;background:#f6f8ff;border:1px solid #dfe5fb;border-radius:10px;padding:10px;color:#5a6c96}.definition p{font-size:9px;line-height:1.6;margin:0}.toolbar{display:grid;grid-template-columns:1fr 210px 230px;gap:8px}.toolbar label{display:flex;align-items:center;gap:6px;border:1px solid #dfe4ef;background:#fff;border-radius:8px;padding:0 9px}.toolbar input,.toolbar select,.toolbar>select{border:0;outline:0;background:#fff;padding:9px;width:100%;min-width:0;font-size:10px;color:#53637e}.content-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:10px}.list-panel,.detail-panel,.codes{border:1px solid #e4e8f1;background:#fff;border-radius:11px;padding:12px;min-width:0}.section-title,.detail-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}.section-title span,.detail-head span{font-size:8px;letter-spacing:.08em;color:#7e8ba4}.section-title h3,.detail-head h3{margin:2px 0;color:#34496d;font-size:13px}.section-title small{color:#8f9aad}.workflow-list{display:grid;gap:6px;max-height:61vh;overflow:auto}.workflow-row{width:100%;display:grid;grid-template-columns:1fr auto;gap:8px;text-align:left;padding:9px;border:1px solid #e7eaf2;border-radius:8px;background:#fff;cursor:pointer;color:inherit}.workflow-row:hover,.workflow-row.active{border-color:#bfc9ed;background:#fafbff}.row-main{display:flex;flex-direction:column;min-width:0}.row-main strong{font-size:9px;color:#3c5071}.row-main span,.row-main code{font-size:7px;color:#8692a5;overflow-wrap:anywhere}.row-side{display:flex;flex-direction:column;align-items:flex-end;gap:3px}.row-side>span{font-size:7px;color:#8b97aa}.status{font-size:7px;border-radius:999px;padding:4px 6px;white-space:nowrap}.status.certified{background:#e6f7ef;color:#18785a}.status.needs_review{background:#fff3df;color:#a76c1c}.status.blocked_dependencies{background:#fff0f0;color:#ae4852}.status.comfy_offline{background:#edf0f5;color:#707d92}.meta-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}.meta-grid span{display:flex;flex-direction:column;padding:8px;background:#f7f8fb;border-radius:7px;font-size:8px;color:#7b879a;overflow-wrap:anywhere}.meta-grid b{font-size:7px;color:#4b5d7c;margin-bottom:2px}.issue-block{margin-top:9px;border-radius:8px;padding:9px}.issue-block h4{font-size:9px;margin:0 0 6px}.issue-block article{padding:6px 0;border-top:1px solid rgba(0,0,0,.05)}.issue-block code{font-size:7px}.issue-block p{font-size:8px;line-height:1.5;margin:3px 0 0}.errors{background:#fff4f4;color:#8f434a}.warnings{background:#fff9ee;color:#92651f}.clean{display:flex;gap:8px;align-items:center;margin-top:9px;background:#eef9f4;color:#34735f;border-radius:8px;padding:10px}.clean div{display:flex;flex-direction:column}.clean b{font-size:9px}.clean span{font-size:8px}.read-only{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.read-only b,.read-only span{font-size:7px;padding:4px 6px;border-radius:999px;background:#f3f5f8;color:#68758d}.read-only b{background:#ece9ff;color:#5b4bd0}.detail-empty{min-height:300px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px}.detail-empty b{color:#5b6b85}.detail-empty span{font-size:8px}.codes{padding-bottom:10px}.code-chips{display:flex;flex-wrap:wrap;gap:6px}.code-chips span{display:flex;gap:6px;align-items:center;background:#f5f6fa;border-radius:999px;padding:5px 7px}.code-chips code{font-size:7px;color:#596a87}.code-chips b{font-size:8px;color:#6b57de}.empty{text-align:center;color:#98a2b3;font-size:9px;padding:28px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1050px){.content-grid{grid-template-columns:1fr}.toolbar{grid-template-columns:1fr 1fr}.toolbar label:first-child{grid-column:1/-1}}@media(max-width:700px){.preflight-head{flex-direction:column}.stats{grid-template-columns:1fr 1fr}.toolbar{grid-template-columns:1fr}.toolbar label:first-child{grid-column:auto}.meta-grid{grid-template-columns:1fr}}@media(max-width:480px){.stats{grid-template-columns:1fr}.workflow-row{grid-template-columns:1fr}.row-side{align-items:flex-start}.preflight-head h2{overflow-wrap:anywhere}}
</style>
