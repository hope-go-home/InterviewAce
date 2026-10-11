<template>
  <div class="practice-page">
    <header class="topbar">
      <div class="brand-mini"><span class="seal">练</span><h2>答题练习</h2></div>
      <nav class="nav">
        <router-link to="/chat">问答</router-link>
        <router-link to="/bank">题库</router-link>
        <router-link to="/practice" class="on">练习</router-link>
        <router-link to="/resume">简历</router-link>
          <router-link to="/interview">模拟面试</router-link>
          <router-link to="/me">我的</router-link>
      </nav>
    </header>

    <div class="body">
      <!-- 筛选条 -->
      <div class="filter-bar">
        <select v-model="filter.domain" @change="resetAndNext">
          <option :value="null">全部知识域</option>
          <option v-for="d in domainOptions" :key="d.key" :value="d.key">{{ d.name }}</option>
        </select>
        <PosLevelPicker />
        <span class="count">已练 {{ practicedCount }} 题</span>
      </div>

      <!-- 题卡 -->
      <div v-if="loadingQ" class="card center">出题中…</div>
      <div v-else-if="!current" class="card center">
        <p>点击下方按钮抽一道题开始练习</p>
        <button class="primary" @click="next">开始</button>
      </div>

      <template v-else>
        <div class="card q-card">
          <div class="q-meta">
            <span class="dom">{{ domainName(current.domain) }}</span>
            <span class="diff">{{ ['', '基础', '应用', '进阶'][current.difficulty] }}</span>
            <span v-if="current.company" class="company">{{ current.company }}</span>
          </div>
          <div class="q-title">{{ current.title }}</div>

          <!-- 作答区 -->
          <template v-if="!result">
            <div class="answer-row">
              <textarea v-model="myAnswer" rows="6" :disabled="judging"
                        placeholder="写下你的作答…（分点作答更好，可点麦克风语音输入）"></textarea>
              <VoiceButton class="vbtn" :disabled="judging" @text="(t) => myAnswer = (myAnswer ? myAnswer + ' ' : '') + t" />
            </div>
            <div class="actions">
              <button class="ghost" @click="next">换一题</button>
              <button class="primary" @click="submit" :disabled="judging || !myAnswer.trim()">
                {{ judging ? '评分中…' : '提交作答' }}
              </button>
            </div>
          </template>

          <!-- 评分结果 -->
          <div v-else class="result">
            <div class="score-row">
              <div class="score" :class="scoreClass">{{ result.score }}<i>分</i></div>
              <div class="dims">
                <div v-for="(v, k) in result.dimensions" :key="k" class="dim">
                  <span class="k">{{ k }}</span>
                  <div class="bar"><i :style="{ width: v + '%' }"></i></div>
                  <span class="v">{{ v }}</span>
                </div>
              </div>
            </div>

            <div class="feedback">{{ result.feedback }}</div>

            <div v-if="result.missing_points?.length" class="missing">
              <div class="lbl">遗漏/答错的要点</div>
              <ul><li v-for="(p, i) in result.missing_points" :key="i">{{ p }}</li></ul>
            </div>

            <div class="ref">
              <div class="lbl">参考答案</div>
              <div class="ref-body" v-html="renderRef(result.reference_answer)"></div>
            </div>

            <div class="actions">
              <button class="ghost" @click="fav">{{ favorited ? '已收藏' : '收藏' }}</button>
              <button v-if="result.is_wrong" class="ghost wrong" disabled>已加入错题本</button>
              <button class="primary" @click="next">下一题</button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import api from '../api'
import { useSettingsStore } from '../stores/settings'
import PosLevelPicker from '../components/PosLevelPicker.vue'
import VoiceButton from '../components/VoiceButton.vue'

const settings = useSettingsStore()

const domainOptions = [
  { key: 'llm_basics', name: 'LLM 原理' }, { key: 'prompt', name: 'Prompt 工程' },
  { key: 'rag', name: 'RAG' }, { key: 'agent', name: 'Agent' },
  { key: 'vectordb', name: '向量数据库' }, { key: 'framework', name: '框架' },
  { key: 'python_backend', name: 'Python 后端' }, { key: 'ml_dl', name: 'ML/DL' },
  { key: 'cs_basic', name: 'CS 基础' },
]
const domainName = (k) => domainOptions.find(d => d.key === k)?.name || k

