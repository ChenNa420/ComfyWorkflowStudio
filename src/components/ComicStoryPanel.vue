<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  ArrowLeft, ArrowRight, BookOpenCheck, Braces, CheckCircle2, CircleAlert,
  Copy, ExternalLink, FileText, Film, FolderSearch, LoaderCircle, RefreshCw,
  Sparkles, WandSparkles, Wifi, WifiOff,
} from 'lucide-vue-next'

type Collection = { name:string; path:string; kind:string; itemCount:number; sizeBytes:number; formats:Record<string,number> }
type Issue = { token:string; name:string; filename:string; extension:string; sizeBytes:number; pageCount?:number|null; coverUrl:string; fileUrl:string; modifiedAt?:string; folder?:string; error?:string|null }
type DirectorStatus = 'DRAFT'|'WAITING_GPT'|'RECEIVING'|'COMPLETED'|'FAILED'
type DirectorTask = {
  id:string
  status:DirectorStatus
  source:{ token:string; name:string; filename:string; pageCount:number; selectedPages:number[]; pages:Array<{ref:string;page:number;imageUrl:string;thumbnailUrl:string}> }
  settings:Record<string,unknown>
  createdAt:string
  updatedAt:string
}
type DirectorShot = {
  shotId:string|number
  title:string
  duration:number
  storyPurpose?:string
  speaker?:string|null
  english?:string
  chinese?:string
  keyframeDescription?:string
  imagePrompt:string
  videoPrompt:string
  negativePrompt?:string
  sourcePages:number[]
}
type DirectorResult = {
  sourceUnderstanding?:Record<string,unknown>
  creativeStory:{ title:string; summary?:string; story?:string; adaptationNotes?:string[] }
  characterDefinitions?:Array<Record<string,unknown>>
  sceneDefinitions?:Array<Record<string,unknown>>
  shots:DirectorShot[]
  episode?:Record<string,unknown>
}

const emit = defineEmits<{ navigate:[page:string] }>()
const rootPath = ref('')
const suggestedRoots = ref<string[]>([])
const collections = ref<Collection[]>([])
const selectedCollection = ref<Collection|null>(null)
const issues = ref<Issue[]>([])
const selectedIssue = ref<Issue|null>(null)
const currentPage = ref(1)
const selectedPages = ref<number[]>([])
const loading = ref('')
const error = ref('')
const notice = ref('')
const issueSearch = ref('')
const issueYear = ref('')
const activeTask = ref<DirectorTask|null>(null)
const gptResult = ref<DirectorResult|null>(null)
const manualJson = ref('')
const promptCopied = ref(false)
const gptUrl = ref('')
const webMcpAvailable = ref(false)
const webMcpRegistered = ref(false)
const webMcpError = ref('')
let lifecycle = new AbortController()

const settings = ref({
  targetAge:'3-6岁',
  level:'Pre-A1',
  style:'温馨冒险',
  language:'中英双语',
  duration:30,
  aspectRatio:'9:16',
  adaptationStrength:'high',
  preserveVisualMood:true,
  preserveComposition:true,
  replaceCharacters:true,
  allowEndingChange:true,
  extraRequest:'',
})

const workflowStep = computed(()=>gptResult.value?4:activeTask.value?3:selectedIssue.value?2:1)
const previewUrl = computed(()=>selectedIssue.value ? `/api/comic-story/page/${selectedIssue.value.token}/${currentPage.value}` : '')
const selectedPagesSorted = computed(()=>[...selectedPages.value].sort((a,b)=>a-b))
const selectedPagesText = computed(()=>selectedPagesSorted.value.join(', ') || '尚未选择')
const issueYears = computed(()=>Array.from(new Set(issues.value.map(x=>(x.filename.match(/(?:19|20)\d{2}/)||[])[0]).filter(Boolean))).sort().reverse())
const filteredIssues = computed(()=>issues.value.filter(item=>{
  const needle=issueSearch.value.trim().toLowerCase()
  const year=(item.filename.match(/(?:19|20)\d{2}/)||[])[0]||''
  return (!needle||`${item.name} ${item.filename} ${item.folder||''}`.toLowerCase().includes(needle))&&(!issueYear.value||year===issueYear.value)
}))
const visiblePages = computed(()=>{
  const total=selectedIssue.value?.pageCount||1
  const windowSize=24
  let start=Math.max(1,currentPage.value-Math.floor(windowSize/2))
  let end=Math.min(total,start+windowSize-1)
  start=Math.max(1,end-windowSize+1)
  return Array.from({length:end-start+1},(_,i)=>start+i)
})
const estimatedShots = computed(()=>{
  const base=Math.max(3,Math.round(settings.value.duration/6))
  return `${Math.max(3,base-1)}–${Math.min(12,base+1)}`
})
const directorPrompt = computed(()=>{
  if(!activeTask.value)return ''
  return `你正在为 ComfyWorkflowStudio 执行 GPT Director Task ${activeTask.value.id}。\n\n请先调用 WebMCP 工具 get_comic_story_task，taskId=${activeTask.value.id}，读取漫画来源、选中页和改编设置。\n\n目标：理解选中漫画页面中的故事与画面关系，然后重新创作成适合儿童英语动画的“自己的故事”。不要机械翻译或逐格复刻。可以参考原画面的氛围和构图，但新故事、角色与对白必须遵循任务中的改编设置。\n\n请自动决定合理镜头数量，不固定 6 镜头。每个镜头生成 title、duration、storyPurpose、speaker、english、chinese、keyframeDescription、imagePrompt、videoPrompt、negativePrompt、sourcePages。sourcePages 只能引用任务选中的页。\n\n如果当前环境无法直接看到 page imageUrl，请先让我上传任务中的选中页图片，不要猜画面内容。\n\n完成后调用 import_gpt_story 写回完整结果，最后调用 complete_gpt_story_task。不要调用 ComfyUI，不要生成视频。`
})

function formatBytes(value:number){
  if(!value)return '0 B'
  const units=['B','KB','MB','GB'];let size=value;let index=0
  while(size>=1024&&index<units.length-1){size/=1024;index++}
  return `${size.toFixed(index>1?1:0)} ${units[index]}`
}

