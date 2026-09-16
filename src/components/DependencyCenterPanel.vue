<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, BadgeCheck, Boxes, FileCheck2, Layers3, RefreshCcw, Search, ServerOff, Wrench, X } from 'lucide-vue-next'

type Summary = {
  connected: boolean
  comfyUiUrl: string
  error: string | null
  summary: {
    workflows: number
    ready: number
    missingDependencies: number
    offline: number
    declaredModels: number
    availableModelOptions: number
    missingModels: number
    requiredNodeTypes: number
    missingNodeTypes: number
  }
}

type WorkflowDependency = {
  workflowId: string
  name: string
  category: string
  capabilities: string[]
  status: string
  models: Array<{ name: string; required: boolean; status: string; matched?: string | null; match?: string | null }>
  nodeTypes: Array<{ nodeType: string; status: string }>
  customNodePackages: Array<{ name: string; required: boolean; status: string; verification: string }>
  counts: { models: number; missingModels: number; nodeTypes: number; missingNodeTypes: number; customNodePackages: number }
}

type ModelItem = { name: string; status: string; matched?: string | null; workflows: Array<{ id: string; name: string }> }
type NodeItem = { nodeType: string; status: string; workflows: Array<{ id: string; name: string }> }
type ReviewItem = {
  workflowId: string
  name: string
  category: string
  completeness: { score: number; grade: string; missing: string[] }
  proposalCount: number
  proposals: Array<{ type: string; field?: string; key?: string; confidence?: number; changes?: Record<string, unknown>; value?: unknown; source: string }>
  rules: string[]
}

const tab = ref<'workflows' | 'models' | 'nodes' | 'review'>('workflows')
const summary = ref<Summary | null>(null)
const workflows = ref<WorkflowDependency[]>([])
const models = ref<ModelItem[]>([])
const nodes = ref<NodeItem[]>([])
const reviews = ref<ReviewItem[]>([])
const selected = ref<WorkflowDependency | null>(null)
const selectedReview = ref<ReviewItem | null>(null)
const q = ref('')
const status = ref('')
const loading = ref(false)
const error = ref('')
const message = ref('')
const applying = ref('')

const filteredWorkflows = computed(() => {
  const key = q.value.trim().toLowerCase()
  return workflows.value.filter(item => (!status.value || item.status === status.value) && (!key || `${item.name} ${item.category} ${item.capabilities.join(' ')}`.toLowerCase().includes(key)))
})
const filteredModels = computed(() => {
  const key = q.value.trim().toLowerCase()
  return models.value.filter(item => (!status.value || item.status === status.value) && (!key || item.name.toLowerCase().includes(key)))
})
const filteredNodes = computed(() => {
  const key = q.value.trim().toLowerCase()
  return nodes.value.filter(item => (!status.value || item.status === status.value) && (!key || item.nodeType.toLowerCase().includes(key)))
})
const filteredReviews = computed(() => {
  const key = q.value.trim().toLowerCase()
  return reviews.value.filter(item => (!key || `${item.name} ${item.category} ${item.completeness.missing.join(' ')}`.toLowerCase().includes(key)))
})

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [summaryResponse, workflowResponse, modelResponse, nodeResponse, reviewResponse] = await Promise.all([
      fetch('/api/dependencies/summary'),
      fetch('/api/dependencies/workflows?limit=1000'),
      fetch('/api/dependencies/models?limit=5000'),
      fetch('/api/dependencies/nodes?limit=5000'),
      fetch('/api/manifest-review?limit=1000'),
    ])
    if (!summaryResponse.ok) throw new Error(`Dependency summary HTTP ${summaryResponse.status}`)
    summary.value = await summaryResponse.json()
    const workflowPayload = await workflowResponse.json()
    const modelPayload = await modelResponse.json()
    const nodePayload = await nodeResponse.json()
    workflows.value = workflowPayload.items || []
    models.value = modelPayload.items || []
    nodes.value = nodePayload.items || []
    reviews.value = reviewResponse.ok ? await reviewResponse.json() : []
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法加载依赖中心'
  } finally {
    loading.value = false
  }
}

function statusLabel(value: string) {
  return ({ READY: '依赖就绪', MISSING_DEPENDENCIES: '缺少依赖', COMFY_OFFLINE: 'ComfyUI 离线', PRESENT: '已存在', MISSING: '缺失', UNKNOWN: '未知', DECLARED: '已声明' } as Record<string, string>)[value] || value
}

