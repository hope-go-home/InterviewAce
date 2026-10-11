<template>
  <div class="bank-page">
    <header class="topbar">
      <div class="brand-mini">
        <span class="seal">求</span>
        <h2>题库总览</h2>
      </div>
      <nav class="nav">
        <button class="add-btn" @click="showAdd = true">＋ 录入题目</button>
        <button class="up-btn" @click="fileInput.click()">⇪ 上传文档</button>
        <input type="file" ref="fileInput" accept=".pdf,.docx,.txt,.md" hidden @change="onUpload">
        <router-link to="/chat">问答</router-link>
        <router-link to="/bank" class="on">题库</router-link>
        <router-link to="/practice">练习</router-link>
        <router-link to="/resume">简历</router-link>
          <router-link to="/interview">模拟面试</router-link>
          <router-link to="/me">我的</router-link>
      </nav>
    </header>

    <!-- 手动录入弹窗 -->
    <div v-if="showAdd" class="mask" @click.self="showAdd = false">
      <div class="modal">
        <div class="m-title">录入题目</div>
        <label>题干<textarea v-model="addForm.question" rows="2" placeholder="面试官会问的原话…" /></label>
        <label>参考答案<textarea v-model="addForm.answer" rows="6" placeholder="分点作答，可含代码…" /></label>
        <div class="m-row">
          <label>知识域
            <select v-model="addForm.domain">
              <option v-for="d in domainOptions" :key="d.key" :value="d.key">{{ d.name }}</option>
            </select>
          </label>
          <label>难度
            <select v-model="addForm.difficulty">
              <option :value="1">基础</option>
              <option :value="2">应用</option>
              <option :value="3">进阶</option>
            </select>
          </label>
        </div>
        <div class="m-row">
          <label>公司（可选）<input v-model="addForm.company" placeholder="如：字节跳动" /></label>
          <label>来源链接（可选）<input v-model="addForm.url" placeholder="https://…" /></label>
        </div>
        <p v-if="addError" class="m-err">{{ addError }}</p>
        <div class="m-actions">
          <button class="cancel" @click="showAdd = false">取消</button>
          <button class="ok" @click="submitAdd" :disabled="adding">{{ adding ? '入库中…' : '入库' }}</button>
        </div>
      </div>
    </div>

    <div class="body">
      <!-- Tab 切换：题库 / 待补题 -->
      <div class="tabs">
        <button :class="{ on: tab === 'bank' }" @click="tab = 'bank'">题库</button>
        <button :class="{ on: tab === 'pending' }" @click="tab = 'pending'; loadPending()">
          待补题<span v-if="pendingCount" class="pend-badge">{{ pendingCount }}</span>
        </button>
      </div>

      <!-- 统计总览 -->
      <section class="stat-grid" v-if="tab === 'bank'">
        <div class="stat-cell big">
          <div class="num">{{ stats.total }}</div>
          <div class="lbl">题库总量</div>
        </div>
        <div class="stat-cell">
          <div class="lbl2">类型构成</div>
          <div class="bar-row" v-for="(v, k) in stats.q_type" :key="k">
            <span class="k">{{ k === 'qa_pair' ? '问答题' : '知识短文' }}</span>
            <div class="bar"><i :style="{ width: pct(v, stats.total) }"></i></div>
            <span class="v">{{ v }}</span>
          </div>
        </div>
        <div class="stat-cell">
          <div class="lbl2">难度分布</div>
          <div class="bar-row" v-for="d in stats.difficulty" :key="d.level">
            <span class="k">{{ ['', '基础', '应用', '进阶'][d.level] }}</span>
            <div class="bar"><i :style="{ width: pct(d.count, maxDiff) }"></i></div>
            <span class="v">{{ d.count }}</span>
          </div>
        </div>
        <div class="stat-cell">
          <div class="lbl2">来源构成</div>
          <div class="bar-row" v-for="(v, k) in stats.origin" :key="k">
            <span class="k">{{ k }}</span>
            <div class="bar"><i :style="{ width: pct(v, stats.total) }"></i></div>
            <span class="v">{{ v }}</span>
          </div>
        </div>
      </section>

      <!-- 知识域 -->
      <section class="domains" v-if="tab === 'bank'">
        <div class="sec-title">知识域</div>
        <div class="dom-list">
          <button class="dom" :class="{ on: !filter.domain }" @click="setDomain(null)">
            全部<span>{{ stats.total }}</span>
          </button>
          <button v-for="d in stats.domains" :key="d.key" class="dom"
                  :class="{ on: filter.domain === d.key }" @click="setDomain(d.key)">
            {{ d.name }}<span>{{ d.count }}</span>
          </button>
        </div>
      </section>

      <!-- 待补题池 -->
      <section v-if="tab === 'pending'" class="pending">
        <div class="sec-title">待补题池<span class="pend-count">{{ pending.length }}</span></div>
        <p class="pend-desc">题库外被问到的问题会记录在这里。点「生成答案入库」把它变成正式题目，题库越用越大。</p>
        <div v-if="!pending.length" class="none">暂无待补题</div>
        <div v-for="p in pending" :key="p.id" class="p-item">
          <div class="p-q">{{ p.question }}</div>
          <div class="p-meta">
            <span>{{ p.domain || '未分类' }}</span>
            <span>被问 {{ p.ask_count }} 次</span>
            <span :class="['st', p.status]">{{ { pending: '待补', drafted: '已起草', adopted: '已入库' }[p.status] }}</span>
          </div>
          <div class="p-actions">
            <button v-if="p.status !== 'adopted'" class="ok" :disabled="adopting === p.id"
                    @click="adopt(p)">{{ adopting === p.id ? '生成中…' : '生成答案入库' }}</button>
            <span v-else class="done-tag">已入库</span>
          </div>
        </div>
      </section>

      <!-- 题目列表 -->
      <section class="questions" v-if="tab === 'bank'">
        <div class="q-toolbar">
          <input v-model="filter.q" placeholder="搜索题干…（回车）" @keyup.enter="load(1)" />
          <select v-model="filter.difficulty" @change="load(1)">
            <option :value="null">全部难度</option>
            <option :value="1">基础</option>
            <option :value="2">应用</option>
            <option :value="3">进阶</option>
          </select>
          <span class="count">共 {{ questions.total }} 道</span>
        </div>

        <div class="q-list">
          <div v-for="(it, i) in questions.items" :key="i" class="q-item">
            <div class="q-head" @click="it._open = !it._open">
              <span class="q-title">{{ it.title }}</span>
              <span class="q-meta">{{ it.domain_name }} · {{ ['','基础','应用','进阶'][it.difficulty] }}</span>
            </div>
            <div v-if="it._open" class="q-answer" v-html="renderAnswer(it.answer)"></div>
          </div>
          <div v-if="!questions.items.length" class="none">没有匹配的题目</div>
        </div>

        <div class="pager" v-if="questions.total > questions.page_size">
          <button :disabled="questions.page <= 1" @click="load(questions.page - 1)">上一页</button>
          <span>{{ questions.page }} / {{ pages }}</span>
          <button :disabled="questions.page >= pages" @click="load(questions.page + 1)">下一页</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import api from '../api'

