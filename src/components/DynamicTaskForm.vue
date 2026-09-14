<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { CircleCheck, Film, Image, Upload } from 'lucide-vue-next'

type WorkflowSummary = { id: string; name: string; category: string; description: string }
type ManifestInput = {
  key: string
  label: string
  type: string
  required: boolean
  purpose?: string | null
  description?: string
  help?: string
  accept?: string[]
}
type ManifestParameter = {
  key: string
  label: string
  type: string
  default?: unknown
  min?: number | null
  max?: number | null
  step?: number | null
  unit?: string | null
  options?: unknown[]
  description?: string
}
type Manifest = {
  workflowId: string
  name: string
  description: string
  category: string
  inputs: ManifestInput[]
  parameters: ManifestParameter[]
  runtime?: { executionMode?: string; retryUnknown?: boolean; preserveOriginalWorkflow?: boolean }
}
type FormValue = string | number | boolean

const workflows = ref<WorkflowSummary[]>([])
const selectedId = ref('')
const manifest = ref<Manifest | null>(null)
const values = ref<Record<string, FormValue>>({})
const parameters = ref<Record<string, FormValue>>({})
const uploadedNames = ref<Record<string, string>>({})
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const taskResult = ref<{ taskId: string; status: string } | null>(null)
const compatibility = ref<{ status?: string; missingNodes?: string[] } | null>(null)

const selectedWorkflow = computed(() => workflows.value.find((item) => item.id === selectedId.value))

async function loadWorkflows() {
  const response = await fetch('/api/workflows')
  if (!response.ok) throw new Error(`工作流列表 HTTP ${response.status}`)
  workflows.value = await response.json()
  const saved = sessionStorage.getItem('cws-selected-workflow')
  selectedId.value = saved && workflows.value.some((item) => item.id === saved) ? saved : workflows.value[0]?.id || ''
}

async function loadManifest(id: string) {
  if (!id) {
    manifest.value = null
    return
  }
  loading.value = true
  error.value = ''
  taskResult.value = null
  try {
    const [manifestResponse, compatibilityResponse] = await Promise.all([
      fetch(`/api/workflows/${encodeURIComponent(id)}/manifest`),
      fetch(`/api/workflows/${encodeURIComponent(id)}/compatibility`),
    ])
    if (!manifestResponse.ok) throw new Error(`Manifest HTTP ${manifestResponse.status}`)
    manifest.value = await manifestResponse.json()
    compatibility.value = compatibilityResponse.ok ? await compatibilityResponse.json() : null
    values.value = {}
    parameters.value = {}
    uploadedNames.value = {}
    for (const item of manifest.value?.inputs || []) {
      if (item.type === 'boolean') values.value[item.key] = false
      else values.value[item.key] = ''
    }
    for (const item of manifest.value?.parameters || []) {
      const value = item.default
      parameters.value[item.key] = typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? value : ''
    }
    sessionStorage.setItem('cws-selected-workflow', id)
  } catch (value) {
    error.value = value instanceof Error ? value.message : '读取 Manifest 失败'
  } finally {
    loading.value = false
  }
}

async function uploadMaterial(event: Event, key: string) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  error.value = ''
  try {
    const body = new FormData()
    body.append('file', file)
    const response = await fetch('/api/materials', { method: 'POST', body })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload?.detail || `上传 HTTP ${response.status}`)
    values.value[key] = payload.filePath
    uploadedNames.value[key] = payload.name
  } catch (value) {
    error.value = value instanceof Error ? value.message : '素材上传失败'
  }
}

function isFileInput(type: string) {
  return ['image', 'video', 'audio'].includes(type)
}

function setTextValue(event: Event, key: string) {
  values.value[key] = (event.target as HTMLTextAreaElement).value
}

async function submitTask() {
  if (!manifest.value) return
  error.value = ''
  taskResult.value = null
  for (const item of manifest.value.inputs) {
    if (item.required && !values.value[item.key]) {
      error.value = `请填写：${item.label}`
      return
    }
  }
  submitting.value = true
  try {
    const response = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflowId: manifest.value.workflowId,
        clientApp: 'ComfyWorkflowStudio',
        inputs: values.value,
        parameters: parameters.value,
      }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload?.detail || `任务 HTTP ${response.status}`)
    taskResult.value = payload
    window.dispatchEvent(new CustomEvent('generation-task-created', { detail: payload }))
  } catch (value) {
    error.value = value instanceof Error ? value.message : '创建任务失败'
  } finally {
    submitting.value = false
  }
}

