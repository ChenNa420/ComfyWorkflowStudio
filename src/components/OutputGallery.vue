<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Clock3,
  Download,
  Film,
  Image,
  MoreVertical,
  Music2,
  Play,
  RefreshCw,
} from 'lucide-vue-next'

type Output = {
  id: string
  task_id: string
  workflow_id: string
  workflow_name?: string | null
  project_id?: string | null
  episode_id?: string | null
  shot_id?: string | null
  type: 'image' | 'video' | 'audio' | string
  file_path: string
  created_at: string
}

type MediaInfo = {
  width?: number
  height?: number
  duration?: number
}

const outputs = ref<Output[]>([])
const error = ref('')
const loading = ref(false)
const mediaType = ref<'all' | 'image' | 'video' | 'audio'>('all')
const sortMode = ref<'newest' | 'oldest'>('newest')
const projectFilter = ref('all')
const timeFilter = ref<'all' | 'today' | 'week' | 'month'>('all')
const mediaInfo = reactive<Record<string, MediaInfo>>({})

const waveform = [
  18,26,40,33,48,55,36,28,31,43,57,62,49,37,29,23,34,46,
  58,68,55,42,31,28,35,47,61,52,39,30,24,32,45,54,41,27,
]

const counts = computed(() => ({
  all: outputs.value.length,
  image: outputs.value.filter(item => item.type === 'image').length,
  video: outputs.value.filter(item => item.type === 'video').length,
  audio: outputs.value.filter(item => item.type === 'audio').length,
}))

const projects = computed(() => {
  const map = new Map<string, string>()
  for (const item of outputs.value) {
    const key = item.episode_id || item.project_id || item.workflow_id
    if (!key) continue
    map.set(key, item.episode_id || item.project_id || item.workflow_name || item.workflow_id)
  }
  return [...map.entries()].map(([id, label]) => ({ id, label }))
})

const filteredOutputs = computed(() => {
  const now = Date.now()
  let rows = outputs.value.filter(item => {
    if (mediaType.value !== 'all' && item.type !== mediaType.value) return false
    if (projectFilter.value !== 'all') {
      const key = item.episode_id || item.project_id || item.workflow_id
      if (key !== projectFilter.value) return false
    }
    if (timeFilter.value !== 'all') {
      const created = new Date(item.created_at).getTime()
      const age = now - created
      const maxAge = timeFilter.value === 'today'
        ? 24 * 60 * 60 * 1000
        : timeFilter.value === 'week'
          ? 7 * 24 * 60 * 60 * 1000
          : 30 * 24 * 60 * 60 * 1000
      if (!Number.isFinite(created) || age > maxAge) return false
    }
    return true
  })
  rows = [...rows].sort((a, b) => {
    const left = new Date(a.created_at).getTime() || 0
    const right = new Date(b.created_at).getTime() || 0
    return sortMode.value === 'newest' ? right - left : left - right
  })
  return rows
})

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

function fileUrl(item: Output, download = false) {
  const suffix = download ? '?download=true' : ''
  return `/api/outputs/${encodeURIComponent(item.id)}/file${suffix}`
}

function mediaUrl(item: Output) {
  return item.type === 'video' ? `${fileUrl(item)}#t=0.1` : fileUrl(item)
}

function openOutput(item: Output) {
  window.open(fileUrl(item), '_blank')
}

