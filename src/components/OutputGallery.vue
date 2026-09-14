<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Film, Image, Music2, RefreshCw } from 'lucide-vue-next'

type Output = {
  id: string
  task_id: string
  workflow_id: string
  type: 'image' | 'video' | 'audio' | string
  file_path: string
  created_at: string
}

const outputs = ref<Output[]>([])
const error = ref('')
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    const response = await fetch('/api/outputs?limit=200')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    outputs.value = await response.json()
    error.value = ''
  } catch (value) {
    error.value = value instanceof Error ? value.message : '作品读取失败'
  } finally {
    loading.value = false
  }
}

function openOutput(item: Output) {
  window.open(`/api/outputs/${encodeURIComponent(item.id)}/file`, '_blank')
}

onMounted(refresh)
</script>

<template>
  <div>
    <section class="toolbar panel"><div class="tabs"><button class="active">全部</button><button>图片</button><button>视频</button><button>音频</button></div><button class="secondary" :disabled="loading" @click="refresh"><RefreshCw :size="14" /> 刷新</button></section>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <div v-if="!outputs.length" class="panel empty-page">还没有生成作品。完成第一个任务后，输出会自动进入作品库。</div>
    <section v-else class="card-grid four">
      <article v-for="item in outputs" :key="item.id" class="panel work-card">
        <div class="placeholder-art"><Film v-if="item.type === 'video'" :size="34" /><Music2 v-else-if="item.type === 'audio'" :size="34" /><Image v-else :size="34" /></div>
        <div class="work-meta"><b>{{ item.type.toUpperCase() }} · {{ item.task_id }}</b><small>{{ item.workflow_id }}</small></div>
        <div class="tag-row"><span>{{ item.created_at?.slice(0, 19).replace('T', ' ') }}</span></div>
        <button class="secondary wide" @click="openOutput(item)">打开结果</button>
      </article>
    </section>
  </div>
</template>
