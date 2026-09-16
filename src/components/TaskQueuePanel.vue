<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
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

type OutputRow = { id?: string; filename?: string | null; path?: string | null; type?: string | null; node_id?: string | null }
type TaskDetail = Task & { outputs?: OutputRow[] }
type EventRow = { id: number; event: string; message?: string | null; created_at: string }

const props = defineProps<{ mode?: 'queue' | 'records' }>()
const routeMode = ref<'queue' | 'records'>(location.hash.includes('#/records') ? 'records' : 'queue')
const mode = computed<'queue' | 'records'>(() => props.mode ?? routeMode.value)
const tasks = ref<Task[]>([])
const loading = ref(false)
const selected = ref<TaskDetail | null>(null)
const events = ref<EventRow[]>([])
const error = ref('')
const filter = ref(mode.value === 'queue' ? 'active' : 'all')
let timer: number | undefined

const activeStatuses = ['WAITING', 'PREPARING', 'SUBMITTING', 'QUEUED', 'RUNNING']
const reviewStatuses = ['UNKNOWN', 'NEEDS_REVIEW']

const visibleTasks = computed(() => {
  if (mode.value === 'records') {
    if (filter.value === 'success') return tasks.value.filter((task) => task.status === 'SUCCEEDED')
    if (filter.value === 'failed') return tasks.value.filter((task) => task.status === 'FAILED')
    if (filter.value === 'review') return tasks.value.filter((task) => reviewStatuses.includes(task.status))
    return tasks.value.filter((task) => !activeStatuses.includes(task.status))
  }
  if (filter.value === 'running') return tasks.value.filter((task) => ['RUNNING', 'PREPARING', 'SUBMITTING'].includes(task.status))
  if (filter.value === 'waiting') return tasks.value.filter((task) => ['WAITING', 'QUEUED'].includes(task.status))
  if (filter.value === 'review') return tasks.value.filter((task) => reviewStatuses.includes(task.status))
  if (filter.value === 'all') return tasks.value
  return tasks.value.filter((task) => activeStatuses.includes(task.status) || reviewStatuses.includes(task.status))
})

function statusClass(status: string) {
  if (status === 'SUCCEEDED') return 'success'
  if (activeStatuses.includes(status)) return 'running'
  if (['FAILED', ...reviewStatuses].includes(status)) return 'danger-chip'
  return 'neutral'
}

async function refresh() {
  loading.value = true
  try {
    const response = await fetch('/api/tasks?limit=100')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    tasks.value = await response.json()
    if (selected.value) {
      const fresh = tasks.value.find((item) => item.id === selected.value?.id)
      if (fresh) selected.value = { ...selected.value, ...fresh }
    }
    error.value = ''
  } catch (value) {
    error.value = value instanceof Error ? value.message : '任务列表读取失败'
  } finally {
    loading.value = false
  }
}

async function selectTask(task: Task) {
  const [detailResponse, eventsResponse] = await Promise.all([
    fetch(`/api/tasks/${encodeURIComponent(task.id)}`),
    fetch(`/api/tasks/${encodeURIComponent(task.id)}/events`),
  ])
  selected.value = detailResponse.ok ? await detailResponse.json() : task
  events.value = eventsResponse.ok ? await eventsResponse.json() : []
}

function onCreated() { refresh() }

function onHashChange() {
  routeMode.value = location.hash.includes('#/records') ? 'records' : 'queue'
  filter.value = mode.value === 'queue' ? 'active' : 'all'
  selected.value = null
  events.value = []
}

onMounted(() => {
  refresh()
  timer = window.setInterval(refresh, 3000)
  window.addEventListener('generation-task-created', onCreated)
  window.addEventListener('hashchange', onHashChange)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
  window.removeEventListener('generation-task-created', onCreated)
  window.removeEventListener('hashchange', onHashChange)
})
</script>

