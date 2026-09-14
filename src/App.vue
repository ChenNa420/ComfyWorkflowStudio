<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Activity, Boxes, FolderOpen, Gauge, Image, Layers3, Play, Settings, Sparkles } from 'lucide-vue-next'

type Health = {
  status: string
  service: string
  phase: string
  workflowPackages: number
  comfyUi: string
}

const health = ref<Health | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    const response = await fetch('/api/health')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    health.value = await response.json()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '无法连接本地 API'
  }
})

const nav = [
  [Gauge, '仪表盘'],
  [Boxes, '工作流库'],
  [Play, '创建任务'],
  [Activity, '任务队列'],
  [Image, '作品库'],
  [FolderOpen, '素材库'],
  [Layers3, '模型与节点'],
  [Settings, '系统设置'],
] as const
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><Sparkles :size="22" /></div>
        <div>
          <strong>Comfy Workflow</strong>
          <span>Studio</span>
        </div>
      </div>

      <nav>
        <button v-for="([Icon, label], index) in nav" :key="label" :class="['nav-item', { active: index === 0 }]">
          <component :is="Icon" :size="18" />
          <span>{{ label }}</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <span class="dot" :class="health?.status === 'ok' ? 'ok' : ''"></span>
        <div>
          <strong>Local Studio</strong>
          <small>{{ health?.status === 'ok' ? 'API 已连接' : '等待连接' }}</small>
        </div>
      </div>
    </aside>

    <main class="content">
      <header class="topbar">
        <div>
          <p class="eyebrow">COMFYWORKFLOWSTUDIO</p>
          <h1>让 ComfyUI 工作流真正变成可用的创作工具</h1>
        </div>
        <div class="status-pill">
          <span class="dot" :class="health?.status === 'ok' ? 'ok' : ''"></span>
          Phase {{ health?.phase || '1A' }}
        </div>
      </header>

      <section class="hero panel">
        <div>
          <span class="badge">Workflow Knowledge Base + Runner</span>
          <h2>导入工作流，理解它，然后一键生成。</h2>
          <p>每个 Workflow 都包含输入说明、参数解释、依赖、示例和执行映射；童语工坊也可以按剧集或 Shot 自由选择工作流。</p>
          <div class="hero-actions">
            <button class="primary">导入第一个工作流</button>
            <button class="secondary">查看 Manifest 规范</button>
          </div>
        </div>
        <div class="hero-card">
          <span>当前底座</span>
          <strong>{{ health?.workflowPackages ?? 0 }}</strong>
          <small>Workflow Packages</small>
          <div class="mini-row"><span>FastAPI</span><b>8100</b></div>
          <div class="mini-row"><span>Vue/Vite</span><b>5174</b></div>
          <div class="mini-row"><span>ComfyUI</span><b>待配置</b></div>
        </div>
      </section>

      <section class="stats-grid">
        <article class="stat-card"><span>工作流</span><strong>{{ health?.workflowPackages ?? 0 }}</strong><small>已导入工作流包</small></article>
        <article class="stat-card"><span>可运行</span><strong>0</strong><small>通过模型/节点检查</small></article>
        <article class="stat-card"><span>运行任务</span><strong>0</strong><small>本地 ComfyUI 队列</small></article>
        <article class="stat-card"><span>作品</span><strong>0</strong><small>图片 / 视频 / 音频</small></article>
      </section>

      <section class="workspace-grid">
        <article class="panel">
          <div class="section-head"><div><span class="eyebrow">WORKFLOW LIBRARY</span><h3>工作流库</h3></div><button class="text-button">查看全部</button></div>
          <div class="empty-state">
            <Boxes :size="38" />
            <strong>还没有真实工作流</strong>
            <p>Phase 1A 已建立 Workflow Package 与 Manifest 规范。下一步导入 Pixaroma / 本地 ComfyUI API Workflow。</p>
          </div>
        </article>

        <article class="panel roadmap">
          <div class="section-head"><div><span class="eyebrow">PHASE 1A</span><h3>基础能力</h3></div></div>
          <div class="roadmap-item done"><span>1</span><div><strong>Workflow Manifest V1</strong><small>输入、参数、输出、依赖、教程</small></div></div>
          <div class="roadmap-item done"><span>2</span><div><strong>SQLite Schema</strong><small>Workflow / Binding / Task / Output</small></div></div>
          <div class="roadmap-item"><span>3</span><div><strong>工作流导入与分析</strong><small>下一阶段开始实现</small></div></div>
          <div class="roadmap-item"><span>4</span><div><strong>ComfyUI 执行器</strong><small>Runtime Clone + 安全任务状态</small></div></div>
        </article>
      </section>

      <p v-if="error" class="error">本地 API：{{ error }}</p>
    </main>
  </div>
</template>