function downloadOutput(item: Output) {
  const anchor = document.createElement('a')
  anchor.href = fileUrl(item, true)
  anchor.download = ''
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

function recordImageMeta(event: Event, item: Output) {
  const image = event.target as HTMLImageElement
  mediaInfo[item.id] = { ...mediaInfo[item.id], width: image.naturalWidth, height: image.naturalHeight }
}

function recordVideoMeta(event: Event, item: Output) {
  const video = event.target as HTMLVideoElement
  mediaInfo[item.id] = {
    ...mediaInfo[item.id],
    width: video.videoWidth,
    height: video.videoHeight,
    duration: video.duration,
  }
  if (Number.isFinite(video.duration) && video.duration > 0.12) {
    try { video.currentTime = Math.min(0.1, video.duration / 2) } catch { /* browser decides */ }
  }
}

function recordAudioMeta(event: Event, item: Output) {
  const audio = event.target as HTMLAudioElement
  mediaInfo[item.id] = { ...mediaInfo[item.id], duration: audio.duration }
}

function outputTitle(item: Output) {
  if (item.episode_id && item.shot_id) return `${item.episode_id} · ${item.shot_id}`
  if (item.episode_id) return item.episode_id
  const path = String(item.file_path || '').replace(/\\/g, '/')
  const filename = path.split('/').pop() || ''
  const stem = filename.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim()
  if (stem) return stem
  return `${item.type.toUpperCase()} · ${item.task_id}`
}

function typeLabel(type: string) {
  return type === 'video' ? '视频' : type === 'audio' ? '音频' : type === 'image' ? '图片' : '文件'
}

function typeIcon(type: string) {
  return type === 'video' ? Film : type === 'audio' ? Music2 : Image
}

function formatDate(value: string) {
  return value?.slice(0, 19).replace('T', ' ') || '-'
}

function formatDuration(seconds?: number) {
  if (!seconds || !Number.isFinite(seconds)) return ''
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  const remainder = total % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

function resolution(item: Output) {
  const info = mediaInfo[item.id]
  if (!info?.width || !info?.height) return ''
  return `${info.width} × ${info.height}`
}

onMounted(refresh)
</script>

<template>
  <section class="works-library">
    <section class="panel works-toolbar">
      <div class="works-type-tabs">
        <button :class="{active:mediaType==='all'}" @click="mediaType='all'">全部 ({{ counts.all }})</button>
        <button :class="{active:mediaType==='image'}" @click="mediaType='image'">图片 ({{ counts.image }})</button>
        <button :class="{active:mediaType==='video'}" @click="mediaType='video'">视频 ({{ counts.video }})</button>
        <button :class="{active:mediaType==='audio'}" @click="mediaType='audio'">音频 ({{ counts.audio }})</button>
      </div>

      <div class="works-filter-row">
        <label class="works-sort">
          <span>⇵</span>
          <select v-model="sortMode">
            <option value="newest">最近生成</option>
            <option value="oldest">最早生成</option>
          </select>
        </label>

        <label>项目：
          <select v-model="projectFilter">
            <option value="all">全部</option>
            <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.label }}</option>
          </select>
        </label>

        <label>类型：
          <select :value="mediaType" @change="mediaType=($event.target as HTMLSelectElement).value as any">
            <option value="all">全部</option>
            <option value="image">图片</option>
            <option value="video">视频</option>
            <option value="audio">音频</option>
          </select>
        </label>

        <label>时间：
          <select v-model="timeFilter">
            <option value="all">全部</option>
            <option value="today">24 小时内</option>
            <option value="week">最近 7 天</option>
            <option value="month">最近 30 天</option>
          </select>
        </label>
      </div>

      <button class="works-refresh" :disabled="loading" @click="refresh"><RefreshCw :size="15" :class="{spin:loading}" />刷新</button>
    </section>

    <p v-if="error" class="inline-error">{{ error }}</p>
    <div v-if="!outputs.length&&!loading" class="panel empty-page">还没有生成作品。完成第一个任务后，输出会自动进入作品库。</div>
    <div v-else-if="!filteredOutputs.length&&!loading" class="panel empty-page">当前筛选条件下没有作品。</div>

    <section v-else class="works-grid">
      <article v-for="item in filteredOutputs" :key="item.id" class="panel works-card">
        <div :class="['works-preview',`type-${item.type}`]">
          <img
            v-if="item.type==='image'"
            :src="mediaUrl(item)"
            :alt="outputTitle(item)"
            loading="lazy"
            @load="recordImageMeta($event,item)"
          />

          <video
            v-else-if="item.type==='video'"
            :src="mediaUrl(item)"
            muted
            playsinline
            preload="metadata"
            @loadedmetadata="recordVideoMeta($event,item)"
            @click="openOutput(item)"
          ></video>

          <div v-else-if="item.type==='audio'" class="audio-preview">
            <div class="waveform"><i v-for="(height,index) in waveform" :key="index" :style="{height:`${height}%`}"></i></div>
            <div class="audio-time"><span class="audio-play"><Play :size="14" fill="currentColor"/></span><span>00:00 / {{ formatDuration(mediaInfo[item.id]?.duration) || '--:--' }}</span></div>
            <audio :src="fileUrl(item)" preload="metadata" @loadedmetadata="recordAudioMeta($event,item)"></audio>
          </div>

          <div v-else class="works-file-placeholder"><component :is="typeIcon(item.type)" :size="38"/></div>

          <span class="works-kind"><component :is="typeIcon(item.type)" :size="13"/>{{ typeLabel(item.type) }}</span>
          <span v-if="resolution(item)" class="works-resolution">{{ resolution(item) }}</span>
          <span v-if="item.type==='video' && formatDuration(mediaInfo[item.id]?.duration)" class="works-duration">{{ formatDuration(mediaInfo[item.id]?.duration) }}</span>
          <button v-if="item.type==='video'" class="works-play" @click.stop="openOutput(item)"><Play :size="19" fill="currentColor"/></button>
        </div>

        <div class="works-copy">
          <h3>{{ outputTitle(item) }}</h3>
          <p>工作流：{{ item.workflow_name || item.workflow_id }}</p>
          <span v-if="item.episode_id || item.project_id">项目：{{ item.episode_id || item.project_id }}<template v-if="item.shot_id"> · {{ item.shot_id }}</template></span>
          <span class="works-date"><Clock3 :size="13"/>{{ formatDate(item.created_at) }}</span>
        </div>

        <div class="works-actions">
          <button class="works-open" @click="openOutput(item)">打开结果</button>
          <button class="works-download" @click="downloadOutput(item)"><Download :size="14"/>下载</button>
          <button class="works-more" title="打开原始结果" @click="openOutput(item)"><MoreVertical :size="16"/></button>
        </div>
      </article>
    </section>
  </section>