async function postJson(url:string,body:any){
  const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  const payload=await response.json().catch(()=>({}))
  if(!response.ok)throw new Error(payload?.detail?.message||payload?.detail?.code||payload?.detail||`HTTP ${response.status}`)
  return payload
}

async function loadSuggestedRoots(){
  try{
    const response=await fetch('/api/comic-story/suggested-roots')
    if(response.ok){
      const value=await response.json()
      suggestedRoots.value=value.roots||[]
      if(!rootPath.value&&suggestedRoots.value.length){rootPath.value=suggestedRoots.value[0];await scanRoot()}
    }
  }catch{}
}

async function scanRoot(){
  if(!rootPath.value.trim())return
  loading.value='scan';error.value=''
  try{
    const value=await postJson('/api/comic-story/scan',{path:rootPath.value.trim()})
    collections.value=value.collections||[];selectedCollection.value=null;issues.value=[];clearIssue(false)
  }catch(value){error.value=value instanceof Error?value.message:'扫描失败'}finally{loading.value=''}
}

async function chooseCollection(item:Collection){
  selectedCollection.value=item;loading.value='issues';error.value=''
  try{
    const value=await postJson('/api/comic-story/issues',{path:item.path,limit:200})
    issues.value=value.issues||[]
  }catch(value){error.value=value instanceof Error?value.message:'读取漫画失败'}finally{loading.value=''}
}

function chooseIssue(item:Issue){
  selectedIssue.value=item
  currentPage.value=1
  selectedPages.value=[1]
  activeTask.value=null
  gptResult.value=null
  manualJson.value=''
  error.value=''
  notice.value=''
  persistBridgeState()
}

function clearIssue(resetCollection=true){
  selectedIssue.value=null
  currentPage.value=1
  selectedPages.value=[]
  activeTask.value=null
  gptResult.value=null
  manualJson.value=''
  if(resetCollection){notice.value=''}
  persistBridgeState()
}

function movePage(offset:number){
  const max=selectedIssue.value?.pageCount||1
  currentPage.value=Math.min(max,Math.max(1,currentPage.value+offset))
}

function togglePage(page:number){
  error.value=''
  currentPage.value=page
  const values=new Set(selectedPages.value)
  if(values.has(page))values.delete(page)
  else{
    if(values.size>=12){error.value='GPT Director 第一版每个任务最多选择 12 页。';return}
    values.add(page)
  }
  selectedPages.value=[...values].sort((a,b)=>a-b)
  activeTask.value=null
  gptResult.value=null
  persistBridgeState()
}

function selectCurrentPage(){
  if(!selectedPages.value.includes(currentPage.value))togglePage(currentPage.value)
}

function saveGptUrl(){
  const value=gptUrl.value.trim()
  try{localStorage.setItem('cws-gpt-director-url',value)}catch{}
  notice.value=value?'GPT 页面地址已保存到本浏览器。':'已清空 GPT 页面地址，将打开 ChatGPT 首页。'
}

function pageRef(page:number){return `P${String(page).padStart(3,'0')}`}

function createTask(){
  if(!selectedIssue.value){error.value='请先选择漫画。';return}
  if(!selectedPagesSorted.value.length){error.value='至少选择 1 个漫画页面。';return}
  const now=new Date().toISOString()
  const origin=window.location.origin
  activeTask.value={
    id:crypto.randomUUID(),
    status:'WAITING_GPT',
    source:{
      token:selectedIssue.value.token,
      name:selectedIssue.value.name,
      filename:selectedIssue.value.filename,
      pageCount:selectedIssue.value.pageCount||1,
      selectedPages:selectedPagesSorted.value,
      pages:selectedPagesSorted.value.map(page=>({
        ref:pageRef(page),page,
        imageUrl:`${origin}/api/comic-story/page/${selectedIssue.value!.token}/${page}`,
        thumbnailUrl:`${origin}/api/comic-story/page/${selectedIssue.value!.token}/${page}?thumbnail=true`,
      })),
    },
    settings:{...settings.value},
    createdAt:now,
    updatedAt:now,
  }
  gptResult.value=null
  error.value=''
  notice.value='GPT Director Task 已创建。可以复制任务说明并打开童语工坊 GPT。'
  persistBridgeState()
}

function validateResult(value:any):DirectorResult{
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('GPT 返回结果必须是 JSON 对象。')
  if(!value.creativeStory||typeof value.creativeStory!=='object'||!String(value.creativeStory.title||'').trim())throw new Error('creativeStory.title 不能为空。')
  if(!Array.isArray(value.shots)||!value.shots.length)throw new Error('shots 至少需要 1 个镜头。')
  if(value.shots.length>24)throw new Error('GPT Director 最多接收 24 个镜头。')
  const ids=new Set<string>()
  const allowed=new Set(selectedPagesSorted.value)
  for(const [index,raw] of value.shots.entries()){
    if(!raw||typeof raw!=='object')throw new Error(`Shot ${index+1} 必须是对象。`)
    const id=String(raw.shotId??'').trim()
    if(!id)throw new Error(`Shot ${index+1} 缺少 shotId。`)
    if(ids.has(id))throw new Error(`shotId ${id} 重复。`)
    ids.add(id)
    const duration=Number(raw.duration)
    if(!Number.isFinite(duration)||duration<=0||duration>10)throw new Error(`Shot ${id} duration 必须在 0–10 秒之间。`)
    if(!String(raw.imagePrompt||'').trim()||!String(raw.videoPrompt||'').trim())throw new Error(`Shot ${id} 缺少 imagePrompt 或 videoPrompt。`)
    if(!Array.isArray(raw.sourcePages)||!raw.sourcePages.length)throw new Error(`Shot ${id} 必须提供 sourcePages。`)
    if(raw.sourcePages.some((page:any)=>!Number.isInteger(page)||!allowed.has(page)))throw new Error(`Shot ${id} 引用了未选择的 sourcePages。`)
  }
  return value as DirectorResult
}

