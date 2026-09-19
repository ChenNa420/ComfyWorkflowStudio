<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CheckCircle2, RefreshCw, Save, ShieldCheck } from 'lucide-vue-next'

type Tab = 'comfyui' | 'storage' | 'tasks' | 'workflows' | 'advanced'
type Candidate = { workflowId:string; name:string; category:string; capabilities:string[]; outputs:string[]; health:string; dependencyStatus:string }
type SettingsPayload = {
  comfyUi:{url:string;source:string;connected:boolean;error?:string|null;editable:boolean;takesEffect:string}
  storage:Array<{key:string;label:string;path:string;exists:boolean;writable:boolean;editable:boolean;source:string}>
  taskPolicy:Record<string,{value:unknown;editable:boolean;scope?:string}>
  workflow:{defaultImageWorkflowId?:string|null;defaultVideoWorkflowId?:string|null;productionVideoWorkflowId?:string|null;showReadyOnly:boolean;requireCertified:{value:boolean;editable:boolean};requireDependencyReady:{value:boolean;editable:boolean};candidates:Candidate[]}
  advanced:{phase:string;subphase:string;apiVersion:string;databasePath:string;databaseEditable:boolean;configurationSources:string[];runtimeSafety:string}
  restartRequired:string[]
}

const tabs:Array<{key:Tab;label:string}> = [
  {key:'comfyui',label:'ComfyUI'}, {key:'storage',label:'存储'}, {key:'tasks',label:'任务策略'},
  {key:'workflows',label:'工作流'}, {key:'advanced',label:'高级'},
]
const activeTab = ref<Tab>((localStorage.getItem('cws-settings-tab') as Tab) || 'comfyui')
const settings = ref<SettingsPayload|null>(null)
const draft = ref({comfyUiUrl:'',defaultImageWorkflowId:'',defaultVideoWorkflowId:'',productionVideoWorkflowId:'',showReadyOnly:true})
const original = ref('')
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const message = ref('')
const error = ref('')
const dirty = computed(() => JSON.stringify(draft.value) !== original.value)
const visibleCandidates = computed(() => settings.value?.workflow.candidates.filter(item => !draft.value.showReadyOnly || item.health === 'READY') || [])
const imageCandidates = computed(() => visibleCandidates.value.filter(item => item.outputs.map(v=>v.toLowerCase()).includes('image') || item.capabilities.map(v=>v.toLowerCase()).includes('image-generation')))
const videoCandidates = computed(() => visibleCandidates.value.filter(item => {
  const outputs=item.outputs.map(v=>v.toLowerCase()), capabilities=item.capabilities.map(v=>v.toLowerCase())
  return outputs.includes('video') || capabilities.includes('video-generation') || capabilities.includes('image-to-video')
}))