const filter = reactive({ domain: null })
const current = ref(null)
const myAnswer = ref('')
const result = ref(null)
const judging = ref(false)
const loadingQ = ref(false)
const favorited = ref(false)
const practicedCount = ref(0)

const scoreClass = computed(() => {
  const s = result.value?.score
  if (s == null) return ''
  if (s >= 85) return 'good'
  if (s >= 60) return 'mid'
  return 'bad'
})

function renderRef(text) {
  const m = (text || '').split('【参考答案】')
  const body = m.length > 1 ? m.slice(1).join('【参考答案】') : text
  return DOMPurify.sanitize(marked.parse(body || ''))
}

// 预取队列：一次拿一批，下一题即时切换
const queue = ref([])

async function refillQueue() {
  try {
    const { data } = await api.get('/practice/batch', {
      params: { n: 8, domain: filter.domain, level: settings.level, position: settings.position },
    })
    return data.items || []
  } catch { return [] }
}

async function next() {
  result.value = null
  myAnswer.value = ''
  favorited.value = false

  // 队列空了就先补一批
  if (queue.value.length === 0) {
    loadingQ.value = true
    queue.value = await refillQueue()
    loadingQ.value = false
    if (queue.value.length === 0) {
      current.value = null
      return
    }
  }
  current.value = queue.value.shift()

  // 队列不足 3 题时后台静默补货
  if (queue.value.length < 3) {
    refillQueue().then(items => {
      const have = new Set([current.value?.title, ...queue.value.map(q => q.title)])
      queue.value.push(...items.filter(q => !have.has(q.title)))
    })
  }
}

function resetAndNext() {
  if (current.value) next()
}

async function submit() {
  judging.value = true
  try {
    const { data } = await api.post('/practice/answer', {
      question_title: current.value.title, question_url: current.value.url,
      domain: current.value.domain, difficulty: current.value.difficulty,
      level: settings.level, position: settings.position, my_answer: myAnswer.value,
    }, { timeout: 180000 })   // 评分要跑检索+重排+LLM，CPU 上较慢，超时放宽到 180s
    result.value = data
    practicedCount.value++
  } catch (e) {
    alert(e.response?.data?.detail || '评分失败')
  } finally {
    judging.value = false
  }
}

async function fav() {
  try {
    await api.post('/bank/favorite', {
      question_title: current.value.title, question_url: current.value.url,
      domain: current.value.domain, difficulty: current.value.difficulty, ftype: 'fav',
    })
    favorited.value = true
  } catch { /* 忽略 */ }
}

onMounted(async () => {
  try {
    const { data } = await api.get('/practice/records')
    practicedCount.value = (data.records || []).length
  } catch { /* 忽略 */ }
  next()
})
</script>

<style scoped>
.practice-page { min-height: 100vh; background: transparent; }
.topbar { display: flex; align-items: center; justify-content: space-between;
  padding: 16px 28px; border-bottom: 1px solid var(--line); }
.brand-mini { display: flex; align-items: center; gap: 10px; }
.seal { width: 30px; height: 30px; display: grid; place-items: center; background: var(--seal);
  color: var(--paper); border-radius: 6px; font-family: var(--font-display); font-weight: 700; font-size: 16px; }
.topbar h2 { font-family: var(--font-display); font-size: 19px; font-weight: 600; }
.nav { display: flex; gap: 4px; }
.nav a { padding: 6px 14px; font-size: 13.5px; color: var(--ink-soft); border-radius: var(--radius); }
.nav a:hover { text-decoration: none; background: var(--hover); }
.nav a.on { color: var(--ink); background: var(--hover); font-weight: 500; }

.body { max-width: 760px; margin: 0 auto; padding: 28px 24px 60px; }

.filter-bar { display: flex; gap: 10px; align-items: center; margin-bottom: 18px; }
.filter-bar select { padding: 8px 11px; font-size: 13px; background: var(--card-solid);
  border: 1px solid var(--line); border-radius: var(--radius); outline: none; color: var(--ink); }
.count { margin-left: auto; font-size: 12px; color: var(--ink-faint); font-family: var(--font-mono); }

