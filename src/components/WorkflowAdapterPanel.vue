<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { CircleCheck, Save } from 'lucide-vue-next'

type WorkflowSummary = { id: string; name: string }
type InputRow = {
  key: string
  label: string
  type: string
  required: boolean
  purpose?: string | null
  description?: string
  help?: string
  mapping?: { nodeId?: string | null; field?: string | null; strategy?: string | null }
}
type Manifest = {
  workflowId: string
  name: string
  category: string
  description: string
  inputs: InputRow[]
  [key: string]: unknown
}

type AnalysisInput = {
  key: string
  nodeType?: string
  nodeTitle?: string
  analysisConfidence?: number
}

const workflows = ref<WorkflowSummary[]>([])
const selectedId = ref('')
const manifest = ref<Manifest | null>(null)
const analysisInputs = ref<Record<string, AnalysisInput>>({})
const loading = ref(false)
const saving = ref(false)
const saved = ref(false)
const error = ref('')

const purposes = [
  ['video-start-frame', '首帧'],
  ['video-end-frame', '尾帧'],
  ['source-image', '原图 / 通用参考图'],
  ['character-reference', '角色参考图'],
  ['scene-reference', '场景参考图'],
  ['style-reference', '风格参考图'],
  ['pose', 'Pose'],
  ['depth', 'Depth'],
  ['lineart', 'Lineart'],
  ['mask', 'Mask'],
  ['control-image', '其他控制图'],
  ['prompt', 'Prompt'],
  ['negative-prompt', 'Negative Prompt'],
  ['other', '其他'],
]

const currentWorkflow = computed(() => workflows.value.find((item) => item.id === selectedId.value))

async function loadWorkflows() {
  const response = await fetch('/api/workflows')
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  workflows.value = await response.json()
  const stored = sessionStorage.getItem('cws-selected-workflow')
  selectedId.value = stored && workflows.value.some((item) => item.id === stored) ? stored : workflows.value[0]?.id || ''
}

async function loadWorkflow(id: string) {
  if (!id) {
    manifest.value = null
    return
  }
  loading.value = true
  saved.value = false
  error.value = ''
  try {
    const [manifestResponse, analysisResponse] = await Promise.all([
      fetch(`/api/workflows/${encodeURIComponent(id)}/manifest`),
      fetch(`/api/workflows/${encodeURIComponent(id)}/analysis`),
    ])
    if (!manifestResponse.ok) throw new Error(`Manifest HTTP ${manifestResponse.status}`)
    manifest.value = await manifestResponse.json()
    const analysis = analysisResponse.ok ? await analysisResponse.json() : null
    const map: Record<string, AnalysisInput> = {}
    for (const item of analysis?.inputs || []) map[item.key] = item
    analysisInputs.value = map
    sessionStorage.setItem('cws-selected-workflow', id)
  } catch (value) {
    error.value = value instanceof Error ? value.message : '读取工作流失败'
  } finally {
    loading.value = false
  }
}

async function saveManifest() {
  if (!manifest.value) return
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    const response = await fetch(`/api/workflows/${encodeURIComponent(manifest.value.workflowId)}/manifest`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(manifest.value),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`)
    saved.value = true
    window.dispatchEvent(new CustomEvent('workflow-catalog-updated'))
  } catch (value) {
    error.value = value instanceof Error ? value.message : '保存 Manifest 失败'
  } finally {
    saving.value = false
  }
}

watch(selectedId, (id) => loadWorkflow(id))

onMounted(async () => {
  try {
    await loadWorkflows()
  } catch (value) {
    error.value = value instanceof Error ? value.message : '读取工作流列表失败'
  }
})
</script>

<template>
  <div class="adapter-functional">
    <div class="adapter-toolbar">
      <div><span class="eyebrow">WORKFLOW ADAPTER</span><h3>{{ currentWorkflow?.name || '请选择工作流' }}</h3></div>
      <select v-model="selectedId" class="workflow-select"><option v-for="item in workflows" :key="item.id" :value="item.id">{{ item.name }}</option></select>
    </div>

    <div v-if="loading" class="notice">正在读取分析结果...</div>
    <div v-else-if="manifest">
      <div class="form-grid adapter-meta">
        <label>名称<input v-model="manifest.name" /></label>
        <label>分类<input v-model="manifest.category" /></label>
      </div>
      <label class="adapter-description">工作流说明<textarea v-model="manifest.description"></textarea></label>

      <h3>输入语义</h3>
      <div v-if="!manifest.inputs.length" class="notice">自动分析没有找到可编辑输入。可在技术信息中检查节点或手动补充 Manifest。</div>
      <div v-for="item in manifest.inputs" :key="item.key" class="adapter-node functional-node">
        <div>
          <b>Node {{ item.mapping?.nodeId || '-' }} · {{ analysisInputs[item.key]?.nodeType || item.type }}</b>
          <small>{{ analysisInputs[item.key]?.nodeTitle || item.description || item.key }}</small>
        </div>
        <input v-model="item.label" class="adapter-label-input" />
        <select v-model="item.purpose"><option v-for="option in purposes" :key="option[0]" :value="option[0]">{{ option[1] }}</option></select>
        <span :class="['confidence',(analysisInputs[item.key]?.analysisConfidence || 0)>.85?'high':(analysisInputs[item.key]?.analysisConfidence || 0)>.6?'medium':'low']">{{ Math.round((analysisInputs[item.key]?.analysisConfidence || 0)*100) }}%</span>
      </div>

      <div class="adapter-save-row">
        <span v-if="saved" class="save-success"><CircleCheck :size="16" /> 已保存</span>
        <button class="primary" :disabled="saving" @click="saveManifest"><Save :size="15" /> {{ saving ? '保存中...' : '保存 Manifest' }}</button>
      </div>
    </div>
    <p v-if="error" class="inline-error">{{ error }}</p>
  </div>
</template>