const stats = reactive({ total: 0, domains: [], difficulty: [], q_type: {}, origin: {} })
const questions = reactive({ total: 0, page: 1, page_size: 20, items: [] })
const filter = reactive({ domain: null, difficulty: null, q: '' })

// Tab：题库 / 待补题
const tab = ref('bank')
const pending = ref([])
const pendingCount = ref(0)
const adopting = ref(null)

// 上传文档入库
const fileInput = ref(null)
const uploading = ref(false)
async function onUpload(e) {
  const f = e.target.files[0]
  e.target.value = ''
  if (!f) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', f)
    // 不要手动设 Content-Type，让浏览器自动带 multipart boundary
    const { data } = await api.post('/bank/upload', fd, {
      params: { domain: filter.domain || 'cs_basic' }, timeout: 180000,
    })
    alert(`已入库：${data.filename}（${data.inserted_chunks} 个知识块）`)
    loadStats()
  } catch (err) {
    alert(err.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function loadPending() {
  try {
    const { data } = await api.get('/pending/list', { params: { status: 'pending' } })
    pending.value = data.items || []
    pendingCount.value = pending.value.length
  } catch { /* 忽略 */ }
}

async function adopt(p) {
  adopting.value = p.id
  try {
    await api.post(`/pending/${p.id}/adopt`)
    await loadPending()
    loadStats()
  } catch (e) {
    alert(e.response?.data?.detail || '入库失败')
  } finally {
    adopting.value = null
  }
}

// 手动录入
const showAdd = ref(false)
const adding = ref(false)
const addError = ref('')
const addForm = reactive({ question: '', answer: '', domain: 'llm_basics', difficulty: 2, company: '', url: '' })
const domainOptions = [
  { key: 'llm_basics', name: 'LLM 原理' }, { key: 'prompt', name: 'Prompt 工程' },
  { key: 'rag', name: 'RAG' }, { key: 'agent', name: 'Agent' },
  { key: 'vectordb', name: '向量数据库' }, { key: 'framework', name: '框架' },
  { key: 'python_backend', name: 'Python 后端' }, { key: 'ml_dl', name: 'ML/DL' },
  { key: 'cs_basic', name: 'CS 基础' },
]

async function submitAdd() {
  addError.value = ''
  if (addForm.question.trim().length < 5) { addError.value = '题干至少 5 个字符'; return }
  if (addForm.answer.trim().length < 20) { addError.value = '答案至少 20 个字符'; return }
  adding.value = true
  try {
    await api.post('/bank/add', { ...addForm })
    showAdd.value = false
    addForm.question = ''; addForm.answer = ''; addForm.company = ''; addForm.url = ''
    loadStats(); load(1)
  } catch (e) {
    addError.value = e.response?.data?.detail || '入库失败'
  } finally {
    adding.value = false
  }
}

const maxDiff = computed(() => Math.max(1, ...stats.difficulty.map(d => d.count)))
const pages = computed(() => Math.max(1, Math.ceil(questions.total / questions.page_size)))
const pct = (v, max) => `${Math.min(100, (v / (max || 1)) * 100).toFixed(1)}%`

function renderAnswer(text) {
  // parent_text 形如「【问题】…【参考答案】…」，去掉前缀标题只留答案
  const m = text.split('【参考答案】')
  const body = m.length > 1 ? m.slice(1).join('【参考答案】') : text
  return DOMPurify.sanitize(marked.parse(body))
}

async function loadStats() {
  const { data } = await api.get('/bank/stats')
  Object.assign(stats, data)
}

async function load(page = 1) {
  const { data } = await api.get('/bank/questions', {
    params: { domain: filter.domain, difficulty: filter.difficulty, q: filter.q, page, page_size: 20 },
  })
  data.items.forEach(it => (it._open = false))
  Object.assign(questions, data)
}

function setDomain(d) {
  filter.domain = d
  load(1)
}

onMounted(() => { loadStats(); load(1); loadPending() })
</script>

<style scoped>
.bank-page { min-height: 100vh; background: transparent; }
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 28px; border-bottom: 1px solid var(--line);
}
.brand-mini { display: flex; align-items: center; gap: 10px; }
.seal {
  width: 30px; height: 30px; display: grid; place-items: center;
  background: var(--seal); color: var(--paper); border-radius: 6px;
  font-family: var(--font-display); font-weight: 700; font-size: 16px;
}
.topbar h2 { font-family: var(--font-display); font-size: 19px; font-weight: 600; }
.nav { display: flex; gap: 4px; align-items: center; }
.nav a {
  padding: 6px 14px; font-size: 13.5px; color: var(--ink-soft); border-radius: var(--radius);
}
.nav a:hover { text-decoration: none; background: var(--hover); }
.nav a.on { color: var(--ink); background: var(--hover); font-weight: 500; }
.add-btn {
  margin-right: 10px; padding: 7px 15px; font-size: 13px; font-weight: 500;
  background: var(--ink); color: var(--paper); border: none; border-radius: var(--radius);
}
.add-btn:hover { background: var(--accent); }
.up-btn { margin-right: 10px; padding: 7px 15px; font-size: 13px; font-weight: 500;
  background: none; color: var(--ink); border: 1px solid var(--line); border-radius: var(--radius); }
.up-btn:hover { border-color: var(--accent); color: var(--accent); }

/* 录入弹窗 */
.mask {
  position: fixed; inset: 0; background: rgba(0,0,0,.55);
  display: grid; place-items: center; z-index: 50; padding: 20px;
}
.modal {
  width: 560px; max-width: 100%; background: var(--paper);
  border: 1px solid var(--line); border-radius: 10px; padding: 24px 24px 20px;
  display: flex; flex-direction: column; gap: 14px; max-height: 88vh; overflow-y: auto;
}
.m-title { font-family: var(--font-display); font-size: 17px; font-weight: 600; }
.modal label { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--ink-soft); flex: 1; }
.modal input, .modal textarea, .modal select {
  padding: 9px 11px; font-size: 13.5px; color: var(--ink); font-family: inherit;
  background: var(--card-solid); border: 1px solid var(--line); border-radius: var(--radius);
  outline: none; resize: vertical;
}
.modal input:focus, .modal textarea:focus, .modal select:focus { border-color: var(--accent); }
.m-row { display: flex; gap: 12px; }
.m-err { color: var(--seal); font-size: 12.5px; }
.m-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
.m-actions .cancel { padding: 9px 18px; background: none; border: 1px solid var(--line); border-radius: var(--radius); color: var(--ink-soft); font-size: 13px; }
.m-actions .ok { padding: 9px 22px; background: var(--ink); color: var(--paper); border: none; border-radius: var(--radius); font-size: 13px; }
.m-actions .ok:disabled { background: var(--ink-faint); cursor: not-allowed; }
.nav a.on { color: var(--ink); background: var(--hover); font-weight: 500; }

