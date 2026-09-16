<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, Boxes, CheckCircle2, Filter, RefreshCcw, Search, Target, Wrench } from 'lucide-vue-next'

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

const plan = ref<Plan | null>(null)
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

async function load(forceRefresh = false) {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ limit: '200' })
    if (forceRefresh) params.set('forceRefresh', 'true')
    if (capability.value) params.set('capability', capability.value)
    const response = await fetch(`/api/readiness/plan?${params}`)
    if (!response.ok) throw new Error(`Readiness HTTP ${response.status}`)
    plan.value = await response.json()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法加载就绪提升计划'
  } finally {
    loading.value = false
  }
}

function switchCapability() { void load(false) }

onMounted(() => void load(true))
</script>

<template>
  <section class="readiness-shell">
    <div class="readiness-head">
      <div>
        <span class="eyebrow">PHASE 1G · READINESS REMEDIATION</span>
        <h2><Target :size="23"/>工作流可运行率提升</h2>
        <p>把“172 个缺依赖工作流”拆成具体阻塞项，优先找出修复一个依赖就能直接解锁的 Workflow。这里只做诊断和排序，不自动安装任何模型或节点。</p>
      </div>
      <button class="refresh" :disabled="loading" @click="load(true)"><RefreshCcw :size="15" :class="{spin:loading}"/>重新扫描</button>
    </div>

    <p v-if="error" class="alert"><AlertTriangle :size="15"/>{{ error }}</p>
    <div v-if="plan && !plan.connected" class="offline"><AlertTriangle :size="18"/><div><b>ComfyUI 当前离线</b><span>离线时不会生成缺依赖修复计划，避免把 UNKNOWN 误当 MISSING。</span></div></div>

    <div v-if="plan" class="stats">
      <article><CheckCircle2 :size="18"/><div><b>{{ plan.summary.ready }}</b><span>当前 READY</span></div></article>
      <article class="warn"><Boxes :size="18"/><div><b>{{ plan.summary.blocked }}</b><span>缺依赖</span></div></article>
      <article class="accent"><Wrench :size="18"/><div><b>{{ plan.summary.nearReady }}</b><span>只差 1 个依赖</span></div></article>
      <article><Target :size="18"/><div><b>{{ plan.summary.topUnlockPotential }}</b><span>Top 10 保守解锁潜力</span></div></article>
    </div>

    <div class="toolbar">
      <label><Search :size="14"/><input v-model="q" placeholder="搜索缺失模型、节点或工作流..."/></label>
      <label><Filter :size="14"/><select v-model="kind"><option value="">全部阻塞类型</option><option value="MODEL">缺模型</option><option value="NODE">缺节点</option></select></label>
      <select v-model="capability" @change="switchCapability"><option value="">全部 Capability</option><option v-for="item in capabilityOptions" :key="item[0]" :value="item[0]">{{ item[0] }} · {{ item[1] }}</option></select>
    </div>

    <div class="two-col" v-if="plan">
      <section class="panel-card">
        <div class="section-title"><div><span>PRIORITY BLOCKERS</span><h3>优先修复项</h3></div><small>{{ blockers.length }} 项</small></div>
        <div class="blocker-list">
          <article v-for="item in blockers" :key="item.key" class="blocker-row">
            <div class="blocker-rank"><b>{{ item.unlockCount }}</b><span>可直接解锁</span></div>
            <div class="blocker-main"><div class="blocker-title"><span :class="['kind',item.kind.toLowerCase()]">{{ item.kind==='MODEL'?'模型':'节点' }}</span><strong>{{ item.name }}</strong><em v-if="item.modelType">{{ item.modelType }}</em></div><p>影响 {{ item.affectedCount }} 个工作流；其中 {{ item.unlockCount }} 个只差这一项。</p><div class="chips"><span v-for="cap in item.capabilities.slice(0,4)" :key="cap.key">{{ cap.key }} · {{ cap.count }}</span></div></div>
          </article>
          <p v-if="!blockers.length" class="empty">当前筛选下没有缺依赖阻塞项。</p>
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
          <p v-if="!nearReady.length" class="empty">当前筛选下没有只差一个依赖的工作流。</p>
        </div>
      </section>
    </div>

    <section v-if="plan" class="explain">
      <b>排序原则</b>
      <p><strong>可直接解锁</strong>只统计“当前恰好缺这一项”的 Workflow，属于保守数字；<strong>影响工作流</strong>则表示该依赖在多少个阻塞 Workflow 中出现。系统不会把“影响 20 个”误说成“安装后一定解锁 20 个”。</p>
    </section>
  </section>
</template>