function buildEpisode(result:DirectorResult){
  if(result.episode&&typeof result.episode==='object')return result.episode
  const characterIds=(result.characterDefinitions||[]).map((item:any)=>String(item.id||item.key||'')).filter(Boolean)
  return {
    schemaVersion:'gpt-director-1.0',
    title:result.creativeStory.title,
    story:result.creativeStory.story||result.creativeStory.summary||'',
    style:settings.value.style,
    audience:settings.value.targetAge,
    language:settings.value.language,
    level:settings.value.level,
    aspectRatio:settings.value.aspectRatio,
    duration:result.shots.reduce((sum,item)=>sum+Number(item.duration||0),0),
    source:{fileToken:selectedIssue.value?.token,sourceName:selectedIssue.value?.name,selectedPages:selectedPagesSorted.value},
    characters:characterIds,
    characterDefinitions:result.characterDefinitions||[],
    sceneDefinitions:result.sceneDefinitions||[],
    shots:result.shots.map((shot,index)=>({
      id:index+1,
      shotId:String(shot.shotId),
      title:shot.title||`Shot ${index+1}`,
      duration:Number(shot.duration),
      storyPurpose:shot.storyPurpose||'',
      speaker:shot.speaker??null,
      english:shot.english||'',
      chinese:shot.chinese||'',
      keyframeDescription:shot.keyframeDescription||'',
      imagePrompt:shot.imagePrompt,
      videoPrompt:shot.videoPrompt,
      negativePrompt:shot.negativePrompt||'',
      sourcePage:shot.sourcePages[0],
      sourcePages:shot.sourcePages,
    })),
  }
}

function acceptGptResult(taskId:string,value:any){
  if(!activeTask.value||activeTask.value.id!==taskId)throw new Error('taskId 与当前 GPT Director Task 不匹配。')
  const result=validateResult(value)
  gptResult.value=result
  activeTask.value={...activeTask.value,status:'COMPLETED',updatedAt:new Date().toISOString()}
  const episode=buildEpisode(result)
  sessionStorage.setItem('cws-gpt-director-result',JSON.stringify(result))
  sessionStorage.setItem('cws-comic-story-episode',JSON.stringify(episode))
  notice.value=`GPT 已返回 ${result.shots.length} 个镜头，故事与提示词已写回当前工作台 Session。`
  persistBridgeState()
  return {taskId,shotCount:result.shots.length,title:result.creativeStory.title}
}

function completeTask(taskId:string){
  if(!activeTask.value||activeTask.value.id!==taskId)throw new Error('taskId 与当前 GPT Director Task 不匹配。')
  if(!gptResult.value)throw new Error('尚未收到 import_gpt_story 结果。')
  activeTask.value={...activeTask.value,status:'COMPLETED',updatedAt:new Date().toISOString()}
  persistBridgeState()
  return {taskId,status:'COMPLETED'}
}

async function importManualResult(){
  error.value=''
  if(!activeTask.value){error.value='请先创建 GPT Director Task。';return}
  try{
    acceptGptResult(activeTask.value.id,JSON.parse(manualJson.value))
  }catch(value){error.value=value instanceof Error?value.message:'导入失败'}
}

async function copyTaskPrompt(){
  if(!directorPrompt.value)return
  try{
    await navigator.clipboard.writeText(directorPrompt.value)
    promptCopied.value=true
    window.setTimeout(()=>promptCopied.value=false,1400)
  }catch{error.value='浏览器未允许复制，请手动复制任务说明。'}
}

