<template>
  <div class="layout" :class="{ collapsed: sidebarCollapsed }">
    <!-- 收起后顶部留的展开钮 -->
    <button v-if="sidebarCollapsed" class="expand-btn" @click="sidebarCollapsed = false" aria-label="展开侧栏">☰</button>
    <!-- 左栏：目录 -->
    <aside class="sidebar" v-show="!sidebarCollapsed">
      <div class="brand">
        <router-link to="/" class="brand-link">
          <div class="seal">求</div>
          <div class="brand-text">
            <div class="name">求职助手</div>
            <div class="tag">InterviewAce</div>
          </div>
        </router-link>
        <button class="collapse-btn" @click="sidebarCollapsed = true" aria-label="收起侧栏">‹</button>
      </div>
      <button class="new-btn" @click="newChat">＋ 新对话</button>

      <div class="toc">目录</div>
      <div class="sessions">
        <div v-for="s in sessions" :key="s.session_id" class="session"
             :class="{ active: s.session_id === sessionId }" @click="openSession(s.session_id)">
          <div class="s-q">{{ s.first_question || '（空会话）' }}</div>
          <div class="s-meta">{{ s.count }} 轮</div>
          <button class="s-del" title="删除会话" @click.stop="delSession(s.session_id)">×</button>
        </div>
        <div v-if="!sessions.length" class="none">暂无历史会话</div>
      </div>

      <div class="me">
        <span class="uname">{{ auth.username }}</span>
        <button class="logout" @click="logout">退出</button>
      </div>
    </aside>

    <!-- 主区 -->
    <main class="main">
      <header class="topbar">
        <h2>题库问答</h2>
        <span class="sub" v-if="bankTotal">题库 {{ bankTotal }} 题 · 9 大知识域</span>
        <PosLevelPicker />
        <nav class="nav">
          <router-link to="/chat" class="on">问答</router-link>
          <router-link to="/bank">题库</router-link>
          <router-link to="/practice">练习</router-link>
          <router-link to="/resume">简历</router-link>
          <router-link to="/interview">模拟面试</router-link>
          <router-link to="/me">我的</router-link>
        </nav>
      </header>

      <div ref="scroller" class="messages">
        <div class="col">
          <div v-if="loadingHistory" class="loading-hist">加载会话记录…</div>
          <div v-if="!messages.length" class="empty">
            <div class="seal-large">求</div>
            <h2>求职助手</h2>
            <p>基于混合检索与重排的面试题库问答，答案附引用来源。<br>问一道题，或从下面的题目开始。</p>
            <div class="samples">
              <button v-for="q in samples" :key="q" @click="ask(q)">{{ q }}</button>
            </div>
          </div>

          <MessageBubble v-for="(m, i) in messages" :key="i" :msg="m" />
        </div>
      </div>

      <footer class="input-bar">
        <div class="col">
          <!-- 图片预览 -->
          <div v-if="imagePreview" class="img-preview">
            <img :src="imagePreview" alt="题目图片">
            <button class="rm" @click="clearImage" aria-label="移除图片">×</button>
          </div>
          <div class="composer" @paste="onPaste">
            <button class="attach-btn" @click="fileInput.click()" :disabled="streaming"
                    title="上传图片题目" aria-label="上传图片题目">
              <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16"><path d="M1.5 2.5h13v11h-13zM5 6a1.2 1.2 0 100 2.4A1.2 1.2 0 005 6zm8.5 6L9.5 8l-3 3.5L4 9.5l-2.5 3z"/></svg>
            </button>
            <input type="file" ref="fileInput" accept="image/*" hidden @change="onImagePick">
            <VoiceButton :disabled="streaming" @text="onVoice" />
            <textarea v-model="input" rows="1" placeholder="提问面试题…（Enter 发送，可贴图/语音）"
                      @keydown.enter.exact.prevent="ask()" :disabled="streaming" ref="ta" />
            <button @click="ask()" :disabled="streaming || (!input.trim() && !imageBase64)">
              {{ streaming ? '作答中' : '发问' }}
            </button>
          </div>
        </div>
      </footer>
    </main>
  </div>
</template>

