<template>
  <div class="resume-page">
    <header class="topbar">
      <div class="brand-mini"><span class="seal">历</span><h2>简历备考</h2></div>
      <nav class="nav">
        <router-link to="/chat">问答</router-link>
        <router-link to="/bank">题库</router-link>
        <router-link to="/practice">练习</router-link>
        <router-link to="/resume" class="on">简历</router-link>
        <router-link to="/interview">模拟面试</router-link>
          <router-link to="/me">我的</router-link>
      </nav>
    </header>

    <div class="body">
      <!-- 历史简历 -->
      <section v-if="history.length" class="card history-card">
        <div class="sec-title-sm">历史简历</div>
        <div class="hist-list">
          <button v-for="h in history" :key="h.id" class="hist-item"
                  :class="{ on: currentResumeId === h.id }" @click="loadResume(h.id)">
            <span class="h-name">{{ h.name || '（未命名）' }}</span>
            <span class="h-meta">{{ h.target || '—' }} · {{ h.filename }} · {{ h.created_at.slice(0, 10) }}</span>
          </button>
        </div>
      </section>

      <!-- 上传区 -->
      <section class="upload card">
        <div class="up-title">上传简历，生成针对性面试题</div>
        <p class="up-desc">支持 PDF / Word / TXT / MD（扫描件自动 OCR）。解析出你的技能与项目，生成面试官最可能问的问题。</p>
        <label class="up-zone" :class="{ drag: dragging }"
               @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="onDrop">
          <input type="file" ref="fileInput" accept=".pdf,.docx,.txt,.md" hidden @change="onPick">
          <template v-if="!parsing">
            <div class="up-icon">📄</div>
            <div class="up-text">{{ fileName || '点击选择或拖拽简历到这里' }}</div>
            <div class="up-hint">PDF / DOCX / TXT / MD，不超过 10MB</div>
          </template>
          <template v-else>
            <div class="up-icon spin">⏳</div>
            <div class="up-text">正在解析简历并出题…</div>
          </template>
        </label>
      </section>

      <!-- 解析结果 -->
      <template v-if="result">
        <section class="card profile">
          <div class="p-row"><span class="lbl">姓名</span><span class="val">{{ result.name || '—' }}</span></div>
          <div class="p-row"><span class="lbl">目标岗位</span><span class="val">{{ result.target || '—' }}</span></div>
          <div class="p-row"><span class="lbl">技能</span>
            <span class="val tags"><i v-for="s in result.skills" :key="s">{{ s }}</i></span></div>
          <div class="p-row"><span class="lbl">项目</span>
            <span class="val"><div v-for="(p, i) in result.projects" :key="i" class="proj">{{ p }}</div></span></div>
        </section>

        <!-- 三个子功能 Tab -->
        <div class="tabs">
          <button :class="{ on: rtab === 'questions' }" @click="rtab = 'questions'">针对性面试题</button>
          <button :class="{ on: rtab === 'pitch' }" @click="rtab = 'pitch'; loadPitch()">自我介绍话术</button>
          <button :class="{ on: rtab === 'rehearse' }" @click="rtab = 'rehearse'">项目问答预演</button>
        </div>

        <!-- 面试题 -->
        <section v-if="rtab === 'questions'" class="questions">
          <div class="q-head">
            <div class="sec-title">针对性面试题（{{ result.questions.length }}）</div>
            <button class="primary" @click="addAllToPractice" :disabled="addingAll">
              {{ addingAll ? '加入中…' : '全部加入练习题库' }}
            </button>
          </div>
          <div v-for="(item, i) in result.questions" :key="i" class="q-card">
            <div class="q-text">{{ item.question }}</div>
            <div class="q-foot">
              <span class="dom">{{ domainName(item.domain) }}</span>
              <span class="why">{{ item.why }}</span>
            </div>
          </div>
        </section>

        <!-- 自我介绍话术 -->
        <section v-if="rtab === 'pitch'" class="card">
          <div class="sec-title">自我介绍话术</div>
          <div v-if="pitchLoading" class="none">生成中…</div>
          <template v-else-if="pitch">
            <div class="pitch-block">
              <div class="pitch-lbl">60 秒版</div>
              <p class="pitch-text">{{ pitch.pitch_60 }}</p>
            </div>
            <div class="pitch-block">
              <div class="pitch-lbl">90 秒版</div>
              <p class="pitch-text">{{ pitch.pitch_90 }}</p>
            </div>
          </template>
          <div v-else class="none">点击上方 Tab 生成话术</div>
        </section>

        <!-- 项目预演 -->
        <section v-if="rtab === 'rehearse'" class="rehearse">
          <div class="sec-title">项目问答预演</div>
          <p class="rh-desc">选一个简历里的项目，生成层层递进的深挖问题和应答要点。</p>
          <div class="rh-projects">
            <button v-for="(p, i) in result.projects" :key="i" class="chip"
                    :class="{ on: rehearseProject === p }" @click="runRehearse(p)">
              项目 {{ i + 1 }}
            </button>
          </div>
          <div v-if="rehearseLoading" class="none">出题中…</div>
          <div v-else-if="rehearse" class="rh-list">
            <div class="rh-project">{{ rehearse.project }}</div>
            <div v-for="(q, i) in rehearse.questions" :key="i" class="rh-item">
              <div class="rh-q">{{ i + 1 }}. {{ q.question }}</div>
              <ul class="rh-points"><li v-for="(pt, j) in q.points" :key="j">{{ pt }}</li></ul>
            </div>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from '../api'