.card { background: var(--card-solid); border: 1px solid var(--line); border-radius: 10px; padding: 22px 24px; }
.card.center { text-align: center; padding: 60px 24px; color: var(--ink-soft); }
.card.center p { margin-bottom: 18px; }

.q-meta { display: flex; gap: 8px; margin-bottom: 12px; }
.q-meta span { font-size: 11.5px; padding: 2px 8px; border-radius: 4px; font-family: var(--font-mono); }
.dom { background: var(--accent-bg); color: var(--accent); }
.diff { background: var(--paper-2); color: var(--orange, #f0a35e); }
.company { background: #EAF4EF; color: var(--ok); }

.q-title { font-family: var(--font-display); font-size: 19px; font-weight: 600; line-height: 1.55;
  margin-bottom: 18px; color: var(--ink); }

textarea { width: 100%; padding: 13px 14px; font-size: 14px; font-family: inherit; color: var(--ink);
  background: var(--card-solid); border: 1px solid var(--line); border-radius: 8px; outline: none;
  resize: vertical; line-height: 1.7; }
textarea:focus { border-color: var(--accent); }
.answer-row { display: flex; gap: 8px; align-items: flex-start; }
.answer-row textarea { flex: 1; }
.answer-row .vbtn { margin-top: 2px; }
.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
.primary { padding: 10px 22px; background: var(--ink); color: var(--paper); border: none;
  border-radius: var(--radius); font-size: 13.5px; font-weight: 500; }
.primary:hover:not(:disabled) { background: var(--accent); }
.primary:disabled { background: var(--ink-faint); cursor: not-allowed; }
.ghost { padding: 10px 18px; background: none; border: 1px solid var(--line);
  border-radius: var(--radius); color: var(--ink-soft); font-size: 13px; }
.ghost:hover { border-color: var(--accent); color: var(--accent); }
.ghost.wrong { color: var(--seal); border-color: var(--seal); cursor: default; }

/* 评分结果 */
.result { border-top: 1px dashed var(--line); padding-top: 18px; }
.score-row { display: flex; gap: 24px; align-items: center; margin-bottom: 16px; }
.score { font-family: var(--font-display); font-size: 44px; font-weight: 700; line-height: 1; }
.score i { font-size: 14px; font-weight: 400; font-style: normal; color: var(--ink-faint); margin-left: 3px; }
.score.good { color: var(--ok); } .score.mid { color: #C79017; } .score.bad { color: var(--seal); }
.dims { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.dim { display: flex; align-items: center; gap: 10px; font-size: 12.5px; }
.dim .k { flex: 0 0 48px; color: var(--ink-soft); }
.dim .bar { flex: 1; height: 6px; background: var(--paper-2); border-radius: 3px; overflow: hidden; }
.dim .bar i { display: block; height: 100%; background: var(--accent); border-radius: 3px; }
.dim .v { flex: 0 0 30px; text-align: right; font-family: var(--font-mono); font-size: 11.5px; color: var(--ink-soft); }

.feedback { font-size: 14px; line-height: 1.75; color: var(--ink); margin-bottom: 14px; }
.missing { margin-bottom: 14px; }
.lbl { font-size: 12px; color: var(--ink-faint); letter-spacing: 1px; margin-bottom: 7px; }
.missing ul { padding-left: 20px; margin: 0; font-size: 13.5px; color: var(--ink-soft); line-height: 1.7; }
.ref { background: var(--paper-2); border-radius: 8px; padding: 14px 16px; margin-bottom: 6px; }
.ref-body { font-size: 13.5px; line-height: 1.8; color: var(--ink); }
.ref-body :deep(p) { margin: 6px 0; }
.ref-body :deep(ul), .ref-body :deep(ol) { padding-left: 20px; margin: 6px 0; }
.ref-body :deep(pre) { background: var(--pre-bg); color: var(--pre-text); padding: 10px 12px; border-radius: 6px; overflow-x: auto; font-size: 12px; margin: 8px 0; }
.ref-body :deep(code) { font-family: var(--font-mono); font-size: 12px; background: rgba(255,255,255,.08); padding: 1px 5px; border-radius: 3px; }
.ref-body :deep(pre code) { background: none; padding: 0; }
</style>
