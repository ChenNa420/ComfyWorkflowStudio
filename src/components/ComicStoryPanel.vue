<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowLeft, ArrowRight, BookOpenCheck, Braces, CircleCheck,
  FileText, Film, FolderSearch, LoaderCircle, ScanText, Sparkles,
} from 'lucide-vue-next'

type Collection = { name:string; path:string; kind:string; itemCount:number; sizeBytes:number; formats:Record<string,number> }
type Issue = { token:string; name:string; filename:string; extension:string; sizeBytes:number; pageCount?:number|null; coverUrl:string; fileUrl:string; modifiedAt?:string; folder?:string; error?:string|null }
type Analysis = { sourceName:string; pageCount:number; selectedPages:number[]; textExcerpt:string; keywords:string[]; analysisMode:string; aiReady:boolean; message:string; requiresAiEnrichment:boolean; provider:{name:string;enabled:boolean}; semanticAnalysis:Record<string,unknown> }
type Shot = { id:number; title:string; sourcePage:number; duration:number; sourceText:string; english:string; chinese:string; imagePrompt:string; videoPrompt:string; negativePrompt:string }
type Draft = { generationMode:string; requiresAiEnrichment:boolean; message:string; episode:{ title:string; style:string; audience:string; language:string; aspectRatio:string; source:any; shots:Shot[] } }

const emit = defineEmits<{ navigate:[page:string] }>()
const step = ref(1)
const rootPath = ref('')
const suggestedRoots = ref<string[]>([])
const collections = ref<Collection[]>([])
const selectedCollection = ref<Collection|null>(null)
const issues = ref<Issue[]>([])
const selectedIssue = ref<Issue|null>(null)
const currentPage = ref(1)
const startPage = ref(1)
const endPage = ref(10)
const analysis = ref<Analysis|null>(null)
const draft = ref<Draft|null>(null)
const loading = ref('')
const error = ref('')
const copied = ref(false)
const issueSearch = ref('')
const issueYear = ref('')
const provider = ref({name:'disabled',enabled:false})

const story = ref({ title:'', style:'温馨治愈', audience:'3-8岁儿童', language:'中文（简体）', shotCount:6, aspectRatio:'9:16', level:'Pre-A1', duration:30, fidelity:'balanced', adaptationStrength:'medium', educationalGoal:'', preserveCharacterNames:true, preserveDialogues:true, autoShotCount:false })
const previewUrl = computed(() => selectedIssue.value ? `/api/comic-story/page/${selectedIssue.value.token}/${currentPage.value}` : '')
const canAnalyze = computed(() => !!selectedIssue.value && startPage.value >= 1 && endPage.value >= startPage.value)
const jsonText = computed(() => draft.value ? JSON.stringify(draft.value.episode, null, 2) : '')
const issueYears = computed(()=>Array.from(new Set(issues.value.map(x=>(x.filename.match(/(?:19|20)\d{2}/)||[])[0]).filter(Boolean))).sort().reverse())
const filteredIssues = computed(()=>issues.value.filter(item=>{const needle=issueSearch.value.trim().toLowerCase();const year=(item.filename.match(/(?:19|20)\d{2}/)||[])[0]||'';return(!needle||`${item.name} ${item.filename} ${item.folder||''}`.toLowerCase().includes(needle))&&(!issueYear.value||year===issueYear.value)}))

function formatBytes(value:number) {
  if (!value) return '0 B'
  const units=['B','KB','MB','GB']; let size=value; let index=0
  while(size>=1024 && index<units.length-1){size/=1024;index++}
  return `${size.toFixed(index>1?1:0)} ${units[index]}`
}