import { useSettingsStore } from '../stores/settings'

const settings = useSettingsStore()

const fileInput = ref(null)
const fileName = ref('')
const dragging = ref(false)
const parsing = ref(false)
const result = ref(null)
const addingAll = ref(false)
const history = ref([])
const currentResumeId = ref(null)

// Tab：questions / pitch / rehearse
const rtab = ref('questions')
const pitch = ref(null)
const pitchLoading = ref(false)
const rehearse = ref(null)
const rehearseLoading = ref(false)
const rehearseProject = ref('')

async function loadPitch() {
  if (pitch.value || !result.value) return
  pitchLoading.value = true
  try {
    const { data } = await api.post('/resume/pitch', {
      profile: { name: result.value.name, target: result.value.target,
                 skills: result.value.skills, projects: result.value.projects },
      level: settings.level, resume_id: currentResumeId.value,
    })
    pitch.value = data
  } catch (e) {
    alert(e.response?.data?.detail || '生成话术失败')
  } finally {
    pitchLoading.value = false
  }
}

async function runRehearse(p) {
  rehearseProject.value = p
  rehearseLoading.value = true
  rehearse.value = null
  try {
    const { data } = await api.post('/resume/rehearse', {
      project: p, skills: result.value.skills, n: 5, resume_id: currentResumeId.value,
    })
    rehearse.value = data
  } catch (e) {
    alert(e.response?.data?.detail || '项目预演失败')
  } finally {
    rehearseLoading.value = false
  }
}

const DOMAIN_NAMES = {
  llm_basics: 'LLM 原理', prompt: 'Prompt 工程', rag: 'RAG', agent: 'Agent',
  vectordb: '向量数据库', framework: '框架', python_backend: 'Python 后端',
  ml_dl: 'ML/DL', cs_basic: 'CS 基础',
}
const domainName = (k) => DOMAIN_NAMES[k] || k

function onPick(e) { const f = e.target.files[0]; if (f) upload(f) }
function onDrop(e) { dragging.value = false; const f = e.dataTransfer.files[0]; if (f) upload(f) }

async function upload(file) {
  fileName.value = file.name
  parsing.value = true
  result.value = null
  try {
    const fd = new FormData()
    fd.append('file', file)
    // 不要手动设 Content-Type，让浏览器自动带 multipart boundary
    const { data } = await api.post('/resume/upload', fd, { timeout: 180000 })
    result.value = data
    currentResumeId.value = data.resume_id || null
    pitch.value = null
    rehearse.value = null
    loadHistory()
  } catch (e) {
    alert(e.response?.data?.detail || '解析失败')
    fileName.value = ''
  } finally {
    parsing.value = false
  }
}

async function loadHistory() {
  try {
    const { data } = await api.get('/resume/list')
    history.value = data.items || []
  } catch { /* 忽略 */ }
}

async function loadResume(id) {
  try {
    const { data } = await api.get(`/resume/${id}`)
    result.value = data
    currentResumeId.value = id
    pitch.value = data.pitch || null
    rehearse.value = data.rehearse || null
    rtab.value = 'questions'
  } catch { /* 忽略 */ }
}

async function addAllToPractice() {
  if (!result.value?.questions?.length) return
  addingAll.value = true
  try {
    for (const item of result.value.questions) {
      await api.post('/bank/add', {
        question: item.question, answer: item.why || '（待补充完整答案）' + '。'.repeat(20),
        domain: item.domain || 'llm_basics', difficulty: 2,
      }).catch(() => {})
    }
    alert('已加入题库，可在练习模式抽取')
  } finally {
    addingAll.value = false
  }
}

onMounted(loadHistory)
</script>

<style scoped>
.resume-page { min-height: 100vh; background: transparent; }
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

.body { max-width: 780px; margin: 0 auto; padding: 28px 24px 60px; }
.card { background: var(--card-solid); border: 1px solid var(--line); border-radius: 10px; padding: 22px 24px; }

.up-title { font-family: var(--font-display); font-size: 17px; font-weight: 600; margin-bottom: 6px; }
.up-desc { font-size: 13px; color: var(--ink-soft); margin-bottom: 16px; line-height: 1.7; }
.up-zone { display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 36px 20px; border: 1.5px dashed var(--line); border-radius: 10px; cursor: pointer;
  transition: border-color .15s, background .15s; text-align: center; }