function switchTab(value: typeof tab.value) {
  tab.value = value
  q.value = ''
  status.value = ''
}

async function applySafeReview(item: ReviewItem) {
  if (!item.proposalCount) return
  const ok = confirm(`应用“${item.name}”的 ${item.proposalCount} 项安全补全？\n\n只补空字段和高置信度分析结果；不会修改 original.json，也不会覆盖已有人工字段。`)
  if (!ok) return
  applying.value = item.workflowId
  error.value = ''
  message.value = ''
  try {
    const response = await fetch(`/api/manifest-review/${encodeURIComponent(item.workflowId)}/apply-safe`, { method: 'POST' })
    if (!response.ok) throw new Error(`Apply HTTP ${response.status}`)
    const result = await response.json()
    message.value = `已安全补全 ${result.applied} 项 Manifest 字段。原始 Workflow JSON 未修改。`
    selectedReview.value = null
    await loadAll()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '安全补全失败'
  } finally {
    applying.value = ''
  }
}

function missingLabel(value: string) {
  return ({ description: '说明', recommendedFor: '适用场景', notRecommendedFor: '不适用场景', guide: '使用步骤', promptTips: 'Prompt 技巧', inputs: '输入定义', 'input-semantics': '输入语义', 'input-mappings': '输入映射', 'parameter-mappings': '参数映射', 'output-mappings': '输出映射', outputs: '输出定义', dependencies: '依赖', 'runtime-safety': '运行安全' } as Record<string, string>)[value] || value
}

onMounted(() => void loadAll())
</script>

