<template>
  <div class="page">
    <header class="statusbar" v-if="session">
      <div class="st-left">
        <span class="seal">试</span>
        <span class="st-title">第 {{ seq }} / {{ session.num_questions }} 题</span>
        <span class="st-stage">{{ stageText }}</span>
      </div>
      <div class="st-right">
        <span v-if="avgScore !== null" class="st-score">均分 {{ avgScore }}</span>
        <button class="end-btn" @click="endEarly">结束面试</button>
      </div>
      <div class="progress"><i :style="{ width: (seq / session.num_questions * 100) + '%' }"></i></div>
    </header>

    <div class="room">
      <div class="room-main">
        <!-- 当前题卡 -->
        <div class="qcard" v-if="current">
          <div class="q-badges">
            <span v-if="current.is_followup" class="badge followup">追问</span>
            <span class="badge src">{{ { rag: '题库', llm: '追问', resume: '简历' }[current.source] || '题库' }}</span>
            <span v-if="current.domain" class="badge dom">{{ domainName(current.domain) }}</span>
            <span v-if="current.difficulty" class="badge diff">{{ ['','基础','应用','进阶'][current.difficulty] }}</span>
          </div>
          <div class="q-text">{{ current.text }}</div>

          <!-- 作答 -->
          <template v-if="!feedback">
            <div class="answer-row">
              <textarea v-model="answer" rows="6" :disabled="judging"
                        placeholder="组织你的回答…（分点作答，可点麦克风语音输入）"></textarea>
              <VoiceButton class="vbtn" :disabled="judging" @text="(t) => answer = (answer ? answer + ' ' : '') + t" />
            </div>
            <div class="actions">
              <button class="primary" @click="submit" :disabled="judging || !answer.trim()">
                {{ judging ? '点评中…' : '提交回答' }}
              </button>
            </div>
          </template>

          <!-- 点评 -->
          <div v-else class="feedback">
            <div class="fb-row">
              <div class="fb-score" :class="scoreClass">{{ feedback.score }}<i>分</i></div>
              <div class="fb-dims">
                <div v-for="(v, k) in feedback.dimensions" :key="k" class="dim">
                  <span class="k">{{ k }}</span>
                  <div class="bar"><i :style="{ width: v + '%' }"></i></div>
                  <span class="v">{{ v }}</span>
                </div>
              </div>
            </div>
            <p class="fb-text">{{ feedback.feedback }}</p>
            <div v-if="feedback.missing_points?.length" class="fb-missing">
              <div class="lbl">遗漏/答错的要点</div>
              <ul><li v-for="(p, i) in feedback.missing_points" :key="i">{{ p }}</li></ul>
            </div>
            <div class="actions">
              <button class="primary" @click="proceed">{{ nextLabel }}</button>
            </div>
          </div>
        </div>
        <div v-else class="qcard center">加载中…</div>
      </div>

      <!-- 右侧时间线 -->
      <aside class="timeline">
        <div class="tl-title">本场进度</div>
        <div v-for="t in turns" :key="t.id" class="tl-item" :class="{ cur: current && t.id === current.turn_id }">
          <div class="tl-q">{{ t.followup_no > 0 ? '↳ 追问 ' : '' }}{{ t.question }}</div>
          <div class="tl-meta">
            <span v-if="t.score != null" :class="['tl-score', t.score >= 85 ? 'g' : t.score >= 60 ? 'm' : 'b']">{{ t.score }}分</span>
            <span v-else class="tl-wait">待作答</span>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import VoiceButton from '../components/VoiceButton.vue'

const route = useRoute()
const router = useRouter()
const sid = route.params.id

const session = ref(null)
const current = ref(null)
const answer = ref('')
const feedback = ref(null)
const judging = ref(false)
const turns = ref([])
const nextAction = ref('next_question')
const report = ref(null)

