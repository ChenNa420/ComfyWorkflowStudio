<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  Activity,
  BookOpen,
  Boxes,
  Film,
  FolderOpen,
  Home,
  Image,
  Layers3,
  ListVideo,
  Play,
  Search,
  Send,
  Settings,
  Sparkles,
  Upload,
  Users,
  WandSparkles,
} from 'lucide-vue-next'
import DynamicTaskForm from './components/DynamicTaskForm.vue'
import ComicStoryPanel from './components/ComicStoryPanel.vue'
import MaterialsGallery from './components/MaterialsGallery.vue'
import OutputGallery from './components/OutputGallery.vue'
import TaskQueuePanel from './components/TaskQueuePanel.vue'
import WorkflowImportPanel from './components/WorkflowImportPanel.vue'

defineProps<{ suppressWorkflowPage?: boolean }>()

type Health = {
  status: string
  phase: string
  workflowPackages: number
  runningTasks?: number
  outputs?: number
  materials?: number
  comfyUi: string
}

type WorkflowSummary = {
  id: string
  name: string
  category: string
  description: string
  difficulty: string
  capabilities: string[]
  inputs: number
  outputs: string[]
  source?: { name?: string }
  format?: string | null
  nodeCount?: number | null
}

type NavItem = { key: string; label: string; icon: typeof Home }

const health = ref<Health | null>(null)
const workflows = ref<WorkflowSummary[]>([])
const activePage = ref(location.hash.replace('#/', '') || 'dashboard')
const searchText = ref('')
const selectedWorkflow = ref<WorkflowSummary | null>(null)
const selectedAnalysis = ref<Record<string, any> | null>(null)
const error = ref('')
const comicEpisode = ref<Record<string, any> | null>(null)

const kidsNav: NavItem[] = [
  { key: 'dashboard', label: '首页', icon: Home },
  { key: 'story', label: '故事创作', icon: BookOpen },
  { key: 'comic-story', label: '漫画转故事', icon: Sparkles },
  { key: 'characters', label: '角色管理', icon: Users },
  { key: 'storyboard', label: '分镜设计', icon: Film },
  { key: 'workbench', label: '成片工作台', icon: Play },
  { key: 'kids-works', label: '作品库', icon: Image },
  { key: 'publish', label: '发布管理', icon: Send },
]

const comfyNav: NavItem[] = [
  { key: 'workflows', label: '工作流库', icon: Boxes },
  { key: 'import', label: '导入工作流', icon: Upload },
  { key: 'adapter', label: '工作流适配', icon: WandSparkles },
  { key: 'create-task', label: '生产运行', icon: Play },
  { key: 'queue', label: '任务队列', icon: Activity },
  { key: 'records', label: '生成记录', icon: ListVideo },
  { key: 'works', label: '作品库', icon: Image },
  { key: 'materials', label: '素材管理', icon: FolderOpen },
  { key: 'dependencies', label: '模型与节点', icon: Layers3 },
]

const systemNav: NavItem[] = [{ key: 'settings', label: '系统设置', icon: Settings }]

