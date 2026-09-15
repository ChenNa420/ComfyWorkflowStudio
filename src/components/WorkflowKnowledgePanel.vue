<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Activity,
  BadgeCheck,
  Boxes,
  BrainCircuit,
  ChevronRight,
  CircleAlert,
  Filter,
  Gauge,
  Layers3,
  Play,
  RefreshCcw,
  Search,
  Sparkles,
  X,
} from 'lucide-vue-next'

type KnowledgeCard = {
  id: string
  name: string
  category: string
  categoryLabel: string
  categoryGroup: string
  description: string
  difficulty: string
  capabilities: string[]
  families: string[]
  traits: string[]
  health: string
  healthReasons: string[]
  completeness: { score: number; grade: string; missing: string[]; analysisConfidence: number | null }
  runtimeMetrics: { runs: number; succeeded: number; failed: number; uncertain: number; successRate: number | null; lastUsedAt: string | null }
  format: string | null
  nodeCount: number | null
  modelCount: number
  customNodeCount: number
  inputCount: number
  outputTypes: string[]
  recommendationScore: number
  manifest: { recommendedFor: string[]; notRecommendedFor: string[]; guideSummary: string }
}

type KnowledgeStats = {
  total: number
  averageCompleteness: number
  ready: number
  needsAdaptation: number
  missingDependencies: number
  unsupported: number
  categories: Array<{ key: string; label: string; count: number }>
  capabilities: Array<{ key: string; count: number }>
  families: Array<{ key: string; count: number }>
}

type KnowledgeDetail = KnowledgeCard & {
  manifest: {
    recommendedFor: string[]
    notRecommendedFor: string[]
    guide: { summary: string; steps: string[]; promptTips: string[]; warnings: string[] }
    inputs: Array<{ key: string; label: string; type: string; purpose?: string; description?: string; help?: string; mapping?: { nodeId?: string; field?: string } }>
    parameters: Array<{ key: string; label: string; type: string; default?: unknown; description?: string; mapping?: { nodeId?: string; field?: string } }>
    outputs: Array<{ key: string; type: string; format?: string; mapping?: { nodeId?: string } }>
    dependencies: { models: Array<{ name: string; required: boolean }>; customNodes: Array<{ name: string; required: boolean }> }
  }
  analysis: Record<string, unknown>
  packagePath: string
}

const cards = ref<KnowledgeCard[]>([])
const stats = ref<KnowledgeStats | null>(null)
const detail = ref<KnowledgeDetail | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const q = ref('')
const category = ref('')
const health = ref('')
const capability = ref('')
const family = ref('')
let searchTimer: number | undefined

const filteredCountLabel = computed(() => `${cards.value.length} / ${stats.value?.total ?? 0}`)

function queryString() {
  const params = new URLSearchParams()
  if (q.value.trim()) params.set('q', q.value.trim())
  if (category.value) params.set('category', category.value)
  if (health.value) params.set('health', health.value)
  if (capability.value) params.set('capability', capability.value)
  if (family.value) params.set('family', family.value)
  params.set('limit', '500')
  return params.toString()
}

async function loadStats() {
  const response = await fetch('/api/workflow-knowledge/stats')
  if (!response.ok) throw new Error(`Stats HTTP ${response.status}`)
  stats.value = await response.json()
}

async function loadCards() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch(`/api/workflow-knowledge?${queryString()}`)
    if (!response.ok) throw new Error(`Workflow knowledge HTTP ${response.status}`)
    cards.value = await response.json()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法加载工作流知识库'
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadStats(), loadCards()])
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法连接本地 API'
  } finally {
    loading.value = false
  }
}

async function openDetail(card: KnowledgeCard) {
  detailLoading.value = true
  error.value = ''
  try {
    const response = await fetch(`/api/workflow-knowledge/${encodeURIComponent(card.id)}`)
    if (!response.ok) throw new Error(`Detail HTTP ${response.status}`)
    detail.value = await response.json()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法加载知识卡详情'
  } finally {
    detailLoading.value = false
  }
}

function useWorkflow(card: KnowledgeCard) {
  sessionStorage.setItem('cws-selected-workflow', card.id)
  location.hash = '#/create-task'
}

function openAdapter(card: KnowledgeCard) {
  sessionStorage.setItem('cws-selected-workflow', card.id)
  location.hash = '#/adapter'
}

function resetFilters() {
  q.value = ''
  category.value = ''
  health.value = ''
  capability.value = ''
  family.value = ''
}