<script setup>
import { nextTick, onActivated, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { streamQA } from '../api/stream'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import MessageBubble from '../components/MessageBubble.vue'
import PosLevelPicker from '../components/PosLevelPicker.vue'
import VoiceButton from '../components/VoiceButton.vue'

const auth = useAuthStore()
const settings = useSettingsStore()
const route = useRoute()
const router = useRouter()

const sessions = ref([])
const messages = ref([])
const input = ref('')
const streaming = ref(false)
const scroller = ref(null)
const ta = ref(null)
const sessionId = ref(route.params.sessionId || null)
const bankTotal = ref(0)
const sidebarCollapsed = ref(false)
const loadingHistory = ref(false)
const fileInput = ref(null)
const imageBase64 = ref(null)
const imagePreview = ref(null)

function readImage(file) {
  if (!file || !file.type.startsWith('image/')) return
  const reader = new FileReader()
  reader.onload = () => {
    imagePreview.value = reader.result
    imageBase64.value = reader.result.split(',')[1]  // 去掉 data:image/...;base64, 前缀
  }
  reader.readAsDataURL(file)
}
function onImagePick(e) { readImage(e.target.files[0]); e.target.value = '' }
function onPaste(e) {
  const items = e.clipboardData?.items || []
  for (const it of items) {
    if (it.type.startsWith('image/')) { readImage(it.getAsFile()); e.preventDefault(); break }
  }
}
function clearImage() { imageBase64.value = null; imagePreview.value = null }
function onVoice(txt) { input.value = (input.value ? input.value + ' ' : '') + txt }

const samples = [
  'RAG 中重排（rerank）的作用是什么？',
  '什么是 Reciprocal Rank Fusion？',
  'Transformer 的自注意力计算过程？',
  'Redis 缓存穿透、击穿、雪崩的区别？',
]

function scrollToBottom() {
  nextTick(() => { if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight })
}

async function loadSessions() {
  try {
    const { data } = await api.get('/sessions')
    sessions.value = data.sessions || []
  } catch { /* 忽略 */ }
}

async function openSession(id) {
  if (loadingHistory.value) return
  sessionId.value = id
  router.push(`/chat/${id}`)
  messages.value = []
  loadingHistory.value = true
  try {
    const { data } = await api.get(`/history/${id}`)
    for (const h of data.history || []) {
      messages.value.push({ role: 'user', content: h.question })
      messages.value.push({ role: 'assistant', content: h.answer })
    }
    scrollToBottom()
  } catch { /* 忽略 */ } finally {
    loadingHistory.value = false
  }
}

async function delSession(id) {
  if (!confirm('删除这个会话？')) return
  try {
    await api.delete(`/sessions/${id}`)
    if (sessionId.value === id) newChat()
    await loadSessions()
  } catch { /* 忽略 */ }
}

function newChat() {
  sessionId.value = null
  messages.value = []
  router.push('/chat')
  nextTick(() => ta.value?.focus())
}

function logout() {
  auth.logout()
  router.push('/login')
}

async function ask(preset) {
  const question = (preset ?? input.value).trim()
  if ((!question && !imageBase64.value) || streaming.value) return
  const img = imageBase64.value
  const imgPreview = imagePreview.value
  input.value = ''
  clearImage()
  messages.value.push({ role: 'user', content: question || '（图片题目）', image: imgPreview })

  const assistant = reactive({
    role: 'assistant', content: '', thinking: [], sources: [], stats: {},
    similar: [], streaming: true,
  })
  messages.value.push(assistant)
  streaming.value = true
  scrollToBottom()

  await streamQA(question, sessionId.value, {
    onSession: (id) => { sessionId.value = id; router.replace(`/chat/${id}`) },
    onThinking: (step) => { assistant.thinking.push(step); scrollToBottom() },
    onSources: (srcs) => { assistant.sources = srcs; scrollToBottom() },
    onStats: (s) => { assistant.stats = s },
    onToken: (t) => { assistant.content += t; scrollToBottom() },
    onAnswer: (data) => {
      assistant.content = data.answer || assistant.content
      assistant.similar = data.similar_questions || []
      assistant.is_fallback = !!data.is_fallback
    },
    onDone: () => {
      assistant.streaming = false; streaming.value = false
      loadSessions(); scrollToBottom()
    },
    onError: (msg) => {
      assistant.content = `出错了：${msg}`
      assistant.streaming = false; streaming.value = false
    },
  }, img, { position: settings.position, level: settings.level })
}

watch(() => route.params.sessionId, (id) => { if (id && id !== sessionId.value) openSession(id) })

// KeepAlive 缓存的组件重新激活时，刷新会话列表（onMounted 不会再触发）
onActivated(() => { loadSessions() })

onMounted(() => {
  loadSessions()
  api.get('/bank/stats').then(({ data }) => { bankTotal.value = data.total }).catch(() => {})
  if (sessionId.value) openSession(sessionId.value)
  // 从落地页带来的问题自动提问
  const preset = route.query.q
  if (preset && typeof preset === 'string' && preset.trim()) {
    router.replace({ query: {} })
    ask(preset.trim())
  }
})
</script>

<style scoped>
.layout { display: flex; height: 100vh; background: transparent; }

/* ---- 左栏：目录 ---- */
.sidebar {
  width: 260px; flex: 0 0 260px; background: var(--paper-2);
  border-right: 1px solid var(--line);
  display: flex; flex-direction: column; padding: 20px 16px; gap: 14px;
}
.brand { display: flex; gap: 11px; align-items: center; padding: 2px 4px; justify-content: space-between; }
.brand-link { display: flex; gap: 11px; align-items: center; flex: 1; min-width: 0; }
.brand-link:hover { text-decoration: none; }
.collapse-btn {
  flex: 0 0 auto; width: 24px; height: 24px; border-radius: 6px; border: 1px solid var(--line);
  background: transparent; color: var(--ink-faint); font-size: 16px; line-height: 1; cursor: pointer;
}
.collapse-btn:hover { color: var(--seal); border-color: var(--seal); }
.expand-btn {
  position: fixed; top: 14px; left: 14px; z-index: 40; width: 36px; height: 36px;
  border-radius: 8px; border: 1px solid var(--line); background: var(--card-solid); color: var(--ink-soft);
  font-size: 17px; cursor: pointer; box-shadow: 0 2px 10px rgba(0,0,0,.35);
}
.expand-btn:hover { color: var(--seal); border-color: var(--seal); }
.seal {
  width: 40px; height: 40px; flex: 0 0 40px; display: grid; place-items: center;
  background: var(--seal); color: var(--paper); font-family: var(--font-display);
  font-size: 21px; font-weight: 700; border-radius: 7px;
}
.brand-text .name { font-family: var(--font-display); font-size: 17px; font-weight: 600; line-height: 1.3; }
.brand-text .tag { font-size: 11.5px; color: var(--ink-faint); margin-top: 1px; }

.new-btn {
  padding: 10px; font-size: 13.5px; font-weight: 500; letter-spacing: 1px;
  background: var(--ink); color: var(--paper); border: none; border-radius: var(--radius);
}
.new-btn:hover { background: var(--accent); }

.toc {
  font-size: 11.5px; color: var(--ink-faint); letter-spacing: 2px;
  padding: 0 4px; border-bottom: 1px solid var(--line); padding-bottom: 6px;
}
.sessions { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; margin-top: -6px; }
.session {
  padding: 8px 9px; border-radius: 5px; cursor: pointer;
  border-left: 2px solid transparent; position: relative;
}
.session:hover { background: var(--hover); }
.s-del {
  position: absolute; right: 6px; top: 8px; width: 20px; height: 20px; border-radius: 5px;
  border: none; background: transparent; color: var(--ink-faint); font-size: 15px; line-height: 1;
  display: none; cursor: pointer;
}
.session:hover .s-del { display: grid; place-items: center; }
.s-del:hover { color: var(--seal); background: rgba(244,157,112,.15); }
.session.active { background: var(--hover); border-left-color: var(--seal); }
.s-q { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink); }
.s-meta { font-size: 11px; color: var(--ink-faint); margin-top: 2px; }
.none { font-size: 12.5px; color: var(--ink-faint); padding: 8px 4px; }