.body { max-width: 900px; margin: 0 auto; padding: 28px 24px 60px; }

/* 统计 */
.stat-grid {
  display: grid; grid-template-columns: 180px 1fr 1fr 1fr; gap: 0;
  border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--card-solid);
}
.stat-cell { padding: 18px 18px; border-left: 1px solid var(--line-soft); }
.stat-cell:first-child { border-left: none; }
.stat-cell.big { display: flex; flex-direction: column; justify-content: center; }
.num { font-family: var(--font-display); font-size: 40px; font-weight: 700; color: var(--ink); line-height: 1; }
.lbl { margin-top: 8px; font-size: 12.5px; color: var(--ink-faint); }
.lbl2 { font-size: 12.5px; color: var(--ink-faint); margin-bottom: 10px; letter-spacing: 1px; }
.bar-row { display: flex; align-items: center; gap: 9px; margin: 7px 0; font-size: 12.5px; }
.bar-row .k { flex: 0 0 60px; color: var(--ink-soft); }
.bar { flex: 1; height: 6px; background: var(--paper-2); border-radius: 3px; overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--accent); border-radius: 3px; }
.bar-row .v { flex: 0 0 44px; text-align: right; font-family: var(--font-mono); font-size: 11.5px; color: var(--ink-soft); }

/* 知识域 */
.domains { margin-top: 26px; }
.sec-title { font-family: var(--font-display); font-size: 15px; font-weight: 600; margin-bottom: 12px; }
.dom-list { display: flex; flex-wrap: wrap; gap: 8px; }
.dom {
  padding: 7px 13px; font-size: 13px; color: var(--ink-soft);
  background: var(--card-solid); border: 1px solid var(--line); border-radius: 6px;
  display: inline-flex; gap: 7px; align-items: baseline;
}
.dom span { font-family: var(--font-mono); font-size: 11px; color: var(--ink-faint); }
.dom:hover { border-color: var(--accent); }
.dom.on { background: var(--ink); color: var(--paper); border-color: var(--ink); }
.dom.on span { color: rgba(247,245,240,.6); }