async function openGpt(){
  if(!activeTask.value)createTask()
  if(!activeTask.value)return
  await copyTaskPrompt()
  let url=gptUrl.value.trim()||'https://chatgpt.com/'
  if(!/^https?:\/\//i.test(url))url=`https://${url}`
  window.open(url,'_blank','noopener,noreferrer')
}

function persistBridgeState(){
  try{
    if(activeTask.value)sessionStorage.setItem('cws-gpt-director-task',JSON.stringify(activeTask.value))
    else sessionStorage.removeItem('cws-gpt-director-task')
    if(selectedIssue.value)sessionStorage.setItem('cws-gpt-director-source',JSON.stringify({issue:selectedIssue.value,selectedPages:selectedPages.value,currentPage:currentPage.value}))
  }catch{}
}

function restoreBridgeState(){
  try{
    gptUrl.value=localStorage.getItem('cws-gpt-director-url')||''
    const source=sessionStorage.getItem('cws-gpt-director-source')
    if(source){const parsed=JSON.parse(source);selectedIssue.value=parsed.issue||null;selectedPages.value=Array.isArray(parsed.selectedPages)?parsed.selectedPages:[];currentPage.value=Number(parsed.currentPage)||1}
    const task=sessionStorage.getItem('cws-gpt-director-task')
    if(task)activeTask.value=JSON.parse(task)
    const result=sessionStorage.getItem('cws-gpt-director-result')
    if(result)gptResult.value=validateResult(JSON.parse(result))
  }catch{}
}

async function registerWebMcp(){
  const context=(document as any).modelContext
  webMcpAvailable.value=!!context?.registerTool
  if(!context?.registerTool){webMcpError.value='当前浏览器没有 document.modelContext.registerTool；可使用复制任务说明 + 手动导入 JSON。';return}
  try{
    lifecycle.abort();lifecycle=new AbortController()
    await Promise.all([
      Promise.resolve(context.registerTool({
        name:'get_comic_story_task',
        description:'读取 ComfyWorkflowStudio 当前 GPT Director 漫画改编任务、选中页元数据和改编设置。',
        inputSchema:{type:'object',properties:{taskId:{type:'string'}},required:['taskId'],additionalProperties:false},
        annotations:{readOnlyHint:true},
        async execute(input:any){
          if(!activeTask.value||input?.taskId!==activeTask.value.id)throw new Error('GPT Director task not found')
          return JSON.parse(JSON.stringify(activeTask.value))
        },
      },{signal:lifecycle.signal})),
      Promise.resolve(context.registerTool({
        name:'import_gpt_story',
        description:'将 GPT 编剧导演生成的故事、角色、场景、动态镜头和关键帧/视频提示词写回 ComfyWorkflowStudio。',
        inputSchema:{type:'object',properties:{taskId:{type:'string'},result:{type:'object',additionalProperties:true}},required:['taskId','result'],additionalProperties:false},
        annotations:{readOnlyHint:false,untrustedContentHint:true},
        async execute(input:any){return acceptGptResult(String(input?.taskId||''),input?.result)}
      },{signal:lifecycle.signal})),
      Promise.resolve(context.registerTool({
        name:'complete_gpt_story_task',
        description:'确认当前 GPT Director 任务已完成。必须在 import_gpt_story 成功后调用。',
        inputSchema:{type:'object',properties:{taskId:{type:'string'}},required:['taskId'],additionalProperties:false},
        annotations:{readOnlyHint:false},
        async execute(input:any){return completeTask(String(input?.taskId||''))}
      },{signal:lifecycle.signal})),
    ])
    webMcpRegistered.value=true
    webMcpError.value=''
  }catch(value){
    webMcpRegistered.value=false
    webMcpError.value=value instanceof Error?value.message:'WebMCP 注册失败'
  }
}

function go(page:string){emit('navigate',page)}

onMounted(async()=>{
  restoreBridgeState()
  await registerWebMcp()
  await loadSuggestedRoots()
})
onUnmounted(()=>lifecycle.abort())
</script>

<template>
  <div class="director-shell">
    <section class="director-hero panel">
      <div>
        <span class="eyebrow">COMIC STORY · GPT DIRECTOR BRIDGE</span>
        <h2>漫画拆故事 · GPT 编剧导演</h2>
        <p>选择 1–12 个 PDF/漫画页面，把故事和画面参考交给“童语工坊 · AI动画编剧导演”。GPT 负责理解、重新创作、拆镜头并生成关键帧与视频提示词，再通过 WebMCP 自动返回工作台。</p>
      </div>
      <div :class="['bridge-pill',{ok:webMcpRegistered}]">
        <Wifi v-if="webMcpRegistered" :size="16"/><WifiOff v-else :size="16"/>
        <div><b>WebMCP {{webMcpRegistered?'已就绪':'未连接'}}</b><small>{{webMcpRegistered?'3 个工具已注册':'可使用复制/导入备用流程'}}</small></div>
      </div>
    </section>

    <section class="step-strip panel">
      <div v-for="item in [{n:1,t:'选择漫画',s:'选择来源 PDF'},{n:2,t:'选择页面与改编',s:'1–12 页任意选择'},{n:3,t:'交给 GPT',s:'WebMCP / 手动备用'},{n:4,t:'获取结果',s:'故事、分镜与提示词'}]" :key="item.n" :class="['step-card',{active:workflowStep===item.n,done:workflowStep>item.n}]">
        <span>{{item.n}}</span><div><b>{{item.t}}</b><small>{{item.s}}</small></div>
      </div>
    </section>

    <p v-if="error" class="director-alert error"><CircleAlert :size="16"/>{{error}}</p>
    <p v-if="notice" class="director-alert success"><CheckCircle2 :size="16"/>{{notice}}</p>

    <template v-if="!selectedIssue">
      <section class="source-layout">
        <article class="panel source-picker">
          <div class="section-title"><div><span class="eyebrow">SOURCE</span><h3>选择本地漫画目录</h3><p>支持 PDF、CBZ、ZIP 与图片文件夹。这里只建立索引，不修改源文件。</p></div><FolderSearch :size="30"/></div>
          <div class="path-row"><input v-model="rootPath" placeholder="例如 F:\BaiduNetdiskDownload\漫画目录"/><button class="primary" :disabled="loading==='scan'" @click="scanRoot"><LoaderCircle v-if="loading==='scan'" class="spin" :size="15"/>扫描目录</button></div>
          <div v-if="suggestedRoots.length" class="root-list"><span>检测到：</span><button v-for="root in suggestedRoots" :key="root" @click="rootPath=root">{{root}}</button></div>
        </article>

        <article v-if="collections.length" class="panel collection-panel">
          <div class="section-title"><div><span class="eyebrow">LIBRARY</span><h3>漫画系列</h3></div><span class="count-pill">{{collections.length}}</span></div>
          <div class="collection-list"><button v-for="item in collections" :key="item.path" :class="['collection-row',{active:selectedCollection?.path===item.path}]" @click="chooseCollection(item)"><div class="collection-icon"><BookOpenCheck :size="20"/></div><div><b>{{item.name}}</b><small>{{item.itemCount}} 个文件 · {{formatBytes(item.sizeBytes)}}</small></div><span>{{Object.keys(item.formats).join(' / ').toUpperCase()}}</span><ArrowRight :size="16"/></button></div>
        </article>
      </section>

      <section v-if="selectedCollection" class="panel issue-panel">
        <div class="section-title"><div><span class="eyebrow">ISSUES</span><h3>{{selectedCollection.name}}</h3></div><span class="count-pill">{{filteredIssues.length}} / {{issues.length}}</span></div>
        <div class="issue-filters"><input v-model="issueSearch" placeholder="搜索漫画、年份或文件夹…"/><select v-model="issueYear"><option value="">全部年份</option><option v-for="year in issueYears" :key="year">{{year}}</option></select></div>
        <div v-if="loading==='issues'" class="empty-state"><LoaderCircle class="spin" :size="22"/>正在读取漫画…</div>
        <div v-else-if="!filteredIssues.length" class="empty-state">没有匹配的漫画。</div>
        <div v-else class="issue-grid"><button v-for="item in filteredIssues.slice(0,96)" :key="item.token||item.filename" class="issue-card" :disabled="!!item.error" @click="!item.error&&chooseIssue(item)"><div class="cover"><img v-if="item.coverUrl" :src="item.coverUrl" loading="lazy"/><FileText :size="28"/></div><b>{{item.name}}</b><small v-if="item.error">读取失败 · {{item.error}}</small><small v-else>{{item.pageCount||'?'}} 页 · {{formatBytes(item.sizeBytes)}}</small></button></div>
      </section>
    </template>

    <template v-else>
      <section class="workspace-grid">
        <article class="panel page-card">
          <div class="section-title compact"><div><span class="step-number">1</span><div><h3>选择漫画页面</h3><p>{{selectedIssue.filename}} · {{selectedIssue.pageCount||'?'}} 页</p></div></div><button class="ghost" @click="clearIssue()">更换漫画</button></div>
          <div class="page-preview"><img :src="previewUrl"/><div class="page-nav"><button class="ghost square" @click="movePage(-1)"><ArrowLeft :size="15"/></button><b>P{{currentPage}} / {{selectedIssue.pageCount||'?'}}</b><button class="ghost square" @click="movePage(1)"><ArrowRight :size="15"/></button><button class="secondary small" @click="selectCurrentPage">选择当前页</button></div></div>
          <div class="thumb-head"><b>页面缩略图</b><span>已选 {{selectedPagesSorted.length}} 页：{{selectedPagesText}}</span></div>
          <div class="page-thumbs"><button v-for="page in visiblePages" :key="page" :class="{active:page===currentPage,selected:selectedPages.includes(page)}" @click="togglePage(page)"><img :src="`/api/comic-story/page/${selectedIssue.token}/${page}?thumbnail=true`" loading="lazy"/><span>P{{page}}</span><i v-if="selectedPages.includes(page)">✓</i></button></div>
          <div class="page-window-note"><span>当前显示 P{{visiblePages[0]}}–P{{visiblePages[visiblePages.length-1]}}</span><button class="text-button" @click="selectedPages=[];activeTask=null;gptResult=null">清空选择</button></div>
        </article>

        <article class="panel settings-card">
          <div class="section-title compact"><div><span class="step-number">2</span><div><h3>设置改编方式</h3><p>让 GPT 把原漫画变成自己的儿童英语动画故事。</p></div></div></div>
          <div class="settings-form">
            <label>目标年龄<select v-model="settings.targetAge"><option>3-6岁</option><option>4-7岁</option><option>6-9岁</option><option>9-12岁</option></select></label>
            <label>英语等级<select v-model="settings.level"><option>Pre-A1</option><option>A1</option><option>A2</option></select></label>
            <label>故事风格<select v-model="settings.style"><option>温馨冒险</option><option>日常治愈</option><option>轻松搞笑</option><option>悬疑奇趣</option><option>知识科普</option></select></label>
            <label>语言<select v-model="settings.language"><option>中英双语</option><option>英语</option><option>中文（简体）</option></select></label>
            <label>目标时长<input v-model.number="settings.duration" type="number" min="10" max="120" step="5"/></label>
            <label>画幅<select v-model="settings.aspectRatio"><option>9:16</option><option>16:9</option><option>1:1</option></select></label>
            <label class="span-two">改编强度<select v-model="settings.adaptationStrength"><option value="low">轻度 · 基本保留原剧情</option><option value="medium">中度 · 保留核心事件，重写角色与对白</option><option value="high">高度原创 · 只保留故事灵感与结构</option></select></label>
          </div>
          <div class="toggle-list">
            <label><span><b>保留原画面氛围</b><small>色调、时间、情绪可以作为视觉参考</small></span><input v-model="settings.preserveVisualMood" type="checkbox"/></label>
            <label><span><b>保留构图参考</b><small>允许关键帧借用原画面的站位和镜头关系</small></span><input v-model="settings.preserveComposition" type="checkbox"/></label>
            <label><span><b>替换角色</b><small>把原角色改造成新的儿童动画角色</small></span><input v-model="settings.replaceCharacters" type="checkbox"/></label>
            <label><span><b>允许改变结局</b><small>高改编强度下可以创造新的收束方式</small></span><input v-model="settings.allowEndingChange" type="checkbox"/></label>
          </div>
          <label class="extra-request">额外要求<textarea v-model="settings.extraRequest" rows="3" placeholder="例如：改成小熊和小猫的友情故事；对白简单；不要恐怖元素。"/></label>
          <div class="estimate-row"><span>预计镜头数 <b>{{estimatedShots}}</b></span><span>单镜头建议 <b>4–8 秒</b></span><span>最终镜头数由 GPT 根据故事决定</span></div>
        </article>

        <article class="panel task-card">
          <div class="section-title compact"><div><span class="step-number">3</span><div><h3>创建 GPT 编剧导演任务</h3><p>GPT 负责故事创作与关键帧提示词，工作台负责接收结构化结果。</p></div></div></div>
          <button class="primary task-create" :disabled="!selectedPagesSorted.length" @click="createTask"><WandSparkles :size="17"/>{{activeTask?'重新创建 GPT Task':'创建 GPT 编剧导演 Task'}}</button>

          <div v-if="activeTask" class="task-summary">
            <div class="task-status"><CheckCircle2 :size="18"/><div><b>{{activeTask.status==='COMPLETED'?'结果已返回':'任务已创建'}}</b><small>{{activeTask.updatedAt.replace('T',' ').slice(0,19)}}</small></div></div>
            <dl><div><dt>Task ID</dt><dd>{{activeTask.id}}</dd></div><div><dt>漫画</dt><dd>{{activeTask.source.filename}}</dd></div><div><dt>选择页面</dt><dd>{{activeTask.source.selectedPages.join(', ')}}</dd></div><div><dt>改编设置</dt><dd>{{settings.targetAge}} · {{settings.level}} · {{settings.style}} · {{settings.adaptationStrength==='high'?'高度原创':settings.adaptationStrength==='medium'?'中度':'轻度'}}</dd></div></dl>
          </div>

          <label class="gpt-url">童语工坊 GPT 页面地址<input v-model="gptUrl" placeholder="粘贴你的自定义 GPT 链接；留空则打开 ChatGPT 首页" @change="saveGptUrl"/></label>
          <div class="task-actions"><button class="gpt-open" :disabled="!activeTask" @click="openGpt"><Sparkles :size="16"/>打开童语工坊 GPT<ExternalLink :size="15"/></button><button class="secondary" :disabled="!activeTask" @click="copyTaskPrompt"><Copy :size="15"/>{{promptCopied?'已复制':'复制任务说明'}}</button></div>
          <div :class="['mcp-state',{ok:webMcpRegistered}]"><div><component :is="webMcpRegistered?Wifi:WifiOff" :size="18"/><span><b>WebMCP {{webMcpRegistered?'可用':'不可用'}}</b><small>{{webMcpRegistered?'get_comic_story_task / import_gpt_story / complete_gpt_story_task':'复制任务说明到 GPT，完成后把 JSON 粘贴到下方即可。'}}</small></span></div><button class="ghost small" @click="registerWebMcp"><RefreshCw :size="14"/>重新检测</button></div>
          <p v-if="webMcpError" class="mcp-help">{{webMcpError}}</p>
        </article>
      </section>

      <section class="panel result-stage">
        <div class="section-title"><div><span class="step-number">4</span><div><h3>{{gptResult?'GPT 已返回故事与分镜':'等待 GPT 返回结果'}}</h3><p>{{gptResult?'结果已写入当前 Session，可以继续进入分镜与动画生产。':'WebMCP 成功时会自动回填；否则可使用下方手动导入 JSON。'}}</p></div></div><span v-if="gptResult" class="ready-pill">{{gptResult.shots.length}} Shots · READY</span></div>

        <template v-if="gptResult">
          <div class="result-overview"><article><span>故事标题</span><b>{{gptResult.creativeStory.title}}</b><p>{{gptResult.creativeStory.summary||gptResult.creativeStory.story||'—'}}</p></article><article><span>角色</span><b>{{gptResult.characterDefinitions?.length||0}}</b><p>统一角色定义将交给后续角色管理与关键帧流程。</p></article><article><span>场景</span><b>{{gptResult.sceneDefinitions?.length||0}}</b><p>场景与镜头 sourcePages 保持可追溯。</p></article><article><span>镜头</span><b>{{gptResult.shots.length}}</b><p>动态镜头数量，不固定 6 个。</p></article></div>
          <div class="returned-shots"><article v-for="(shot,index) in gptResult.shots" :key="String(shot.shotId)"><div class="shot-thumb"><img :src="`/api/comic-story/page/${selectedIssue.token}/${shot.sourcePages[0]}`"/><span>S{{String(index+1).padStart(2,'0')}}</span></div><div><b>{{shot.title}}</b><p>{{shot.chinese||shot.storyPurpose||shot.english||'—'}}</p><small>P{{shot.sourcePages.join(', P')}} · {{shot.duration}} 秒 · {{shot.speaker||'无对白/未指定'}}</small><details><summary>查看关键帧与视频提示词</summary><strong>关键帧</strong><p>{{shot.keyframeDescription||'—'}}</p><strong>Image Prompt</strong><p>{{shot.imagePrompt}}</p><strong>Video Prompt</strong><p>{{shot.videoPrompt}}</p></details></div></article></div>
          <div class="downstream-actions"><button class="secondary" @click="go('characters')">角色管理</button><button class="secondary" @click="go('storyboard')">分镜设计</button><button class="primary" @click="go('workbench')"><Film :size="15"/>进入成片工作台</button></div>
        </template>

        <template v-else>
          <div class="waiting-flow"><div class="done"><span>✓</span><b>任务已创建</b><small>{{activeTask?'可打开 GPT':'先创建 Task'}}</small></div><i></i><div :class="{active:!!activeTask}"><span>2</span><b>GPT 处理中</b><small>拆故事 / 重写 / 分镜</small></div><i></i><div><span>3</span><b>接收结果</b><small>WebMCP 自动回填</small></div><i></i><div><span>4</span><b>完成</b><small>进入动画生产</small></div></div>
          <details class="manual-import"><summary>WebMCP 不可用？使用手动 JSON 导入</summary><p>让 GPT 输出完整 GPTDirectorResult JSON，然后粘贴到这里。工作台会检查镜头 ID、时长、Prompt 与 sourcePages。</p><textarea v-model="manualJson" rows="8" placeholder='{"creativeStory":{"title":"..."},"shots":[...]}'></textarea><button class="secondary" :disabled="!activeTask||!manualJson.trim()" @click="importManualResult"><Braces :size="15"/>校验并导入 GPT 结果</button></details>
        </template>
      </section>
    </template>
  </div>
</template>

<style scoped>
.director-shell{display:grid;gap:14px;color:#26324b}.director-hero{display:flex;justify-content:space-between;align-items:center;gap:24px;padding:24px 26px;background:linear-gradient(135deg,#fff 0%,#f5f8ff 58%,#f7f4ff 100%);border:1px solid #e9edf7}.director-hero h2{margin:5px 0 8px;font-size:28px;letter-spacing:-.5px}.director-hero p{margin:0;max-width:820px;color:#6d7893;font-size:12px;line-height:1.7}.eyebrow{font-size:9px;letter-spacing:1.2px;font-weight:800;color:#6a5ee8}.bridge-pill{min-width:220px;display:flex;align-items:center;gap:10px;padding:12px 14px;border-radius:13px;background:#fff7f7;border:1px solid #f0dede;color:#a45b63}.bridge-pill.ok{background:#effbf5;border-color:#cdebdc;color:#27845e}.bridge-pill b,.bridge-pill small{display:block}.bridge-pill b{font-size:11px}.bridge-pill small{font-size:9px;margin-top:2px;color:#7f8aa1}.step-strip{display:grid;grid-template-columns:repeat(4,1fr);padding:10px;gap:8px}.step-card{display:flex;align-items:center;gap:10px;padding:12px 14px;border-radius:13px;border:1px solid transparent;color:#8992a8}.step-card>span{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:#edf0f6;font-size:11px;font-weight:800}.step-card b,.step-card small{display:block}.step-card b{font-size:11px}.step-card small{font-size:9px;margin-top:3px}.step-card.active{border-color:#b9c9ff;background:#f4f7ff;color:#305fd8}.step-card.active>span{background:#3477ef;color:#fff;box-shadow:0 6px 14px rgba(52,119,239,.22)}.step-card.done{color:#398067}.step-card.done>span{background:#e3f7ed;color:#27845e}.director-alert{display:flex;align-items:center;gap:8px;margin:0;padding:11px 13px;border-radius:10px;font-size:11px}.director-alert.error{background:#fff2f4;border:1px solid #ffd8df;color:#b8475a}.director-alert.success{background:#effbf5;border:1px solid #d3efdf;color:#277a59}.source-layout{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(320px,.6fr);gap:14px}.source-picker,.collection-panel,.issue-panel,.page-card,.settings-card,.task-card,.result-stage{padding:18px}.section-title{display:flex;align-items:flex-start;justify-content:space-between;gap:15px}.section-title.compact>div:first-child{display:flex;align-items:flex-start;gap:10px}.section-title h3{margin:3px 0 4px;font-size:16px}.section-title p{margin:0;color:#7b859d;font-size:10px;line-height:1.55}.section-title>svg{color:#6a5ee8}.step-number{width:28px;height:28px;flex:0 0 auto;border-radius:50%;display:grid;place-items:center;background:#3477ef;color:#fff;font-size:11px;font-weight:800}.path-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;margin-top:15px}.path-row input,.issue-filters input,.issue-filters select,.settings-form input,.settings-form select,.gpt-url input,.extra-request textarea,.manual-import textarea{width:100%;min-width:0;border:1px solid #dfe5f1;border-radius:9px;background:#fbfcff;padding:10px;color:#34405c;outline:none}.path-row input:focus,.issue-filters input:focus,.settings-form input:focus,.settings-form select:focus,.gpt-url input:focus,.extra-request textarea:focus,.manual-import textarea:focus{border-color:#7da4f6;box-shadow:0 0 0 3px rgba(79,125,238,.08)}.root-list{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:9px;color:#8a93a9;font-size:9px}.root-list button{border:0;border-radius:8px;background:#f2f4f8;color:#5e6880;padding:6px 8px;cursor:pointer;max-width:100%;overflow-wrap:anywhere}.collection-list{display:grid;gap:7px;margin-top:12px;max-height:300px;overflow:auto}.collection-row{display:grid;grid-template-columns:38px minmax(0,1fr) auto auto;gap:9px;align-items:center;border:1px solid #e6eaf2;background:#fff;border-radius:10px;padding:9px;text-align:left;color:#39445f;cursor:pointer}.collection-row.active{border-color:#8ca9ef;background:#f6f8ff}.collection-icon{width:35px;height:35px;border-radius:9px;display:grid;place-items:center;background:#efedff;color:#6657e8}.collection-row b,.collection-row small{display:block}.collection-row b{font-size:10px}.collection-row small{font-size:8px;color:#8b94a9;margin-top:3px}.collection-row>span{font-size:8px;color:#8590aa}.count-pill,.ready-pill{padding:6px 9px;border-radius:999px;background:#eef3ff;color:#456dd1;font-size:9px;font-weight:800}.ready-pill{background:#e7f8ef;color:#21825c}.issue-filters{display:grid;grid-template-columns:minmax(0,1fr) 150px;gap:8px;margin-top:12px}.issue-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px;margin-top:12px}.issue-card{border:1px solid #e5e9f1;background:#fff;border-radius:11px;padding:8px;text-align:left;cursor:pointer;min-width:0}.issue-card:hover{border-color:#7fa0ee;box-shadow:0 8px 22px rgba(53,73,128,.08)}.cover{position:relative;height:142px;border-radius:8px;overflow:hidden;background:#f2f4f8;display:grid;place-items:center;color:#a0a8bb}.cover img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.issue-card b,.issue-card small{display:block}.issue-card b{font-size:9px;line-height:1.4;margin-top:7px;overflow-wrap:anywhere}.issue-card small{font-size:8px;color:#8c95a9;margin-top:4px}.empty-state{display:flex;align-items:center;justify-content:center;gap:8px;padding:28px;color:#8b94a8;font-size:11px}.workspace-grid{display:grid;grid-template-columns:minmax(360px,1.08fr) minmax(330px,.92fr) minmax(340px,.92fr);gap:14px;align-items:start}.ghost,.secondary,.primary,.gpt-open{border-radius:9px;padding:9px 12px;cursor:pointer;font-weight:700;font-size:10px;display:inline-flex;align-items:center;justify-content:center;gap:6px}.ghost{border:1px solid #e2e7f0;background:#fff;color:#66708a}.secondary{border:1px solid #dce3f2;background:#fff;color:#53607b}.primary{border:0;background:#3477ef;color:#fff;box-shadow:0 6px 14px rgba(52,119,239,.16)}button:disabled{opacity:.5;cursor:not-allowed}.small{padding:7px 9px;font-size:9px}.square{padding:7px;width:32px;height:32px}.page-preview{display:grid;justify-items:center;gap:8px;margin:12px 0}.page-preview>img{max-width:100%;max-height:420px;border-radius:10px;background:#f2f4f8;box-shadow:0 10px 26px rgba(34,47,84,.11)}.page-nav{display:flex;align-items:center;gap:7px}.page-nav b{font-size:10px}.thumb-head{display:flex;justify-content:space-between;gap:10px;align-items:center;margin:9px 0 7px;font-size:9px;color:#7d879e}.thumb-head b{font-size:10px;color:#44506a}.page-thumbs{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:6px;max-height:270px;overflow:auto;padding:2px}.page-thumbs button{position:relative;border:2px solid transparent;background:#f7f8fb;border-radius:8px;padding:4px;cursor:pointer;color:#7e889f}.page-thumbs button.active{border-color:#8ca9ef}.page-thumbs button.selected{border-color:#3477ef;background:#eef4ff}.page-thumbs img{width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:5px;background:#edf0f5}.page-thumbs span{display:block;font-size:8px;padding-top:3px}.page-thumbs i{position:absolute;right:4px;top:4px;width:18px;height:18px;border-radius:50%;display:grid;place-items:center;background:#3477ef;color:#fff;font-style:normal;font-size:10px}.page-window-note{display:flex;justify-content:space-between;align-items:center;margin-top:7px;color:#8a93a7;font-size:8px}.text-button{border:0;background:transparent;color:#4376dc;font-size:9px;cursor:pointer}.settings-form{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.settings-form label,.gpt-url,.extra-request{display:grid;gap:5px;color:#59637b;font-size:9px}.span-two{grid-column:1/-1}.toggle-list{display:grid;gap:7px;margin-top:12px}.toggle-list label{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px;border:1px solid #e9ecf3;border-radius:9px;background:#fcfdff}.toggle-list b,.toggle-list small{display:block}.toggle-list b{font-size:9px}.toggle-list small{font-size:8px;color:#8a93a7;margin-top:2px}.toggle-list input{width:34px;height:18px;accent-color:#3477ef}.extra-request{margin-top:12px}.extra-request textarea{resize:vertical}.estimate-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.estimate-row span{padding:6px 8px;border-radius:8px;background:#f5f7fb;color:#7a849a;font-size:8px}.estimate-row b{color:#485975}.task-create{width:100%;margin-top:14px;padding:12px}.task-summary{margin-top:11px;padding:12px;border:1px solid #dcefe5;background:#f3fbf7;border-radius:11px}.task-status{display:flex;align-items:center;gap:8px;color:#2a865f}.task-status b,.task-status small{display:block}.task-status b{font-size:10px}.task-status small{font-size:8px;color:#82908a;margin-top:2px}.task-summary dl{display:grid;gap:6px;margin:10px 0 0}.task-summary dl>div{display:grid;grid-template-columns:74px minmax(0,1fr);gap:8px;font-size:8px}.task-summary dt{color:#8a93a7}.task-summary dd{margin:0;color:#4f5a72;overflow-wrap:anywhere}.gpt-url{margin-top:11px}.task-actions{display:grid;grid-template-columns:1.1fr .9fr;gap:8px;margin-top:9px}.gpt-open{border:0;color:#fff;background:linear-gradient(135deg,#6f48ef,#7d4ee7 55%,#4c6ff0);box-shadow:0 7px 16px rgba(102,72,225,.2)}.mcp-state{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:12px;padding:10px;border:1px solid #f0dfe0;background:#fff7f7;border-radius:10px;color:#a35b61}.mcp-state.ok{border-color:#d4ecdf;background:#f1fbf6;color:#27825c}.mcp-state>div{display:flex;align-items:center;gap:8px}.mcp-state b,.mcp-state small{display:block}.mcp-state b{font-size:9px}.mcp-state small{font-size:7px;color:#818b9f;margin-top:2px;line-height:1.4}.mcp-help{margin:6px 0 0;font-size:8px;line-height:1.5;color:#8a7180}.result-stage{display:grid;gap:13px}.result-overview{display:grid;grid-template-columns:2fr repeat(3,1fr);gap:9px}.result-overview article{padding:12px;border:1px solid #e6eaf2;border-radius:10px;background:#fbfcff}.result-overview span,.result-overview b{display:block}.result-overview span{font-size:8px;color:#8a93a7}.result-overview b{font-size:15px;margin:4px 0;color:#34405c}.result-overview p{margin:0;font-size:8px;line-height:1.5;color:#7c869b}.returned-shots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.returned-shots>article{display:grid;grid-template-columns:112px minmax(0,1fr);gap:10px;padding:9px;border:1px solid #e6eaf2;border-radius:10px}.shot-thumb{position:relative}.shot-thumb img{width:112px;height:82px;object-fit:cover;border-radius:7px;background:#f1f3f7}.shot-thumb span{position:absolute;left:5px;top:5px;padding:3px 5px;border-radius:5px;background:rgba(28,38,60,.78);color:#fff;font-size:8px}.returned-shots b{font-size:10px}.returned-shots p{font-size:8px;line-height:1.5;margin:4px 0;color:#69758d}.returned-shots small{font-size:7px;color:#8d96a9}.returned-shots details{margin-top:6px;font-size:8px}.returned-shots summary{cursor:pointer;color:#4e70c7}.returned-shots details strong{display:block;margin-top:6px}.downstream-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}.waiting-flow{display:flex;align-items:center;justify-content:center;padding:18px 8px}.waiting-flow>div{text-align:center;min-width:120px;color:#919aaf}.waiting-flow>div.active,.waiting-flow>div.done{color:#4774dc}.waiting-flow>div.done{color:#28815c}.waiting-flow span{width:34px;height:34px;margin:0 auto 6px;border-radius:50%;display:grid;place-items:center;background:#edf0f5;font-size:10px;font-weight:800}.waiting-flow .active span{background:#e9f0ff;color:#3477ef}.waiting-flow .done span{background:#e6f7ee;color:#21825c}.waiting-flow b,.waiting-flow small{display:block}.waiting-flow b{font-size:9px}.waiting-flow small{font-size:7px;margin-top:3px}.waiting-flow>i{width:70px;height:1px;background:#dfe4ed}.manual-import{border-top:1px solid #edf0f5;padding-top:11px}.manual-import summary{cursor:pointer;font-size:9px;font-weight:700;color:#5b6881}.manual-import p{font-size:8px;color:#8790a5}.manual-import textarea{resize:vertical;margin-bottom:7px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:1400px){.workspace-grid{grid-template-columns:1fr 1fr}.task-card{grid-column:1/-1}.issue-grid{grid-template-columns:repeat(5,minmax(0,1fr))}.source-layout{grid-template-columns:1fr}.result-overview{grid-template-columns:1fr 1fr}}
@media(max-width:900px){.director-hero{align-items:flex-start;flex-direction:column}.step-strip{grid-template-columns:1fr 1fr}.workspace-grid{grid-template-columns:1fr}.task-card{grid-column:auto}.issue-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.returned-shots{grid-template-columns:1fr}.waiting-flow{align-items:stretch;flex-direction:column;gap:8px}.waiting-flow>i{width:1px;height:16px;margin:auto}.result-overview{grid-template-columns:1fr}.page-thumbs{grid-template-columns:repeat(5,minmax(0,1fr))}}
@media(max-width:560px){.step-strip{grid-template-columns:1fr}.path-row,.issue-filters,.settings-form,.task-actions{grid-template-columns:1fr}.issue-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.page-thumbs{grid-template-columns:repeat(4,minmax(0,1fr))}.returned-shots>article{grid-template-columns:90px minmax(0,1fr)}.shot-thumb img{width:90px}.bridge-pill{min-width:0;width:100%}.director-hero{padding:18px}.director-hero h2{font-size:23px}}
</style>