.up-zone:hover, .up-zone.drag { border-color: var(--accent); background: var(--accent-bg); }
.up-icon { font-size: 34px; margin-bottom: 10px; }
.up-icon.spin { animation: pulse 1.2s ease infinite; }
@keyframes pulse { 50% { opacity: .4 } }
.up-text { font-size: 14px; color: var(--ink); }
.up-hint { font-size: 12px; color: var(--ink-faint); margin-top: 5px; }

.profile { margin-top: 20px; }
.p-row { display: flex; gap: 14px; padding: 8px 0; border-bottom: 1px solid var(--line-soft); }
.p-row:last-child { border-bottom: none; }
.lbl { flex: 0 0 68px; font-size: 12.5px; color: var(--ink-faint); }
.val { flex: 1; font-size: 13.5px; color: var(--ink); }
.val.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.val.tags i { font-style: normal; font-size: 12px; background: var(--accent-bg); color: var(--accent);
  padding: 2px 9px; border-radius: 5px; }
.proj { padding: 3px 0; font-size: 13px; }

.questions { margin-top: 22px; }
.q-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.sec-title { font-family: var(--font-display); font-size: 16px; font-weight: 600; }
.primary { padding: 9px 18px; background: var(--ink); color: var(--paper); border: none;
  border-radius: var(--radius); font-size: 13px; font-weight: 500; }
.primary:hover:not(:disabled) { background: var(--accent); }
.primary:disabled { background: var(--ink-faint); cursor: not-allowed; }
.q-card { background: var(--card-solid); border: 1px solid var(--line-soft); border-radius: 8px;
  padding: 14px 16px; margin-bottom: 8px; }
.q-text { font-size: 14px; font-weight: 500; color: var(--ink); line-height: 1.65; margin-bottom: 8px; }
.q-foot { display: flex; gap: 10px; align-items: baseline; }
.dom { font-size: 11px; font-family: var(--font-mono); color: var(--accent); flex: 0 0 auto; }
.why { font-size: 12px; color: var(--ink-faint); line-height: 1.5; }

/* 子功能 Tab */
.tabs { display: flex; gap: 6px; margin: 20px 0 16px; border-bottom: 1px solid var(--line); }
.tabs button { padding: 9px 16px; font-size: 13.5px; color: var(--ink-soft); background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.tabs button:hover { color: var(--ink); }
.tabs button.on { color: var(--ink); font-weight: 600; border-bottom-color: var(--seal); }

.pitch-block { margin-bottom: 18px; }
.pitch-block:last-child { margin-bottom: 0; }
.pitch-lbl { font-size: 12px; color: var(--ink-faint); font-family: var(--font-mono); margin-bottom: 7px; letter-spacing: 1px; }
.pitch-text { font-size: 14px; line-height: 1.9; color: var(--ink); background: var(--paper-2); padding: 14px 16px; border-radius: 8px; }

.rh-desc { font-size: 13px; color: var(--ink-soft); margin-bottom: 14px; }
.rh-projects { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.rh-projects .chip { padding: 7px 14px; font-size: 12.5px; background: var(--paper-2); border: 1px solid var(--line-soft); border-radius: 7px; color: var(--ink-soft); cursor: pointer; }
.rh-projects .chip.on { background: var(--ink); color: var(--paper); border-color: var(--ink); }
.rh-project { font-size: 12.5px; color: var(--ink-faint); margin-bottom: 12px; font-family: var(--font-mono); }
.rh-item { background: var(--card-solid); border: 1px solid var(--line-soft); border-radius: 8px; padding: 13px 16px; margin-bottom: 9px; }
.rh-q { font-size: 14px; font-weight: 500; color: var(--ink); margin-bottom: 8px; line-height: 1.6; }
.rh-points { padding-left: 18px; margin: 0; font-size: 13px; color: var(--ink-soft); line-height: 1.75; }
.none { text-align: center; color: var(--ink-faint); font-size: 13px; padding: 20px 0; }

/* 历史简历 */
.history-card { margin-bottom: 18px; padding: 16px 20px; }
.sec-title-sm { font-size: 12px; color: var(--ink-faint); letter-spacing: 1px; margin-bottom: 10px; }
.hist-list { display: flex; flex-direction: column; gap: 5px; }
.hist-item { display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
  padding: 9px 12px; border-radius: 7px; border: 1px solid var(--line-soft); background: transparent;
  cursor: pointer; text-align: left; transition: border-color .15s, background .15s; }
.hist-item:hover { border-color: var(--accent); background: var(--hover); }
.hist-item.on { border-color: var(--seal); background: rgba(244,157,112,.08); }
.h-name { font-size: 13.5px; font-weight: 500; color: var(--ink); }
.h-meta { font-size: 11.5px; color: var(--ink-faint); font-family: var(--font-mono); }
</style>
