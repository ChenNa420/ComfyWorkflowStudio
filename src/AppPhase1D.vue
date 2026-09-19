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
const comicFrameUrls = ref<Record<string, string>>({})
const editingShotIndex = ref<number | null>(null)
const shotDraft = ref<Record<string, any> | null>(null)
const shotEditorMode = ref<'edit' | 'view'>('edit')
const shotEditorError = ref('')
const workbenchFilter = ref<'all' | 'pending' | 'running' | 'completed' | 'failed'>('all')
const workbenchSelected = ref<number[]>([])
const workbenchCurrentIndex = ref(0)
const workbenchDefaultWorkflow = ref('MiniMax H3')
const workbenchResolution = ref('1080 × 1920 (9:16)')
const workbenchDurationMode = ref('按分镜时长')
const workbenchSeed = ref('')
const workbenchUsePreviousFrame = ref(false)
const workbenchShotWorkflows = ref<Record<string, string>>({})
const workbenchHelpOpen = ref(false)

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
    comicFrameUrls.value[String(shot.shotId ?? '')] || String(shot.frameUrl || ''),
  ])
})
const displayCharacters = computed(() => {
  if (!comicEpisode.value) return ['Benny · 小熊', 'Mimi · 小猫', '新角色']
  return (comicEpisode.value.characterDefinitions || []).map((role: any) => role.name || role.id)
})

type WorkbenchShotStatus = 'pending' | 'running' | 'completed' | 'failed'

const workbenchShots = computed(() => {
  const source = comicEpisode.value?.shots || []
  return source.map((shot: any, index: number) => {
    const shotId = String(shot.shotId ?? shot.id ?? index + 1)
    const raw = String(shot.videoStatus || shot.renderStatus || shot.video?.status || '').toLowerCase()
    let status: WorkbenchShotStatus = 'pending'
    if (['running','generating','queued','processing'].includes(raw)) status = 'running'
    else if (['completed','complete','done','success','succeeded'].includes(raw) || shot.videoUrl || shot.video?.url) status = 'completed'
    else if (['failed','error'].includes(raw)) status = 'failed'
    const workflow = workbenchShotWorkflows.value[shotId] || String(shot.workflow || shot.workflowName || workbenchDefaultWorkflow.value)
    return {
      index,
      shotId,
      id: String(index + 1).padStart(2, '0'),
      title: shot.title || `镜头 ${index + 1}`,
      english: shot.english || '',
      chinese: shot.chinese || '',
      duration: Number(shot.duration || 5),
      workflow,
      status,
      frameUrl: comicFrameUrls.value[shotId] || String(shot.frameUrl || ''),
      videoUrl: String(shot.videoUrl || shot.video?.url || ''),
      videoPoster: String(shot.videoPoster || shot.video?.poster || ''),
      generatedAt: String(shot.generatedAt || shot.video?.generatedAt || ''),
    }
  })
})

const workbenchStatusCounts = computed(() => ({
  all: workbenchShots.value.length,
  pending: workbenchShots.value.filter(item => item.status === 'pending').length,
  running: workbenchShots.value.filter(item => item.status === 'running').length,
  completed: workbenchShots.value.filter(item => item.status === 'completed').length,
  failed: workbenchShots.value.filter(item => item.status === 'failed').length,
}))

const filteredWorkbenchShots = computed(() => workbenchFilter.value === 'all'
  ? workbenchShots.value
  : workbenchShots.value.filter(item => item.status === workbenchFilter.value))

const currentWorkbenchShot = computed(() => workbenchShots.value[workbenchCurrentIndex.value] || workbenchShots.value[0] || null)
const workbenchCompletedCount = computed(() => workbenchStatusCounts.value.completed)
const workbenchProgress = computed(() => workbenchShots.value.length
  ? Math.round((workbenchCompletedCount.value / workbenchShots.value.length) * 100)
  : 0)
const workbenchSelectedVisibleAll = computed(() => {
  const visible = filteredWorkbenchShots.value.map(item => item.index)
  return visible.length > 0 && visible.every(index => workbenchSelected.value.includes(index))
})

function setWorkbenchCurrent(index: number) {
  if (index < 0 || index >= workbenchShots.value.length) return
  workbenchCurrentIndex.value = index
}