<template>
  <section class="dependency-center">
    <div class="dep-head">
      <div><span class="eyebrow">PHASE 1F-2 · REAL DEPENDENCY INVENTORY</span><h2><Layers3 :size="23"/>模型与节点依赖中心</h2><p>通过当前 ComfyUI `/object_info` 实时核对节点类型和模型枚举；不扫描、不移动、不安装任何本地文件。</p></div>
      <button class="refresh" :disabled="loading" @click="loadAll"><RefreshCcw :size="15" :class="{spin:loading}"/>刷新</button>
    </div>

    <p v-if="error" class="alert error"><AlertTriangle :size="15"/>{{ error }}</p>
    <p v-if="message" class="alert success"><BadgeCheck :size="15"/>{{ message }}</p>
    <div v-if="summary&&!summary.connected" class="offline"><ServerOff :size="20"/><div><b>ComfyUI 当前离线</b><span>{{ summary.error || summary.comfyUiUrl }}</span></div></div>

    <div v-if="summary" class="dep-stats">
      <article><b>{{ summary.summary.workflows }}</b><span>工作流</span></article>
      <article><b>{{ summary.summary.ready }}</b><span>依赖就绪</span></article>
      <article class="warn"><b>{{ summary.summary.missingDependencies }}</b><span>缺少依赖</span></article>
      <article><b>{{ summary.summary.declaredModels }}</b><span>声明模型</span></article>
      <article class="warn"><b>{{ summary.summary.missingModels }}</b><span>缺少模型</span></article>
      <article class="warn"><b>{{ summary.summary.missingNodeTypes }}</b><span>缺少节点类型</span></article>
    </div>

    <div class="dep-tabs">
      <button :class="{active:tab==='workflows'}" @click="switchTab('workflows')"><Boxes :size="14"/>按工作流</button>
      <button :class="{active:tab==='models'}" @click="switchTab('models')">模型</button>
      <button :class="{active:tab==='nodes'}" @click="switchTab('nodes')">节点类型</button>
      <button :class="{active:tab==='review'}" @click="switchTab('review')"><FileCheck2 :size="14"/>Manifest 审核</button>
    </div>

    <div class="dep-toolbar"><label><Search :size="14"/><input v-model="q" :placeholder="tab==='review'?'搜索待审核工作流...':'搜索依赖、工作流、节点...'"/></label><select v-if="tab!=='review'" v-model="status"><option value="">全部状态</option><option v-if="tab==='workflows'" value="READY">依赖就绪</option><option v-if="tab==='workflows'" value="MISSING_DEPENDENCIES">缺少依赖</option><option v-if="tab==='workflows'" value="COMFY_OFFLINE">ComfyUI 离线</option><option v-if="tab!=='workflows'" value="PRESENT">已存在</option><option v-if="tab!=='workflows'" value="MISSING">缺失</option><option v-if="tab!=='workflows'" value="UNKNOWN">未知</option></select></div>

    <div v-if="tab==='workflows'" class="dep-list">
      <article v-for="item in filteredWorkflows" :key="item.workflowId" class="dep-row" @click="selected=item"><div><strong>{{ item.name }}</strong><span>{{ item.category }} · {{ item.capabilities.join(', ') }}</span></div><div class="counts"><span>模型 {{ item.counts.models }}</span><span :class="{bad:item.counts.missingModels}">缺 {{ item.counts.missingModels }}</span><span>节点 {{ item.counts.nodeTypes }}</span><span :class="{bad:item.counts.missingNodeTypes}">缺 {{ item.counts.missingNodeTypes }}</span></div><b :class="['state',item.status.toLowerCase()]">{{ statusLabel(item.status) }}</b></article>
      <p v-if="!filteredWorkflows.length" class="empty">没有匹配工作流。</p>
    </div>

    <div v-else-if="tab==='models'" class="dep-list compact">
      <article v-for="item in filteredModels" :key="item.name" class="dep-row"><div><strong>{{ item.name }}</strong><span v-if="item.matched">ComfyUI: {{ item.matched }}</span><span>{{ item.workflows.length }} 个工作流依赖</span></div><b :class="['state',item.status.toLowerCase()]">{{ statusLabel(item.status) }}</b></article>
      <p v-if="!filteredModels.length" class="empty">没有匹配模型。</p>
    </div>

    <div v-else-if="tab==='nodes'" class="dep-list compact">
      <article v-for="item in filteredNodes" :key="item.nodeType" class="dep-row"><div><strong>{{ item.nodeType }}</strong><span>{{ item.workflows.length }} 个工作流使用</span></div><b :class="['state',item.status.toLowerCase()]">{{ statusLabel(item.status) }}</b></article>
      <p v-if="!filteredNodes.length" class="empty">没有匹配节点。</p>
    </div>

    <div v-else class="review-grid">
      <article v-for="item in filteredReviews" :key="item.workflowId" class="review-card"><div class="review-top"><div><span>{{ item.category }}</span><strong>{{ item.name }}</strong></div><b>Manifest {{ item.completeness.score }} · {{ item.completeness.grade }}</b></div><div class="bar"><i :style="{width:`${item.completeness.score}%`}"></i></div><p>待补：{{ item.completeness.missing.length ? item.completeness.missing.map(missingLabel).join('、') : '无' }}</p><div class="review-foot"><span>安全建议 {{ item.proposalCount }} 项</span><button @click="selectedReview=item">查看建议</button></div></article>
      <p v-if="!filteredReviews.length" class="empty">没有匹配审核项。</p>
    </div>

    <div v-if="selected" class="drawer-mask" @click.self="selected=null"><aside class="drawer"><div class="drawer-head"><div><span>{{ selected.category }}</span><h3>{{ selected.name }}</h3></div><button @click="selected=null"><X :size="17"/></button></div><div class="drawer-summary"><b :class="['state',selected.status.toLowerCase()]">{{ statusLabel(selected.status) }}</b><span>模型 {{ selected.counts.models }} · 缺 {{ selected.counts.missingModels }}</span><span>节点 {{ selected.counts.nodeTypes }} · 缺 {{ selected.counts.missingNodeTypes }}</span></div><section><h4>模型依赖</h4><div v-for="item in selected.models" :key="item.name" class="detail-line"><div><b>{{ item.name }}</b><small v-if="item.matched">匹配：{{ item.matched }} · {{ item.match }}</small></div><span :class="['state',item.status.toLowerCase()]">{{ statusLabel(item.status) }}</span></div><p v-if="!selected.models.length" class="empty small">Manifest 未声明模型依赖。</p></section><section><h4>实际节点类型</h4><div v-for="item in selected.nodeTypes" :key="item.nodeType" class="detail-line"><b>{{ item.nodeType }}</b><span :class="['state',item.status.toLowerCase()]">{{ statusLabel(item.status) }}</span></div></section><section><h4>Custom Node 包声明</h4><div v-for="item in selected.customNodePackages" :key="item.name" class="detail-line"><div><b>{{ item.name }}</b><small>安装验证以该工作流的实际 nodeTypes 为准</small></div><span class="state declared">已声明</span></div><p v-if="!selected.customNodePackages.length" class="empty small">Manifest 未声明 Custom Node 包。</p></section></aside></div>

    <div v-if="selectedReview" class="drawer-mask" @click.self="selectedReview=null"><aside class="drawer review-drawer"><div class="drawer-head"><div><span>SAFE MANIFEST REVIEW</span><h3>{{ selectedReview.name }}</h3></div><button @click="selectedReview=null"><X :size="17"/></button></div><p class="review-rule">只补空字段和 analyzer 高置信度结果，不覆盖已有人工内容，也绝不修改 original.json。</p><div class="rule-list"><span v-for="rule in selectedReview.rules" :key="rule"><BadgeCheck :size="12"/>{{ rule }}</span></div><section><h4>建议 · {{ selectedReview.proposalCount }}</h4><div v-for="(proposal,index) in selectedReview.proposals" :key="index" class="proposal"><div><b>{{ proposal.type==='input'?`输入 ${proposal.key}`:proposal.field }}</b><small>{{ proposal.source }}<template v-if="proposal.confidence"> · confidence {{ Math.round(proposal.confidence*100) }}%</template></small></div><code>{{ proposal.type==='input'?JSON.stringify(proposal.changes):JSON.stringify(proposal.value) }}</code></div><p v-if="!selectedReview.proposals.length" class="empty small">当前没有可自动安全补全的字段。</p></section><button class="apply-safe" :disabled="!selectedReview.proposalCount||applying===selectedReview.workflowId" @click="applySafeReview(selectedReview)"><Wrench :size="14"/>{{ applying===selectedReview.workflowId?'应用中…':`显式应用 ${selectedReview.proposalCount} 项安全补全` }}</button></aside></div>
  </section>