function selectTab(tab:Tab){ activeTab.value=tab; localStorage.setItem('cws-settings-tab',tab) }
function applyPayload(payload:SettingsPayload){
  settings.value=payload
  draft.value={
    comfyUiUrl:payload.comfyUi.url,
    defaultImageWorkflowId:payload.workflow.defaultImageWorkflowId||'',
    defaultVideoWorkflowId:payload.workflow.defaultVideoWorkflowId||'',
    productionVideoWorkflowId:payload.workflow.productionVideoWorkflowId||'',
    showReadyOnly:payload.workflow.showReadyOnly,
  }
  original.value=JSON.stringify(draft.value)
}
async function load(){
  loading.value=true;error.value='';message.value=''
  try{const response=await fetch('/api/settings');if(!response.ok)throw new Error(`Settings HTTP ${response.status}`);applyPayload(await response.json())}
  catch(value){error.value=value instanceof Error?value.message:'读取设置失败'}finally{loading.value=false}
}
function reset(){if(!settings.value)return;applyPayload(settings.value);message.value='已撤销未保存修改';error.value=''}
async function save(){
  if(saving.value||!dirty.value)return
  saving.value=true;error.value='';message.value=''
  try{
    const response=await fetch('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(draft.value)})
    const payload=await response.json().catch(()=>({}))
    if(!response.ok)throw new Error(payload?.detail?.code||payload?.detail?.[0]?.msg||`Settings HTTP ${response.status}`)
    applyPayload(payload);message.value='设置已保存并立即生效';window.dispatchEvent(new CustomEvent('system-settings-updated',{detail:payload}))
  }catch(value){error.value=value instanceof Error?value.message:'保存失败'}finally{saving.value=false}
}
async function testComfy(){
  if(testing.value)return
  testing.value=true;error.value='';message.value=''
  try{
    const response=await fetch('/api/settings/comfyui/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({comfyUiUrl:draft.value.comfyUiUrl})})
    const payload=await response.json();if(!payload.connected)throw new Error(payload.error||'无法连接 ComfyUI')
    message.value=`连接成功：${payload.url}`
  }catch(value){error.value=value instanceof Error?value.message:'连接测试失败'}finally{testing.value=false}
}
onMounted(load)
</script>

<template>
  <section class="settings-layout settings-center">
    <aside class="panel settings-menu"><button v-for="tab in tabs" :key="tab.key" :class="{active:activeTab===tab.key}" @click="selectTab(tab.key)">{{tab.label}}</button></aside>
    <article class="panel form-panel settings-body">
      <div class="settings-head"><div><span class="eyebrow">LOCAL APPLICATION SETTINGS</span><h2>{{tabs.find(tab=>tab.key===activeTab)?.label}}</h2></div><button class="secondary" :disabled="loading" @click="load"><RefreshCw :size="14"/>刷新</button></div>
      <div v-if="loading" class="notice">正在读取本地设置…</div>
      <template v-else-if="settings">
        <template v-if="activeTab==='comfyui'">
          <label>ComfyUI 地址<input v-model.trim="draft.comfyUiUrl" placeholder="http://127.0.0.1:8188"/></label>
          <div class="connection-card"><span :class="['dot',{ok:settings.comfyUi.connected}]"></span><div><b>{{settings.comfyUi.connected?'当前可连接':'当前不可连接'}}</b><small>实际生效：{{settings.comfyUi.url}} · 来源：{{settings.comfyUi.source}}</small><small v-if="settings.comfyUi.error" class="bad">{{settings.comfyUi.error}}</small></div></div>
          <div class="button-row"><button class="secondary" :disabled="testing" @click="testComfy">{{testing?'测试中…':'测试连接'}}</button></div>
        </template>
        <template v-else-if="activeTab==='storage'">
          <div class="setting-rows"><div v-for="item in settings.storage" :key="item.key" class="setting-row"><div><b>{{item.label}}</b><code>{{item.path}}</code></div><div class="tag-row"><span :class="item.exists?'good':'bad'">{{item.exists?'目录存在':'尚未创建'}}</span><span :class="item.writable?'good':'bad'">{{item.writable?'可写':'不可写'}}</span><span>只读 · 系统管理</span></div></div></div>
          <div class="notice">这些路径被运行时、安全文件下载和数据恢复逻辑共同使用，当前版本不允许动态改址。</div>
        </template>
        <template v-else-if="activeTab==='tasks'">
          <div class="setting-rows"><div v-for="(item,key) in settings.taskPolicy" :key="key" class="setting-row"><div><b>{{({maxConcurrency:'最大并发',executionMode:'执行模式',outputTimeout:'输出超时（秒）',retryUnknown:'UNKNOWN 自动重试',uncertainBehavior:'UNKNOWN / NEEDS_REVIEW 行为',duplicateSubmissionProtection:'重复提交保护',runtimeClone:'Runtime Clone',preserveOriginalWorkflow:'保留原始 Workflow'} as Record<string,string>)[key]}}</b><span>{{String(item.value)}}</span></div><em><ShieldCheck :size="13"/>系统安全策略 · 不可修改</em></div></div>
        </template>
        <template v-else-if="activeTab==='workflows'">
          <label>默认图片工作流<select v-model="draft.defaultImageWorkflowId"><option value="">自动选择第一个可用工作流</option><option v-for="item in imageCandidates" :key="item.workflowId" :value="item.workflowId">{{item.name}} · {{item.workflowId}} · {{item.health}}</option></select></label>
          <label>默认视频工作流<select v-model="draft.defaultVideoWorkflowId"><option value="">自动选择第一个可用工作流</option><option v-for="item in videoCandidates" :key="item.workflowId" :value="item.workflowId">{{item.name}} · {{item.workflowId}} · {{item.health}}</option></select></label>
          <label>成片工作台默认视频工作流<select v-model="draft.productionVideoWorkflowId"><option value="">跟随默认视频工作流</option><option v-for="item in videoCandidates" :key="item.workflowId" :value="item.workflowId">{{item.name}} · {{item.workflowId}} · {{item.health}}</option></select></label>
          <label class="check-line"><input v-model="draft.showReadyOnly" type="checkbox"/>候选列表仅显示“可直接使用”工作流</label>
          <div class="setting-row"><div><b>Runtime 执行门槛</b><span>CERTIFIED + dependency READY</span></div><em><ShieldCheck :size="13"/>系统安全策略 · 不可修改</em></div>
        </template>
        <template v-else>
          <div class="setting-rows"><div class="setting-row"><div><b>Phase / Build</b><span>{{settings.advanced.phase}} · {{settings.advanced.subphase}} · API {{settings.advanced.apiVersion}}</span></div></div><div class="setting-row"><div><b>本地数据库</b><code>{{settings.advanced.databasePath}}</code></div><em>只读</em></div><div class="setting-row"><div><b>Runtime 安全策略</b><span>{{settings.advanced.runtimeSafety}}</span></div></div><div class="setting-row"><div><b>配置优先级</b><span>{{settings.advanced.configurationSources.join(' → ')}}</span></div></div></div>
        </template>
        <div v-if="message" class="settings-message success"><CheckCircle2 :size="14"/>{{message}}</div><div v-if="error" class="settings-message failure">{{error}}</div>
        <div v-if="['comfyui','workflows'].includes(activeTab)" class="settings-actions"><span>{{dirty?'有未保存修改':'所有修改已保存'}}</span><button class="secondary" :disabled="!dirty||saving" @click="reset">重置未保存修改</button><button class="primary" :disabled="!dirty||saving" @click="save"><Save :size="14"/>{{saving?'保存中…':'保存设置'}}</button></div>
      </template>
    </article>
  </section>
</template>

<style scoped>
.settings-center{align-items:start}.settings-body{min-height:540px}.settings-head{display:flex;justify-content:space-between;align-items:start}.settings-head h2{margin:4px 0 12px}.settings-head button{margin:0}.setting-rows{display:grid;gap:9px}.setting-row{display:flex;justify-content:space-between;align-items:center;gap:18px;border:1px solid #e7eaf2;border-radius:10px;padding:12px;margin-top:9px}.setting-row>div{display:grid;gap:5px;min-width:0}.setting-row b{font-size:12px}.setting-row span,.setting-row code{font-size:10px;color:#737d99;overflow-wrap:anywhere}.setting-row em{display:flex;align-items:center;gap:5px;color:#6c5bd8;font-size:10px;font-style:normal;white-space:nowrap}.good{color:#208b62!important}.bad{color:#c94357!important}.settings-actions{display:flex;align-items:center;justify-content:flex-end;gap:9px;border-top:1px solid #edf0f6;margin-top:20px;padding-top:14px}.settings-actions>span{margin-right:auto;font-size:10px;color:#7e86a1}.settings-message{display:flex;gap:6px;align-items:center;padding:10px;border-radius:9px;margin-top:13px;font-size:11px}.settings-message.success{background:#eaf8f1;color:#208b62}.settings-message.failure{background:#fff0f2;color:#c94357}button:disabled{opacity:.5;cursor:not-allowed}
</style>