function healthLabel(value: string) {
  return ({ READY: '可直接使用', NEEDS_ADAPTATION: '需要适配', MISSING_DEPENDENCIES: '缺少依赖', UNSUPPORTED: '暂不支持' } as Record<string, string>)[value] || value
}

function difficultyLabel(value: string) {
  return ({ easy: '简单', medium: '中等', advanced: '高级' } as Record<string, string>)[value] || value
}

function missingLabel(value: string) {
  return ({
    description: '说明', recommendedFor: '适用场景', notRecommendedFor: '不适用场景', guide: '使用步骤', promptTips: 'Prompt 技巧',
    inputs: '输入定义', 'input-semantics': '输入语义', 'input-mappings': '输入映射', 'parameter-mappings': '参数映射',
    'output-mappings': '输出映射', outputs: '输出定义', dependencies: '依赖', 'runtime-safety': '运行安全',
  } as Record<string, string>)[value] || value
}

watch([category, health, capability, family], () => void loadCards())
watch(q, () => {
  if (searchTimer) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => void loadCards(), 220)
})

onMounted(() => void refreshAll())
</script>

<template>
  <section class="knowledge-shell">
    <div class="knowledge-head">
      <div>
        <span class="eyebrow">WORKFLOW KNOWLEDGE BASE · PHASE 1F</span>
        <h2><BrainCircuit :size="23" /> 工作流知识库</h2>
        <p>把本地 ComfyUI Workflow 从 JSON 文件升级为可理解、可筛选、可推荐、可执行的 Workflow App Package。</p>
      </div>
      <button class="refresh-button" :disabled="loading" @click="refreshAll"><RefreshCcw :size="15" :class="{spin:loading}"/>刷新知识库</button>
    </div>

    <p v-if="error" class="error-banner"><CircleAlert :size="15"/>{{ error }}</p>

    <div v-if="stats" class="stats-row">
      <article><Boxes :size="18"/><div><strong>{{ stats.total }}</strong><span>Workflow Packages</span></div></article>
      <article><BadgeCheck :size="18"/><div><strong>{{ stats.ready }}</strong><span>可直接使用</span></div></article>
      <article><Gauge :size="18"/><div><strong>{{ stats.averageCompleteness }}</strong><span>平均 Manifest 完整度</span></div></article>
      <article><Activity :size="18"/><div><strong>{{ stats.needsAdaptation }}</strong><span>需要继续适配</span></div></article>
    </div>

    <div class="knowledge-toolbar">
      <label class="search-box"><Search :size="16"/><input v-model="q" placeholder="搜索：首帧视频、角色一致性、Wan、TTS、Pose..."/></label>
      <label><Filter :size="14"/><select v-model="category"><option value="">全部分类</option><option v-for="item in stats?.categories||[]" :key="item.key" :value="item.key">{{ item.label }} · {{ item.count }}</option></select></label>
      <label><select v-model="capability"><option value="">全部能力</option><option v-for="item in stats?.capabilities||[]" :key="item.key" :value="item.key">{{ item.key }} · {{ item.count }}</option></select></label>
      <label><select v-model="health"><option value="">全部状态</option><option value="READY">可直接使用</option><option value="NEEDS_ADAPTATION">需要适配</option><option value="MISSING_DEPENDENCIES">缺少依赖</option><option value="UNSUPPORTED">暂不支持</option></select></label>
      <label><select v-model="family"><option value="">全部模型族</option><option v-for="item in stats?.families||[]" :key="item.key" :value="item.key">{{ item.key }} · {{ item.count }}</option></select></label>
      <button class="reset-button" @click="resetFilters">重置</button>
    </div>

    <div class="result-meta"><span>当前结果 <b>{{ filteredCountLabel }}</b></span><span>按推荐分、完整度与名称排序</span></div>

    <div class="workflow-grid">
      <article v-for="card in cards" :key="card.id" class="knowledge-card">
        <div class="card-top">
          <div class="category-mark" :data-group="card.categoryGroup"><Sparkles :size="16"/></div>
          <div class="card-title"><span>{{ card.categoryLabel }}</span><h3>{{ card.name }}</h3></div>
          <b :class="['health-badge',card.health.toLowerCase()]">{{ healthLabel(card.health) }}</b>
        </div>
        <p class="description">{{ card.description || '等待补充工作流说明。' }}</p>
        <div class="score-line"><span>Manifest</span><div><i :style="{width:`${card.completeness.score}%`}"></i></div><b>{{ card.completeness.score }} · {{ card.completeness.grade }}</b></div>
        <div class="chip-row"><span v-for="item in card.families" :key="item" class="family-chip">{{ item }}</span><span v-for="item in card.traits.slice(0,4)" :key="item">{{ item }}</span></div>
        <div class="card-metrics">
          <span><b>{{ card.inputCount }}</b>输入</span><span><b>{{ card.modelCount }}</b>模型</span><span><b>{{ card.customNodeCount }}</b>节点包</span><span><b>{{ card.nodeCount ?? '-' }}</b>节点</span>
        </div>
        <div v-if="card.completeness.missing.length" class="missing-line"><CircleAlert :size="12"/><span>待补：{{ card.completeness.missing.slice(0,4).map(missingLabel).join('、') }}</span></div>
        <div class="recommend-row"><span>推荐分 <b>{{ card.recommendationScore }}</b></span><span v-if="card.runtimeMetrics.runs">历史 {{ card.runtimeMetrics.runs }} 次 · 成功率 {{ card.runtimeMetrics.successRate }}%</span><span v-else>暂无运行历史</span></div>
        <div class="card-actions"><button class="secondary-action" @click="openDetail(card)">知识卡 <ChevronRight :size="13"/></button><button v-if="card.health==='READY'" class="primary-action" @click="useWorkflow(card)"><Play :size="13"/>使用工作流</button><button v-else class="primary-action adapt" @click="openAdapter(card)"><Layers3 :size="13"/>继续适配</button></div>
      </article>
      <div v-if="!loading&&!cards.length" class="empty-state"><Search :size="30"/><strong>没有匹配的工作流</strong><span>调整关键词或筛选条件后再试。</span></div>
    </div>

    <div v-if="detail" class="detail-overlay" @click.self="detail=null">
      <section class="detail-card">
        <div class="detail-head"><div><span class="eyebrow">WORKFLOW KNOWLEDGE CARD</span><h2>{{ detail.name }}</h2><p>{{ detail.description }}</p></div><button @click="detail=null"><X :size="18"/></button></div>
        <div class="detail-badges"><b :class="['health-badge',detail.health.toLowerCase()]">{{ healthLabel(detail.health) }}</b><span>{{ detail.categoryLabel }}</span><span>{{ difficultyLabel(detail.difficulty) }}</span><span>Manifest {{ detail.completeness.score }}/100</span><span>推荐 {{ detail.recommendationScore }}/100</span></div>

        <div class="detail-grid">
          <article><h4>适合</h4><ul><li v-for="item in detail.manifest.recommendedFor" :key="item">{{ item }}</li><li v-if="!detail.manifest.recommendedFor.length">待补充</li></ul></article>
          <article><h4>不适合</h4><ul><li v-for="item in detail.manifest.notRecommendedFor" :key="item">{{ item }}</li><li v-if="!detail.manifest.notRecommendedFor.length">待补充</li></ul></article>
          <article><h4>能力标签</h4><div class="chip-row"><span v-for="item in detail.capabilities" :key="item">{{ item }}</span><span v-for="item in detail.traits" :key="item">{{ item }}</span></div></article>
          <article><h4>运行记录</h4><p>{{ detail.runtimeMetrics.runs }} 次任务 · 成功 {{ detail.runtimeMetrics.succeeded }} · 失败 {{ detail.runtimeMetrics.failed }} · 不确定 {{ detail.runtimeMetrics.uncertain }}</p></article>
        </div>

        <section class="detail-section"><h3>如何使用</h3><p>{{ detail.manifest.guide?.summary || '等待补充使用说明。' }}</p><ol><li v-for="item in detail.manifest.guide?.steps||[]" :key="item">{{ item }}</li></ol></section>
        <section class="detail-section"><h3>输入语义</h3><div class="table-list"><div v-for="item in detail.manifest.inputs" :key="item.key"><b>{{ item.label }}</b><span>{{ item.purpose || item.type }}</span><p>{{ item.description || item.help || '等待补充说明' }}</p><code>{{ item.mapping?.nodeId || '?' }} · {{ item.mapping?.field || '?' }}</code></div><p v-if="!detail.manifest.inputs.length" class="empty-copy">尚未识别出业务输入。</p></div></section>
        <section class="detail-section"><h3>参数</h3><div class="table-list compact"><div v-for="item in detail.manifest.parameters" :key="item.key"><b>{{ item.label }}</b><span>{{ item.type }}</span><p>{{ item.description || `默认值：${String(item.default ?? '-')}` }}</p><code>{{ item.mapping?.nodeId || '?' }} · {{ item.mapping?.field || '?' }}</code></div><p v-if="!detail.manifest.parameters.length" class="empty-copy">没有暴露可调参数。</p></div></section>
        <section class="detail-section two"><article><h3>模型依赖 · {{ detail.manifest.dependencies.models.length }}</h3><p v-for="item in detail.manifest.dependencies.models" :key="item.name">{{ item.name }}</p><p v-if="!detail.manifest.dependencies.models.length" class="empty-copy">未声明模型依赖。</p></article><article><h3>Custom Nodes · {{ detail.manifest.dependencies.customNodes.length }}</h3><p v-for="item in detail.manifest.dependencies.customNodes" :key="item.name">{{ item.name }}</p><p v-if="!detail.manifest.dependencies.customNodes.length" class="empty-copy">未声明 Custom Node。</p></article></section>
        <section v-if="detail.completeness.missing.length" class="detail-section warning"><h3>知识卡还缺什么</h3><div class="chip-row"><span v-for="item in detail.completeness.missing" :key="item">{{ missingLabel(item) }}</span></div></section>

        <div class="detail-actions"><button class="secondary-action" @click="openAdapter(detail)"><Layers3 :size="14"/>打开适配向导</button><button v-if="detail.health==='READY'" class="primary-action" @click="useWorkflow(detail)"><Play :size="14"/>创建任务</button></div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.knowledge-shell{display:grid;gap:16px}.knowledge-head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.knowledge-head h2{margin:5px 0 5px;display:flex;align-items:center;gap:9px;font-size:22px;color:#263960}.knowledge-head p{margin:0;color:#75829d;font-size:12px;line-height:1.65}.eyebrow{font-size:9px;letter-spacing:.12em;color:#7d6bf1;font-weight:800}.refresh-button,.reset-button,.primary-action,.secondary-action{border:0;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px;font-weight:700}.refresh-button{padding:9px 12px;background:#f3f1ff;color:#6754e9}.refresh-button:disabled{opacity:.55}.error-banner{display:flex;align-items:center;gap:7px;background:#fff0f1;color:#b84657;border:1px solid #f4d1d6;padding:10px;border-radius:9px;font-size:11px}.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.stats-row article{display:flex;align-items:center;gap:10px;padding:13px;border:1px solid #e6e9f3;border-radius:11px;background:#fff;color:#7160e9}.stats-row div{display:flex;flex-direction:column}.stats-row strong{color:#253860;font-size:19px}.stats-row span{color:#8b98af;font-size:9px}.knowledge-toolbar{display:grid;grid-template-columns:minmax(280px,1.8fr) repeat(4,minmax(130px,.8fr)) auto;gap:8px;align-items:center;padding:10px;background:#f7f8fc;border:1px solid #e6e9f2;border-radius:11px}.knowledge-toolbar label{display:flex;align-items:center;gap:6px}.knowledge-toolbar input,.knowledge-toolbar select{width:100%;min-width:0;border:1px solid #dde3ef;background:#fff;border-radius:7px;padding:8px 9px;color:#445575;font-size:10px}.search-box{position:relative}.reset-button{padding:8px 10px;background:#fff;border:1px solid #dde3ef;color:#677692}.result-meta{display:flex;justify-content:space-between;color:#8b98af;font-size:9px}.result-meta b{color:#4c5d7d}.workflow-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}.knowledge-card{padding:13px;border:1px solid #e3e7f1;border-radius:12px;background:#fff;box-shadow:0 5px 20px rgba(40,52,83,.035);display:flex;flex-direction:column;min-height:300px}.card-top{display:flex;align-items:flex-start;gap:9px}.category-mark{width:34px;height:34px;border-radius:9px;background:#efedff;color:#6652e8;display:grid;place-items:center;flex:0 0 auto}.category-mark[data-group="video"]{background:#eef4ff;color:#3f6fd1}.category-mark[data-group="audio"]{background:#fff1eb;color:#d07041}.category-mark[data-group="image"]{background:#edf9f4;color:#248461}.card-title{min-width:0;flex:1}.card-title span{font-size:8px;color:#8c98ad}.card-title h3{font-size:12px;color:#293c64;margin:2px 0 0;line-height:1.35}.health-badge{font-size:8px;padding:4px 6px;border-radius:999px;white-space:nowrap;background:#eef1f6;color:#6d7b94}.health-badge.ready{background:#e5f7ee;color:#18825f}.health-badge.needs_adaptation{background:#fff3df;color:#ac6b19}.health-badge.missing_dependencies{background:#fff0f0;color:#b84751}.health-badge.unsupported{background:#edf0f5;color:#79859a}.description{font-size:10px;line-height:1.55;color:#6f7e98;min-height:47px;margin:10px 0}.score-line{display:grid;grid-template-columns:auto 1fr auto;gap:7px;align-items:center;font-size:8px;color:#8a97ad}.score-line>div{height:5px;background:#edf0f6;border-radius:999px;overflow:hidden}.score-line i{display:block;height:100%;background:linear-gradient(90deg,#8772fb,#5e4be4);border-radius:999px}.score-line b{color:#51617d}.chip-row{display:flex;gap:5px;flex-wrap:wrap;margin:10px 0}.chip-row span{font-size:8px;background:#f5f6fa;color:#65748e;padding:4px 6px;border-radius:999px}.chip-row .family-chip{background:#eeeaff;color:#654fe2}.card-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-top:auto;padding-top:8px;border-top:1px solid #edf0f5}.card-metrics span{text-align:center;font-size:7px;color:#93a0b5}.card-metrics b{display:block;color:#4c5e7c;font-size:10px}.missing-line{display:flex;align-items:center;gap:5px;color:#ab6a20;font-size:8px;margin-top:8px}.recommend-row{display:flex;justify-content:space-between;gap:8px;color:#8592a8;font-size:8px;margin:8px 0}.recommend-row b{color:#6754ea}.card-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px}.primary-action,.secondary-action{padding:8px 10px;font-size:9px}.primary-action{background:#6553e8;color:#fff}.primary-action.adapt{background:#786aa7}.secondary-action{background:#f6f7fa;color:#566783;border:1px solid #e2e6ef}.empty-state{grid-column:1/-1;display:flex;flex-direction:column;align-items:center;gap:7px;padding:44px;color:#94a0b4}.empty-state strong{color:#5c6c86}.detail-overlay{position:fixed;inset:0;z-index:90;background:rgba(29,39,61,.45);display:flex;justify-content:flex-end}.detail-card{width:min(760px,92vw);height:100%;overflow:auto;background:#fff;padding:22px;box-shadow:-20px 0 60px rgba(29,39,61,.15)}.detail-head{display:flex;justify-content:space-between;gap:18px}.detail-head h2{margin:4px 0;color:#263a62;font-size:20px}.detail-head p{margin:0;color:#73809a;font-size:11px;line-height:1.6}.detail-head>button{width:32px;height:32px;border:0;border-radius:8px;background:#f3f5f8;color:#6b7990;display:grid;place-items:center;cursor:pointer}.detail-badges{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0}.detail-badges>span{font-size:8px;padding:4px 7px;background:#f4f5f8;color:#68758d;border-radius:999px}.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.detail-grid article,.detail-section{border:1px solid #e5e8f0;border-radius:10px;padding:11px}.detail-grid h4,.detail-section h3{margin:0 0 7px;color:#34496e;font-size:11px}.detail-grid ul,.detail-section ol{margin:0;padding-left:17px}.detail-grid li,.detail-grid p,.detail-section li,.detail-section p{font-size:9px;line-height:1.55;color:#738199}.detail-section{margin-top:9px}.detail-section.two{display:grid;grid-template-columns:1fr 1fr;gap:8px;border:0;padding:0}.detail-section.two article{border:1px solid #e5e8f0;border-radius:10px;padding:11px}.detail-section.warning{background:#fffaf2;border-color:#efdfc3}.table-list{display:grid;gap:6px}.table-list>div{display:grid;grid-template-columns:1fr .8fr 2fr 1fr;gap:8px;align-items:center;padding:7px;background:#f8f9fc;border-radius:7px}.table-list b{font-size:9px;color:#435675}.table-list span,.table-list p,.table-list code{font-size:8px;color:#7d8ba1;margin:0}.table-list code{white-space:nowrap}.empty-copy{color:#9aa5b7!important}.detail-actions{position:sticky;bottom:-22px;margin:14px -22px -22px;padding:12px 22px;background:rgba(255,255,255,.96);border-top:1px solid #e5e8f0;display:flex;justify-content:flex-end;gap:8px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1250px){.workflow-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.knowledge-toolbar{grid-template-columns:1fr 1fr 1fr}.search-box{grid-column:1/-1}.stats-row{grid-template-columns:repeat(2,1fr)}}@media(max-width:820px){.knowledge-head{flex-direction:column}.workflow-grid{grid-template-columns:1fr}.knowledge-toolbar{grid-template-columns:1fr}.search-box{grid-column:auto}.stats-row{grid-template-columns:1fr 1fr}.detail-grid,.detail-section.two{grid-template-columns:1fr}.table-list>div{grid-template-columns:1fr 1fr}.table-list p{grid-column:1/-1}}@media(max-width:520px){.stats-row{grid-template-columns:1fr}.detail-card{width:100vw}.result-meta{flex-direction:column;gap:3px}}
</style>