</template>

<style scoped>
.works-library{display:grid;gap:14px}
.works-toolbar{display:flex;align-items:center;gap:18px;min-height:82px;padding:14px 18px}
.works-type-tabs{display:flex;gap:8px;flex-shrink:0}
.works-type-tabs button{height:40px;padding:0 17px;border:0;border-radius:11px;background:#f3f5f9;color:#59647e;font-size:12px;font-weight:650;cursor:pointer}
.works-type-tabs button.active{background:#6557e8;color:#fff;box-shadow:0 7px 16px rgba(101,87,232,.18)}
.works-filter-row{display:flex;align-items:center;gap:12px;flex:1;justify-content:center}
.works-filter-row label{display:flex;align-items:center;gap:6px;color:#75809b;font-size:11px;white-space:nowrap}
.works-filter-row select{height:36px;min-width:94px;border:1px solid #dce2ef;border-radius:9px;background:#fff;color:#4d5872;padding:0 28px 0 10px;font-size:11px;outline:none}
.works-sort{padding-left:4px}
.works-sort span{font-size:17px;color:#39445f}
.works-sort select{min-width:112px;border:0;padding-left:2px;font-weight:650}
.works-refresh{height:40px;margin-left:auto;border:0;border-radius:11px;background:#f4f6fa;color:#38435f;padding:0 14px;display:flex;align-items:center;gap:7px;font-size:11px;cursor:pointer}
.works-refresh:disabled{opacity:.55;cursor:not-allowed}

.works-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.works-card{overflow:hidden;padding:12px;border-radius:15px;min-width:0}
.works-preview{position:relative;height:181px;border-radius:11px;overflow:hidden;background:linear-gradient(135deg,#eef2ff,#f8eefd);display:grid;place-items:center;color:#7168dc}
.works-preview>img,.works-preview>video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center;display:block}
.works-preview>video{cursor:pointer;background:#111}
.works-kind{position:absolute;left:10px;top:10px;z-index:2;display:flex;align-items:center;gap:5px;height:28px;padding:0 9px;border-radius:9px;background:rgba(255,255,255,.94);color:#5d55d8;font-size:10px;font-weight:750;box-shadow:0 2px 8px rgba(30,36,70,.08)}
.works-resolution,.works-duration{position:absolute;right:9px;z-index:2;border-radius:8px;background:rgba(30,31,40,.64);color:#fff;padding:5px 7px;font-size:9px;font-weight:750}
.works-resolution{top:9px}.works-duration{bottom:9px}
.works-play{position:absolute;z-index:3;left:50%;top:50%;width:48px;height:48px;transform:translate(-50%,-50%);border:2px solid rgba(255,255,255,.88);border-radius:50%;background:rgba(33,39,55,.48);color:#fff;display:grid;place-items:center;cursor:pointer;backdrop-filter:blur(2px)}
.audio-preview{position:absolute;inset:0;padding:40px 18px 20px;background:linear-gradient(135deg,#f8efff,#f2efff);display:flex;flex-direction:column;justify-content:center;gap:18px}
.waveform{height:64px;display:flex;align-items:center;gap:3px}
.waveform i{display:block;flex:1;min-width:2px;border-radius:999px;background:linear-gradient(180deg,#ac8cff,#7164ef)}
.audio-time{display:flex;align-items:center;gap:10px;color:#323b59;font-size:10px}
.audio-play{width:36px;height:36px;border-radius:50%;background:#715cf0;color:#fff;display:grid;place-items:center}
.audio-preview audio{display:none}
.works-file-placeholder{display:grid;place-items:center;width:100%;height:100%}

.works-copy{padding:11px 2px 8px;min-height:91px}
.works-copy h3{margin:0 0 6px;font-size:14px;color:#1f2944;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.works-copy p,.works-copy>span{display:block;margin:0;color:#7d879f;font-size:9.5px;line-height:1.5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.works-date{display:flex!important;align-items:center;gap:5px;margin-top:3px!important}
.works-actions{display:grid;grid-template-columns:1.2fr .9fr 38px;gap:8px}
.works-actions button{height:38px;border:0;border-radius:9px;font-size:11px;font-weight:650;cursor:pointer}
.works-open{background:linear-gradient(135deg,#765bf2,#6655ea);color:#fff}
.works-download{background:#f3f5f9;color:#35405d;display:flex;align-items:center;justify-content:center;gap:6px}
.works-more{background:#f3f5f9;color:#35405d;display:grid;place-items:center}

@media(max-width:1350px){.works-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.works-filter-row{justify-content:flex-start;flex-wrap:wrap}.works-toolbar{align-items:flex-start;flex-wrap:wrap}}
@media(max-width:980px){.works-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){.works-grid{grid-template-columns:1fr}.works-toolbar{display:grid}.works-type-tabs{overflow:auto}.works-filter-row{display:grid;grid-template-columns:1fr 1fr}.works-refresh{margin-left:0}}
</style>