.me {
  display: flex; justify-content: space-between; align-items: center;
  border-top: 1px solid var(--line); padding-top: 12px; font-size: 12.5px;
}
.uname { color: var(--ink-soft); }
.logout { background: none; border: 1px solid var(--line); color: var(--ink-soft); border-radius: 5px; padding: 3px 10px; font-size: 12px; }
.logout:hover { color: var(--seal); border-color: var(--seal); }

/* ---- 主区 ---- */
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.topbar {
  padding: 16px 24px; border-bottom: 1px solid var(--line);
  display: flex; align-items: baseline; gap: 14px;
}
.topbar h2 { font-family: var(--font-display); font-size: 19px; font-weight: 600; }
.topbar .sub { font-size: 12px; color: var(--ink-faint); }
.nav { margin-left: auto; display: flex; gap: 4px; }
.nav a { padding: 6px 14px; font-size: 13.5px; color: var(--ink-soft); border-radius: var(--radius); }
.nav a:hover { text-decoration: none; background: var(--hover); }
.nav a.on { color: var(--ink); background: var(--hover); font-weight: 500; }

.messages { flex: 1; overflow-y: auto; padding: 0 24px; }
.loading-hist { text-align: center; color: var(--ink-faint); font-size: 13px; padding: 30px 0; }
.col { max-width: var(--content-w); margin: 0 auto; }

