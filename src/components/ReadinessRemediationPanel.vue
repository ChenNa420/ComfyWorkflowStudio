<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, Boxes, CheckCircle2, ExternalLink, FileSearch, Filter, FolderSearch, RefreshCcw, Search, ShieldCheck, Target, Wrench } from 'lucide-vue-next'

type Blocker = {
  key: string
  kind: 'MODEL' | 'NODE'
  name: string
  modelType?: string | null
  affectedCount: number
  unlockCount: number
  priorityScore: number
  capabilities: Array<{ key: string; count: number }>
  categories: Array<{ key: string; count: number }>
  workflows: Array<{ id: string; name: string }>
}

type WorkflowRow = {
  workflowId: string
  name: string
  category: string
  capabilities: string[]
  blockerCount: number
  missingModels: number
  missingNodes: number
  nearReady: boolean
  blockers: Array<{ key: string; kind: string; name: string; modelType?: string }>
}

type Plan = {
  connected: boolean
  comfyUiUrl: string
  error?: string | null
  filters: { capability?: string | null; category?: string | null }
  summary: {
    workflows: number
    ready: number
    blocked: number
    nearReady: number
    multiBlocker: number
    modelBlockers: number
    nodeBlockers: number
    topUnlockPotential: number
  }
  topBlockers: Blocker[]
  nearReadyWorkflows: WorkflowRow[]
  blockedWorkflows: WorkflowRow[]
}

type PackageCandidate = {
  packageName: string
  installUrl?: string | null
  evidenceCount: number
  workflowCount: number
  coverage: number
  confidence: string
  reason: string
}

type Guide = {
  key: string
  kind: 'MODEL' | 'NODE'
  name: string
  modelType?: string | null
  affectedCount: number
  unlockCount: number
  priorityScore: number
  writeMode: boolean
  action: string
  confidence: 'HIGH' | 'MEDIUM' | 'LOW'
  evidence: string[]
  safety: string[]
  sourceUrl?: string
  sourceUrls?: Array<{ url: string; evidenceCount: number }>
  declaredPaths?: Array<{ declaredPath: string; evidenceCount: number }>
  candidatePackages?: PackageCandidate[]
}

type GuidePayload = {
  connected: boolean
  blocked: number
  summary: {
    guides: number
    withHighConfidenceAction: number
    withSourceUrl: number
    withDeclaredPath: number
    ignoredNodeTypes: number
    ignoredNodeOccurrences: number
  }
  guides: Guide[]
  rules: string[]
}

const tab = ref<'plan' | 'guides'>('plan')
const plan = ref<Plan | null>(null)
const guidePayload = ref<GuidePayload | null>(null)
const loading = ref(false)
const error = ref('')
const q = ref('')
const kind = ref('')
const capability = ref('')

const capabilityOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const item of plan.value?.blockedWorkflows || []) {
    for (const cap of item.capabilities || []) counts.set(cap, (counts.get(cap) || 0) + 1)
  }
  return [...counts.entries()].sort((a,b) => b[1]-a[1])
})

const blockers = computed(() => {
  const key = q.value.trim().toLowerCase()
  return (plan.value?.topBlockers || []).filter(item => {
    if (kind.value && item.kind !== kind.value) return false
    if (key && !`${item.name} ${item.modelType || ''}`.toLowerCase().includes(key)) return false
    return true
  })
})

const nearReady = computed(() => {
  const key = q.value.trim().toLowerCase()
  return (plan.value?.nearReadyWorkflows || []).filter(item => !key || `${item.name} ${item.category} ${item.capabilities.join(' ')}`.toLowerCase().includes(key))
})

const guides = computed(() => {
  const key = q.value.trim().toLowerCase()
  return (guidePayload.value?.guides || []).filter(item => {
    if (kind.value && item.kind !== kind.value) return false
    const packageNames = (item.candidatePackages || []).map(candidate => candidate.packageName).join(' ')
    if (key && !`${item.name} ${item.modelType || ''} ${packageNames}`.toLowerCase().includes(key)) return false
    return true
  })
})

