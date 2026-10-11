<template>
  <div class="me-page">
    <header class="topbar">
      <div class="brand-mini"><span class="seal">我</span><h2>我的画像</h2></div>
      <nav class="nav">
        <router-link to="/chat">问答</router-link>
        <router-link to="/bank">题库</router-link>
        <router-link to="/practice">练习</router-link>
        <router-link to="/resume">简历</router-link>
        <router-link to="/interview">模拟面试</router-link>
        <router-link to="/me" class="on">我的</router-link>
      </nav>
    </header>

    <div class="body">
      <!-- 概览卡片 -->
      <section class="overview">
        <div class="ov-cell"><div class="ov-num">{{ profile.total_practiced }}</div><div class="ov-lbl">累计练习</div></div>
        <div class="ov-cell"><div class="ov-num">{{ profile.avg_score }}</div><div class="ov-lbl">平均得分</div></div>
        <div class="ov-cell"><div class="ov-num">{{ profile.streak_days }}</div><div class="ov-lbl">连续学习(天)</div></div>
        <div class="ov-cell"><div class="ov-num">{{ wrongCount }}</div><div class="ov-lbl">错题</div></div>
        <div class="ov-cell"><div class="ov-num">{{ favCount }}</div><div class="ov-lbl">收藏</div></div>
      </section>

      <div class="grid">
        <!-- 能力雷达 -->
        <section class="card radar-card">
          <div class="sec-title">知识域能力雷达</div>
          <div v-if="!profile.domains?.length" class="none">还没有练习数据，先去 <router-link to="/practice">练几道题</router-link></div>
          <div v-else class="radar-wrap">
            <svg :viewBox="`0 0 ${R*2+40} ${R*2+40}`" class="radar">
              <!-- 网格圈 -->
              <polygon v-for="lvl in [0.33,0.66,1]" :key="lvl" class="grid-line"
                       :points="polygonPoints(lvl * R)" />
              <!-- 轴线 -->
              <line v-for="(p, i) in axisPoints" :key="'a'+i" class="axis"
                    :x1="cx" :y1="cy" :x2="p.x" :y2="p.y" />
              <!-- 数据多边形 -->
              <polygon class="data-poly" :points="dataPolygon" />
              <!-- 顶点标签 -->
              <text v-for="(p, i) in axisPoints" :key="'t'+i" class="axis-label"
                    :x="p.lx" :y="p.ly" text-anchor="middle">{{ p.name }}</text>
            </svg>
          </div>
        </section>

        <!-- 薄弱域 -->
        <section class="card">
          <div class="sec-title">薄弱知识域 TOP3</div>
          <div v-if="!profile.weak_domains?.length" class="none">暂无薄弱域，继续保持</div>
          <div v-for="d in profile.weak_domains" :key="d.domain" class="weak-item">
            <div class="w-head">
              <span class="w-name">{{ domainName(d.domain) }}</span>
              <span class="w-score">{{ d.avg_score }} 分</span>
            </div>
            <div class="w-bar"><i :style="{ width: d.avg_score + '%' }"></i></div>
            <div class="w-meta">练 {{ d.count }} 题 · 掌握 {{ d.mastered }} · 错 {{ d.weak }}</div>
            <button class="w-btn" @click="$router.push('/practice')">去练这个域</button>
          </div>
        </section>
      </div>

      <!-- 学习日历 -->
      <section class="card cal-card">
        <div class="sec-title">学习日历（近 12 周）</div>
        <div class="calendar">
          <div v-for="(cell, i) in calendarCells" :key="i" class="day"
               :class="'lv' + cell.level" :title="cell.day + '：' + cell.count + ' 题'"></div>
        </div>
        <div class="cal-legend">
          <span>少</span><i class="lv0"></i><i class="lv1"></i><i class="lv2"></i><i class="lv3"></i><i class="lv4"></i><span>多</span>
        </div>
      </section>

      <!-- 错题本 / 收藏 -->
      <div class="grid">
        <section class="card">
          <div class="sec-title">错题本（{{ wrong.length }}）</div>
          <div v-if="!wrong.length" class="none">暂无错题</div>
          <div v-for="w in wrong" :key="w.id" class="mini-item">
            <span class="m-q">{{ w.question_title }}</span>
            <span class="m-meta">{{ domainName(w.domain) }}</span>
          </div>
        </section>
        <section class="card">
          <div class="sec-title">收藏（{{ favorites.length }}）</div>
          <div v-if="!favorites.length" class="none">暂无收藏</div>
          <div v-for="f in favorites" :key="f.id" class="mini-item">
            <span class="m-q">{{ f.question_title }}</span>
            <span class="m-meta">{{ domainName(f.domain) }}</span>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api'