/* 题目列表 */
.questions { margin-top: 26px; }
.q-toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 14px; }
.q-toolbar input {
  flex: 1; padding: 9px 12px; font-size: 13.5px; background: var(--card-solid);
  border: 1px solid var(--line); border-radius: var(--radius); outline: none;
}
.q-toolbar input:focus { border-color: var(--accent); }
.q-toolbar select {
  padding: 9px 10px; font-size: 13px; background: var(--card-solid);
  border: 1px solid var(--line); border-radius: var(--radius); outline: none; color: var(--ink);
}
.count { font-size: 12.5px; color: var(--ink-faint); font-family: var(--font-mono); }

.q-list { display: flex; flex-direction: column; gap: 6px; }
.q-item { background: var(--card-solid); border: 1px solid var(--line-soft); border-radius: var(--radius); }
.q-head {
  display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
  padding: 12px 15px; cursor: pointer;
}
.q-head:hover { background: var(--hover); }
.q-title { font-size: 14px; font-weight: 500; color: var(--ink); line-height: 1.6; }
.q-meta { flex: 0 0 auto; font-size: 11.5px; color: var(--ink-faint); font-family: var(--font-mono); }
.q-answer {
  padding: 0 15px 14px; font-size: 13.5px; line-height: 1.8; color: var(--ink);
  border-top: 1px dashed var(--line);
}
.q-answer :deep(p) { margin: 7px 0; }
.q-answer :deep(ul), .q-answer :deep(ol) { padding-left: 20px; margin: 7px 0; }
.q-answer :deep(pre) { background: var(--pre-bg); color: var(--pre-text); padding: 10px 12px; border-radius: 5px; overflow-x: auto; font-size: 12px; }
.q-answer :deep(code) { font-family: var(--font-mono); font-size: 12px; background: var(--paper-2); padding: 1px 5px; border-radius: 3px; }
.q-answer :deep(pre code) { background: none; padding: 0; }
.none { text-align: center; color: var(--ink-faint); font-size: 13px; padding: 30px 0; }

