<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  Activity,
  BookOpen,
  Boxes,
  Captions,
  CircleCheck,
  Film,
  FolderOpen,
  Gauge,
  Home,
  Image,
  Layers3,
  ListVideo,
  Mic2,
  Play,
  Search,
  Send,
  Settings,
  Sparkles,
  Upload,
  Users,
  WandSparkles,
} from 'lucide-vue-next'

type Health = {
  status: string
  service: string
  phase: string
  workflowPackages: number
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
}

type NavItem = {
  key: string
  label: string
  icon: typeof Home
}

const health = ref<Health | null>(null)
const workflows = ref<WorkflowSummary[]>([])
const error = ref('')
const searchText = ref('')
const activePage = ref(location.hash.replace('#/', '') || 'dashboard')
const selectedWorkflow = ref<WorkflowSummary | null>(null)

const kidsNav: NavItem[] = [
  { key: 'dashboard', label: '首页', icon: Home },
  { key: 'story', label: '故事创作', icon: BookOpen },
  { key: 'characters', label: '角色管理', icon: Users },
  { key: 'storyboard', label: '分镜设计', icon: Film },
  { key: 'workbench', label: '成片工作台', icon: Play },
  { key: 'kids-works', label: '作品库', icon: Image },
  { key: 'publish', label: '发布管理', icon: Send },
]

const comfyNav: NavItem[] = [
  { key: 'workflows', label: '工作流库', icon: Boxes },
  { key: 'import', label: '导入工作流', icon: Upload },
  { key: 'create-task', label: '创建任务', icon: WandSparkles },
  { key: 'queue', label: '任务队列', icon: Activity },
  { key: 'records', label: '生成记录', icon: ListVideo },
  { key: 'works', label: '作品库', icon: Image },
  { key: 'materials', label: '素材管理', icon: FolderOpen },
  { key: 'dependencies', label: '模型与节点', icon: Layers3 },
]

const systemNav: NavItem[] = [{ key: 'settings', label: '系统设置', icon: Settings }]

const pageTitles: Record<string, [string, string]> = {
  dashboard: ['首页', '从故事创作到工作流执行，统一查看当前生产状态。'],
  story: ['故事创作', '生成 Episode、教学目标、角色和 Shot 的创作入口。'],
  characters: ['角色管理', '维护角色参考图、Canonical Character Lock 和角色 Prompt。'],
  storyboard: ['分镜设计', '管理 Shot、对白、首帧 Prompt、视频 Prompt 与连续性。'],
  workbench: ['成片工作台', '把故事、首帧、视频、字幕配音和最终成片串成一条生产线。'],
  'kids-works': ['童语作品库', '按剧集、Shot 和成片维度管理童语工坊产物。'],
  publish: ['发布管理', '生成适配不同平台的视频发布素材包。'],
  workflows: ['工作流库', '按能力、输入类型和可运行状态浏览所有 ComfyUI 工作流。'],
  'workflow-detail': ['工作流详情', '查看用途、输入说明、参数、依赖、示例和技术映射。'],
  import: ['导入工作流', '支持 JSON、多个 JSON 与 ZIP 批量导入。'],
  adapter: ['工作流适配向导', '把节点输入翻译成首帧、尾帧、角色参考等业务语义。'],
  'create-task': ['创建任务', '根据 Workflow Manifest 动态生成任务表单。'],
  queue: ['任务队列', '查看等待、运行、失败、需要确认和已完成任务。'],
  records: ['生成记录', '按工作流、项目、时间追溯所有历史生成。'],
  works: ['作品库', '统一管理图片、视频、音频和最终输出。'],
  materials: ['素材管理', '管理角色、场景、首帧、Pose、Depth、Mask 和音频素材。'],
  dependencies: ['模型与节点', '同时检查本机已有依赖和工作流需要的依赖。'],
  settings: ['系统设置', '配置 ComfyUI、存储目录、执行策略和高级选项。'],
}

const currentTitle = computed(() => pageTitles[activePage.value] || ['Comfy Workflow Studio', ''])
const filteredWorkflows = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) return workflows.value
  return workflows.value.filter((item) => `${item.name} ${item.category} ${item.description}`.toLowerCase().includes(keyword))
})