const DOMAIN_NAMES = { llm_basics: 'LLM 原理', prompt: 'Prompt', rag: 'RAG', agent: 'Agent', vectordb: '向量库', framework: '框架', python_backend: 'Python', ml_dl: 'ML/DL', cs_basic: 'CS 基础' }
const domainName = (k) => DOMAIN_NAMES[k] || k

const seq = computed(() => current.value?.seq || session.value?.current_seq || 1)
const avgScore = computed(() => {
  const scored = turns.value.filter(t => t.score != null)
  if (!scored.length) return null
  return Math.round(scored.reduce((a, t) => a + t.score, 0) / scored.length)
})
const stageText = computed(() => judging.value ? '点评中' : (feedback.value ? '点评' : '作答中'))
const scoreClass = computed(() => {
  const s = feedback.value?.score
  return s == null ? '' : s >= 85 ? 'good' : s >= 60 ? 'mid' : 'bad'
})
const nextLabel = computed(() => nextAction.value === 'finish' ? '查看总评报告' : (nextAction.value === 'next_question' ? '下一题' : '继续'))

async function loadSnapshot() {
  const { data } = await api.get(`/interview/${sid}`)
  session.value = data.session
  turns.value = data.turns || []
  if (data.session.status === 'finished') { router.replace(`/interview/${sid}/report`); return }
  if (data.current) {
    current.value = { turn_id: data.current.turn_id, seq: data.current.seq, text: data.current.text, is_followup: data.current.is_followup }
  }
}

async function submit() {
  judging.value = true
  try {
    const { data } = await api.post(`/interview/${sid}/answer`, { turn_id: current.value.turn_id, answer: answer.value }, { timeout: 180000 })
    feedback.value = data.feedback
    nextAction.value = data.action
    report.value = data.report || null
    await loadSnapshot()
  } catch (e) {
    alert(e.response?.data?.detail || '评分失败')
  } finally {
    judging.value = false
  }
}

function proceed() {
  if (nextAction.value === 'finish') { router.push(`/interview/${sid}/report`); return }
  const nxt = turns.value.find(t => t.answer == null)
  if (nxt) {
    current.value = { turn_id: nxt.id, seq: nxt.seq, text: nxt.question, is_followup: nxt.followup_no > 0 }
  }
  answer.value = ''
  feedback.value = null
}

async function endEarly() {
  if (!confirm('确定提前结束并生成报告吗？')) return
  await api.post(`/interview/${sid}/end`)
  router.push(`/interview/${sid}/report`)
}

onMounted(loadSnapshot)
</script>

<style scoped>
.page { min-height: 100vh; background: transparent; display: flex; flex-direction: column; }
.statusbar { background: var(--card-solid); border-bottom: 1px solid var(--line); padding: 12px 26px 0; position: sticky; top: 0; z-index: 10; }
.st-left { display: flex; align-items: center; gap: 12px; padding-bottom: 10px; }
.seal { width: 28px; height: 28px; display: grid; place-items: center; background: var(--seal); color: var(--paper); border-radius: 6px; font-family: var(--font-display); font-weight: 700; font-size: 15px; }
.st-title { font-family: var(--font-display); font-size: 16px; font-weight: 600; }
.st-stage { font-size: 12px; color: var(--ink-faint); }
.st-right { margin-left: auto; display: flex; align-items: center; gap: 14px; }
.st-score { font-family: var(--font-display); font-size: 16px; font-weight: 700; color: var(--accent); }
.end-btn { padding: 6px 14px; font-size: 12.5px; background: none; border: 1px solid var(--line); border-radius: 6px; color: var(--ink-soft); }
.end-btn:hover { border-color: var(--seal); color: var(--seal); }
.progress { height: 3px; background: var(--paper-2); }
.progress i { display: block; height: 100%; background: var(--seal); transition: width .4s ease; }

.statusbar { display: flex; flex-wrap: wrap; align-items: center; }
.statusbar .st-right { margin-left: auto; }
.progress { flex-basis: 100%; }