async function load(forceRefresh = false) {
  loading.value = true
  error.value = ''
  try {
    const planParams = new URLSearchParams({ limit: '200' })
    const guideParams = new URLSearchParams({ limit: '100' })
    if (forceRefresh) {
      planParams.set('forceRefresh', 'true')
      guideParams.set('forceRefresh', 'true')
    }
    if (capability.value) {
      planParams.set('capability', capability.value)
      guideParams.set('capability', capability.value)
    }
    const [planResponse, guideResponse] = await Promise.all([
      fetch(`/api/readiness/plan?${planParams}`),
      fetch(`/api/remediation-guides?${guideParams}`),
    ])
    if (!planResponse.ok) throw new Error(`Readiness HTTP ${planResponse.status}`)
    if (!guideResponse.ok) throw new Error(`Guide HTTP ${guideResponse.status}`)
    plan.value = await planResponse.json()
    guidePayload.value = await guideResponse.json()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法加载就绪提升计划'
  } finally {
    loading.value = false
  }
}

function switchCapability() { void load(false) }
function confidenceLabel(value: string) { return ({ HIGH: '高证据', MEDIUM: '中等证据', LOW: '需人工确认' } as Record<string,string>)[value] || value }
function actionLabel(value: string) { return ({ VERIFY_CUSTOM_NODE_PACKAGE: '核对 Custom Node 包', VERIFY_MODEL_FILE: '核对模型文件位置', VERIFY_MODEL_SOURCE: '核对模型来源', MANUAL_REVIEW: '人工调查' } as Record<string,string>)[value] || value }

onMounted(() => void load(true))
</script>

