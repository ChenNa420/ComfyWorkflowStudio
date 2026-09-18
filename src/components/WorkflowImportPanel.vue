<script setup lang="ts">
import { ref } from 'vue'
import { CircleCheck, Upload } from 'lucide-vue-next'

type ImportSummary = { imported: number; duplicates: number; resources: number; invalid: number }
type ImportResult = {
  ok: boolean
  summary: ImportSummary
  files: Array<{ source: string; scanned: number; imported: Array<{ workflowId: string; filename: string; category: string; nodeCount: number }>; duplicates: unknown[]; resources: unknown[] }>
}

const inputRef = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const error = ref('')
const result = ref<ImportResult | null>(null)

function chooseFiles() {
  inputRef.value?.click()
}

async function onFiles(event: Event) {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  if (!files.length) return
  importing.value = true
  error.value = ''
  result.value = null
  try {
    const body = new FormData()
    for (const file of files) body.append('files', file)
    const response = await fetch('/api/workflows/import', { method: 'POST', body })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`)
    result.value = payload
    window.dispatchEvent(new CustomEvent('workflow-catalog-updated'))
  } catch (value) {
    error.value = value instanceof Error ? value.message : '导入失败'
  } finally {
    importing.value = false
    target.value = ''
  }
}
</script>

<template>
  <div class="import-control">
    <input ref="inputRef" class="hidden-file-input" type="file" accept=".json,.zip,application/json,application/zip" multiple @change="onFiles" />
    <button class="primary" :disabled="importing" @click="chooseFiles">
      <Upload :size="16" /> {{ importing ? '正在扫描...' : '选择 JSON / ZIP' }}
    </button>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <div v-if="result" class="import-result">
      <div class="import-result-head"><CircleCheck :size="18" /><b>扫描完成</b></div>
      <div class="scan-summary compact">
        <div><span>新导入</span><b>{{ result.summary.imported }}</b></div>
        <div><span>重复</span><b>{{ result.summary.duplicates }}</b></div>
        <div><span>资源 JSON</span><b>{{ result.summary.resources }}</b></div>
        <div><span>无效</span><b>{{ result.summary.invalid }}</b></div>
      </div>
      <div class="imported-list" v-for="file in result.files" :key="file.source">
        <small>{{ file.source }} · 扫描 {{ file.scanned }}</small>
        <div v-for="item in file.imported.slice(0, 8)" :key="item.workflowId" class="imported-item">
          <span>{{ item.filename }}</span><b>{{ item.category }} · {{ item.nodeCount }} nodes</b>
        </div>
        <small v-if="file.imported.length > 8">还有 {{ file.imported.length - 8 }} 个工作流已导入</small>
      </div>
    </div>
  </div>
</template>