<style scoped>
.readiness-shell{display:grid;gap:15px}.readiness-head{display:flex;justify-content:space-between;gap:18px}.readiness-head h2{margin:5px 0;color:#263a61;display:flex;align-items:center;gap:8px}.readiness-head p{margin:0;color:#76849d;font-size:11px;line-height:1.6;max-width:850px}.eyebrow{font-size:9px;letter-spacing:.12em;color:#6d59e6;font-weight:800}.refresh{border:0;background:#efedff;color:#6250df;border-radius:8px;padding:9px 12px;height:max-content;display:flex;gap:6px;align-items:center}.alert,.offline{display:flex;align-items:center;gap:8px;border-radius:9px;padding:10px;font-size:10px}.alert{background:#fff1f1;color:#a74953}.offline{background:#f4f5f8;color:#6f7b91}.offline div{display:flex;flex-direction:column}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.stats article{padding:12px;border:1px solid #e4e8f1;border-radius:10px;background:#fff;display:flex;gap:9px;align-items:center;color:#3d7a66}.stats article.warn{color:#bb7044}.stats article.accent{color:#6b56e7}.stats div{display:flex;flex-direction:column}.stats b{font-size:18px;color:#2f4267}.stats span{font-size:8px;color:#8996aa}.toolbar{display:grid;grid-template-columns:1fr 180px 220px;gap:8px}.toolbar label{display:flex;align-items:center;gap:6px;border:1px solid #dfe4ef;background:#fff;border-radius:8px;padding:0 9px}.toolbar input,.toolbar select,.toolbar>select{border:0;outline:0;background:#fff;padding:9px;width:100%;font-size:10px;color:#53637e}.two-col{display:grid;grid-template-columns:1.15fr .85fr;gap:10px}.panel-card{border:1px solid #e4e8f1;background:#fff;border-radius:11px;padding:12px;min-width:0}.section-title{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}.section-title span{font-size:8px;letter-spacing:.08em;color:#8b7be9}.section-title h3{margin:2px 0;color:#34496d;font-size:13px}.section-title small{color:#8f9aad}.blocker-list,.workflow-list{display:grid;gap:6px;max-height:57vh;overflow:auto}.blocker-row{display:grid;grid-template-columns:68px 1fr;gap:10px;padding:10px;border:1px solid #e7eaf2;border-radius:9px}.blocker-rank{display:flex;flex-direction:column;align-items:center;justify-content:center;background:#f6f4ff;border-radius:8px}.blocker-rank b{font-size:18px;color:#6551df}.blocker-rank span{font-size:7px;color:#8d81b0}.blocker-title{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.blocker-title strong{font-size:10px;color:#3b4e70}.blocker-title em{font-size:7px;color:#75829a;font-style:normal}.kind{font-size:7px;border-radius:999px;padding:3px 5px}.kind.model{background:#edf3ff;color:#4f6fc1}.kind.node{background:#fff0e8;color:#ac6840}.blocker-main p{font-size:8px;color:#7f8ca1;margin:5px 0}.chips{display:flex;gap:4px;flex-wrap:wrap}.chips span{font-size:7px;padding:3px 5px;background:#f3f5f8;border-radius:999px;color:#738096}.workflow-row{display:grid;grid-template-columns:1fr auto;gap:5px 8px;padding:9px;border:1px solid #e7eaf2;border-radius:8px}.workflow-row>div:first-child{display:flex;flex-direction:column}.workflow-row strong{font-size:9px;color:#3c5071}.workflow-row span,.workflow-row code{font-size:7px;color:#8692a5}.workflow-row code{grid-column:1/-1;background:#f6f7fa;padding:5px;border-radius:5px;white-space:normal}.missing{display:flex;gap:4px}.missing span{background:#fff2e8;color:#a9653d;padding:3px 5px;border-radius:999px}.explain{border:1px solid #e3e0fb;background:#f8f7ff;border-radius:10px;padding:10px}.explain b{font-size:9px;color:#5c4bd1}.explain p{font-size:9px;line-height:1.6;color:#6f7d96;margin:4px 0 0}.empty{text-align:center;color:#98a2b3;font-size:9px;padding:28px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1100px){.two-col{grid-template-columns:1fr}.toolbar{grid-template-columns:1fr 1fr}.toolbar label:first-child{grid-column:1/-1}}@media(max-width:700px){.readiness-head{flex-direction:column}.stats{grid-template-columns:1fr 1fr}.toolbar{grid-template-columns:1fr}.toolbar label:first-child{grid-column:auto}}@media(max-width:480px){.stats{grid-template-columns:1fr}.blocker-row{grid-template-columns:1fr}.blocker-rank{align-items:flex-start;padding:8px}}
</style>
