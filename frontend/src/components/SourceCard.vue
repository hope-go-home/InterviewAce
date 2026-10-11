<template>
  <div class="sources">
    <button class="head" @click="open = !open">
      <span class="label">检索来源 · {{ sources.length }} 条</span>
      <span v-if="stats.fused_count" class="stat">
        稠密 {{ stats.dense_hits }} / 稀疏 {{ stats.sparse_hits }} / 融合 {{ stats.fused_count }}
      </span>
      <span v-if="stats.cross_domain" class="warn">跨域</span>
      <span class="arrow">{{ open ? '−' : '+' }}</span>
    </button>
    <div v-if="open" class="list">
      <div v-for="(s, i) in sources" :key="i" class="card">
        <div class="row" @click="s._open = !s._open" style="cursor:pointer">
          <span class="idx">{{ i + 1 }}</span>
          <span class="dom">{{ s.domain }}</span>
          <span v-if="s.company" class="company">{{ s.company }}</span>
          <span class="score">重排 {{ s.rerank_score }}</span>
        </div>
        <a class="title" :href="s.url || undefined" target="_blank" rel="noreferrer"
           @click.stop>{{ s.title || s.source }}</a>
        <div class="preview">{{ s._open ? s.text : s.preview }}</div>
        <div class="ranks" @click="s._open = !s._open" style="cursor:pointer">
          稠密 #{{ s.dense_rank || '—' }} · 稀疏 #{{ s.sparse_rank || '—' }} · RRF {{ s.rrf_score }}
          <span class="more">{{ s._open ? '收起' : '看命中内容' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
defineProps({
  sources: { type: Array, default: () => [] },
  stats: { type: Object, default: () => ({}) },
})
const open = ref(true)
</script>

<style scoped>
.sources { margin-bottom: 16px; }
.head {
  display: flex; align-items: center; gap: 10px; width: 100%;
  background: none; border: none; padding: 4px 0;
  font-size: 13px; color: var(--ink-faint); text-align: left;
}
.head:hover { color: var(--ink-soft); }
.label { font-weight: 500; }
.stat { font-family: var(--font-mono); font-size: 11px; color: var(--ink-faint); }
.warn { font-size: 11px; color: var(--seal); }
.arrow { margin-left: auto; font-size: 15px; }
.list { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.card {
  display: block; padding: 10px 13px; background: var(--card-solid);
  border: 1px solid var(--line-soft); border-radius: var(--radius);
}
.row { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; }
.idx {
  font-family: var(--font-mono); font-size: 11px; color: var(--paper);
  background: var(--accent); border-radius: 3px; width: 17px; height: 17px;
  display: grid; place-items: center; flex: 0 0 auto;
}
.dom { font-size: 11px; color: var(--accent); font-family: var(--font-mono); }
.company { font-size: 11px; color: var(--ok); }
.score { margin-left: auto; font-size: 11px; color: var(--ink-faint); font-family: var(--font-mono); }
.title { display: block; font-size: 13.5px; font-weight: 500; color: var(--ink); }
a.title:hover { color: var(--accent); }
.preview {
  margin-top: 5px; font-size: 12.5px; color: var(--ink-soft); line-height: 1.7;
  white-space: pre-wrap; word-break: break-word;
}
.ranks { margin-top: 6px; font-size: 11px; color: var(--ink-faint); font-family: var(--font-mono); }
.more { margin-left: 8px; color: var(--accent); }
</style>