const profile = ref({ total_practiced: 0, avg_score: 0, streak_days: 0, domains: [], weak_domains: [], calendar: [] })
const favorites = ref([])
const wrong = ref([])

const DOMAIN_NAMES = {
  llm_basics: 'LLM 原理', prompt: 'Prompt', rag: 'RAG', agent: 'Agent',
  vectordb: '向量库', framework: '框架', python_backend: 'Python', ml_dl: 'ML/DL', cs_basic: 'CS 基础',
}
const domainName = (k) => DOMAIN_NAMES[k] || k

const wrongCount = computed(() => wrong.value.length)
const favCount = computed(() => favorites.value.length)

/* 雷达图 */
const R = 90
const cx = R + 20, cy = R + 20
const domains9 = ['llm_basics','prompt','rag','agent','vectordb','framework','python_backend','ml_dl','cs_basic']

function polar(i, total, r) {
  const ang = (Math.PI * 2 * i) / total - Math.PI / 2
  return { x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang) }
}
const axisPoints = computed(() => domains9.map((d, i) => {
  const p = polar(i, domains9.length, R)
  const lp = polar(i, domains9.length, R + 14)
  return { ...p, lx: lp.x, ly: lp.y, name: DOMAIN_NAMES[d] || d }
}))
function polygonPoints(r) {
  return domains9.map((_, i) => { const p = polar(i, domains9.length, r); return `${p.x},${p.y}` }).join(' ')
}
const dataPolygon = computed(() => {
  const map = {}
  for (const d of profile.value.domains || []) map[d.domain] = d.avg_score
  return domains9.map((d, i) => {
    const score = map[d] || 0
    const p = polar(i, domains9.length, R * (score / 100))
    return `${p.x},${p.y}`
  }).join(' ')
})

/* 学习日历：近 84 天 */
const calendarCells = computed(() => {
  const map = {}
  for (const c of profile.value.calendar || []) map[c.day] = c.count
  const cells = []
  const today = new Date()
  for (let i = 83; i >= 0; i--) {
    const d = new Date(today); d.setDate(d.getDate() - i)
    const key = d.toISOString().slice(0, 10)
    const count = map[key] || 0
    const level = count === 0 ? 0 : count <= 1 ? 1 : count <= 3 ? 2 : count <= 5 ? 3 : 4
    cells.push({ day: key, count, level })
  }
  return cells
})

onMounted(async () => {
  try {
    const [{ data: p }, { data: f }, { data: w }] = await Promise.all([
      api.get('/me/profile'), api.get('/bank/favorites'), api.get('/bank/wrong'),
    ])
    profile.value = p
    favorites.value = f.items || []
    wrong.value = w.items || []
  } catch { /* 忽略 */ }
})
</script>

<style scoped>
.me-page { min-height: 100vh; background: transparent; }
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 16px 28px; border-bottom: 1px solid var(--line); }
.brand-mini { display: flex; align-items: center; gap: 10px; }
.seal { width: 30px; height: 30px; display: grid; place-items: center; background: var(--seal); color: var(--paper); border-radius: 6px; font-family: var(--font-display); font-weight: 700; font-size: 16px; }
.topbar h2 { font-family: var(--font-display); font-size: 19px; font-weight: 600; }
.nav { display: flex; gap: 4px; }
.nav a { padding: 6px 14px; font-size: 13.5px; color: var(--ink-soft); border-radius: var(--radius); }
.nav a:hover { text-decoration: none; background: var(--hover); }
.nav a.on { color: var(--ink); background: var(--hover); font-weight: 500; }