const titles: Record<string, [string, string]> = {
  dashboard: ['首页', '故事创作与 ComfyUI 工作流执行的统一入口。'],
  story: ['故事创作', '生成 Episode、角色、教学目标与 6 个 Shot。'],
  'comic-story': ['漫画转故事', '扫描本地漫画，解析页面并生成 Episode / Shot 结构草稿。'],
  characters: ['角色管理', '角色参考图、角色锁和 Canonical Character Lock。'],
  storyboard: ['分镜设计', '管理对白、Prompt、首帧与镜头连续性。'],
  workbench: ['成片工作台', '故事 → 首帧 → 视频 → 字幕配音 → 成片输出。'],
  'kids-works': ['童语作品库', '童语工坊剧集、镜头和最终成片。'],
  publish: ['发布管理', '生成抖音、视频号、B站、TikTok、YouTube 发布素材包。'],
  workflows: ['工作流库', '浏览、搜索并选择本地 ComfyUI Workflow Package。'],
  'workflow-detail': ['工作流详情', '查看输入、参数、使用说明、依赖与技术映射。'],
  import: ['导入工作流', '批量扫描 JSON / ZIP，自动分类、去重并生成 Manifest。'],
  adapter: ['工作流适配', '确认首帧、尾帧、角色参考、Pose、Depth 等输入语义。'],
  'create-task': ['Production Run', '使用通过认证的 Workflow 创建、跟踪和复用生产任务。'],
  queue: ['任务队列', '实时查看等待、执行、成功、失败和需要确认的任务。'],
  records: ['生成记录', '追溯任务、Prompt、Workflow 和输出。'],
  works: ['作品库', '管理由 ComfyWorkflowStudio 生成的图片、视频与音频。'],
  materials: ['素材管理', '角色图、场景图、首帧、Pose、Depth、Mask 与音频。'],
  dependencies: ['模型与节点', '检查工作流要求与当前 ComfyUI 节点环境。'],
  settings: ['系统设置', 'ComfyUI 地址、存储目录与安全执行策略。'],
}

const currentTitle = computed(() => titles[activePage.value] || ['ComfyWorkflowStudio', ''])
const filteredWorkflows = computed(() => {
  const key = searchText.value.trim().toLowerCase()
  if (!key) return workflows.value
  return workflows.value.filter((item) => `${item.name} ${item.category} ${item.description}`.toLowerCase().includes(key))
})

const shots = [
  ['01', '早餐怪兽', 'Benny arranges the pancake.', '7 秒', 'MiniMax H3', '已完成'],
  ['02', '两只眼睛摆好了', 'Two blueberries for eyes!', '7 秒', 'MiniMax H3', '已完成'],
  ['03', '蓝莓滚走了', 'Oh no! One eye is rolling!', '8 秒', 'Wan 2.2', '已完成'],
  ['04', '小猫帮忙找', "Let's find it!", '8 秒', 'MiniMax H3', '生成中'],
  ['05', '找到大葡萄', 'A big grape?', '7 秒', 'MiniMax H3', '待生成'],
  ['06', '三只眼早餐怪兽', 'Yay! Three eyes!', '8 秒', 'MiniMax H3', '待生成'],
]
const displayShots = computed(() => {
  if (!comicEpisode.value?.shots?.length) return shots
  return comicEpisode.value.shots.map((shot: any, index: number) => [
    String(shot.id ?? index + 1).padStart(2, '0'), shot.title || `镜头 ${index + 1}`,
    shot.english || shot.chinese || '等待 AI Provider 补充对白', `${shot.duration || 5} 秒`, '待选择', '待完善',
  ])
})
const displayCharacters = computed(() => {
  if (!comicEpisode.value) return ['Benny · 小熊', 'Mimi · 小猫', '新角色']
  return (comicEpisode.value.characterDefinitions || []).map((role: any) => role.name || role.id)
})

function navigate(key: string) {
  activePage.value = key
  location.hash = `#/${key}`
}

function onHashChange() {
  activePage.value = location.hash.replace('#/', '') || 'dashboard'
  try { comicEpisode.value = JSON.parse(sessionStorage.getItem('cws-comic-story-episode') || 'null') } catch { comicEpisode.value = null }
}

async function loadData() {
  try {
    const [healthResponse, workflowResponse] = await Promise.all([fetch('/api/health'), fetch('/api/workflows')])
    if (!healthResponse.ok) throw new Error(`Health HTTP ${healthResponse.status}`)
    health.value = await healthResponse.json()
    workflows.value = workflowResponse.ok ? await workflowResponse.json() : []
    error.value = ''
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法连接本地 API'
  }
}

