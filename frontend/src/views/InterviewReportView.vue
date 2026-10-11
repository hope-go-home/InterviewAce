<template>
  <div class="page">
    <header class="topbar">
      <div class="brand-mini"><span class="seal">评</span><h2>面试总评</h2></div>
      <nav class="nav">
        <router-link to="/interview">再来一场</router-link>
        <router-link to="/chat">问答</router-link>
        <router-link to="/me">我的</router-link>
      </nav>
    </header>

    <div class="body" v-if="report">
      <!-- 总分 + 四维雷达 -->
      <section class="card top">
        <div class="total">
          <div class="total-num" :class="scoreClass">{{ report.total_score }}<i>分</i></div>
          <div class="total-sub">本场综合得分</div>
        </div>
        <div class="radar-wrap" v-if="dimKeys.length">
          <svg :viewBox="`0 0 ${R*2+30} ${R*2+30}`" class="radar">
            <polygon v-for="lvl in [0.33,0.66,1]" :key="lvl" class="grid-line" :points="gridPoints(lvl)" />
            <line v-for="(p, i) in axisPoints" :key="i" class="axis" :x1="cx" :y1="cy" :x2="p.x" :y2="p.y" />
            <polygon class="data-poly" :points="dataPoly" />
            <text v-for="(p, i) in axisPoints" :key="'t'+i" class="axis-label" :x="p.lx" :y="p.ly" text-anchor="middle">{{ p.name }}</text>
          </svg>
        </div>
      </section>

      <!-- 总评文字 -->
      <section class="card" v-if="report.summary">
        <div class="sec-title">面试官总评</div>
        <p class="summary">{{ report.summary }}</p>
      </section>

      <!-- 薄弱域 -->
      <section class="card" v-if="report.weak_domains?.length">
        <div class="sec-title">薄弱知识域</div>
        <div class="weak-list">
          <div v-for="w in report.weak_domains" :key="w.domain" class="weak-item">
            <span class="w-name">{{ domainName(w.domain) }}</span>
            <span class="w-score">{{ w.avg }} 分</span>
            <button class="w-btn" @click="$router.push('/practice')">去复习</button>
          </div>
        </div>
      </section>

      <!-- 逐题回顾 -->
      <section class="card">
        <div class="sec-title">逐题回顾</div>
        <div v-for="q in report.per_question" :key="q.seq" class="pq-item">
          <div class="pq-head">
            <span class="pq-seq">Q{{ q.seq }}</span>
            <span class="pq-q">{{ q.question }}</span>
            <span class="pq-score" :class="q.score >= 85 ? 'g' : q.score >= 60 ? 'm' : 'b'">{{ q.score }}</span>
          </div>
          <p v-if="q.feedback" class="pq-fb">{{ q.feedback }}</p>
          <div v-if="q.qa_refs?.length" class="pq-refs">
            参考：<a v-for="(r, i) in q.qa_refs" :key="i" :href="r.url || undefined" target="_blank" rel="noreferrer">{{ r.title || '题库题目' }}</a>
          </div>
        </div>
      </section>
    </div>
    <div v-else class="body"><div class="card center">加载报告…</div></div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()
const sid = route.params.id
const report = ref(null)

const DOMAIN_NAMES = { llm_basics: 'LLM 原理', prompt: 'Prompt', rag: 'RAG', agent: 'Agent', vectordb: '向量库', framework: '框架', python_backend: 'Python', ml_dl: 'ML/DL', cs_basic: 'CS 基础' }
const domainName = (k) => DOMAIN_NAMES[k] || k

const scoreClass = computed(() => {
  const s = report.value?.total_score
  return s == null ? '' : s >= 85 ? 'good' : s >= 60 ? 'mid' : 'bad'
})

/* 雷达图 */
const R = 80
const cx = R + 15, cy = R + 15
const dimKeys = computed(() => Object.keys(report.value?.dimensions || {}))
function polar(i, total, r) {
  const ang = (Math.PI * 2 * i) / total - Math.PI / 2
  return { x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang) }
}
const axisPoints = computed(() => dimKeys.value.map((k, i) => {
  const p = polar(i, dimKeys.value.length, R)
  const lp = polar(i, dimKeys.value.length, R + 12)
  return { ...p, lx: lp.x, ly: lp.y, name: k }
}))
function gridPoints(ratio) {
  return dimKeys.value.map((_, i) => { const p = polar(i, dimKeys.value.length, R * ratio); return `${p.x},${p.y}` }).join(' ')
}
const dataPoly = computed(() => dimKeys.value.map((k, i) => {
  const v = (report.value?.dimensions || {})[k] || 0
  const p = polar(i, dimKeys.value.length, R * (v / 100))
  return `${p.x},${p.y}`
}).join(' '))