function toggleWorkbenchShot(index: number, checked: boolean) {
  const next = new Set(workbenchSelected.value)
  if (checked) next.add(index)
  else next.delete(index)
  workbenchSelected.value = [...next].sort((a, b) => a - b)
}

function toggleWorkbenchVisible(checked: boolean) {
  const next = new Set(workbenchSelected.value)
  for (const item of filteredWorkbenchShots.value) {
    if (checked) next.add(item.index)
    else next.delete(item.index)
  }
  workbenchSelected.value = [...next].sort((a, b) => a - b)
}

function setWorkbenchWorkflow(shotId: string, value: string) {
  workbenchShotWorkflows.value = {...workbenchShotWorkflows.value, [shotId]: value}
}

function workbenchStatusLabel(status: WorkbenchShotStatus) {
  if (status === 'completed') return '已完成'
  if (status === 'running') return '生成中'
  if (status === 'failed') return '失败'
  return '待生成'
}

function queueWorkbenchGeneration(indices: number[], mode: string, replace = false) {
  const unique = [...new Set(indices)].filter(index => index >= 0 && index < workbenchShots.value.length)
  if (!unique.length) {
    error.value = '请先选择至少一个镜头。'
    return
  }
  const request = {
    episodeTitle: comicEpisode.value?.title || '',
    directorTaskId: comicEpisode.value?.directorTaskId || localStorage.getItem('cws-gpt-director-last-task-id') || '',
    mode,
    replace,
    workflow: workbenchDefaultWorkflow.value,
    resolution: workbenchResolution.value,
    durationMode: workbenchDurationMode.value,
    seed: workbenchSeed.value.trim() || null,
    usePreviousLastFrame: workbenchUsePreviousFrame.value,
    shots: unique.map(index => {
      const shot = comicEpisode.value?.shots?.[index] || {}
      const wb = workbenchShots.value[index]
      return {
        index,
        shotId: wb?.shotId || String(shot.shotId || ''),
        workflow: wb?.workflow || workbenchDefaultWorkflow.value,
        frameUrl: wb?.frameUrl || '',
        videoPrompt: shot.videoPrompt || '',
        negativePrompt: shot.negativePrompt || '',
        duration: Number(shot.duration || 5),
      }
    }),
  }
  sessionStorage.setItem('cws-workbench-generation-request', JSON.stringify(request))
  sessionStorage.setItem('cws-workbench-return-page', 'workbench')
  error.value = ''
  navigate('create-task')
}

function regenerateSelectedWorkbench() {
  queueWorkbenchGeneration(workbenchSelected.value, 'regenerate-selected', true)
}

function generateFromCurrentWorkbench() {
  queueWorkbenchGeneration(
    workbenchShots.value.map(item => item.index).filter(index => index >= workbenchCurrentIndex.value),
    'from-current',
    false,
  )
}

function generateWholeWorkbench() {
  queueWorkbenchGeneration(workbenchShots.value.map(item => item.index), 'whole-episode', false)
}

function generateSingleWorkbench(index: number) {
  setWorkbenchCurrent(index)
  queueWorkbenchGeneration([index], 'single-shot', false)
}

function openShotEditor(index: number, mode: 'edit' | 'view' = 'edit') {
  const shot = comicEpisode.value?.shots?.[index]
  if (!shot) {
    error.value = '当前镜头没有可用的漫画 Episode 数据。'
    return
  }
  editingShotIndex.value = index
  shotEditorMode.value = mode
  shotEditorError.value = ''
  shotDraft.value = JSON.parse(JSON.stringify(shot))
}

function closeShotEditor() {
  editingShotIndex.value = null
  shotDraft.value = null
  shotEditorMode.value = 'edit'
  shotEditorError.value = ''
}

function saveShotEditor() {
  if (editingShotIndex.value === null || !shotDraft.value || !comicEpisode.value?.shots?.length) return
  const duration = Number(shotDraft.value.duration)
  if (!Number.isFinite(duration) || duration <= 0 || duration > 10) {
    shotEditorError.value = '镜头时长必须大于 0 且不超过 10 秒。'
    return
  }
  if (!String(shotDraft.value.imagePrompt || '').trim()) {
    shotEditorError.value = 'Image Prompt 不能为空。'
    return
  }
  if (!String(shotDraft.value.videoPrompt || '').trim()) {
    shotEditorError.value = 'Video Prompt 不能为空。'
    return
  }
  const shots = [...comicEpisode.value.shots]
  shots[editingShotIndex.value] = {
    ...shots[editingShotIndex.value],
    ...shotDraft.value,
    duration,
  }
  comicEpisode.value = {...comicEpisode.value, shots}
  sessionStorage.setItem('cws-comic-story-episode', JSON.stringify(comicEpisode.value))
  closeShotEditor()
}

