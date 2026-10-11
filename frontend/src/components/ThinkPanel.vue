<template>
  <details class="think" open>
    <summary>
      <span class="dot"></span>检索与作答过程 · {{ steps.length }} 步
    </summary>
    <div class="steps">
      <div v-for="(s, i) in steps" :key="i" class="step">
        <span class="idx">{{ i + 1 }}</span>
        <span class="node">{{ nodeName(s.node) }}</span>
        <span class="info">{{ s.info }}</span>
      </div>
    </div>
  </details>
</template>

<script setup>
defineProps({ steps: { type: Array, default: () => [] } })
const NODE_NAMES = {
  query_analysis: '意图分析',
  retrieve: '检索',
  rewrite: '改写重检',
  generate: '生成',
  direct_answer: '直答',
}
const nodeName = (n) => NODE_NAMES[n] || n
</script>

<style scoped>
.think { margin-bottom: 14px; font-size: 13px; }
summary {
  display: inline-flex; align-items: center; gap: 8px;
  cursor: pointer; color: var(--ink-faint); user-select: none;
  padding: 4px 0; list-style: none;
}
summary::-webkit-details-marker { display: none; }
summary:hover { color: var(--ink-soft); }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); flex: 0 0 auto; }
.think[open] .dot { background: var(--ok); }
.steps {
  margin-top: 8px; padding: 12px 14px;
  background: var(--card-solid); border: 1px solid var(--line-soft); border-radius: var(--radius);
  display: flex; flex-direction: column; gap: 8px;
}
.step { display: flex; gap: 10px; align-items: baseline; font-size: 12.5px; }
.node { flex: 0 0 auto; font-family: var(--font-mono); font-size: 11px; color: var(--accent); }
.info { color: var(--ink-soft); line-height: 1.6; }
</style>