/* 空态 */
.empty { padding: 10vh 0 4vh; text-align: center; }
.seal-large {
  width: 74px; height: 74px; margin: 0 auto 22px; display: grid; place-items: center;
  background: var(--seal); color: var(--paper); font-family: var(--font-display);
  font-size: 36px; font-weight: 700; border-radius: 10px;
}
.empty h2 { font-family: var(--font-display); font-size: 26px; font-weight: 600; margin-bottom: 12px; }
.empty p { color: var(--ink-soft); font-size: 14px; line-height: 1.8; margin-bottom: 30px; }
.samples { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; max-width: 560px; margin: 0 auto; }
.samples button {
  padding: 13px 15px; text-align: left; font-size: 13.5px; color: var(--ink);
  background: var(--card-solid); border: 1px solid var(--line); border-radius: var(--radius);
  transition: border-color .15s, transform .12s;
}
.samples button:hover { border-color: var(--accent); transform: translateY(-1px); }

/* 输入栏 */
.input-bar { border-top: 1px solid var(--line); padding: 14px 24px 18px; }
.img-preview { position: relative; display: inline-block; margin-bottom: 8px; }
.img-preview img { max-width: 200px; max-height: 120px; border-radius: 8px; border: 1px solid var(--line); }
.img-preview .rm {
  position: absolute; top: -7px; right: -7px; width: 22px; height: 22px; border-radius: 50%;
  background: var(--ink); color: var(--paper); border: none; font-size: 14px; line-height: 1;
  display: grid; place-items: center; cursor: pointer;
}
.attach-btn {
  flex: 0 0 auto; width: 38px; height: 38px; border-radius: 8px; display: grid; place-items: center;
  color: var(--ink-soft); border: 1px solid var(--line); background: transparent; cursor: pointer;
  transition: color .15s, border-color .15s;
}
.attach-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.attach-btn:disabled { color: var(--ink-faint); cursor: not-allowed; }
.composer {
  display: flex; gap: 10px; align-items: flex-end;
  background: var(--card-solid); border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 8px 8px 15px;
  transition: border-color .15s;
}
.composer:focus-within { border-color: var(--accent); }
textarea {
  flex: 1; border: none; outline: none; resize: none; background: transparent;
  font-family: inherit; font-size: 14.5px; color: var(--ink); line-height: 1.7;
  max-height: 140px; padding: 6px 0;
}
textarea::placeholder { color: var(--ink-faint); }
.composer button {
  padding: 9px 20px; font-size: 13.5px; font-weight: 500; letter-spacing: 1px;
  background: var(--ink); color: var(--paper); border: none; border-radius: var(--radius);
  flex: 0 0 auto;
}
.composer button:hover:not(:disabled) { background: var(--accent); }
.composer button:disabled { background: var(--ink-faint); cursor: not-allowed; }

/* 移动端 */
@media (max-width: 720px) {
  .sidebar { display: none; }
  .samples { grid-template-columns: 1fr; }
}
</style>