async function postJson(url:string, body:any) {
  const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  const payload=await response.json().catch(()=>({}))
  if(!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`)
  return payload
}

async function loadSuggestedRoots(){
  try{
    const response=await fetch('/api/comic-story/suggested-roots')
    if(response.ok){const value=await response.json(); suggestedRoots.value=value.roots||[]; provider.value=value.provider||provider.value; if(!rootPath.value && suggestedRoots.value.length){rootPath.value=suggestedRoots.value[0]; await scanRoot()}}
  }catch{}
}

async function scanRoot(){
  if(!rootPath.value.trim()) return
  loading.value='scan'; error.value=''
  try{
    const value=await postJson('/api/comic-story/scan',{path:rootPath.value.trim()})
    collections.value=value.collections||[]; selectedCollection.value=null; issues.value=[]; selectedIssue.value=null; step.value=1
  }catch(value){error.value=value instanceof Error?value.message:'扫描失败'}finally{loading.value=''}
}

async function chooseCollection(item:Collection){
  selectedCollection.value=item; loading.value='issues'; error.value=''
  try{
    const value=await postJson('/api/comic-story/issues',{path:item.path,limit:200})
    issues.value=value.issues||[]
  }catch(value){error.value=value instanceof Error?value.message:'读取漫画失败'}finally{loading.value=''}
}

function chooseIssue(item:Issue){
  selectedIssue.value=item; currentPage.value=1; startPage.value=1; endPage.value=Math.min(item.pageCount||10,10)
  analysis.value=null; draft.value=null; story.value.title=item.name; step.value=2
}

async function analyze(){
  if(!selectedIssue.value || !canAnalyze.value) return
  loading.value='analyze'; error.value=''
  try{
    analysis.value=await postJson('/api/comic-story/analyze',{token:selectedIssue.value.token,startPage:startPage.value,endPage:endPage.value})
    story.value.title=story.value.title || analysis.value?.sourceName || ''; step.value=3
  }catch(value){error.value=value instanceof Error?value.message:'解析失败'}finally{loading.value=''}
}

async function generateDraft(){
  if(!selectedIssue.value) return
  loading.value='draft'; error.value=''
  try{
    draft.value=await postJson('/api/comic-story/draft',{token:selectedIssue.value.token,...story.value,startPage:startPage.value,endPage:endPage.value})
    sessionStorage.setItem('cws-comic-story-episode',JSON.stringify(draft.value?.episode||{})); step.value=4
  }catch(value){error.value=value instanceof Error?value.message:'生成草稿失败'}finally{loading.value=''}
}

function movePage(offset:number){
  const max=selectedIssue.value?.pageCount||1
  currentPage.value=Math.min(max,Math.max(1,currentPage.value+offset))
}

async function copyJson(){
  if(!jsonText.value) return
  await navigator.clipboard.writeText(jsonText.value)
  copied.value=true; window.setTimeout(()=>copied.value=false,1200)
}
function downloadJson(){
  if(!jsonText.value) return
  const blob=new Blob([jsonText.value],{type:'application/json;charset=utf-8'})
  const url=URL.createObjectURL(blob); const a=document.createElement('a')
  a.href=url; a.download=`${draft.value?.episode.title||'episode'}.json`; a.click(); URL.revokeObjectURL(url)
}

function go(page:string){ emit('navigate',page) }
onMounted(loadSuggestedRoots)
</script>

<template>
  <div class="comic-story-shell">
    <section class="comic-hero panel">
      <div><span class="eyebrow">COMIC TO STORY · PHASE 1H-2</span><h2>漫画生成故事</h2><p>从本地漫画中提取素材，整理为可编辑故事、Episode 与 Shot，并继续进入动画生产流程。</p></div>
      <div class="hero-flow"><span>本地扫描</span><i></i><span>页面解析</span><i></i><span>故事改编</span><i></i><span>分镜草稿</span></div>
    </section>

    <section class="comic-steps panel">
      <button v-for="item in [{n:1,t:'选择漫画'},{n:2,t:'解析分析'},{n:3,t:'故事改编'},{n:4,t:'生成结果'}]" :key="item.n" :class="{active:step===item.n,done:step>item.n}" @click="item.n<=step&&(step=item.n)">
        <span>{{ item.n }}</span><b>{{ item.t }}</b>
      </button>
    </section>

    <p v-if="error" class="comic-error">{{ error }}</p>

    <template v-if="step===1">
      <section class="panel comic-stage">
        <div class="stage-head"><div><span class="eyebrow">STEP 1</span><h3>选择本地漫画目录</h3><p>支持 PDF、CBZ、ZIP、图片文件夹。系统只建立索引，不复制原漫画。</p></div><FolderSearch :size="32"/></div>
        <div class="path-row"><input v-model="rootPath" placeholder="例如 F:\BaiduNetdiskDownload\漫画目录"/><button class="primary" :disabled="loading==='scan'" @click="scanRoot"><LoaderCircle v-if="loading==='scan'" class="spin" :size="15"/>扫描目录</button></div>
        <div v-if="suggestedRoots.length" class="root-suggestions"><span>检测到：</span><button v-for="root in suggestedRoots" :key="root" @click="rootPath=root">{{ root }}</button></div>
      </section>

      <section v-if="collections.length" class="panel comic-stage">
        <div class="section-head"><div><span class="eyebrow">LIBRARY</span><h3>扫描结果 · {{ collections.length }} 个系列</h3></div></div>
        <div class="collection-list"><button v-for="item in collections" :key="item.path" :class="['collection-row',{active:selectedCollection?.path===item.path}]" @click="chooseCollection(item)"><div class="collection-icon"><BookOpenCheck :size="20"/></div><div><b>{{ item.name }}</b><small>{{ item.itemCount }} 个文件 · {{ formatBytes(item.sizeBytes) }}</small></div><span>{{ Object.keys(item.formats).join(' / ').toUpperCase() }}</span><ArrowRight :size="16"/></button></div>
      </section>

      <section v-if="selectedCollection" class="panel comic-stage">
        <div class="section-head"><div><span class="eyebrow">ISSUES</span><h3>{{ selectedCollection.name }}</h3></div><span class="badge">{{ issues.length }} 本</span></div>
        <div class="issue-filters"><input v-model="issueSearch" placeholder="搜索期刊、年份或文件夹…"/><select v-model="issueYear"><option value="">全部年份</option><option v-for="year in issueYears" :key="year">{{year}}</option></select><span>{{filteredIssues.length}} / {{issues.length}}</span></div>
        <div v-if="loading==='issues'" class="empty-comic"><LoaderCircle class="spin" :size="24"/>正在读取漫画...</div>
        <div v-else-if="!filteredIssues.length" class="empty-comic">没有匹配的漫画。</div>
        <div v-else class="issue-grid"><button v-for="item in filteredIssues.slice(0,96)" :key="item.token||item.filename" class="issue-card" :disabled="!!item.error" @click="!item.error&&chooseIssue(item)"><div class="cover"><img v-if="item.coverUrl" :src="item.coverUrl" loading="lazy"/><FileText :size="28"/></div><b>{{ item.name }}</b><small v-if="item.error">读取失败 · {{item.error}}</small><small v-else>{{ item.pageCount||'?' }} 页 · {{ formatBytes(item.sizeBytes) }}</small></button></div>
      </section>
    </template>

    <template v-else-if="step===2 && selectedIssue">
      <section class="comic-analysis-grid">
        <article class="panel comic-stage page-browser">
          <div class="section-head"><div><span class="eyebrow">STEP 2</span><h3>{{ selectedIssue.name }}</h3></div><span class="badge">{{ selectedIssue.pageCount||'?' }} 页</span></div>
          <div class="page-layout"><div class="page-thumbs"><button v-for="page in Math.min(selectedIssue.pageCount||1,40)" :key="page" :class="{active:page===currentPage,selected:page>=startPage&&page<=endPage}" @click="currentPage=page"><img :src="`/api/comic-story/page/${selectedIssue.token}/${page}?thumbnail=true`" loading="lazy"/><span>{{page}}</span></button></div><div class="page-preview"><img :src="previewUrl"/><div class="page-controls"><button class="secondary" @click="movePage(-1)"><ArrowLeft :size="14"/></button><b>{{ currentPage }} / {{ selectedIssue.pageCount||'?' }}</b><button class="secondary" @click="movePage(1)"><ArrowRight :size="14"/></button></div></div></div>
        </article>
        <article class="panel comic-stage analysis-panel">
          <span class="eyebrow">SOURCE ANALYSIS</span><h3>解析漫画页面</h3><p>先选择需要分析的页码范围。第一版完成页面渲染与文字提取，AI 角色/场景/剧情识别将在 Provider 接入后增强。</p>
          <div class="range-grid"><label>起始页<input v-model.number="startPage" type="number" min="1"/></label><label>结束页<input v-model.number="endPage" type="number" min="1" :max="selectedIssue.pageCount||999"/></label></div>
          <button class="primary wide" :disabled="loading==='analyze'||!canAnalyze" @click="analyze"><ScanText :size="16"/><span>{{ loading==='analyze'?'解析中...':'解析选中页面' }}</span></button>
          <div class="provider-state">AI Provider：<b>{{provider.name}}</b> · {{provider.enabled?'已启用':'disabled（不会调用外网或产生费用）'}}</div><div v-if="analysis" class="analysis-result"><div class="ok-line"><CircleCheck :size="17"/>页面解析完成</div><div class="tag-row"><span v-for="key in analysis.keywords" :key="key">{{ key }}</span></div><p>{{ analysis.message }}</p><div class="semantic-grid"><div v-for="key in ['characters','scenes','dialogues','plotEvents','visualStyle','props','locations','storySummary']" :key="key"><b>{{key}}</b><span>等待 AI 语义分析</span></div></div></div>
        </article>
      </section>
    </template>

    <template v-else-if="step===3 && analysis && selectedIssue">
      <section class="comic-edit-grid">
        <article class="panel comic-stage">
          <span class="eyebrow">STEP 3</span><h3>故事改编设置</h3>
          <div class="story-form"><label>故事标题<input v-model="story.title"/></label><label>故事风格<select v-model="story.style"><option>温馨治愈</option><option>轻松幽默</option><option>冒险成长</option><option>悬疑奇趣</option></select></label><label>目标受众<select v-model="story.audience"><option>3-8岁儿童</option><option>6-12岁儿童</option><option>青少年</option><option>全年龄</option></select></label><label>语言<select v-model="story.language"><option>中文（简体）</option><option>英语</option><option>中英双语</option></select></label><label>英语等级<select v-model="story.level"><option>Pre-A1</option><option>A1</option><option>A2</option></select></label><label>目标时长<input v-model.number="story.duration" type="number" min="5" max="600"/></label><label>原作忠实度<select v-model="story.fidelity"><option value="strict">高度忠实</option><option value="balanced">平衡</option><option value="free">自由改编</option></select></label><label>改编强度<select v-model="story.adaptationStrength"><option value="low">轻度</option><option value="medium">中度</option><option value="high">深度</option></select></label><label>镜头数量<select v-model.number="story.shotCount"><option :value="6">6 镜头</option><option :value="10">10 镜头</option><option :value="12">12 镜头</option></select></label><label>画幅<select v-model="story.aspectRatio"><option>9:16</option><option>16:9</option></select></label><label class="span-two">教育目标<input v-model="story.educationalGoal" placeholder="可留空，等待 AI Provider 补充"/></label><label class="check"><input v-model="story.preserveCharacterNames" type="checkbox"/>保留角色名</label><label class="check"><input v-model="story.preserveDialogues" type="checkbox"/>保留原对白</label><label class="check"><input v-model="story.autoShotCount" type="checkbox"/>AI 自动决定 Shot 数（Provider 启用后）</label></div>
          <button class="primary wide generate" :disabled="loading==='draft'" @click="generateDraft"><Sparkles :size="16"/>{{ loading==='draft'?'生成中...':'生成 Episode / Shot 结构草稿' }}</button>
        </article>
        <article class="panel comic-stage extracted-copy"><span class="eyebrow">EXTRACTED SOURCE</span><h3>漫画内容提取</h3><p class="source-note">页码：{{ analysis.selectedPages[0] }}–{{ analysis.selectedPages[analysis.selectedPages.length-1] }} · {{ analysis.analysisMode }}</p><div class="source-text">{{ analysis.textExcerpt || '当前漫画页没有可提取的文本层。仍可继续使用页面图像作为后续 AI 视觉分析输入。' }}</div></article>
      </section>
    </template>

    <template v-else-if="step===4 && draft">
      <section class="result-banner panel"><div class="success-mark"><CircleCheck :size="24"/></div><div><h3>Episode 结构草稿已生成</h3><p>{{ draft.message }}</p></div><span class="warning-chip">需要 AI 语义增强</span></section>
      <section class="result-grid">
        <article class="panel comic-stage"><div class="section-head"><div><span class="eyebrow">STORYBOARD</span><h3>{{ draft.episode.title }}</h3></div><span class="badge">{{ draft.episode.shots.length }} Shots</span></div><div class="shot-cards"><article v-for="shot in draft.episode.shots" :key="shot.id"><img :src="`/api/comic-story/page/${draft.episode.source.token}/${shot.sourcePage}`"/><div><b>Shot {{ String(shot.id).padStart(2,'0') }} · 第 {{ shot.sourcePage }} 页</b><p>{{ shot.sourceText || '等待 AI 根据画面补充剧情与对白。' }}</p><small>{{ shot.duration }} 秒 · {{ draft.episode.aspectRatio }}</small></div></article></div></article>
        <article class="panel comic-stage json-panel"><div class="section-head"><div><span class="eyebrow">EPISODE JSON</span><h3>结构化输出</h3></div><div class="json-actions"><button class="secondary" @click="copyJson">{{ copied?'已复制':'复制 JSON' }}</button><button class="primary" @click="downloadJson">下载</button><Braces :size="22"/></div></div><pre>{{ jsonText }}</pre></article>
      </section>
      <section class="panel downstream"><div><span class="eyebrow">NEXT WORKFLOW</span><h3>继续进入动画生产</h3><p>草稿已保存在当前浏览器 Session，可继续完善角色、分镜和 ComfyUI 生产。</p></div><div class="downstream-actions"><button class="secondary" @click="go('characters')">导入角色管理</button><button class="secondary" @click="go('storyboard')">进入分镜设计</button><button class="primary" @click="go('workbench')"><Film :size="15"/>进入成片工作台</button></div></section>
    </template>
  </div>
</template>

<style scoped>
.comic-story-shell{display:grid;gap:14px}.comic-hero{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:22px 24px;background:linear-gradient(135deg,#fff,#f7f8ff)}.comic-hero h2{margin:4px 0 7px;font-size:26px;color:#283452}.comic-hero p{margin:0;max-width:760px;font-size:12px}.hero-flow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:#67708f;font-size:10px}.hero-flow span{padding:7px 9px;border-radius:999px;background:#f0edff;color:#6657dc;font-weight:700}.hero-flow i{width:18px;height:1px;background:#d9def0}.comic-steps{display:grid;grid-template-columns:repeat(4,1fr);padding:10px}.comic-steps button{border:0;background:transparent;display:flex;align-items:center;justify-content:center;gap:8px;padding:10px;border-right:1px solid #edf0f6;color:#8b93ad;cursor:pointer}.comic-steps button:last-child{border-right:0}.comic-steps span{width:25px;height:25px;border-radius:50%;display:grid;place-items:center;background:#edf0f6;font-size:10px;font-weight:800}.comic-steps button.active{color:#5f52dc}.comic-steps button.active span{background:#6557e8;color:#fff}.comic-steps button.done span{background:#e5f7ee;color:#198461}.comic-error{margin:0;padding:10px 12px;border-radius:10px;background:#fff0f2;border:1px solid #ffd8df;color:#be4255;font-size:11px}.comic-stage{padding:18px;min-width:0}.stage-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.stage-head h3,.section-head h3,.comic-stage>h3{margin:4px 0 5px}.stage-head>svg{color:#6657e8}.path-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;margin-top:15px}.path-row input,.story-form input,.story-form select,.range-grid input{width:100%;min-width:0;border:1px solid #dfe4ef;border-radius:9px;background:#fbfcff;padding:10px;color:#35405e;outline:none}.root-suggestions{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:8px;font-size:10px;color:#8b93aa}.root-suggestions button{border:0;background:#f2f4fa;color:#596482;border-radius:8px;padding:6px 8px;cursor:pointer;max-width:100%;overflow-wrap:anywhere}.collection-list{display:grid;gap:7px;margin-top:12px}.collection-row{display:grid;grid-template-columns:38px minmax(0,1fr) auto auto;gap:10px;align-items:center;width:100%;padding:10px;border:1px solid #e7eaf2;background:#fff;border-radius:10px;text-align:left;color:#3f4866;cursor:pointer}.collection-row.active{border-color:#8d82f4;background:#f8f7ff}.collection-icon{width:36px;height:36px;border-radius:9px;display:grid;place-items:center;background:#efedff;color:#6557e8}.collection-row b,.collection-row small{display:block}.collection-row b{font-size:11px}.collection-row small{font-size:9px;color:#8c94aa;margin-top:3px}.collection-row>span{font-size:9px;color:#7c86a2}.issue-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin-top:12px}.issue-card{border:1px solid #e6e9f2;background:#fff;border-radius:11px;padding:8px;text-align:left;cursor:pointer;min-width:0}.issue-card:hover{border-color:#8578ef;box-shadow:0 8px 24px rgba(82,73,180,.08)}.cover{position:relative;height:150px;border-radius:8px;overflow:hidden;background:#f2f4f8;display:grid;place-items:center;color:#a0a8bb}.cover img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.cover img:not([src]),.cover img[src=""]{display:none}.issue-card b,.issue-card small{display:block}.issue-card b{font-size:10px;line-height:1.35;margin-top:7px;color:#394460;overflow-wrap:anywhere}.issue-card small{font-size:8px;color:#8b93aa;margin-top:4px}.empty-comic{display:flex;align-items:center;justify-content:center;gap:8px;padding:30px;color:#8b93aa;font-size:11px}
.comic-analysis-grid,.comic-edit-grid,.result-grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:14px}.page-preview{display:grid;justify-items:center;gap:10px;margin-top:12px}.page-preview img{max-width:100%;max-height:640px;border-radius:10px;box-shadow:0 10px 28px rgba(35,46,78,.12);background:#f4f5f8}.page-controls{display:flex;align-items:center;gap:8px}.analysis-panel>p,.extracted-copy>p{font-size:11px}.range-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}.range-grid label,.story-form label{display:grid;gap:6px;font-size:10px;color:#59627c}.analysis-result{margin-top:12px;padding:11px;border-radius:10px;background:#f3fbf7;border:1px solid #d7efe4}.ok-line{display:flex;align-items:center;gap:6px;color:#22875f;font-size:11px;font-weight:700}.analysis-result p{font-size:10px;margin:8px 0 0}.story-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}.generate{margin-top:8px}.source-note{color:#8790a8}.source-text{max-height:440px;overflow:auto;padding:12px;border:1px solid #e6e9f2;background:#fafbfe;border-radius:10px;color:#56617d;font-size:10px;line-height:1.75;white-space:pre-wrap}.result-banner{display:flex;align-items:center;gap:12px;padding:14px 17px}.result-banner h3{margin:0 0 3px}.result-banner p{margin:0;font-size:10px}.success-mark{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#e7f8ef;color:#1f9569}.warning-chip{margin-left:auto;background:#fff6df;color:#9d6c19;border-radius:999px;padding:6px 8px;font-size:9px;font-weight:700}.shot-cards{display:grid;gap:8px;margin-top:12px}.shot-cards article{display:grid;grid-template-columns:110px minmax(0,1fr);gap:10px;padding:8px;border:1px solid #e7eaf2;border-radius:10px}.shot-cards img{width:110px;height:74px;object-fit:cover;border-radius:7px;background:#f3f4f8}.shot-cards b{font-size:10px}.shot-cards p{font-size:9px;margin:4px 0;line-height:1.55}.shot-cards small{font-size:8px;color:#8a93aa}.json-actions{display:flex;align-items:center;gap:7px}.json-actions button{padding:7px 9px;font-size:9px}.json-panel pre{max-height:620px;overflow:auto;padding:14px;border-radius:10px;background:#1c2333;color:#d7e2f4;font-size:9px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}.downstream{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:16px 18px}.downstream h3{margin:3px 0}.downstream p{margin:0;font-size:10px}.downstream-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.spin{animation:comic-spin 1s linear infinite}@keyframes comic-spin{to{transform:rotate(360deg)}}
@media(max-width:1300px){.issue-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.comic-analysis-grid,.comic-edit-grid,.result-grid{grid-template-columns:1fr}.comic-hero{align-items:flex-start;flex-direction:column}}
@media(max-width:820px){.issue-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.comic-steps{grid-template-columns:repeat(2,1fr)}.comic-steps button:nth-child(2){border-right:0}.story-form{grid-template-columns:1fr}.downstream{align-items:flex-start;flex-direction:column}.downstream-actions{justify-content:flex-start}.collection-row{grid-template-columns:38px minmax(0,1fr) auto}.collection-row>span{display:none}}
@media(max-width:520px){.path-row{grid-template-columns:1fr}.issue-grid{grid-template-columns:1fr}.range-grid{grid-template-columns:1fr}.hero-flow{display:none}.shot-cards article{grid-template-columns:90px minmax(0,1fr)}.shot-cards img{width:90px}}
</style>
<style scoped>
.issue-filters{display:grid;grid-template-columns:minmax(0,1fr) 150px auto;gap:8px;align-items:center;margin-top:12px}.issue-filters input,.issue-filters select{min-width:0;width:100%;border:1px solid #dfe4ef;border-radius:9px;background:#fbfcff;padding:9px;color:#35405e}.issue-filters span{font-size:9px;color:#7c86a2}
.page-layout{display:grid;grid-template-columns:76px minmax(0,1fr);gap:10px;margin-top:12px}.page-layout .page-preview{margin-top:0}.page-thumbs{display:grid;gap:6px;max-height:650px;overflow:auto;align-content:start}.page-thumbs button{position:relative;border:2px solid transparent;border-radius:7px;padding:2px;background:#f1f3f8;color:#707a95}.page-thumbs button.selected{border-color:#c8c1fa}.page-thumbs button.active{border-color:#6557e8}.page-thumbs img{display:block;width:100%;height:82px;object-fit:cover;border-radius:4px}.page-thumbs span{position:absolute;right:4px;bottom:4px;background:rgba(24,28,48,.75);color:#fff;border-radius:4px;padding:2px 4px;font-size:8px}
.provider-state{margin-top:10px;padding:8px;border-radius:8px;background:#f4f2ff;color:#665b8d;font-size:9px}.semantic-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px}.semantic-grid>div{display:flex;flex-direction:column;padding:7px;background:#fff;border-radius:7px}.semantic-grid b{font-size:8px;color:#405675}.semantic-grid span{font-size:8px;color:#8a96aa;margin-top:2px}.story-form .span-two{grid-column:1/-1}.story-form .check{display:flex;align-items:center;gap:7px}.story-form .check input{width:auto}
@media(max-width:520px){.path-row,.issue-filters{grid-template-columns:1fr}.page-layout{grid-template-columns:1fr}.page-thumbs{grid-template-columns:repeat(4,1fr);max-height:none}.page-thumbs img{height:86px}.semantic-grid{grid-template-columns:1fr}}
</style>
