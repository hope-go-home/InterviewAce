<template>
  <div class="page">
    <header class="topbar">
      <div class="brand-mini"><span class="seal">试</span><h2>模拟面试</h2></div>
      <nav class="nav">
        <router-link to="/chat">问答</router-link>
        <router-link to="/bank">题库</router-link>
        <router-link to="/practice">练习</router-link>
        <router-link to="/resume">简历</router-link>
        <router-link to="/interview" class="on">模拟面试</router-link>
        <router-link to="/me">我的</router-link>
      </nav>
    </header>

    <div class="body">
      <!-- 配置大厅 -->
      <section class="card">
        <div class="sec-title">配置一场模拟面试</div>
        <div class="form-grid">
          <label>岗位
            <select v-model="form.position">
              <option v-for="p in POSITIONS" :key="p.key" :value="p.key">{{ p.name }}</option>
            </select>
          </label>
          <label>级别
            <select v-model="form.level">
              <option v-for="l in LEVELS" :key="l.key" :value="l.key">{{ l.name }}</option>
            </select>
          </label>
          <label>题目数量
            <select v-model.number="form.num_questions">
              <option :value="5">5 题</option>
              <option :value="10">10 题</option>
              <option :value="15">15 题</option>
            </select>
          </label>
        </div>
        <label class="dom-label">考察知识域（不选则全库轮转）</label>
        <div class="dom-chips">
          <button v-for="d in domainOptions" :key="d.key" type="button"
                  class="chip" :class="{ on: form.domains.includes(d.key) }"
                  @click="toggleDomain(d.key)">{{ d.name }}</button>
        </div>
        <button class="start" @click="start" :disabled="starting">
          {{ starting ? '出题中…' : '开始面试' }}
        </button>
      </section>

      <!-- 历史面试 -->
      <section v-if="history.length" class="card history">
        <div class="sec-title">历史面试</div>
        <div v-for="h in history" :key="h.id" class="h-item" @click="openReport(h)">
          <div class="h-left">
            <span class="h-pos">{{ posName(h.position) }} · {{ lvlName(h.level) }}</span>
            <span class="h-meta">{{ h.num_questions }} 题 · {{ h.created_at.slice(0, 10) }}</span>
          </div>
          <div class="h-right">
            <span v-if="h.status === 'finished'" class="h-score">{{ h.total_score }} 分</span>
            <span v-else class="h-ongoing">进行中</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { POSITIONS, LEVELS } from '../stores/settings'

const router = useRouter()
const form = reactive({ position: 'ai_app_dev', level: 'campus', num_questions: 10, domains: [] })
const starting = ref(false)
const history = ref([])

const domainOptions = [
  { key: 'llm_basics', name: 'LLM 原理' }, { key: 'prompt', name: 'Prompt' },
  { key: 'rag', name: 'RAG' }, { key: 'agent', name: 'Agent' },
  { key: 'vectordb', name: '向量库' }, { key: 'framework', name: '框架' },
  { key: 'python_backend', name: 'Python' }, { key: 'ml_dl', name: 'ML/DL' },
  { key: 'cs_basic', name: 'CS 基础' },
]
const posName = (k) => POSITIONS.find(p => p.key === k)?.name || k
const lvlName = (k) => LEVELS.find(l => l.key === k)?.name || k

function toggleDomain(d) {
  const i = form.domains.indexOf(d)
  if (i >= 0) form.domains.splice(i, 1); else form.domains.push(d)
}

async function start() {
  starting.value = true
  try {
    const { data } = await api.post('/interview/start', { ...form })
    router.push(`/interview/${data.interview_id}`)
  } catch (e) {
    alert(e.response?.data?.detail || '开始面试失败')
  } finally {
    starting.value = false
  }
}

function openReport(h) {
  router.push(h.status === 'finished' ? `/interview/${h.id}/report` : `/interview/${h.id}`)
}

onMounted(async () => {
  try {
    const { data } = await api.get('/interviews')
    history.value = data.items || []
  } catch { /* 忽略 */ }
})
</script>

<style scoped>
.page { min-height: 100vh; background: transparent; }
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 16px 28px; border-bottom: 1px solid var(--line); flex-wrap: wrap; gap: 8px; }
.brand-mini { display: flex; align-items: center; gap: 10px; }
.seal { width: 30px; height: 30px; display: grid; place-items: center; background: var(--seal); color: var(--paper); border-radius: 6px; font-family: var(--font-display); font-weight: 700; font-size: 16px; }
.topbar h2 { font-family: var(--font-display); font-size: 19px; font-weight: 600; }
.nav { display: flex; gap: 4px; flex-wrap: wrap; }
.nav a { padding: 6px 13px; font-size: 13px; color: var(--ink-soft); border-radius: var(--radius); }
.nav a:hover { text-decoration: none; background: var(--hover); }
.nav a.on { color: var(--ink); background: var(--hover); font-weight: 500; }

.body { max-width: 720px; margin: 0 auto; padding: 28px 24px 60px; }
.card { background: var(--card-solid); border: 1px solid var(--line); border-radius: 10px; padding: 22px 24px; margin-bottom: 18px; }
.sec-title { font-family: var(--font-display); font-size: 17px; font-weight: 600; margin-bottom: 16px; }

.form-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; margin-bottom: 16px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--ink-soft); }
label select { padding: 9px 11px; font-size: 13.5px; background: var(--paper); border: 1px solid var(--line); border-radius: var(--radius); outline: none; color: var(--ink); }
.dom-label { font-size: 12.5px; color: var(--ink-soft); margin-bottom: 8px; display: block; }
.dom-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.chip { padding: 7px 13px; font-size: 12.5px; color: var(--ink-soft); background: var(--paper-2); border: 1px solid var(--line-soft); border-radius: 7px; }
.chip:hover { border-color: var(--accent); color: var(--accent); }
.chip.on { background: var(--ink); color: var(--paper); border-color: var(--ink); }
.start { width: 100%; padding: 13px; background: var(--ink); color: var(--paper); border: none; border-radius: 8px; font-size: 15px; font-weight: 500; letter-spacing: 1px; }
.start:hover:not(:disabled) { background: var(--accent); }
.start:disabled { background: var(--ink-faint); cursor: not-allowed; }

.history .h-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 4px; border-bottom: 1px solid var(--line-soft); cursor: pointer; }
.history .h-item:last-child { border-bottom: none; }
.history .h-item:hover { background: var(--paper-2); }
.h-pos { font-size: 13.5px; font-weight: 500; color: var(--ink); display: block; }
.h-meta { font-size: 11.5px; color: var(--ink-faint); font-family: var(--font-mono); }
.h-score { font-family: var(--font-display); font-size: 18px; font-weight: 700; color: var(--accent); }
.h-ongoing { font-size: 12px; color: var(--orange, #C79017); }

@media (max-width: 640px) { .form-grid { grid-template-columns: 1fr; } }
</style>
