<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { RefreshCw } from 'lucide-vue-next'

type Task = {
  id: string
  workflow_id: string
  client_app?: string | null
  episode_id?: string | null
  shot_id?: string | null
  status: string
  prompt_id?: string | null
  progress: number
  current_node_title?: string | null
  error?: string | null
  created_at: string
}

type EventRow = { id: number; event: string; message?: string | null; created_at: string }

const tasks = ref<Task[]>([])
const loading = ref(false)
const selected = ref<Task | null>(null)
const events = ref<EventRow[]>([])
const error = ref('')
let timer: number | undefined

function statusClass(status: string) {
  if (status === 'SUCCEEDED') return 'success'
  if (['RUNNING', 'PREPARING', 'SUBMITTING', 'QUEUED'].includes(status)) return 'running'
  if (['FAILED', 'UNKNOWN', 'NEEDS_REVIEW'].includes(status)) return 'danger-chip'
  return 'neutral'
}

async function refresh() {
  loading.value = true
  try {
    const response = await fetch('/api/tasks?limit=100')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    tasks.value = await response.json()
    if (selected.value) {
      selected.value = tasks.value.find((item) => item.id === selected.value?.id) || selected.value
    }
    error.value = ''
  } catch (value) {
    error.value = value instanceof Error ? value.message : '任务列表读取失败'
  } finally {
    loading.value = false
  }
}

async function selectTask(task: Task) {
  selected.value = task
  const response = await fetch(`/api/tasks/${encodeURIComponent(task.id)}/events`)
  events.value = response.ok ? await response.json() : []
}

function onCreated() { refresh() }

onMounted(() => {
  refresh()
  timer = window.setInterval(refresh, 3000)
  window.addEventListener('generation-task-created', onCreated)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
  window.removeEventListener('generation-task-created', onCreated)
})
</script>

<template>
  <section class="queue-layout">
    <article class="panel table-panel">
      <div class="toolbar no-border">
        <div class="tabs"><button class="active">全部</button><button>运行中</button><button>等待</button><button>成功</button><button>失败 / 待确认</button></div>
        <button class="secondary" :disabled="loading" @click="refresh"><RefreshCw :size="14" /> 刷新</button>
      </div>
      <div v-if="error" class="inline-error">{{ error }}</div>
      <div class="task-table">
        <div class="task-table-row head"><span>状态</span><span>任务</span><span>工作流</span><span>进度</span><span>创建时间</span><span>操作</span></div>
        <div v-if="!tasks.length" class="empty-row">还没有生成任务。</div>
        <div v-for="task in tasks" :key="task.id" class="task-table-row">
          <span :class="['status-chip', statusClass(task.status)]">{{ task.status }}</span>
          <div><b>{{ task.episode_id || task.client_app || 'Studio Task' }}{{ task.shot_id ? ` · ${task.shot_id}` : '' }}</b><small>{{ task.id }}</small></div>
          <span>{{ task.workflow_id }}</span>
          <div class="inline-progress"><i :style="{ width: `${Math.round((task.progress || 0) * 100)}%` }"></i><small>{{ Math.round((task.progress || 0) * 100) }}%</small></div>
          <span>{{ task.created_at?.slice(11, 19) || '-' }}</span>
          <button class="secondary" @click="selectTask(task)">查看</button>
        </div>
      </div>
    </article>

    <aside v-if="selected" class="panel section-card task-inspector">
      <h3>任务详情</h3>
      <div class="status-list">
        <div><span>Task ID</span><b>{{ selected.id }}</b></div>
        <div><span>状态</span><b>{{ selected.status }}</b></div>
        <div><span>Prompt ID</span><b>{{ selected.prompt_id || '-' }}</b></div>
        <div><span>当前节点</span><b>{{ selected.current_node_title || '-' }}</b></div>
      </div>
      <p v-if="selected.error" class="inline-error">{{ selected.error }}</p>
      <h3>事件</h3>
      <div class="event-list"><div v-for="item in events" :key="item.id"><small>{{ item.created_at?.slice(11, 19) }}</small><b>{{ item.event }}</b><span>{{ item.message }}</span></div></div>
    </aside>
  </section>
</template>
