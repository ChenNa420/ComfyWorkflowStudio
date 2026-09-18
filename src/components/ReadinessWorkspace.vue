<script setup lang="ts">
import { ref } from 'vue'
import { ShieldCheck, Target } from 'lucide-vue-next'
import PreflightCertificationPanel from './PreflightCertificationPanel.vue'
import ReadinessRemediationPanel from './ReadinessRemediationPanel.vue'

const tab = ref<'remediation' | 'preflight'>('remediation')
</script>

<template>
  <section class="workspace-shell">
    <div class="workspace-tabs">
      <button :class="{ active: tab === 'remediation' }" @click="tab='remediation'"><Target :size="14"/>依赖治理</button>
      <button :class="{ active: tab === 'preflight' }" @click="tab='preflight'"><ShieldCheck :size="14"/>Runtime 预检认证</button>
    </div>
    <ReadinessRemediationPanel v-if="tab === 'remediation'" />
    <PreflightCertificationPanel v-else />
  </section>
</template>

<style scoped>
.workspace-shell{display:grid;gap:14px}.workspace-tabs{display:flex;gap:7px;padding:5px;background:#f5f6fa;border:1px solid #e3e7f0;border-radius:10px;width:max-content;max-width:100%}.workspace-tabs button{border:0;background:transparent;color:#738096;border-radius:7px;padding:8px 11px;font-size:9px;font-weight:700;display:flex;align-items:center;gap:6px;cursor:pointer}.workspace-tabs button.active{background:#fff;color:#5c4bd6;box-shadow:0 2px 9px rgba(58,66,92,.08)}@media(max-width:520px){.workspace-tabs{width:100%;display:grid;grid-template-columns:1fr 1fr}.workspace-tabs button{justify-content:center;min-width:0}}
</style>