<template>
  <section class="readiness-shell">
    <div class="readiness-head">
      <div>
        <span class="eyebrow">PHASE 1G-2 · EXECUTION-AWARE REMEDIATION</span>
        <h2><Target :size="23"/>工作流可运行率提升</h2>
        <p>先按 Runtime Converter 的真实执行语义排除 Note、MarkdownNote、禁用节点和无输出的 UI 装饰节点，再对剩余真实阻塞项提供证据化修复指南。所有指南只读，不自动下载或安装。</p>
      </div>
      <button class="refresh" :disabled="loading" @click="load(true)"><RefreshCcw :size="15" :class="{spin:loading}"/>重新扫描</button>
    </div>

    <p v-if="error" class="alert"><AlertTriangle :size="15"/>{{ error }}</p>
    <div v-if="plan && !plan.connected" class="offline"><AlertTriangle :size="18"/><div><b>ComfyUI 当前离线</b><span>离线时不会生成缺依赖修复计划或安装建议，避免把 UNKNOWN 误当 MISSING。</span></div></div>

    <div v-if="plan" class="stats">
      <article><CheckCircle2 :size="18"/><div><b>{{ plan.summary.ready }}</b><span>当前 READY</span></div></article>
      <article class="warn"><Boxes :size="18"/><div><b>{{ plan.summary.blocked }}</b><span>真实执行阻塞</span></div></article>
      <article class="accent"><Wrench :size="18"/><div><b>{{ plan.summary.nearReady }}</b><span>只差 1 个依赖</span></div></article>
      <article><Target :size="18"/><div><b>{{ plan.summary.topUnlockPotential }}</b><span>Top 10 保守解锁潜力</span></div></article>
    </div>

    <div class="mode-tabs">
      <button :class="{active:tab==='plan'}" @click="tab='plan'">优先级计划</button>
      <button :class="{active:tab==='guides'}" @click="tab='guides'"><ShieldCheck :size="13"/>安全修复指南</button>
    </div>

    <div class="toolbar">
      <label><Search :size="14"/><input v-model="q" placeholder="搜索缺失模型、节点、包名或工作流..."/></label>
      <label><Filter :size="14"/><select v-model="kind"><option value="">全部阻塞类型</option><option value="MODEL">缺模型</option><option value="NODE">缺节点</option></select></label>
      <select v-model="capability" @change="switchCapability"><option value="">全部 Capability</option><option v-for="item in capabilityOptions" :key="item[0]" :value="item[0]">{{ item[0] }} · {{ item[1] }}</option></select>
    </div>

    <template v-if="tab==='plan' && plan">
      <div class="two-col">
        <section class="panel-card">
          <div class="section-title"><div><span>PRIORITY BLOCKERS</span><h3>优先修复项</h3></div><small>{{ blockers.length }} 项</small></div>
          <div class="blocker-list">
            <article v-for="item in blockers" :key="item.key" class="blocker-row">
              <div class="blocker-rank"><b>{{ item.unlockCount }}</b><span>可直接解锁</span></div>
              <div class="blocker-main"><div class="blocker-title"><span :class="['kind',item.kind.toLowerCase()]">{{ item.kind==='MODEL'?'模型':'节点' }}</span><strong>{{ item.name }}</strong><em v-if="item.modelType">{{ item.modelType }}</em></div><p>影响 {{ item.affectedCount }} 个工作流；其中 {{ item.unlockCount }} 个只差这一项。</p><div class="chips"><span v-for="cap in item.capabilities.slice(0,4)" :key="cap.key">{{ cap.key }} · {{ cap.count }}</span></div></div>
            </article>
            <p v-if="!blockers.length" class="empty">当前筛选下没有真实执行阻塞项。</p>
          </div>
        </section>

        <section class="panel-card">
          <div class="section-title"><div><span>NEAR READY</span><h3>最接近可运行</h3></div><small>{{ nearReady.length }} 个</small></div>
          <div class="workflow-list">
            <article v-for="item in nearReady" :key="item.workflowId" class="workflow-row">
              <div><strong>{{ item.name }}</strong><span>{{ item.category }} · {{ item.capabilities.join(', ') }}</span></div>
              <div class="missing"><span v-if="item.missingModels">模型 {{ item.missingModels }}</span><span v-if="item.missingNodes">节点 {{ item.missingNodes }}</span></div>
              <code>{{ item.blockers[0]?.name }}</code>
            </article>
            <p v-if="!nearReady.length" class="empty">当前筛选下没有只差一个真实执行依赖的工作流。</p>
          </div>
        </section>
      </div>

      <section class="explain">
        <b>执行依赖规则</b>
        <p><strong>可直接解锁</strong>只统计当前恰好缺这一项的 Workflow。依赖盘点现在与 Runtime Converter 对齐：Note、MarkdownNote、PixaromaNote/Label、mode=Never 节点，以及缺失但没有任何下游输出连接的 UI 辅助节点，都不会再被当成运行阻塞。</p>
      </section>
    </template>

    <template v-else-if="tab==='guides' && guidePayload">
      <div class="guide-stats">
        <article><ShieldCheck :size="16"/><b>{{ guidePayload.summary.guides }}</b><span>证据化指南</span></article>
        <article><FileSearch :size="16"/><b>{{ guidePayload.summary.withHighConfidenceAction }}</b><span>高证据动作</span></article>
        <article><ExternalLink :size="16"/><b>{{ guidePayload.summary.withSourceUrl }}</b><span>Manifest 有来源</span></article>
        <article><FolderSearch :size="16"/><b>{{ guidePayload.summary.ignoredNodeOccurrences }}</b><span>已排除非执行节点出现次数</span></article>
      </div>

      <section class="safety-banner"><ShieldCheck :size="18"/><div><b>只读修复指南</b><span>系统不会根据节点名称猜 GitHub 仓库，也不会根据模型文件名猜下载地址。只有 Manifest 已声明的包名、installUrl、模型 path/installUrl 才会作为证据展示。</span></div></section>

      <div class="guide-list">
        <article v-for="item in guides" :key="item.key" class="guide-card">
          <div class="guide-head">
            <div><span :class="['kind',item.kind.toLowerCase()]">{{ item.kind==='MODEL'?'模型':'节点' }}</span><strong>{{ item.name }}</strong><em v-if="item.modelType">{{ item.modelType }}</em></div>
            <span :class="['confidence',item.confidence.toLowerCase()]">{{ confidenceLabel(item.confidence) }}</span>
          </div>
          <div class="guide-impact"><b>可直接解锁 {{ item.unlockCount }}</b><span>影响 {{ item.affectedCount }} 个工作流</span><span>{{ actionLabel(item.action) }}</span></div>
          <p v-for="evidence in item.evidence" :key="evidence" class="evidence">{{ evidence }}</p>

          <div v-if="item.candidatePackages?.length" class="evidence-box">
            <h4>Manifest Custom Node 候选</h4>
            <div v-for="candidate in item.candidatePackages.slice(0,4)" :key="`${candidate.packageName}-${candidate.installUrl}`" class="evidence-row">
              <div><b>{{ candidate.packageName }}</b><span>{{ candidate.evidenceCount }}/{{ candidate.workflowCount }} 个 Workflow 声明 · 覆盖 {{ candidate.coverage }}%</span></div>
              <a v-if="candidate.installUrl" :href="candidate.installUrl" target="_blank" rel="noreferrer">核对来源 <ExternalLink :size="11"/></a>
            </div>
          </div>

          <div v-if="item.declaredPaths?.length" class="evidence-box">
            <h4>Manifest 声明路径</h4>
            <code v-for="candidate in item.declaredPaths.slice(0,4)" :key="candidate.declaredPath">{{ candidate.declaredPath }}</code>
          </div>

          <div v-if="item.sourceUrls?.length" class="evidence-box">
            <h4>Manifest 声明来源</h4>
            <a v-for="candidate in item.sourceUrls.slice(0,4)" :key="candidate.url" :href="candidate.url" target="_blank" rel="noreferrer">{{ candidate.url }} <ExternalLink :size="11"/></a>
          </div>

          <div class="safety-line"><span v-for="rule in item.safety.slice(0,3)" :key="rule"><CheckCircle2 :size="11"/>{{ rule }}</span></div>
        </article>
        <p v-if="!guides.length" class="empty">当前筛选下没有具有真实执行阻塞的修复指南。</p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.readiness-shell{display:grid;gap:15px}.readiness-head{display:flex;justify-content:space-between;gap:18px}.readiness-head h2{margin:5px 0;color:#263a61;display:flex;align-items:center;gap:8px}.readiness-head p{margin:0;color:#76849d;font-size:11px;line-height:1.6;max-width:900px}.eyebrow{font-size:9px;letter-spacing:.12em;color:#6d59e6;font-weight:800}.refresh{border:0;background:#efedff;color:#6250df;border-radius:8px;padding:9px 12px;height:max-content;display:flex;gap:6px;align-items:center}.alert,.offline{display:flex;align-items:center;gap:8px;border-radius:9px;padding:10px;font-size:10px}.alert{background:#fff1f1;color:#a74953}.offline{background:#f4f5f8;color:#6f7b91}.offline div{display:flex;flex-direction:column}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.stats article{padding:12px;border:1px solid #e4e8f1;border-radius:10px;background:#fff;display:flex;gap:9px;align-items:center;color:#3d7a66}.stats article.warn{color:#bb7044}.stats article.accent{color:#6b56e7}.stats div{display:flex;flex-direction:column}.stats b{font-size:18px;color:#2f4267}.stats span{font-size:8px;color:#8996aa}.mode-tabs{display:flex;gap:6px;border-bottom:1px solid #e4e8f1}.mode-tabs button{border:0;background:transparent;padding:9px 11px;color:#75829a;font-size:10px;display:flex;align-items:center;gap:5px;border-bottom:2px solid transparent}.mode-tabs button.active{color:#5e4bdc;border-color:#6755e7;font-weight:800}.toolbar{display:grid;grid-template-columns:1fr 180px 220px;gap:8px}.toolbar label{display:flex;align-items:center;gap:6px;border:1px solid #dfe4ef;background:#fff;border-radius:8px;padding:0 9px}.toolbar input,.toolbar select,.toolbar>select{border:0;outline:0;background:#fff;padding:9px;width:100%;font-size:10px;color:#53637e}.two-col{display:grid;grid-template-columns:1.15fr .85fr;gap:10px}.panel-card{border:1px solid #e4e8f1;background:#fff;border-radius:11px;padding:12px;min-width:0}.section-title{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}.section-title span{font-size:8px;letter-spacing:.08em;color:#8b7be9}.section-title h3{margin:2px 0;color:#34496d;font-size:13px}.section-title small{color:#8f9aad}.blocker-list,.workflow-list{display:grid;gap:6px;max-height:57vh;overflow:auto}.blocker-row{display:grid;grid-template-columns:68px 1fr;gap:10px;padding:10px;border:1px solid #e7eaf2;border-radius:9px}.blocker-rank{display:flex;flex-direction:column;align-items:center;justify-content:center;background:#f6f4ff;border-radius:8px}.blocker-rank b{font-size:18px;color:#6551df}.blocker-rank span{font-size:7px;color:#8d81b0}.blocker-title,.guide-head>div{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.blocker-title strong,.guide-head strong{font-size:10px;color:#3b4e70;word-break:break-word}.blocker-title em,.guide-head em{font-size:7px;color:#75829a;font-style:normal}.kind{font-size:7px;border-radius:999px;padding:3px 5px;white-space:nowrap}.kind.model{background:#edf3ff;color:#4f6fc1}.kind.node{background:#fff0e8;color:#ac6840}.blocker-main p{font-size:8px;color:#7f8ca1;margin:5px 0}.chips{display:flex;gap:4px;flex-wrap:wrap}.chips span{font-size:7px;padding:3px 5px;background:#f3f5f8;border-radius:999px;color:#738096}.workflow-row{display:grid;grid-template-columns:1fr auto;gap:5px 8px;padding:9px;border:1px solid #e7eaf2;border-radius:8px}.workflow-row>div:first-child{display:flex;flex-direction:column}.workflow-row strong{font-size:9px;color:#3c5071}.workflow-row span,.workflow-row code{font-size:7px;color:#8692a5}.workflow-row code{grid-column:1/-1;background:#f6f7fa;padding:5px;border-radius:5px;white-space:normal;word-break:break-all}.missing{display:flex;gap:4px}.missing span{background:#fff2e8;color:#a9653d;padding:3px 5px;border-radius:999px}.explain{border:1px solid #e3e0fb;background:#f8f7ff;border-radius:10px;padding:10px}.explain b{font-size:9px;color:#5c4bd1}.explain p{font-size:9px;line-height:1.6;color:#6f7d96;margin:4px 0 0}.guide-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.guide-stats article{display:grid;grid-template-columns:auto auto 1fr;align-items:center;gap:7px;border:1px solid #e5e8f1;background:#fff;border-radius:9px;padding:10px;color:#6754df}.guide-stats b{font-size:15px;color:#34486c}.guide-stats span{font-size:8px;color:#8793a8}.safety-banner{display:flex;gap:9px;align-items:center;background:#edf8f3;border:1px solid #d7eee3;color:#267b60;padding:10px;border-radius:9px}.safety-banner div{display:flex;flex-direction:column}.safety-banner b{font-size:9px}.safety-banner span{font-size:8px;line-height:1.5;color:#68877d}.guide-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.guide-card{border:1px solid #e4e8f1;background:#fff;border-radius:11px;padding:11px;min-width:0}.guide-head{display:flex;justify-content:space-between;gap:8px}.confidence{font-size:7px;padding:4px 6px;border-radius:999px;white-space:nowrap}.confidence.high{background:#e5f7ee;color:#187c5d}.confidence.medium{background:#fff3df;color:#a86a1e}.confidence.low{background:#f0f1f5;color:#748197}.guide-impact{display:flex;gap:6px;flex-wrap:wrap;margin:9px 0}.guide-impact b,.guide-impact span{font-size:8px;padding:4px 6px;background:#f5f6fa;border-radius:999px;color:#68758c}.guide-impact b{background:#f0edff;color:#624fdf}.evidence{font-size:8px;color:#748198;line-height:1.5;margin:5px 0}.evidence-box{margin-top:8px;background:#f8f9fc;border-radius:8px;padding:8px;display:grid;gap:5px}.evidence-box h4{font-size:8px;color:#485b79;margin:0}.evidence-row{display:flex;justify-content:space-between;gap:8px;align-items:center}.evidence-row>div{display:flex;flex-direction:column;min-width:0}.evidence-row b{font-size:8px;color:#415574;word-break:break-word}.evidence-row span{font-size:7px;color:#8a96a9}.evidence-box code,.evidence-box a{font-size:7px;color:#5e6f8b;word-break:break-all}.evidence-box a{display:flex;align-items:center;gap:3px;color:#5d4bd2;text-decoration:none}.safety-line{display:grid;gap:3px;margin-top:8px}.safety-line span{display:flex;gap:4px;align-items:flex-start;font-size:7px;color:#7b879a}.empty{text-align:center;color:#98a2b3;font-size:9px;padding:28px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1100px){.two-col{grid-template-columns:1fr}.toolbar{grid-template-columns:1fr 1fr}.toolbar label:first-child{grid-column:1/-1}.guide-list{grid-template-columns:1fr}.guide-stats{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.readiness-head{flex-direction:column}.stats{grid-template-columns:1fr 1fr}.toolbar{grid-template-columns:1fr}.toolbar label:first-child{grid-column:auto}.guide-stats{grid-template-columns:1fr 1fr}}@media(max-width:480px){.stats,.guide-stats{grid-template-columns:1fr}.blocker-row{grid-template-columns:1fr}.blocker-rank{align-items:flex-start;padding:8px}.evidence-row{flex-direction:column;align-items:flex-start}}
</style>