function navigate(key: string) {
  activePage.value = key
  location.hash = `#/${key}`
}

function openWorkflow(item: WorkflowSummary) {
  selectedWorkflow.value = item
  navigate('workflow-detail')
}

function onHashChange() {
  activePage.value = location.hash.replace('#/', '') || 'dashboard'
}

async function loadData() {
  try {
    const [healthResponse, workflowResponse] = await Promise.all([fetch('/api/health'), fetch('/api/workflows')])
    if (!healthResponse.ok) throw new Error(`Health HTTP ${healthResponse.status}`)
    health.value = await healthResponse.json()
    if (workflowResponse.ok) workflows.value = await workflowResponse.json()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法连接本地 API'
  }
}

onMounted(() => {
  window.addEventListener('hashchange', onHashChange)
  loadData()
})

onUnmounted(() => window.removeEventListener('hashchange', onHashChange))

const shots = [
  ['01', '早餐怪兽', 'Benny arranges the pancake.', '7 秒', 'MiniMax H3', '已完成'],
  ['02', '两只眼睛摆好了', 'Two blueberries for eyes!', '7 秒', 'MiniMax H3', '已完成'],
  ['03', '蓝莓滚走了', 'Oh no! One eye is rolling!', '8 秒', 'Wan 2.2', '已完成'],
  ['04', '小猫帮忙找', "Let's find it!", '8 秒', 'MiniMax H3', '生成中'],
  ['05', '找到大葡萄', 'A big grape?', '7 秒', 'MiniMax H3', '待生成'],
  ['06', '三只眼早餐怪兽', 'Yay! Three eyes!', '8 秒', 'MiniMax H3', '待生成'],
]