function navigate(key: string) {
  activePage.value = key
  location.hash = `#/${key}`
}

async function loadComicFrameUrls() {
  const taskId = String(
    comicEpisode.value?.directorTaskId
    || localStorage.getItem('cws-gpt-director-last-task-id')
    || '',
  ).trim()
  if (!/^gdt-[a-f0-9]{32}$/.test(taskId)) {
    comicFrameUrls.value = {}
    return
  }
  try {
    const response = await fetch(`/api/gpt-image/tasks/${encodeURIComponent(taskId)}/frames`)
    if (!response.ok) throw new Error(`Frame HTTP ${response.status}`)
    const payload = await response.json()
    const next: Record<string, string> = {}
    for (const frame of payload.frames || []) {
      if (frame?.status !== 'IMPORTED' || !frame?.url) continue
      const version = String(frame.sha256 || frame.generatedAt || '1').slice(0, 12)
      next[String(frame.shotId)] = `${frame.url}?v=${encodeURIComponent(version)}`
    }
    comicFrameUrls.value = next
  } catch {
    comicFrameUrls.value = {}
  }
}

function onHashChange() {
  activePage.value = location.hash.replace('#/', '') || 'dashboard'
  try { comicEpisode.value = JSON.parse(sessionStorage.getItem('cws-comic-story-episode') || 'null') } catch { comicEpisode.value = null }
  void loadComicFrameUrls()
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
      <header v-if="activePage!=='workbench'" class="topbar"><div><p class="eyebrow">COMFY WORKFLOW STUDIO</p><h1>{{ currentTitle[0] }}</h1><span>{{ currentTitle[1] }}</span></div><div class="top-actions"><div class="top-search"><Search :size="15"/><input placeholder="搜索工作流、模型、作品..."/></div><div class="status-pill"><span class="dot" :class="health?.comfyUi==='connected'?'ok':''"></span>Phase {{ health?.phase || '1D' }}</div></div></header>
      <header v-else class="wb-header">
        <div>
          <div class="wb-breadcrumbs"><span>首页</span><i>›</i><span>项目</span><i>›</i><span>{{ comicEpisode?.title || '当前项目' }}</span><i>›</i><b>成片工作台</b></div>
          <h1>成片工作台</h1>
          <p>将分镜生成完整动画视频，支持单镜头、批量和整集生成。</p>
        </div>
        <div class="wb-header-actions">
          <button class="secondary" @click="navigate('settings')"><Settings :size="15"/>项目设置</button>
          <button class="secondary" @click="workbenchHelpOpen=!workbenchHelpOpen">使用帮助</button>
          <button class="primary" @click="navigate('publish')"><Upload :size="15"/>导出成片</button>
        </div>
        <div v-if="workbenchHelpOpen" class="wb-help-popover">
          <b>成片工作台</b>
          <p>先选择镜头与工作流，再通过单镜头、批量或整集入口创建生产任务。关键帧和 Video Prompt 会一起带入动态任务表单。</p>
        </div>
      </header>

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
        <section class="panel table-panel"><div class="section-head"><div><span class="eyebrow">{{ comicEpisode?.title || 'EP003' }}</span><h3>分镜与连续性</h3></div><div class="tag-row"><span>角色一致性 ✓</span><span>对白一致性 ✓</span><span>道具连续性 ⚠</span></div></div><div class="shot-list"><div v-for="(shot,index) in displayShots" :key="shot[0]" class="shot-row"><b>{{ shot[0] }}</b><div class="thumb"><img v-if="shot[6]" :src="shot[6]" :alt="`Shot ${shot[0]} 关键帧`"/><Image v-else :size="18"/></div><div class="shot-copy"><strong>{{ shot[1] }}</strong><small>{{ shot[2] }}</small></div><span>{{ shot[3] }}</span><span class="status-chip neutral">首帧已就绪</span><button class="secondary" @click="openShotEditor(index)">编辑 Shot</button></div></div></section>
      </template>

      <template v-else-if="activePage==='workbench'">
        <section class="wb-steps panel">
          <div v-for="(step,index) in ['故事创作','分镜设计','首帧生成','视频生成','字幕配音','成片输出']" :key="step" :class="['wb-step',{active:index===3,done:index<3}]">
            <span>{{ index<3?'✓':index+1 }}</span>
            <div><b>{{ step }}</b><small>{{ index<3?'已完成':index===3?'进行中':'待处理' }}</small></div>
            <i v-if="index<5">→</i>
          </div>
        </section>

        <section class="wb-layout">
          <div class="wb-main">
            <section class="panel wb-project-card">
              <div class="wb-project-cover">
                <img v-if="workbenchShots[0]?.frameUrl" :src="workbenchShots[0].frameUrl" alt="项目关键帧"/>
                <Image v-else :size="36"/>
              </div>
              <div class="wb-project-copy">
                <span class="eyebrow">当前项目</span>
                <h2>{{ comicEpisode?.title || '当前漫画项目' }}</h2>
                <div class="wb-meta">
                  <span>{{ comicEpisode?.audience || '3–6 岁' }}</span>
                  <span>{{ comicEpisode?.level || 'Pre-A1' }}</span>
                  <span>{{ workbenchShots.length }} 镜头</span>
                  <span>{{ comicEpisode?.duration || workbenchShots.reduce((sum,item)=>sum+item.duration,0) }} 秒</span>
                  <span>{{ comicEpisode?.aspectRatio || '9:16' }}</span>
                  <em>漫画改编</em>
                </div>
                <p>{{ comicEpisode?.story || '当前视频阶段使用已确认关键帧与 Video Prompt，Shot 可以单独覆盖工作流。' }}</p>
              </div>
              <div class="wb-project-progress">
                <div class="wb-ring" :style="{'--progress':workbenchProgress+'%'}"><b>{{ workbenchProgress }}%</b></div>
                <div><strong>{{ workbenchCompletedCount }} / {{ workbenchShots.length }} 完成</strong><small>视频生成阶段</small></div>
              </div>
            </section>

            <section class="panel wb-shot-card">
              <div class="wb-shot-toolbar">
                <div>
                  <h3>镜头列表 ({{ workbenchShots.length }})</h3>
                  <div class="wb-filter-tabs">
                    <button :class="{active:workbenchFilter==='all'}" @click="workbenchFilter='all'">全部 {{ workbenchStatusCounts.all }}</button>
                    <button :class="{active:workbenchFilter==='pending'}" @click="workbenchFilter='pending'">待生成 {{ workbenchStatusCounts.pending }}</button>
                    <button :class="{active:workbenchFilter==='running'}" @click="workbenchFilter='running'">生成中 {{ workbenchStatusCounts.running }}</button>
                    <button :class="{active:workbenchFilter==='completed'}" @click="workbenchFilter='completed'">已完成 {{ workbenchStatusCounts.completed }}</button>
                    <button :class="{active:workbenchFilter==='failed'}" @click="workbenchFilter='failed'">失败 {{ workbenchStatusCounts.failed }}</button>
                  </div>
                </div>
                <button class="secondary small">镜头顺序⌄</button>
              </div>

              <div class="wb-shot-table">
                <div class="wb-shot-head">
                  <label><input type="checkbox" :checked="workbenchSelectedVisibleAll" @change="toggleWorkbenchVisible(($event.target as HTMLInputElement).checked)"/></label>
                  <span>#</span><span>画面</span><span>镜头信息</span><span>时长</span><span>工作流</span><span>状态</span><span>生成结果</span><span>操作</span>
                </div>
                <div v-for="item in filteredWorkbenchShots" :key="item.shotId" :class="['wb-shot-row',{current:item.index===workbenchCurrentIndex}]" @click="setWorkbenchCurrent(item.index)">
                  <label @click.stop><input type="checkbox" :checked="workbenchSelected.includes(item.index)" @change="toggleWorkbenchShot(item.index,($event.target as HTMLInputElement).checked)"/></label>
                  <b>{{ item.id }}</b>
                  <div class="wb-shot-thumb"><img v-if="item.frameUrl" :src="item.frameUrl" :alt="`Shot ${item.id}`"/><Image v-else :size="18"/></div>
                  <div class="wb-shot-copy">
                    <strong>{{ item.title }}</strong>
                    <small>{{ item.english || item.chinese || '无对白' }}</small>
                    <button @click.stop="openShotEditor(item.index,'edit')">编辑 Prompt ↗</button>
                  </div>
                  <span>{{ item.duration }} 秒</span>
                  <select :value="item.workflow" @click.stop @change="setWorkbenchWorkflow(item.shotId,($event.target as HTMLSelectElement).value)">
                    <option>MiniMax H3</option><option>Wan 2.2</option><option>Anime V1</option>
                  </select>
                  <div :class="['wb-render-status',item.status]"><i></i><span>{{ workbenchStatusLabel(item.status) }}</span></div>
                  <div class="wb-result-cell">
                    <template v-if="item.status==='completed'">
                      <div class="wb-video-thumb"><img :src="item.videoPoster||item.frameUrl"/><span>▶</span></div>
                    </template>
                    <template v-else>—</template>
                  </div>
                  <div class="wb-row-actions">
                    <button v-if="item.status==='pending'||item.status==='failed'" class="wb-generate-btn" @click.stop="generateSingleWorkbench(item.index)">立即生成</button>
                    <button class="secondary small" @click.stop="openShotEditor(item.index,'view')">查看</button>
                    <button class="wb-more" @click.stop>•••</button>
                  </div>
                </div>
              </div>

              <div class="wb-batch-bar">
                <div><input type="checkbox" :checked="workbenchSelected.length>0"/><b>已选择 {{ workbenchSelected.length }} 个镜头</b></div>
                <div>
                  <button class="secondary" :disabled="!workbenchSelected.length" @click="regenerateSelectedWorkbench">↻ 重新生成选中</button>
                  <button class="secondary" :disabled="!workbenchShots.length" @click="generateFromCurrentWorkbench">▶ 从当前开始批量生成</button>
                  <button class="primary" :disabled="!workbenchShots.length" @click="generateWholeWorkbench">✦ 开始整集生成</button>
                  <button class="secondary" disabled>停止生成</button>
                </div>
              </div>
            </section>
          </div>

          <aside class="wb-side">
            <section class="panel wb-side-card wb-preview-card">
              <h3>当前镜头预览</h3>
              <div class="wb-current-preview">
                <img v-if="currentWorkbenchShot?.frameUrl" :src="currentWorkbenchShot.frameUrl" alt="当前镜头关键帧"/>
                <Image v-else :size="36"/>
              </div>
              <b>{{ currentWorkbenchShot?.id }}. {{ currentWorkbenchShot?.title || '请选择镜头' }}</b>
              <small>{{ currentWorkbenchShot?.english || currentWorkbenchShot?.chinese || '—' }}</small>
            </section>

            <section class="panel wb-side-card wb-settings-card">
              <h3>生成设置</h3>
              <label>视频工作流<select v-model="workbenchDefaultWorkflow"><option>MiniMax H3</option><option>Wan 2.2</option><option>Anime V1</option></select></label>
              <label>分辨率<select v-model="workbenchResolution"><option>1080 × 1920 (9:16)</option><option>1920 × 1080 (16:9)</option><option>720 × 1280 (9:16)</option></select></label>
              <label>生成时长<select v-model="workbenchDurationMode"><option>按分镜时长</option><option>统一 5 秒</option><option>统一 10 秒</option></select></label>
              <label>随机种子（可选）<input v-model="workbenchSeed" placeholder="不填则随机"/></label>
              <details><summary>高级参数⌄</summary><p>高级参数将在动态任务表单中继续配置。</p></details>
            </section>

            <section class="panel wb-side-card wb-progress-card">
              <div class="wb-progress-head"><h3>生成进度</h3><b>{{ workbenchProgress }}%</b></div>
              <div class="wb-progress-line"><i :style="{width:workbenchProgress+'%'}"></i></div>
              <div class="wb-progress-list">
                <div v-for="item in workbenchShots" :key="item.shotId">
                  <span :class="['wb-progress-dot',item.status]">{{ item.status==='completed'?'✓':item.status==='running'?'•':'+' }}</span>
                  <p>镜头 {{ item.id }} {{ workbenchStatusLabel(item.status) }}</p>
                  <small>{{ item.generatedAt ? item.generatedAt.slice(11,16) : item.status==='completed'?'完成':'—' }}</small>
                </div>
              </div>
            </section>

            <section class="panel wb-side-card wb-continuity-card">
              <h3>连续性</h3>
              <label><input v-model="workbenchUsePreviousFrame" type="checkbox"/> 使用上一镜头最后一帧</label>
              <p>成功镜头默认不自动重新生成；UNKNOWN 状态禁止自动重提。</p>
            </section>
          </aside>
        </section>
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

      <div v-if="shotDraft && editingShotIndex !== null" class="shot-editor-overlay" @click.self="closeShotEditor">
        <section class="shot-editor-panel" role="dialog" aria-modal="true" :aria-label="shotEditorMode==='view'?'查看 Shot':'编辑 Shot'">
          <header class="shot-editor-head">
            <div>
              <span class="eyebrow">{{ shotEditorMode==='view'?'SHOT DETAIL':'SHOT EDITOR' }}</span>
              <h3>{{ shotEditorMode==='view'?'查看':'编辑' }} Shot {{ String((editingShotIndex ?? 0) + 1).padStart(2, '0') }}</h3>
              <p v-if="shotEditorMode==='view'">查看当前关键帧、对白和 Prompt；需要修改时可切换到编辑模式。</p>
              <p v-else>修改会同步到当前漫画 Episode，并用于后续成片工作台；已生成关键帧不会自动重生。</p>
            </div>
            <button class="secondary small" @click="closeShotEditor">关闭</button>
          </header>

          <div class="shot-editor-body">
            <aside class="shot-editor-preview">
              <div class="shot-editor-frame">
                <img v-if="comicFrameUrls[String(shotDraft.shotId || '')]" :src="comicFrameUrls[String(shotDraft.shotId || '')]" alt="当前关键帧"/>
                <Image v-else :size="30"/>
              </div>
              <small>当前关键帧预览</small>
            </aside>

            <div class="shot-editor-form">
              <div class="shot-editor-grid">
                <label>标题<input v-model="shotDraft.title" :disabled="shotEditorMode==='view'"/></label>
                <label>时长（秒）<input v-model.number="shotDraft.duration" type="number" min="0.1" max="10" step="0.5" :disabled="shotEditorMode==='view'"/></label>
                <label>说话人<input v-model="shotDraft.speaker" placeholder="无对白可留空" :disabled="shotEditorMode==='view'"/></label>
                <label>Shot ID<input :value="shotDraft.shotId" disabled/></label>
              </div>
              <label>英文对白<textarea v-model="shotDraft.english" rows="2" :disabled="shotEditorMode==='view'"></textarea></label>
              <label>中文对白<textarea v-model="shotDraft.chinese" rows="2" :disabled="shotEditorMode==='view'"></textarea></label>
              <label>关键帧描述<textarea v-model="shotDraft.keyframeDescription" rows="3" :disabled="shotEditorMode==='view'"></textarea></label>
              <label>Image Prompt<textarea v-model="shotDraft.imagePrompt" rows="6" :disabled="shotEditorMode==='view'"></textarea></label>
              <label>Video Prompt<textarea v-model="shotDraft.videoPrompt" rows="6" :disabled="shotEditorMode==='view'"></textarea></label>
              <label>Negative Prompt<textarea v-model="shotDraft.negativePrompt" rows="3" :disabled="shotEditorMode==='view'"></textarea></label>
              <p v-if="shotEditorError" class="shot-editor-error">{{ shotEditorError }}</p>
            </div>
          </div>

          <footer class="shot-editor-actions">
            <button class="secondary" @click="closeShotEditor">{{ shotEditorMode==='view'?'关闭':'取消' }}</button>
            <button v-if="shotEditorMode==='view'" class="primary" @click="shotEditorMode='edit'">编辑此 Shot</button>
            <button v-else class="primary" @click="saveShotEditor">保存 Shot</button>
          </footer>
        </section>
      </div>

      <p v-if="error" class="error">本地 API：{{ error }}</p>
    </main>
  </div>
</template>