onMounted(async () => {
  try {
    const { data } = await api.get(`/interview/${sid}/report`)
    report.value = data.report
    if (!report.value) {  // 还没出报告就主动结束
      const r = await api.post(`/interview/${sid}/end`)
      report.value = r.data
    }
  } catch (e) {
    alert(e.response?.data?.detail || '加载报告失败')
  }
})
</script>

<style scoped>
.page { min-height: 100vh; background: transparent; }
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 16px 28px; border-bottom: 1px solid var(--line); }
.brand-mini { display: flex; align-items: center; gap: 10px; }
.seal { width: 30px; height: 30px; display: grid; place-items: center; background: var(--seal); color: var(--paper); border-radius: 6px; font-family: var(--font-display); font-weight: 700; font-size: 16px; }
.topbar h2 { font-family: var(--font-display); font-size: 19px; font-weight: 600; }
.nav { display: flex; gap: 4px; }
.nav a { padding: 6px 14px; font-size: 13.5px; color: var(--ink-soft); border-radius: var(--radius); }
.nav a:hover { text-decoration: none; background: var(--hover); }

.body { max-width: 800px; margin: 0 auto; padding: 28px 24px 60px; }
.card { background: var(--card-solid); border: 1px solid var(--line); border-radius: 10px; padding: 22px 24px; margin-bottom: 16px; }
.card.center { text-align: center; padding: 50px; color: var(--ink-faint); }
.card.top { display: flex; gap: 30px; align-items: center; }
.total { text-align: center; }
.total-num { font-family: var(--font-display); font-size: 56px; font-weight: 700; line-height: 1; }
.total-num i { font-size: 15px; font-weight: 400; font-style: normal; color: var(--ink-faint); }
.total-num.good { color: var(--ok); } .total-num.mid { color: #C79017; } .total-num.bad { color: var(--seal); }
.total-sub { margin-top: 8px; font-size: 12.5px; color: var(--ink-faint); }
.radar-wrap { flex: 1; display: flex; justify-content: center; }
.radar { width: 100%; max-width: 280px; }
.grid-line { fill: none; stroke: var(--line); }
.axis { stroke: var(--line-soft); }
.data-poly { fill: rgba(46,74,122,.18); stroke: var(--accent); stroke-width: 1.5; }
.axis-label { font-size: 10px; fill: var(--ink-soft); }

.sec-title { font-family: var(--font-display); font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.summary { font-size: 14px; line-height: 1.85; color: var(--ink); }

.weak-list { display: flex; flex-direction: column; gap: 4px; }
.weak-item { display: flex; align-items: center; gap: 14px; padding: 10px 0; border-bottom: 1px solid var(--line-soft); }
.weak-item:last-child { border-bottom: none; }
.w-name { flex: 0 0 auto; font-size: 13.5px; font-weight: 500; }
.w-score { font-family: var(--font-mono); font-size: 12.5px; color: var(--seal); }
.w-btn { margin-left: auto; padding: 6px 14px; background: var(--ink); color: var(--paper); border: none; border-radius: 6px; font-size: 12px; }
.w-btn:hover { background: var(--accent); }

.pq-item { padding: 13px 0; border-bottom: 1px solid var(--line-soft); }
.pq-item:last-child { border-bottom: none; }
.pq-head { display: flex; gap: 10px; align-items: baseline; }
.pq-seq { font-family: var(--font-mono); font-size: 12px; color: var(--ink-faint); flex: 0 0 auto; }
.pq-q { flex: 1; font-size: 14px; font-weight: 500; color: var(--ink); line-height: 1.55; }
.pq-score { font-family: var(--font-display); font-size: 19px; font-weight: 700; flex: 0 0 auto; }
.pq-score.g { color: var(--ok); } .pq-score.m { color: #C79017; } .pq-score.b { color: var(--seal); }
.pq-fb { font-size: 12.5px; color: var(--ink-soft); line-height: 1.7; margin: 7px 0 0; }
.pq-refs { margin-top: 6px; font-size: 11.5px; color: var(--ink-faint); }
.pq-refs a { color: var(--accent); margin-right: 10px; }

@media (max-width: 640px) { .card.top { flex-direction: column; } }
</style>