const demoWorkflows = computed(() => {
  if (filteredWorkflows.value.length) return filteredWorkflows.value
  return [
    {
      id: 'minimax-h3-ff',
      name: 'MiniMax H3 · 首帧转视频',
      category: 'image-to-video',
      description: '一张首帧生成短视频，适合儿童动画、动物和人物微动作。',
      difficulty: 'easy',
      capabilities: ['image-to-video'],
      inputs: 2,
      outputs: ['video'],
      source: { name: 'Pixaroma' },
    },
    {
      id: 'wan22-i2v',
      name: 'Wan 2.2 · 图生视频',
      category: 'image-to-video',
      description: '适合镜头运动、人物动作和场景动态。',
      difficulty: 'medium',
      capabilities: ['image-to-video'],
      inputs: 2,
      outputs: ['video'],
      source: { name: 'Local' },
    },
    {
      id: 'h3-fflf',
      name: 'MiniMax H3 · 首尾帧视频',
      category: 'first-last-video',
      description: '使用首帧和尾帧控制镜头起止状态。',
      difficulty: 'medium',
      capabilities: ['first-last-video'],
      inputs: 3,
      outputs: ['video'],
      source: { name: 'Pixaroma' },
    },
  ] satisfies WorkflowSummary[]
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><Sparkles :size="22" /></div>
        <div><strong>童语工坊</strong><span>AI Animation Studio</span></div>
      </div>

      <div class="nav-group">
        <p>童语工坊</p>
        <button v-for="item in kidsNav" :key="item.key" :class="['nav-item', { active: activePage === item.key }]" @click="navigate(item.key)">
          <component :is="item.icon" :size="17" /><span>{{ item.label }}</span>
        </button>
      </div>

      <div class="nav-divider"></div>
      <div class="nav-group">
        <p>Comfy 工作流</p>
        <button v-for="item in comfyNav" :key="item.key" :class="['nav-item', { active: activePage === item.key }]" @click="navigate(item.key)">
          <component :is="item.icon" :size="17" /><span>{{ item.label }}</span>
        </button>
      </div>

      <div class="nav-divider"></div>
      <div class="nav-group system-group">
        <p>系统管理</p>
        <button v-for="item in systemNav" :key="item.key" :class="['nav-item', { active: activePage === item.key }]" @click="navigate(item.key)">
          <component :is="item.icon" :size="17" /><span>{{ item.label }}</span>
        </button>
      </div>

      <div class="sidebar-footer">
        <span class="dot" :class="health?.status === 'ok' ? 'ok' : ''"></span>
        <div><strong>Local Studio</strong><small>{{ health?.status === 'ok' ? 'API 已连接' : '等待连接' }}</small></div>
      </div>
    </aside>

    <main class="content">
      <header class="topbar">
        <div><p class="eyebrow">COMFY WORKFLOW STUDIO</p><h1>{{ currentTitle[0] }}</h1><span>{{ currentTitle[1] }}</span></div>
        <div class="top-actions"><div class="top-search"><Search :size="15" /><input placeholder="搜索工作流、模型、作品..." /></div><div class="status-pill"><span class="dot ok"></span>Phase {{ health?.phase || '1B' }}</div></div>
      </header>

      <template v-if="activePage === 'dashboard'">
        <section class="hero panel compact-hero">
          <div>
            <span class="badge">Kids English Animation + Comfy Workflow Center</span>
            <h2>从故事到成片，再到任意 ComfyUI 工作流。</h2>
            <p>童语工坊负责故事、角色、分镜与成片；Comfy 工作流中心负责工作流知识库、生成任务、依赖和作品管理。</p>
            <div class="hero-actions"><button class="primary" @click="navigate('workbench')">继续制作 EP003</button><button class="secondary" @click="navigate('workflows')">浏览工作流</button></div>
          </div>
          <div class="hero-card"><span>当前工作流库</span><strong>{{ health?.workflowPackages ?? workflows.length }}</strong><small>Workflow Packages</small><div class="mini-row"><span>FastAPI</span><b>8100</b></div><div class="mini-row"><span>Vue/Vite</span><b>5174</b></div><div class="mini-row"><span>ComfyUI</span><b>{{ health?.comfyUi === 'not-configured' ? '待配置' : health?.comfyUi || '检测中' }}</b></div></div>
        </section>
        <section class="stats-grid"><article class="stat-card"><span>当前剧集</span><strong>EP003</strong><small>三眼早餐怪兽</small></article><article class="stat-card"><span>镜头进度</span><strong>3/6</strong><small>视频已完成</small></article><article class="stat-card"><span>运行任务</span><strong>1</strong><small>ComfyUI 队列</small></article><article class="stat-card"><span>作品</span><strong>12</strong><small>最近生成结果</small></article></section>
        <section class="workspace-grid"><article class="panel section-card"><div class="section-head"><div><span class="eyebrow">CURRENT EPISODE</span><h3>EP003 · 三眼早餐怪兽</h3></div><button class="text-button" @click="navigate('workbench')">进入成片工作台</button></div><div class="progress-lines"><div><span>故事创作</span><b>100%</b></div><div><span>分镜设计</span><b>100%</b></div><div><span>首帧生成</span><b>100%</b></div><div><span>视频生成</span><b>50%</b></div><div><span>字幕配音</span><b>0%</b></div></div></article><article class="panel section-card"><div class="section-head"><div><span class="eyebrow">ENVIRONMENT</span><h3>AI 环境</h3></div></div><div class="status-list"><div><span>ComfyUI</span><b class="green">● 可连接</b></div><div><span>工作流包</span><b>{{ health?.workflowPackages ?? 0 }}</b></div><div><span>执行模式</span><b>串行</b></div><div><span>UNKNOWN 自动重试</span><b class="red">禁止</b></div></div></article></section>
      </template>

      <template v-else-if="activePage === 'story'">
        <section class="two-column"><article class="panel form-panel"><div class="section-head"><div><span class="eyebrow">STORY BRIEF</span><h3>故事设定</h3></div></div><div class="form-grid"><label>故事主题<input value="早餐怪兽少了一只眼睛" /></label><label>年龄段<select><option>3–6 岁</option></select></label><label>英语等级<select><option>Pre-A1</option></select></label><label>目标时长<input value="45 秒" /></label><label>镜头数量<input value="6" /></label><label>画幅<select><option>16:9</option><option>9:16</option></select></label></div><label>必学单词<textarea>blueberry, grape, pancake, eye</textarea></label><label>必学句型<textarea>Let's… / I found it! / Three eyes!</textarea></label><button class="primary wide">使用童语工坊 GPT 创作</button></article><article class="panel section-card"><span class="eyebrow">OUTPUT</span><h3>Episode 生成结果</h3><div class="summary-block"><b>角色</b><p>Benny · bear / Mimi · cat</p></div><div class="summary-block"><b>结构</b><p>6 Shots · 每镜头独立对白、imagePrompt、videoPrompt、negativePrompt。</p></div><div class="summary-block"><b>导入方式</b><p>通过童语工坊创作桥检测并导入合法 Episode JSON。</p></div><button class="secondary wide">查看 Episode JSON</button></article></section>
      </template>

      <template v-else-if="activePage === 'characters'">
        <section class="card-grid three"><article v-for="role in ['Benny · 小熊','Mimi · 小猫','新角色']" :key="role" class="panel media-card"><div class="placeholder-art character"><Users :size="38" /></div><h3>{{ role }}</h3><p>{{ role === '新角色' ? '创建新的角色定义与参考图。' : '角色锁定已启用 · 毛色、脸型、服装、配饰保持一致。' }}</p><div class="tag-row"><span>Canonical Lock</span><span>Reference</span></div><button class="secondary wide">{{ role === '新角色' ? '创建角色' : '编辑角色' }}</button></article></section>
      </template>

      <template v-else-if="activePage === 'storyboard'">
        <section class="panel table-panel"><div class="section-head"><div><span class="eyebrow">EP003</span><h3>6 个 Shot</h3></div><div class="tag-row"><span>角色一致性 ✓</span><span>对白一致性 ✓</span><span>道具连续性 ⚠</span></div></div><div class="shot-list"><div v-for="shot in shots" :key="shot[0]" class="shot-row"><b>{{ shot[0] }}</b><div class="thumb"><Image :size="18" /></div><div class="shot-copy"><strong>{{ shot[1] }}</strong><small>{{ shot[2] }}</small></div><span>{{ shot[3] }}</span><span class="status-chip neutral">首帧已就绪</span><button class="secondary">编辑 Shot</button></div></div></section>
      </template>

      <template v-else-if="activePage === 'workbench'">
        <section class="production-steps panel"><div v-for="(step, index) in ['故事创作','分镜设计','首帧生成','视频生成','字幕配音','成片输出']" :key="step" :class="['step', { active: index === 3, done: index < 3 }]"><span>{{ index + 1 }}</span><div><b>{{ step }}</b><small>{{ index < 3 ? '已完成' : index === 3 ? 'ComfyUI 批量生成' : '待处理' }}</small></div></div></section>
        <section class="workbench-grid"><div class="workbench-main"><section class="project-row"><article class="panel project-card"><span class="eyebrow">当前项目</span><h3>EP003 · 三眼早餐怪兽</h3><div class="tag-row"><span>3–6 岁</span><span>Pre-A1</span><span>6 镜头</span><span>45 秒</span><span>16:9</span></div><p>小熊和小猫一起制作早餐怪兽，一颗蓝莓眼睛滚走了……</p></article><article class="panel progress-card"><div class="ring">50%</div><div><b>3 / 6 完成</b><small>当前视频生成阶段</small></div></article></section>
          <section class="panel table-panel"><div class="tabs"><button class="active">镜头列表</button><button>批量生成</button><button>ComfyUI 配置</button><button>字幕与配音</button><button>成片预览</button></div><div class="shot-table"><div class="shot-table-head"><span>#</span><span>画面</span><span>镜头描述</span><span>时长</span><span>Workflow</span><span>状态</span><span>操作</span></div><div v-for="shot in shots" :key="shot[0]" class="shot-table-row"><b>{{ shot[0] }}</b><div class="thumb"><Image :size="17" /></div><div class="shot-copy"><strong>{{ shot[1] }}</strong><small>{{ shot[2] }}</small></div><span>{{ shot[3] }}</span><span>{{ shot[4] }}</span><span :class="['status-chip', shot[5] === '已完成' ? 'success' : shot[5] === '生成中' ? 'running' : 'neutral']">{{ shot[5] }}</span><button class="secondary">{{ shot[5] === '待生成' ? '生成' : '查看' }}</button></div></div><div class="table-actions"><button class="secondary">重新生成选中</button><button class="secondary">从当前开始批量生成</button><button class="primary">开始整集生成</button></div></section></div>
          <aside class="workbench-side"><section class="panel section-card"><div class="section-head"><h3>工作流选择</h3><button class="text-button" @click="navigate('workflows')">打开工作流库</button></div><div class="workflow-selected"><div class="workflow-cover"><Film :size="28" /></div><div><b>MiniMax H3 · 首帧转视频</b><p>首帧 + Prompt · 推荐 5–10 秒</p><div class="tag-row"><span>视频</span><span>官方推荐</span><span>适合动画</span></div></div></div><div class="button-row"><button class="primary">更换工作流</button><button class="secondary" @click="navigate('workflow-detail')">查看详情</button></div></section><section class="panel section-card"><div class="section-head"><h3>输入与参数设置</h3><span class="badge">当前镜头 04</span></div><label>当前镜头首帧<div class="upload-mini"><Image :size="24" /><span>EP003-S04-first.png</span></div></label><label>视频提示词<textarea>The cat looks around the table and floor, searching for the blueberry. She looks curious and a little worried.</textarea></label><label>负面提示词<textarea>character drift, duplicated props, text, watermark</textarea></label><div class="form-grid"><label>视频时长<select><option>8 秒</option></select></label><label>FPS<select><option>24</option></select></label><label>分辨率<select><option>16:9 (1536 × 864)</option></select></label><label>Seed<input value="-1" /></label></div><label class="check-line"><input type="checkbox" /> 使用上一镜头结果作为当前输入</label></section><section class="panel section-card"><div class="tabs"><button class="active">实时预览</button><button>生成日志</button></div><div class="preview-box"><Film :size="42" /><b>Shot04 正在生成</b><div class="progress-bar"><i style="width:68%"></i></div><div class="status-list"><div><span>任务 ID</span><b>#1025</b></div><div><span>当前节点</span><b>Video Generation</b></div><div><span>进度</span><b>68%</b></div><div><span>已用时间</span><b>00:01:32</b></div></div><button class="danger wide">停止生成</button></div></section></aside></section>
      </template>

      <template v-else-if="activePage === 'kids-works' || activePage === 'works'">
        <section class="toolbar panel"><div class="tabs"><button class="active">全部</button><button>图片</button><button>视频</button><button>音频</button><button>最终成片</button></div><div class="top-search"><Search :size="15" /><input placeholder="搜索作品..." /></div></section><section class="card-grid four"><article v-for="index in 8" :key="index" class="panel work-card"><div class="placeholder-art"><Film v-if="index % 2" :size="34" /><Image v-else :size="34" /></div><div class="work-meta"><b>{{ index % 2 ? `EP003 · Shot0${(index % 6) + 1}` : `角色参考图 ${index}` }}</b><small>{{ index % 2 ? 'MiniMax H3 · 8 秒' : 'Flux · 1536×864' }}</small></div><div class="tag-row"><span>查看参数</span><span>再次生成</span></div></article></section>
      </template>

      <template v-else-if="activePage === 'publish'">
        <section class="two-column"><article class="panel section-card"><span class="eyebrow">PUBLISH PACKAGE</span><h3>EP003 发布素材包</h3><div class="status-list"><div><span>最终视频</span><b class="green">已就绪</b></div><div><span>封面</span><b class="green">已就绪</b></div><div><span>中文标题</span><b>已生成</b></div><div><span>英文标题</span><b>已生成</b></div><div><span>标签</span><b>12</b></div></div><button class="primary wide">生成最新发布包</button></article><article class="panel section-card"><h3>平台模板</h3><div class="platform-list"><button>抖音 <span>9:16 · 中文简介</span></button><button>视频号 <span>9:16 · 中文简介</span></button><button>Bilibili <span>16:9 · 双语简介</span></button><button>YouTube Shorts <span>9:16 · English</span></button><button>TikTok <span>9:16 · English</span></button></div></article></section>
      </template>

      <template v-else-if="activePage === 'workflows'">
        <section class="toolbar panel"><div class="filter-row"><button class="active">全部</button><button>图片生成</button><button>图生视频</button><button>首尾帧</button><button>ControlNet</button><button>TTS</button><button>音频</button><button>3D</button></div><div class="toolbar-right"><div class="top-search"><Search :size="15" /><input v-model="searchText" placeholder="搜索工作流..." /></div><button class="primary" @click="navigate('import')"><Upload :size="15" /> 导入工作流</button></div></section><section class="card-grid four"><article v-for="item in demoWorkflows" :key="item.id" class="panel workflow-card"><div class="workflow-cover"><Boxes :size="34" /></div><div class="workflow-card-title"><span class="badge">{{ item.category }}</span><h3>{{ item.name }}</h3></div><p>{{ item.description }}</p><div class="meta-grid"><span>输入 <b>{{ item.inputs }}</b></span><span>输出 <b>{{ item.outputs.join(', ') }}</b></span><span>难度 <b>{{ item.difficulty }}</b></span><span>来源 <b>{{ item.source?.name || 'Local' }}</b></span></div><div class="status-chip success">● 当前环境待检测</div><div class="button-row"><button class="primary" @click="navigate('create-task')">使用工作流</button><button class="secondary" @click="openWorkflow(item)">详情</button></div></article></section>
      </template>

      <template v-else-if="activePage === 'workflow-detail'">
        <section class="detail-hero panel"><div class="workflow-cover large"><Boxes :size="42" /></div><div><span class="badge">{{ selectedWorkflow?.category || 'image-to-video' }}</span><h2>{{ selectedWorkflow?.name || 'MiniMax H3 · 首帧转视频' }}</h2><p>{{ selectedWorkflow?.description || '将一张静态首帧生成自然动态视频。' }}</p><div class="tag-row"><span>Pixaroma</span><span>简单</span><span>视频输出</span></div></div><button class="primary" @click="navigate('create-task')">使用这个工作流</button></section><section class="detail-grid"><article class="panel section-card span-2"><div class="tabs"><button class="active">概览</button><button>如何使用</button><button>参数说明</button><button>示例作品</button><button>技术信息</button></div><div class="guide-grid"><div><h3>它是干什么的？</h3><p>使用一张首帧作为视频 0 秒画面，根据视频 Prompt 生成连续动态。</p><h3>适合</h3><div class="tag-row"><span>儿童动画</span><span>人物微动作</span><span>动物</span><span>风景动态</span></div></div><div><h3>输入素材</h3><div class="input-guide"><b>1. 首帧图片 · 必填</b><p>上传视频开始时的完整画面，主体清晰并尽量与目标比例一致。</p></div><div class="input-guide"><b>2. 视频 Prompt · 必填</b><p>按“起始状态 → 主要动作 → 完成状态 → 角色反应 → 运镜”描述。</p></div></div></div></article><article class="panel section-card"><h3>依赖状态</h3><div class="status-list"><div><span>MiniMax H3 Model</span><b class="green">待扫描</b></div><div><span>Text Encoder</span><b class="green">待扫描</b></div><div><span>Video VAE</span><b class="green">待扫描</b></div><div><span>ComfyUI-Pixaroma</span><b class="green">待扫描</b></div></div><button class="secondary wide" @click="navigate('dependencies')">查看模型与节点</button></article></section>
      </template>

      <template v-else-if="activePage === 'import'">
        <section class="import-grid"><article class="panel import-zone"><Upload :size="52" /><h2>导入 ComfyUI 工作流</h2><p>支持单个 JSON、多个 JSON 和 ZIP 批量扫描。UI Workflow 与 API Workflow 都会识别。</p><button class="primary">选择文件 / ZIP</button><small>原始文件只读保存；不会覆盖源工作流。</small></article><article class="panel section-card"><span class="eyebrow">SCAN PIPELINE</span><h3>导入后系统会做什么</h3><div class="roadmap"><div class="roadmap-item done"><span>1</span><div><strong>识别格式</strong><small>UI Workflow / API Workflow / 资源 JSON</small></div></div><div class="roadmap-item"><span>2</span><div><strong>扫描节点和依赖</strong><small>图片输入、Prompt、模型、Custom Nodes、输出</small></div></div><div class="roadmap-item"><span>3</span><div><strong>自动分类与去重</strong><small>根据内容 Hash 避免重复导入</small></div></div><div class="roadmap-item"><span>4</span><div><strong>进入适配向导</strong><small>确认每个输入的真实用途</small></div></div></div></article></section><section class="panel section-card"><div class="section-head"><h3>最近扫描</h3><button class="text-button">查看全部</button></div><div class="scan-summary"><div><span>发现 Workflow</span><b>236</b></div><div><span>资源 JSON</span><b>1</b></div><div><span>精确重复</span><b>待扫描</b></div><div><span>需要人工确认</span><b>待扫描</b></div></div></section>
      </template>

      <template v-else-if="activePage === 'adapter'">
        <section class="adapter-layout"><article class="panel section-card"><span class="eyebrow">STEP 1 / 4</span><h3>输入用途确认</h3><p>系统已经识别到 3 个图片节点，请确认它们在业务上代表什么。</p><div class="adapter-node"><div><b>Node 236 · PixaromaLoadImageMini</b><small>标题：1. Load Image - First Frame</small></div><select><option>首帧</option><option>尾帧</option><option>角色参考图</option></select><span class="confidence high">高置信度</span></div><div class="adapter-node"><div><b>Node 248 · LoadImage</b><small>标题：Reference Image</small></div><select><option>角色参考图</option><option>场景参考图</option><option>风格参考图</option></select><span class="confidence medium">中置信度</span></div><div class="adapter-node"><div><b>Node 261 · LoadImage</b><small>标题：Control Image</small></div><select><option>其他控制图</option><option>Pose</option><option>Depth</option><option>Mask</option></select><span class="confidence low">需确认</span></div></article><aside class="panel section-card"><h3>保存后生成 Manifest</h3><div class="status-list"><div><span>输入定义</span><b>3</b></div><div><span>参数定义</span><b>6</b></div><div><span>模型依赖</span><b>4</b></div><div><span>Custom Nodes</span><b>1</b></div></div><button class="primary wide">保存并继续</button></aside></section>
      </template>

      <template v-else-if="activePage === 'create-task'">
        <section class="task-layout"><article class="panel form-panel"><div class="workflow-selected"><div class="workflow-cover"><Film :size="28" /></div><div><b>MiniMax H3 · 首帧转视频</b><p>表单来自 Workflow Manifest，不直接暴露 Node ID。</p></div><button class="secondary" @click="navigate('workflows')">更换</button></div><label>首帧图片<div class="upload-box"><Upload :size="28" /><span>上传图片或从素材库选择</span></div></label><label>视频 Prompt<textarea>The kitten slowly looks under the table, blinks once, then looks back toward the pancake.</textarea></label><label>Negative Prompt<textarea>identity drift, duplicated props, disappearing objects, generated text</textarea></label><div class="form-grid"><label>视频时长<select><option>8 秒</option></select></label><label>FPS<select><option>24</option></select></label><label>分辨率<select><option>16:9 · 1536×864</option></select></label><label>Seed<input value="-1" /></label></div><button class="primary wide">开始生成</button></article><aside class="panel section-card"><h3>执行前检查</h3><div class="status-list"><div><span>ComfyUI</span><b class="green">可连接</b></div><div><span>输入完整</span><b class="green">通过</b></div><div><span>模型依赖</span><b>待检查</b></div><div><span>Custom Nodes</span><b>待检查</b></div></div><div class="notice">任务执行时会创建 Runtime Clone，原始 Workflow 不会被修改。</div></aside></section>
      </template>

      <template v-else-if="activePage === 'queue' || activePage === 'records'">
        <section class="panel table-panel"><div class="toolbar no-border"><div class="tabs"><button class="active">全部</button><button>运行中</button><button>等待</button><button>成功</button><button>失败</button><button>需要确认</button></div><button class="secondary">刷新</button></div><div class="task-table"><div class="task-table-row head"><span>状态</span><span>任务</span><span>工作流</span><span>进度</span><span>创建时间</span><span>操作</span></div><div class="task-table-row"><span class="status-chip running">运行中</span><div><b>EP003 · Shot04</b><small>小猫帮忙找蓝莓</small></div><span>MiniMax H3</span><div class="inline-progress"><i style="width:68%"></i><small>68%</small></div><span>16:42:10</span><button class="secondary">查看</button></div><div class="task-table-row"><span class="status-chip neutral">等待</span><div><b>EP003 · Shot05</b><small>找到大葡萄</small></div><span>MiniMax H3</span><span>-</span><span>16:42:12</span><button class="secondary">取消</button></div><div class="task-table-row"><span class="status-chip success">成功</span><div><b>EP003 · Shot03</b><small>蓝莓滚走了</small></div><span>Wan 2.2</span><span>100%</span><span>16:31:08</span><button class="secondary">查看</button></div></div></section>
      </template>

      <template v-else-if="activePage === 'materials'">
        <section class="toolbar panel"><div class="filter-row"><button class="active">全部</button><button>角色</button><button>场景</button><button>首帧</button><button>尾帧</button><button>Pose</button><button>Depth</button><button>Mask</button><button>音频</button></div><button class="primary"><Upload :size="15" /> 添加素材</button></section><section class="card-grid five"><article v-for="name in ['Benny 正面','Mimi 正面','厨房场景','EP003 S04 首帧','人物 Pose','Depth Map','对白音频','早餐桌参考']" :key="name" class="panel material-card"><div class="placeholder-art"><Image :size="30" /></div><b>{{ name }}</b><small>EP003 · 本地素材</small><div class="tag-row"><span>查看</span><span>用于任务</span></div></article></section>
      </template>

      <template v-else-if="activePage === 'dependencies'">
        <section class="two-column"><article class="panel section-card"><div class="section-head"><h3>模型</h3><button class="secondary">重新扫描</button></div><div class="dependency-list"><div><span>minimax_h3_fl2va_pruned_int8_convrot.safetensors</span><b class="green">已安装</b></div><div><span>qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors</span><b class="green">已安装</b></div><div><span>minimax_h3_video_vae_fp16.safetensors</span><b class="green">已安装</b></div><div><span>Wan Animate Model</span><b class="red">缺失</b></div></div></article><article class="panel section-card"><div class="section-head"><h3>Custom Nodes</h3><button class="secondary">查看 ComfyUI</button></div><div class="dependency-list"><div><span>ComfyUI-Pixaroma</span><b class="green">已安装</b></div><div><span>VideoHelperSuite</span><b class="green">已安装</b></div><div><span>IPAdapter Plus</span><b class="green">已安装</b></div><div><span>KJNodes</span><b class="red">缺失</b></div></div></article></section><section class="panel section-card"><h3>受影响的工作流</h3><div class="status-list"><div><span>MiniMax H3 · 首帧转视频</span><b class="green">可运行</b></div><div><span>Wan Animate · 角色替换</span><b class="red">缺少 1 个依赖</b></div><div><span>ControlNet Pose</span><b class="green">可运行</b></div></div></section>
      </template>

      <template v-else-if="activePage === 'settings'">
        <section class="settings-layout"><aside class="panel settings-menu"><button class="active">ComfyUI</button><button>存储</button><button>任务策略</button><button>工作流</button><button>高级</button></aside><article class="panel form-panel"><h3>ComfyUI 连接</h3><label>ComfyUI 地址<input value="http://127.0.0.1:8188" /></label><div class="connection-card"><span class="dot ok"></span><div><b>当前可连接</b><small>/system_stats 返回正常</small></div><button class="secondary">测试连接</button></div><h3>任务执行策略</h3><div class="form-grid"><label>最大并发<select><option>1 · 串行</option></select></label><label>输出超时<input value="900 秒" /></label></div><label class="check-line"><input type="checkbox" /> FAILED 自动重试一次</label><label class="check-line disabled"><input type="checkbox" disabled /> UNKNOWN 自动重试（安全策略禁止）</label><button class="primary">保存设置</button></article></section>
      </template>

      <p v-else class="empty-page panel">该页面正在接入真实数据。</p>
      <p v-if="error" class="error">本地 API：{{ error }}</p>
    </main>
  </div>
</template>
