<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ArrowLeft, WandSparkles } from 'lucide-vue-next'
import AppPhase1D from './AppPhase1D.vue'
import DependencyCenterPanel from './components/DependencyCenterPanel.vue'
import ReadinessRemediationPanel from './components/ReadinessRemediationPanel.vue'
import WorkflowAdapterPanel from './components/WorkflowAdapterPanel.vue'
import WorkflowKnowledgePanel from './components/WorkflowKnowledgePanel.vue'

const page = ref(location.hash.replace('#/', '') || 'dashboard')

function syncHash() {
  page.value = location.hash.replace('#/', '') || 'dashboard'
}

function goWorkflows() {
  location.hash = '#/workflows'
}

onMounted(() => window.addEventListener('hashchange', syncHash))
onUnmounted(() => window.removeEventListener('hashchange', syncHash))
</script>

<template>
  <AppPhase1D />

  <div v-if="page === 'workflows'" class="adapter-overlay knowledge-overlay">
    <section class="panel adapter-overlay-card knowledge-overlay-card">
      <WorkflowKnowledgePanel />
    </section>
  </div>

  <div v-if="page === 'dependencies'" class="adapter-overlay knowledge-overlay">
    <section class="panel adapter-overlay-card knowledge-overlay-card">
      <DependencyCenterPanel />
    </section>
  </div>

  <div v-if="page === 'readiness'" class="adapter-overlay knowledge-overlay">
    <section class="panel adapter-overlay-card knowledge-overlay-card">
      <ReadinessRemediationPanel />
    </section>
  </div>

  <div v-if="page === 'adapter'" class="adapter-overlay">
    <section class="panel adapter-overlay-card">
      <div class="adapter-overlay-head">
        <div>
          <span class="eyebrow">WORKFLOW ADAPTER</span>
          <h2><WandSparkles :size="22" /> 工作流适配向导</h2>
          <p>把自动识别出的 Node 映射为“首帧、尾帧、角色参考图、Pose、Depth、Prompt”等业务输入，保存后直接驱动创建任务页面。</p>
        </div>
        <button class="secondary" @click="goWorkflows"><ArrowLeft :size="15" /> 返回工作流库</button>
      </div>
      <WorkflowAdapterPanel />
    </section>
  </div>
</template>