async function openWorkflow(item: WorkflowSummary) {
  selectedWorkflow.value = item
  selectedAnalysis.value = null
  const response = await fetch(`/api/workflows/${encodeURIComponent(item.id)}/analysis`)
  if (response.ok) selectedAnalysis.value = await response.json()
  navigate('workflow-detail')
}

function useWorkflow(item: WorkflowSummary) {
  sessionStorage.setItem('cws-selected-workflow', item.id)
  selectedWorkflow.value = item
  navigate('create-task')
}

function onCatalogUpdated() { loadData() }

onMounted(() => {
  window.addEventListener('hashchange', onHashChange)
  window.addEventListener('workflow-catalog-updated', onCatalogUpdated)
  loadData()
  onHashChange()
})

onUnmounted(() => {
  window.removeEventListener('hashchange', onHashChange)
  window.removeEventListener('workflow-catalog-updated', onCatalogUpdated)
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark"><Sparkles :size="22" /></div><div><strong>童语工坊</strong><span>AI Animation Studio</span></div></div>
      <div class="nav-group"><p>童语工坊</p><button v-for="item in kidsNav" :key="item.key" :class="['nav-item',{active:activePage===item.key}]" @click="navigate(item.key)"><component :is="item.icon" :size="17"/><span>{{ item.label }}</span></button></div>
      <div class="nav-divider"></div>
      <div class="nav-group"><p>Comfy 工作流</p><button v-for="item in comfyNav" :key="item.key" :class="['nav-item',{active:activePage===item.key}]" @click="navigate(item.key)"><component :is="item.icon" :size="17"/><span>{{ item.label }}</span></button></div>
      <div class="nav-divider"></div>
      <div class="nav-group system-group"><p>系统管理</p><button v-for="item in systemNav" :key="item.key" :class="['nav-item',{active:activePage===item.key}]" @click="navigate(item.key)"><component :is="item.icon" :size="17"/><span>{{ item.label }}</span></button></div>
      <div class="sidebar-footer"><span class="dot" :class="health?.status==='ok'?'ok':''"></span><div><strong>Local Studio</strong><small>{{ health?.status==='ok'?'API 已连接':'等待连接' }}</small></div></div>
    </aside>

    <main class="content">
      <header class="topbar"><div><p class="eyebrow">COMFY WORKFLOW STUDIO</p><h1>{{ currentTitle[0] }}</h1><span>{{ currentTitle[1] }}</span></div><div class="top-actions"><div class="top-search"><Search :size="15"/><input placeholder="搜索工作流、模型、作品..."/></div><div class="status-pill"><span class="dot" :class="health?.comfyUi==='connected'?'ok':''"></span>Phase {{ health?.phase || '1D' }}</div></div></header>

      <template v-if="activePage==='dashboard'">
        <section class="hero panel compact-hero"><div><span class="badge">Kids English Animation + Comfy Workflow Center</span><h2>从故事到成片，再到任意 ComfyUI 工作流。</h2><p>童语工坊负责故事、角色、分镜与成片；Comfy 工作流中心负责 Workflow Knowledge Base、生成任务、依赖和作品。</p><div class="hero-actions"><button class="primary" @click="navigate('workbench')">继续制作 EP003</button><button class="secondary" @click="navigate('workflows')">浏览工作流</button></div></div><div class="hero-card"><span>当前工作流库</span><strong>{{ health?.workflowPackages ?? 0 }}</strong><small>Workflow Packages</small><div class="mini-row"><span>FastAPI</span><b>8100</b></div><div class="mini-row"><span>Vue/Vite</span><b>5174</b></div><div class="mini-row"><span>ComfyUI</span><b>{{ health?.comfyUi || '检测中' }}</b></div></div></section>
        <section class="stats-grid"><article class="stat-card"><span>工作流</span><strong>{{ health?.workflowPackages ?? 0 }}</strong><small>本地 Package</small></article><article class="stat-card"><span>运行任务</span><strong>{{ health?.runningTasks ?? 0 }}</strong><small>串行安全队列</small></article><article class="stat-card"><span>作品</span><strong>{{ health?.outputs ?? 0 }}</strong><small>图片 / 视频 / 音频</small></article><article class="stat-card"><span>素材</span><strong>{{ health?.materials ?? 0 }}</strong><small>本地素材库</small></article></section>
        <section class="workspace-grid"><article class="panel section-card"><div class="section-head"><div><span class="eyebrow">CURRENT EPISODE</span><h3>EP003 · 三眼早餐怪兽</h3></div><button class="text-button" @click="navigate('workbench')">进入成片工作台</button></div><div class="progress-lines"><div><span>故事创作</span><b>100%</b></div><div><span>分镜设计</span><b>100%</b></div><div><span>首帧生成</span><b>100%</b></div><div><span>视频生成</span><b>50%</b></div><div><span>字幕配音</span><b>0%</b></div></div></article><article class="panel section-card"><div class="section-head"><div><span class="eyebrow">RUNTIME</span><h3>执行安全</h3></div></div><div class="status-list"><div><span>原始 Workflow</span><b class="green">只读</b></div><div><span>Runtime Clone</span><b class="green">开启</b></div><div><span>并发</span><b>1 · 串行</b></div><div><span>UNKNOWN 自动重试</span><b class="red">禁止</b></div></div></article></section>
      </template>

      <template v-else-if="activePage==='story'">
        <section class="two-column"><article class="panel form-panel"><span class="eyebrow">STORY BRIEF</span><h3>故事设定</h3><div class="form-grid"><label>故事主题<input value="早餐怪兽少了一只眼睛"/></label><label>年龄段<select><option>3–6 岁</option></select></label><label>英语等级<select><option>Pre-A1</option></select></label><label>目标时长<input value="45 秒"/></label><label>镜头数量<input value="6"/></label><label>画幅<select><option>16:9</option><option>9:16</option></select></label></div><label>必学单词<textarea>blueberry, grape, pancake, eye</textarea></label><label>必学句型<textarea>Let's… / I found it! / Three eyes!</textarea></label><button class="primary wide">使用童语工坊 GPT 创作</button></article><article class="panel section-card"><span class="eyebrow">EPISODE OUTPUT</span><h3>标准 Episode JSON</h3><div class="summary-block"><b>角色</b><p>Benny · bear / Mimi · cat</p></div><div class="summary-block"><b>镜头</b><p>6 个 Shot，每个镜头包含双语对白、imagePrompt、videoPrompt 和 negativePrompt。</p></div><div class="summary-block"><b>规则</b><p>Shot.english 是实际视频对白与英文字幕唯一真源。</p></div></article></section>
      </template>

      <template v-else-if="activePage==='comic-story'"><ComicStoryPanel @navigate="navigate"/></template>

      <template v-else-if="activePage==='characters'">
        <section v-if="comicEpisode" class="notice"><b>已载入漫画 Episode：{{ comicEpisode.title }}</b> · {{ comicEpisode.characters?.length || 0 }} 个已识别角色；待 AI Provider 补充的角色不会伪造。</section>
        <section v-if="comicEpisode && !displayCharacters.length" class="panel empty-page"><Users :size="34"/><p>当前漫画 Episode 尚无已确认角色。AI Provider 未启用时不会用示例角色填充。</p></section>
        <section v-else class="card-grid three"><article v-for="role in displayCharacters" :key="role" class="panel media-card"><div class="placeholder-art character"><Users :size="38"/></div><h3>{{ role }}</h3><p>{{ role==='新角色'?'创建角色定义、参考图和角色锁。':'Canonical Character Lock 已启用，保持脸型、毛色、体型、服装和配饰一致。' }}</p><div class="tag-row"><span>角色锁</span><span>参考图</span><span>Prompt</span></div><button class="secondary wide">{{ role==='新角色'?'创建角色':'编辑角色' }}</button></article></section>
      </template>

      <template v-else-if="activePage==='storyboard'">
        <section v-if="comicEpisode" class="notice"><b>漫画分镜已载入：</b>{{ comicEpisode.shots?.length || 0 }} Shots · {{ comicEpisode.aspectRatio }} · 来源页 {{ comicEpisode.source?.pages?.join(', ') }}</section>
        <section class="panel table-panel"><div class="section-head"><div><span class="eyebrow">{{ comicEpisode?.title || 'EP003' }}</span><h3>分镜与连续性</h3></div><div class="tag-row"><span>角色一致性 ✓</span><span>对白一致性 ✓</span><span>道具连续性 ⚠</span></div></div><div class="shot-list"><div v-for="shot in displayShots" :key="shot[0]" class="shot-row"><b>{{ shot[0] }}</b><div class="thumb"><Image :size="18"/></div><div class="shot-copy"><strong>{{ shot[1] }}</strong><small>{{ shot[2] }}</small></div><span>{{ shot[3] }}</span><span class="status-chip neutral">首帧已就绪</span><button class="secondary">编辑 Shot</button></div></div></section>
      </template>

      <template v-else-if="activePage==='workbench'">
        <section v-if="comicEpisode" class="notice"><b>当前生产来源：</b>{{ comicEpisode.title }} · {{ comicEpisode.shots?.length || 0 }} Shots。空对白和 Prompt 将保持待补充状态。</section>
        <section class="production-steps panel"><div v-for="(step,index) in ['故事创作','分镜设计','首帧生成','视频生成','字幕配音','成片输出']" :key="step" :class="['step',{active:index===3,done:index<3}]"><span>{{ index+1 }}</span><div><b>{{ step }}</b><small>{{ index<3?'已完成':index===3?'ComfyUI 生成':'待处理' }}</small></div></div></section>
        <section class="workbench-grid"><div class="workbench-main"><section class="project-row"><article class="panel project-card"><span class="eyebrow">当前项目</span><h3>{{ comicEpisode?.title || 'EP003 · 三眼早餐怪兽' }}</h3><div class="tag-row"><span>3–6 岁</span><span>Pre-A1</span><span>6 镜头</span><span>45 秒</span><span>16:9</span></div><p>当前视频阶段默认使用 MiniMax H3，Shot 可以单独覆盖工作流。</p></article><article class="panel progress-card"><div class="ring">50%</div><div><b>3 / 6 完成</b><small>视频生成阶段</small></div></article></section><section class="panel table-panel"><div class="tabs"><button class="active">镜头列表</button><button>批量生成</button><button>ComfyUI 配置</button><button>字幕与配音</button><button>成片预览</button></div><div class="shot-table"><div class="shot-table-head"><span>#</span><span>画面</span><span>镜头描述</span><span>时长</span><span>Workflow</span><span>状态</span><span>操作</span></div><div v-for="shot in displayShots" :key="shot[0]" class="shot-table-row"><b>{{ shot[0] }}</b><div class="thumb"><Image :size="17"/></div><div class="shot-copy"><strong>{{ shot[1] }}</strong><small>{{ shot[2] }}</small></div><span>{{ shot[3] }}</span><span>{{ shot[4] }}</span><span :class="['status-chip',shot[5]==='已完成'?'success':shot[5]==='生成中'?'running':'neutral']">{{ shot[5] }}</span><button class="secondary">{{ shot[5]==='待生成'?'生成':'查看' }}</button></div></div><div class="table-actions"><button class="secondary">重新生成选中</button><button class="secondary">从当前开始批量生成</button><button class="primary">开始整集生成</button></div></section></div><aside class="workbench-side"><section class="panel section-card"><div class="section-head"><h3>工作流选择</h3><button class="text-button" @click="navigate('workflows')">打开工作流库</button></div><div class="workflow-selected"><div class="workflow-cover"><Film :size="28"/></div><div><b>MiniMax H3 · 首帧转视频</b><p>剧集默认 · Shot04 可单独覆盖</p><div class="tag-row"><span>首帧</span><span>Prompt</span><span>5–10 秒</span></div></div></div><button class="primary wide" @click="navigate('create-task')">打开动态任务表单</button></section><section class="panel section-card"><h3>三级工作流选择</h3><div class="status-list"><div><span>系统默认</span><b>MiniMax H3</b></div><div><span>EP003 默认</span><b>MiniMax H3</b></div><div><span>Shot03 覆盖</span><b>Wan 2.2</b></div><div><span>优先级</span><b>SHOT &gt; EPISODE &gt; SYSTEM</b></div></div></section><section class="panel section-card"><h3>连续性</h3><label class="check-line"><input type="checkbox"/> 使用上一镜头最后一帧</label><div class="notice">成功镜头默认不自动重新生成；UNKNOWN 状态禁止自动重提。</div></section></aside></section>
      </template>

      <template v-else-if="activePage==='kids-works' || activePage==='works'"><OutputGallery/></template>

      <template v-else-if="activePage==='publish'">
        <section class="two-column"><article class="panel section-card"><span class="eyebrow">PUBLISH PACKAGE</span><h3>EP003 发布素材包</h3><div class="status-list"><div><span>最终视频</span><b class="green">待成片输出</b></div><div><span>封面</span><b>自动选择</b></div><div><span>标题 / 简介</span><b>自动生成</b></div><div><span>学习单词 / 句型</span><b>来自 Episode</b></div></div><button class="primary wide">生成发布包</button></article><article class="panel section-card"><h3>平台模板</h3><div class="platform-list"><button>抖音 <span>9:16 · 中文</span></button><button>视频号 <span>9:16 · 中文</span></button><button>Bilibili <span>16:9 · 双语</span></button><button>YouTube Shorts <span>9:16 · English</span></button><button>TikTok <span>9:16 · English</span></button></div></article></section>
      </template>

      <template v-else-if="activePage==='workflows' && suppressWorkflowPage"></template>
      <template v-else-if="activePage==='workflows'">
        <section class="toolbar panel"><div class="filter-row"><button class="active">全部</button><button>图片生成</button><button>图生视频</button><button>首尾帧</button><button>ControlNet</button><button>TTS</button><button>音频</button><button>3D</button></div><div class="toolbar-right"><div class="top-search"><Search :size="15"/><input v-model="searchText" placeholder="搜索工作流..."/></div><button class="primary" @click="navigate('import')"><Upload :size="15"/> 导入工作流</button></div></section><div v-if="!filteredWorkflows.length" class="panel empty-page"><Boxes :size="34"/><p>工作流库为空。导入“学习工作流.zip”后，系统会建立本地 Workflow Catalog。</p><button class="primary" @click="navigate('import')">开始导入</button></div><section v-else class="card-grid four"><article v-for="item in filteredWorkflows" :key="item.id" class="panel workflow-card"><div class="workflow-cover"><Boxes :size="34"/></div><div class="workflow-card-title"><span class="badge">{{ item.category }}</span><h3>{{ item.name }}</h3></div><p>{{ item.description }}</p><div class="meta-grid"><span>格式 <b>{{ item.format || 'package' }}</b></span><span>节点 <b>{{ item.nodeCount ?? '-' }}</b></span><span>输入 <b>{{ item.inputs }}</b></span><span>输出 <b>{{ item.outputs.join(', ') }}</b></span></div><div class="button-row"><button class="primary" @click="useWorkflow(item)">使用工作流</button><button class="secondary" @click="openWorkflow(item)">详情</button></div></article></section>
      </template>

      <template v-else-if="activePage==='workflow-detail'">
        <section class="detail-hero panel"><div class="workflow-cover large"><Boxes :size="42"/></div><div><span class="badge">{{ selectedWorkflow?.category || 'workflow' }}</span><h2>{{ selectedWorkflow?.name || '请选择工作流' }}</h2><p>{{ selectedWorkflow?.description }}</p><div class="tag-row"><span>{{ selectedWorkflow?.format || 'Package' }}</span><span>{{ selectedWorkflow?.nodeCount ?? '-' }} nodes</span><span>{{ selectedWorkflow?.source?.name || 'Local' }}</span></div></div><button v-if="selectedWorkflow" class="primary" @click="useWorkflow(selectedWorkflow)">使用这个工作流</button></section><section class="detail-grid"><article class="panel section-card span-2"><div class="tabs"><button class="active">概览</button><button>如何使用</button><button>参数说明</button><button>技术信息</button></div><h3>自动分析</h3><div class="scan-summary compact"><div><span>格式</span><b>{{ selectedAnalysis?.format || '-' }}</b></div><div><span>节点</span><b>{{ selectedAnalysis?.nodeCount ?? '-' }}</b></div><div><span>输入</span><b>{{ selectedAnalysis?.inputs?.length ?? '-' }}</b></div><div><span>模型</span><b>{{ selectedAnalysis?.dependencies?.models?.length ?? '-' }}</b></div></div><h3>输入说明</h3><div v-for="item in selectedAnalysis?.inputs || []" :key="item.key" class="input-guide"><b>{{ item.label }} · {{ item.purpose || '待确认' }}</b><p>{{ item.description }} · Node {{ item.mapping?.nodeId }}</p></div></article><article class="panel section-card"><h3>后续操作</h3><button class="secondary wide" @click="navigate('adapter')">打开适配向导</button><button v-if="selectedWorkflow" class="primary wide" @click="useWorkflow(selectedWorkflow)">创建任务</button><div class="notice">自动识别只是初稿；低置信度输入必须人工确认后再批量生产。</div></article></section>
      </template>

      <template v-else-if="activePage==='import'">
        <section class="import-grid"><article class="panel import-zone"><Upload :size="52"/><h2>导入 ComfyUI 工作流</h2><p>支持单个 JSON、多个 JSON 和 ZIP。UI Workflow（nodes + links）与 API Workflow 都会自动识别。</p><WorkflowImportPanel/><small>第三方 Workflow Package 保存在 storage/workflow-packages，不进入 Git。</small></article><article class="panel section-card"><span class="eyebrow">SCAN PIPELINE</span><h3>自动处理流程</h3><div class="roadmap"><div class="roadmap-item done"><span>1</span><div><strong>识别格式</strong><small>UI / API / Resource JSON</small></div></div><div class="roadmap-item done"><span>2</span><div><strong>分析节点</strong><small>图片输入、Prompt、输出、模型、Custom Nodes</small></div></div><div class="roadmap-item done"><span>3</span><div><strong>Hash 去重</strong><small>重复工作流不会再次保存</small></div></div><div class="roadmap-item done"><span>4</span><div><strong>生成 Manifest</strong><small>进入适配向导继续确认输入语义</small></div></div></div></article></section>
      </template>

      <template v-else-if="activePage==='adapter'">
        <section class="adapter-layout"><article class="panel section-card"><span class="eyebrow">ADAPTER WIZARD</span><h3>输入用途确认</h3><p>选择工作流详情后进入本页，可以根据自动分析结果确认 Node 的业务语义。第一版已经提供 Manifest PUT API；UI 编辑器下一阶段继续增强。</p><div v-if="selectedAnalysis?.inputs?.length"><div v-for="item in selectedAnalysis.inputs" :key="item.key" class="adapter-node"><div><b>Node {{ item.mapping?.nodeId }} · {{ item.nodeType }}</b><small>{{ item.nodeTitle || item.description }}</small></div><select><option :selected="item.purpose==='video-start-frame'">首帧</option><option>尾帧</option><option>角色参考图</option><option>场景参考图</option><option>Pose</option><option>Depth</option><option>Mask</option><option>其他</option></select><span :class="['confidence',(item.analysisConfidence||0)>.85?'high':(item.analysisConfidence||0)>.6?'medium':'low']">{{ Math.round((item.analysisConfidence||0)*100) }}%</span></div></div><div v-else class="notice">请先从“工作流库 → 详情”选择一个已导入工作流。</div></article><aside class="panel section-card"><h3>Manifest</h3><div class="status-list"><div><span>原始 Workflow</span><b class="green">只读</b></div><div><span>输入映射</span><b>可编辑</b></div><div><span>运行策略</span><b>串行</b></div><div><span>UNKNOWN 自动重试</span><b class="red">禁止</b></div></div></aside></section>
      </template>

      <template v-else-if="activePage==='create-task'"><section class="task-layout"><article class="panel form-panel"><DynamicTaskForm/></article><aside class="panel section-card"><h3>执行链</h3><div class="roadmap"><div class="roadmap-item done"><span>1</span><div><strong>读取 Manifest</strong><small>动态生成输入和参数</small></div></div><div class="roadmap-item done"><span>2</span><div><strong>Runtime Clone</strong><small>不修改原始 JSON</small></div></div><div class="roadmap-item done"><span>3</span><div><strong>UI → API Prompt</strong><small>根据 ComfyUI /object_info 转换</small></div></div><div class="roadmap-item done"><span>4</span><div><strong>/prompt → /history</strong><small>完成后自动回收输出</small></div></div></div></aside></section></template>

      <template v-else-if="activePage==='queue' || activePage==='records'"><TaskQueuePanel/></template>
      <template v-else-if="activePage==='materials'"><MaterialsGallery/></template>

      <template v-else-if="activePage==='dependencies'">
        <section class="two-column"><article class="panel section-card"><h3>依赖检查策略</h3><p>系统从 Workflow JSON 中提取模型文件与 Custom Node 包，并使用 ComfyUI `/object_info` 检查节点类型是否存在。</p><div class="status-list"><div><span>ComfyUI</span><b :class="health?.comfyUi==='connected'?'green':'red'">{{ health?.comfyUi }}</b></div><div><span>节点检查</span><b>已接入</b></div><div><span>模型提取</span><b>已接入</b></div></div></article><article class="panel section-card"><h3>当前工作流</h3><p>从工作流详情页选择 Workflow 后，可以查看缺失节点和依赖。模型物理文件的全目录扫描仍以本地 ComfyUI 为准。</p><button class="primary wide" @click="navigate('workflows')">选择工作流</button></article></section>
      </template>

      <template v-else-if="activePage==='settings'">
        <section class="settings-layout"><aside class="panel settings-menu"><button class="active">ComfyUI</button><button>存储</button><button>任务策略</button><button>工作流</button><button>高级</button></aside><article class="panel form-panel"><h3>ComfyUI 连接</h3><label>地址<input value="http://127.0.0.1:8188"/></label><div class="connection-card"><span class="dot" :class="health?.comfyUi==='connected'?'ok':''"></span><div><b>{{ health?.comfyUi==='connected'?'当前可连接':'当前不可连接' }}</b><small>默认从 COMFYUI_URL 读取，未配置时使用 127.0.0.1:8188。</small></div></div><h3>安全执行策略</h3><div class="form-grid"><label>最大并发<select><option>1 · 串行</option></select></label><label>输出超时<input value="900 秒"/></label></div><label class="check-line disabled"><input type="checkbox" disabled/> UNKNOWN 自动重试（强制禁止）</label><div class="notice">发生提交后网络异常时，如果无法确定 ComfyUI 是否已接收任务，状态标记为 UNKNOWN / NEEDS_REVIEW，不会自动重复提交。</div></article></section>
      </template>

      <p v-else class="panel empty-page">页面正在接入真实数据。</p>
      <p v-if="error" class="error">本地 API：{{ error }}</p>
    </main>
  </div>
</template>