<template>
  <section class="queue-layout">
    <article class="panel table-panel">
      <div class="toolbar no-border">
        <div v-if="mode === 'queue'" class="tabs">
          <button :class="{ active: filter === 'active' }" @click="filter='active'">当前任务</button>
          <button :class="{ active: filter === 'running' }" @click="filter='running'">运行中</button>
          <button :class="{ active: filter === 'waiting' }" @click="filter='waiting'">等待</button>
          <button :class="{ active: filter === 'review' }" @click="filter='review'">待确认</button>
          <button :class="{ active: filter === 'all' }" @click="filter='all'">全部</button>
        </div>
        <div v-else class="tabs">
          <button :class="{ active: filter === 'all' }" @click="filter='all'">全部记录</button>
          <button :class="{ active: filter === 'success' }" @click="filter='success'">成功</button>
          <button :class="{ active: filter === 'failed' }" @click="filter='failed'">失败</button>
          <button :class="{ active: filter === 'review' }" @click="filter='review'">待确认</button>
        </div>
        <button class="secondary" :disabled="loading" @click="refresh"><RefreshCw :size="14" /> 刷新</button>
      </div>
      <div v-if="error" class="inline-error">{{ error }}</div>
      <div class="task-table">
        <div v-if="mode === 'queue'" class="task-table-row head"><span>状态</span><span>任务</span><span>工作流</span><span>进度</span><span>创建时间</span><span>操作</span></div>
        <div v-else class="task-table-row head"><span>结果</span><span>任务</span><span>工作流</span><span>Prompt ID</span><span>创建时间</span><span>操作</span></div>
        <div v-if="!visibleTasks.length" class="empty-row">{{ mode === 'queue' ? '当前没有等待、运行或待确认任务。' : '还没有符合条件的历史生成记录。' }}</div>
        <div v-for="task in visibleTasks" :key="task.id" class="task-table-row">
          <span :class="['status-chip', statusClass(task.status)]">{{ task.status }}</span>
          <div><b>{{ task.episode_id || task.client_app || 'Studio Task' }}{{ task.shot_id ? ` · ${task.shot_id}` : '' }}</b><small>{{ task.id }}</small></div>
          <span class="breakable">{{ task.workflow_id }}</span>
          <div v-if="mode === 'queue'" class="inline-progress"><i :style="{ width: `${Math.round((task.progress || 0) * 100)}%` }"></i><small>{{ Math.round((task.progress || 0) * 100) }}%</small></div>
          <span v-else class="breakable prompt-cell">{{ task.prompt_id || '-' }}</span>
          <span>{{ task.created_at?.replace('T',' ').slice(0, 19) || '-' }}</span>
          <button class="secondary" @click="selectTask(task)">查看</button>
        </div>
      </div>
    </article>

    <aside v-if="selected" class="panel section-card task-inspector">
      <h3>{{ mode === 'queue' ? '任务详情' : '生成记录详情' }}</h3>
      <div class="status-list">
        <div><span>Task ID</span><b class="breakable">{{ selected.id }}</b></div>
        <div><span>状态</span><b>{{ selected.status }}</b></div>
        <div><span>Prompt ID</span><b class="breakable">{{ selected.prompt_id || '-' }}</b></div>
        <div v-if="mode === 'queue'"><span>当前节点</span><b>{{ selected.current_node_title || '-' }}</b></div>
        <div v-else><span>输出数量</span><b>{{ selected.outputs?.length || 0 }}</b></div>
      </div>
      <p v-if="selected.error" class="inline-error">{{ selected.error }}</p>
      <template v-if="mode === 'records'">
        <h3>输出</h3>
        <div v-if="selected.outputs?.length" class="record-output-list">
          <div v-for="(output, index) in selected.outputs" :key="output.id || output.path || output.filename || `output-${index}`"><b>{{ output.filename || output.path || 'Output' }}</b><small>{{ output.type || 'file' }} · Node {{ output.node_id || '-' }}</small></div>
        </div>
        <div v-else class="empty-row compact-empty">没有持久化输出。</div>
      </template>
      <h3>事件</h3>
      <div class="event-list"><div v-for="item in events" :key="item.id"><small>{{ item.created_at?.slice(11, 19) }}</small><b>{{ item.event }}</b><span>{{ item.message }}</span></div></div>
    </aside>
  </section>
</template>

<style scoped>
.breakable{overflow-wrap:anywhere;word-break:break-word}.prompt-cell{font-size:9px;color:#69738f}.record-output-list{display:grid;gap:7px;margin-top:8px}.record-output-list>div{padding:9px 10px;border-radius:9px;background:#f7f8fc}.record-output-list b,.record-output-list small{display:block}.record-output-list b{font-size:10px;color:#48516d;overflow-wrap:anywhere}.record-output-list small{font-size:9px;color:#8b93aa;margin-top:3px}.compact-empty{padding:14px}
</style>