watch(selectedId, (id) => loadManifest(id))

onMounted(async () => {
  try {
    await loadWorkflows()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '读取工作流失败'
  }
})
</script>

<template>
  <div class="dynamic-task-form">
    <div class="workflow-selected task-workflow-select">
      <div class="workflow-cover"><Film :size="28" /></div>
      <div>
        <b>{{ selectedWorkflow?.name || '请选择工作流' }}</b>
        <p>{{ selectedWorkflow?.description || '先从工作流库导入或选择一个 Workflow。' }}</p>
      </div>
      <select v-model="selectedId" class="workflow-select">
        <option v-for="item in workflows" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
    </div>

    <div v-if="loading" class="notice">正在读取 Workflow Manifest...</div>
    <div v-else-if="!manifest" class="notice">当前没有可用工作流。请先进入“导入工作流”页面导入 JSON 或 ZIP。</div>

    <template v-else>
      <div class="manifest-summary">
        <span class="badge">{{ manifest.category }}</span>
        <span>{{ manifest.inputs.length }} 个输入</span>
        <span>{{ manifest.parameters.length }} 个参数</span>
        <span :class="compatibility?.status === 'READY' ? 'green' : ''">{{ compatibility?.status || '待检查' }}</span>
      </div>

      <div class="dynamic-fields">
        <div v-for="item in manifest.inputs" :key="item.key" class="dynamic-field">
          <label>{{ item.label }} <em v-if="item.required">*</em></label>
          <div v-if="isFileInput(item.type)" class="upload-box compact-upload">
            <Image v-if="item.type === 'image'" :size="24" />
            <Upload v-else :size="24" />
            <span>{{ uploadedNames[item.key] || item.help || `选择${item.label}` }}</span>
            <input class="file-overlay" type="file" :accept="item.accept?.join(',')" @change="uploadMaterial($event, item.key)" />
          </div>
          <textarea v-else-if="item.type === 'textarea'" :value="String(values[item.key] ?? '')" :placeholder="item.help || item.description" @input="setTextValue($event, item.key)"></textarea>
          <select v-else-if="item.type === 'boolean'" v-model="values[item.key]"><option :value="false">关闭</option><option :value="true">开启</option></select>
          <input v-else v-model="values[item.key]" :type="['number','seed','slider'].includes(item.type) ? 'number' : 'text'" :placeholder="item.help || item.description" />
          <small v-if="item.purpose">用途：{{ item.purpose }}</small>
        </div>
      </div>

      <div v-if="manifest.parameters.length" class="parameter-grid">
        <div v-for="item in manifest.parameters" :key="item.key" class="dynamic-field">
          <label>{{ item.label }}</label>
          <select v-if="item.type === 'select'" v-model="parameters[item.key]">
            <option v-for="option in item.options || []" :key="String(option)" :value="option">{{ option }}</option>
          </select>
          <select v-else-if="item.type === 'boolean'" v-model="parameters[item.key]"><option :value="false">关闭</option><option :value="true">开启</option></select>
          <input v-else v-model="parameters[item.key]" :type="['number','seed','slider'].includes(item.type) ? 'number' : 'text'" :min="item.min ?? undefined" :max="item.max ?? undefined" :step="item.step ?? undefined" />
          <small>{{ item.description }} {{ item.unit ? `· ${item.unit}` : '' }}</small>
        </div>
      </div>

      <div class="runtime-safety">
        <span>Runtime Clone：{{ manifest.runtime?.preserveOriginalWorkflow === false ? '关闭' : '开启' }}</span>
        <span>执行：{{ manifest.runtime?.executionMode || 'serial' }}</span>
        <span>UNKNOWN 自动重试：{{ manifest.runtime?.retryUnknown ? '开启' : '禁止' }}</span>
      </div>

      <button class="primary wide" :disabled="submitting || compatibility?.status === 'MISSING_NODES'" @click="submitTask">
        {{ submitting ? '正在创建任务...' : '开始生成' }}
      </button>
      <p v-if="error" class="inline-error">{{ error }}</p>
      <div v-if="taskResult" class="task-created"><CircleCheck :size="18" /><div><b>任务已进入队列</b><small>{{ taskResult.taskId }} · {{ taskResult.status }}</small></div></div>
    </template>
  </div>
</template>