.body { max-width: 900px; margin: 0 auto; padding: 28px 24px 60px; }

.overview { display: grid; grid-template-columns: repeat(5, 1fr); border: 1px solid var(--line); border-radius: 10px; background: var(--card-solid); overflow: hidden; }
.ov-cell { padding: 18px 14px; text-align: center; border-left: 1px solid var(--line-soft); }
.ov-cell:first-child { border-left: none; }
.ov-num { font-family: var(--font-display); font-size: 32px; font-weight: 700; color: var(--ink); line-height: 1; }
.ov-lbl { margin-top: 7px; font-size: 12px; color: var(--ink-faint); }

.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 18px; }
.card { background: var(--card-solid); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px; }
.sec-title { font-family: var(--font-display); font-size: 15px; font-weight: 600; margin-bottom: 14px; }
.none { font-size: 13px; color: var(--ink-faint); padding: 16px 0; text-align: center; }

.radar-wrap { display: flex; justify-content: center; }
.radar { width: 100%; max-width: 320px; }
.grid-line { fill: none; stroke: var(--line); stroke-width: 1; }
.axis { stroke: var(--line-soft); stroke-width: 1; }
.data-poly { fill: rgba(46,74,122,.18); stroke: var(--accent); stroke-width: 1.5; }
.axis-label { font-size: 10px; fill: var(--ink-soft); font-family: var(--font-mono); }

.weak-item { padding: 12px 0; border-bottom: 1px solid var(--line-soft); }
.weak-item:last-child { border-bottom: none; }
.w-head { display: flex; justify-content: space-between; margin-bottom: 6px; }
.w-name { font-size: 14px; font-weight: 500; color: var(--ink); }
.w-score { font-family: var(--font-mono); font-size: 12.5px; color: var(--seal); }
.w-bar { height: 6px; background: var(--paper-2); border-radius: 3px; overflow: hidden; }
.w-bar i { display: block; height: 100%; background: var(--seal); border-radius: 3px; }
.w-meta { font-size: 11.5px; color: var(--ink-faint); margin-top: 5px; font-family: var(--font-mono); }
.w-btn { margin-top: 9px; padding: 6px 14px; background: var(--ink); color: var(--paper); border: none; border-radius: 6px; font-size: 12px; }
.w-btn:hover { background: var(--accent); }

.cal-card { margin-top: 16px; }
.calendar { display: grid; grid-template-columns: repeat(12, 1fr); gap: 4px; }
.day { aspect-ratio: 1; border-radius: 3px; background: var(--paper-2); }
.day.lv1 { background: #D8E3D2; } .day.lv2 { background: #A8C79E; }
.day.lv3 { background: #6FA35F; } .day.lv4 { background: #3E7C43; }
.cal-legend { display: flex; align-items: center; gap: 5px; justify-content: flex-end; margin-top: 10px; font-size: 11px; color: var(--ink-faint); }
.cal-legend i { width: 12px; height: 12px; border-radius: 3px; background: var(--paper-2); display: inline-block; }
.cal-legend i.lv1 { background:#D8E3D2 } .cal-legend i.lv2 { background:#A8C79E } .cal-legend i.lv3 { background:#6FA35F } .cal-legend i.lv4 { background:#3E7C43 }

.mini-item { display: flex; justify-content: space-between; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--line-soft); align-items: baseline; }
.mini-item:last-child { border-bottom: none; }
.m-q { font-size: 13px; color: var(--ink); line-height: 1.5; }
.m-meta { flex: 0 0 auto; font-size: 11px; color: var(--ink-faint); font-family: var(--font-mono); }

@media (max-width: 720px) { .overview { grid-template-columns: repeat(2,1fr); } .grid { grid-template-columns: 1fr; } }
</style>