.room { flex: 1; display: flex; max-width: 1080px; margin: 0 auto; width: 100%; padding: 24px; gap: 20px; }
.room-main { flex: 1; min-width: 0; }
.qcard { background: var(--card-solid); border: 1px solid var(--line); border-radius: 10px; padding: 22px 24px; }
.qcard.center { text-align: center; padding: 60px; color: var(--ink-faint); }
.q-badges { display: flex; gap: 8px; margin-bottom: 12px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; font-family: var(--font-mono); }
.badge.followup { background: rgba(176,58,46,.1); color: var(--seal); }
.badge.src { background: var(--accent-bg); color: var(--accent); }
.badge.dom { background: var(--paper-2); color: var(--ink-soft); }
.badge.diff { background: var(--paper-2); color: #C79017; }
.q-text { font-family: var(--font-display); font-size: 19px; font-weight: 600; line-height: 1.6; margin-bottom: 18px; }
textarea { width: 100%; padding: 13px 14px; font-size: 14px; font-family: inherit; background: var(--card-solid); border: 1px solid var(--line); border-radius: 8px; outline: none; resize: vertical; line-height: 1.7; }
textarea:focus { border-color: var(--accent); }
.answer-row { display: flex; gap: 8px; align-items: flex-start; }
.answer-row textarea { flex: 1; }
.answer-row .vbtn { margin-top: 2px; }
.actions { display: flex; justify-content: flex-end; margin-top: 14px; }
.primary { padding: 10px 22px; background: var(--ink); color: var(--paper); border: none; border-radius: var(--radius); font-size: 13.5px; font-weight: 500; }
.primary:hover:not(:disabled) { background: var(--accent); }
.primary:disabled { background: var(--ink-faint); cursor: not-allowed; }

.feedback { border-top: 1px dashed var(--line); padding-top: 16px; }
.fb-row { display: flex; gap: 22px; align-items: center; margin-bottom: 14px; }
.fb-score { font-family: var(--font-display); font-size: 40px; font-weight: 700; line-height: 1; }
.fb-score i { font-size: 13px; font-weight: 400; font-style: normal; color: var(--ink-faint); margin-left: 2px; }
.fb-score.good { color: var(--ok); } .fb-score.mid { color: #C79017; } .fb-score.bad { color: var(--seal); }
.fb-dims { flex: 1; display: flex; flex-direction: column; gap: 7px; }
.dim { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.dim .k { flex: 0 0 48px; color: var(--ink-soft); }
.dim .bar { flex: 1; height: 6px; background: var(--paper-2); border-radius: 3px; overflow: hidden; }
.dim .bar i { display: block; height: 100%; background: var(--accent); border-radius: 3px; }
.dim .v { flex: 0 0 28px; text-align: right; font-family: var(--font-mono); font-size: 11px; color: var(--ink-soft); }
.fb-text { font-size: 14px; line-height: 1.75; margin-bottom: 12px; }
.fb-missing .lbl { font-size: 12px; color: var(--ink-faint); margin-bottom: 6px; }
.fb-missing ul { padding-left: 20px; margin: 0; font-size: 13px; color: var(--ink-soft); line-height: 1.7; }

.timeline { width: 260px; flex: 0 0 260px; }
.tl-title { font-size: 12px; color: var(--ink-faint); letter-spacing: 1px; margin-bottom: 10px; }
.tl-item { padding: 10px 12px; border-radius: 8px; border: 1px solid var(--line-soft); background: var(--card-solid); margin-bottom: 7px; }
.tl-item.cur { border-color: var(--seal); }
.tl-q { font-size: 12px; color: var(--ink); line-height: 1.5; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.tl-meta { margin-top: 5px; font-size: 11px; font-family: var(--font-mono); }
.tl-score.g { color: var(--ok); } .tl-score.m { color: #C79017; } .tl-score.b { color: var(--seal); }
.tl-wait { color: var(--ink-faint); }

@media (max-width: 860px) { .room { flex-direction: column; } .timeline { width: 100%; flex: none; order: 2; } }
</style>
