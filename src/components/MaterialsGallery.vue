<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { FolderOpen, Image, Music2, Upload, Video } from 'lucide-vue-next'

type Material = { id: string; type: string; name?: string | null; file_path: string; created_at: string }

const materials = ref<Material[]>([])
const inputRef = ref<HTMLInputElement | null>(null)
const error = ref('')

async function refresh() {
  try {
    const response = await fetch('/api/materials?limit=500')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    materials.value = await response.json()
    error.value = ''
  } catch (value) {
    error.value = value instanceof Error ? value.message : '素材读取失败'
  }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  for (const file of files) {
    const body = new FormData()
    body.append('file', file)
    const response = await fetch('/api/materials', { method: 'POST', body })
    if (!response.ok) {
      error.value = `${file.name} 上传失败`
      break
    }
  }
  input.value = ''
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <div>
    <section class="toolbar panel">
      <div class="filter-row"><button class="active">全部</button><button>图片</button><button>视频</button><button>音频</button><button>角色</button><button>场景</button><button>控制图</button></div>
      <div><input ref="inputRef" class="hidden-file-input" type="file" multiple @change="upload" /><button class="primary" @click="inputRef?.click()"><Upload :size="15" /> 添加素材</button></div>
    </section>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <div v-if="!materials.length" class="panel empty-page"><FolderOpen :size="34" /><p>素材库为空。上传角色图、场景图、首帧、Pose、Depth 或音频后会显示在这里。</p></div>
    <section v-else class="card-grid five">
      <article v-for="item in materials" :key="item.id" class="panel material-card">
        <div class="placeholder-art"><Video v-if="item.type === 'video'" :size="30" /><Music2 v-else-if="item.type === 'audio'" :size="30" /><Image v-else :size="30" /></div>
        <b>{{ item.name || item.id }}</b><small>{{ item.type }} · {{ item.created_at?.slice(0, 10) }}</small><div class="tag-row"><span>{{ item.id }}</span></div>
      </article>
    </section>
  </div>
</template>