/* Tab 切换 */
.tabs { display: flex; gap: 6px; margin-bottom: 22px; border-bottom: 1px solid var(--line); }
.tabs button {
  padding: 9px 18px; font-size: 14px; color: var(--ink-soft); background: none; border: none;
  border-bottom: 2px solid transparent; margin-bottom: -1px; display: inline-flex; align-items: center; gap: 6px;
}
.tabs button:hover { color: var(--ink); }
.tabs button.on { color: var(--ink); font-weight: 600; border-bottom-color: var(--seal); }
.pend-badge {
  font-family: var(--font-mono); font-size: 11px; background: var(--seal); color: var(--paper);
  border-radius: 8px; padding: 0 6px; min-width: 18px; text-align: center;
}

/* 待补题池 */
.pend-desc { font-size: 13px; color: var(--ink-soft); margin-bottom: 16px; line-height: 1.7; }
.pend-count { font-family: var(--font-mono); font-size: 12px; color: var(--seal); margin-left: 8px; }
.p-item { background: var(--card-solid); border: 1px solid var(--line-soft); border-radius: var(--radius);
  padding: 13px 16px; margin-bottom: 8px; }
.p-q { font-size: 14px; font-weight: 500; color: var(--ink); line-height: 1.6; margin-bottom: 7px; }
.p-meta { display: flex; gap: 12px; font-size: 11.5px; color: var(--ink-faint); font-family: var(--font-mono); }
.p-meta .st.pending { color: var(--seal); }
.p-meta .st.drafted { color: #C79017; }
.p-meta .st.adopted { color: var(--ok); }
.p-actions { margin-top: 9px; }
.p-actions .ok { padding: 7px 16px; background: var(--ink); color: var(--paper); border: none;
  border-radius: 6px; font-size: 12.5px; }
.p-actions .ok:hover:not(:disabled) { background: var(--accent); }
.p-actions .ok:disabled { background: var(--ink-faint); cursor: not-allowed; }
.done-tag { font-size: 12px; color: var(--ok); }

.pager { display: flex; gap: 14px; align-items: center; justify-content: center; margin-top: 18px; font-size: 13px; }
.pager button {
  padding: 7px 16px; background: var(--card-solid); border: 1px solid var(--line);
  border-radius: var(--radius); color: var(--ink); font-size: 13px;
}
.pager button:disabled { color: var(--ink-faint); cursor: not-allowed; }
.pager span { font-family: var(--font-mono); color: var(--ink-soft); font-size: 12.5px; }

@media (max-width: 720px) {
  .stat-grid { grid-template-columns: 1fr; }
  .stat-cell { border-left: none; border-top: 1px solid var(--line-soft); }
  .stat-cell:first-child { border-top: none; }
}
</style>