</template>

<style scoped>
.dependency-center{display:grid;gap:14px}.dep-head{display:flex;justify-content:space-between;gap:20px}.dep-head h2{display:flex;gap:8px;align-items:center;margin:5px 0;color:#263960}.dep-head p{margin:0;color:#78859d;font-size:11px}.eyebrow{font-size:9px;color:#7160e8;font-weight:800;letter-spacing:.12em}.refresh{border:0;border-radius:8px;padding:9px 12px;background:#f1efff;color:#6552e6;display:flex;gap:6px;align-items:center;height:max-content}.alert,.offline{display:flex;align-items:center;gap:8px;border-radius:9px;padding:10px;font-size:10px}.alert.error,.offline{background:#fff1f1;color:#a94852;border:1px solid #f1d0d3}.alert.success{background:#ebf8f2;color:#267b60;border:1px solid #d2eee2}.offline div{display:flex;flex-direction:column}.dep-stats{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}.dep-stats article{padding:11px;border:1px solid #e4e8f1;border-radius:10px;background:#fff;display:flex;flex-direction:column}.dep-stats b{font-size:18px;color:#2d4167}.dep-stats span{font-size:8px;color:#8c99ad}.dep-stats article.warn b{color:#b16d20}.dep-tabs{display:flex;gap:6px;border-bottom:1px solid #e4e8f1}.dep-tabs button{border:0;background:transparent;padding:9px 11px;color:#75829a;font-size:10px;display:flex;align-items:center;gap:5px;border-bottom:2px solid transparent}.dep-tabs button.active{color:#5e4bdc;border-color:#6755e7;font-weight:800}.dep-toolbar{display:grid;grid-template-columns:1fr 180px;gap:8px}.dep-toolbar label{display:flex;align-items:center;gap:6px;border:1px solid #dfe4ef;background:#fff;border-radius:8px;padding:0 9px}.dep-toolbar input,.dep-toolbar select,.dep-toolbar>select{border:0;outline:0;padding:9px;width:100%;font-size:10px;background:#fff;color:#52627d}.dep-list{display:grid;gap:6px;max-height:58vh;overflow:auto}.dep-row{display:grid;grid-template-columns:minmax(260px,1.5fr) 1fr auto;gap:12px;align-items:center;border:1px solid #e6e9f1;background:#fff;border-radius:9px;padding:10px;cursor:pointer}.dep-list.compact .dep-row{grid-template-columns:1fr auto;cursor:default}.dep-row>div{display:flex;flex-direction:column;min-width:0}.dep-row strong{font-size:10px;color:#33496e}.dep-row span{font-size:8px;color:#8b97ab}.counts{display:flex!important;flex-direction:row!important;gap:8px;justify-content:flex-end}.counts .bad{color:#b4631b}.state{font-size:8px;padding:4px 7px;border-radius:999px;background:#edf0f5;color:#6f7d92;white-space:nowrap}.state.ready,.state.present{background:#e5f7ee;color:#167e5d}.state.missing_dependencies,.state.missing{background:#fff0ec;color:#b15142}.state.comfy_offline,.state.unknown{background:#f0f1f5;color:#788397}.state.declared{background:#eeeaff;color:#6250df}.review-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.review-card{border:1px solid #e5e8f1;background:#fff;border-radius:10px;padding:11px}.review-top{display:flex;justify-content:space-between;gap:10px}.review-top>div{display:flex;flex-direction:column}.review-top span{font-size:8px;color:#8b97ac}.review-top strong{font-size:10px;color:#33486d}.review-top>b{font-size:8px;color:#6956e5}.bar{height:5px;background:#eef1f6;border-radius:99px;margin:8px 0;overflow:hidden}.bar i{display:block;height:100%;background:#6b58e6}.review-card p{font-size:8px;color:#8995aa}.review-foot{display:flex;justify-content:space-between;align-items:center}.review-foot span{font-size:8px;color:#7b879c}.review-foot button{border:0;background:#f2efff;color:#6754df;border-radius:6px;padding:6px 8px;font-size:8px}.empty{text-align:center;color:#96a1b3;font-size:10px;padding:30px}.empty.small{padding:10px}.drawer-mask{position:fixed;inset:0;background:rgba(28,38,59,.43);z-index:100;display:flex;justify-content:flex-end}.drawer{width:min(720px,92vw);height:100%;background:#fff;overflow:auto;padding:20px;box-shadow:-18px 0 50px rgba(25,37,61,.15)}.drawer-head{display:flex;justify-content:space-between;gap:12px}.drawer-head span{font-size:8px;color:#8475a4}.drawer-head h3{margin:3px 0;color:#2e4268}.drawer-head button{border:0;background:#f3f5f8;border-radius:7px;width:30px;height:30px}.drawer-summary{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}.drawer-summary>span:not(.state){font-size:8px;background:#f5f6f9;color:#758198;padding:5px 7px;border-radius:999px}.drawer section{margin-top:14px}.drawer h4{font-size:11px;color:#3c5072}.detail-line{display:flex;justify-content:space-between;gap:10px;padding:8px;border:1px solid #e8ebf2;border-radius:7px;margin:5px 0}.detail-line>div{display:flex;flex-direction:column}.detail-line b{font-size:9px;color:#465977}.detail-line small{font-size:7px;color:#8c98ac}.review-rule{font-size:9px;line-height:1.6;color:#75698c;background:#f7f4ff;padding:9px;border-radius:8px}.rule-list{display:grid;gap:5px}.rule-list span{display:flex;align-items:center;gap:5px;font-size:8px;color:#5d6e88}.proposal{padding:9px;border:1px solid #e6e9f1;border-radius:8px;margin:6px 0}.proposal div{display:flex;justify-content:space-between;gap:8px}.proposal b{font-size:9px;color:#415573}.proposal small{font-size:7px;color:#8996aa}.proposal code{display:block;margin-top:5px;font-size:8px;color:#6f7c91;white-space:pre-wrap}.apply-safe{width:100%;border:0;border-radius:8px;padding:10px;background:#6653e5;color:#fff;display:flex;justify-content:center;align-items:center;gap:6px;margin-top:15px}.apply-safe:disabled{opacity:.5}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1200px){.dep-stats{grid-template-columns:repeat(3,1fr)}.review-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.dep-head{flex-direction:column}.dep-stats{grid-template-columns:repeat(2,1fr)}.dep-toolbar{grid-template-columns:1fr}.dep-row{grid-template-columns:1fr}.counts{justify-content:flex-start!important}.review-grid{grid-template-columns:1fr}.drawer{width:100vw}}
</style>
