<template>
  <div class="voice-wrap">
    <!-- 实时识别气泡 -->
    <transition name="vp">
      <div v-if="recording || liveText" class="voice-pop">
        <div class="vp-head">
          <span class="vp-dot" :class="{ on: recording }"></span>
          <span>{{ recording ? '正在听…' : '识别完成' }}</span>
        </div>
        <div class="vp-text">{{ liveText || '（说话中…）' }}</div>
      </div>
    </transition>

    <button type="button" class="voice-btn" :class="{ recording }" @click="toggle"
            :disabled="disabled || connecting"
            :title="recording ? '点击停止' : '点击开始实时语音输入'"
            aria-label="实时语音输入">
      <svg v-if="!recording" viewBox="0 0 16 16" fill="currentColor" width="15" height="15">
        <path d="M8 1.5a2 2 0 00-2 2v4a2 2 0 104 0v-4a2 2 0 00-2-2zM3.5 7.5a4.5 4.5 0 009 0H14a6 6 0 01-5 5.9v1.6H7v-1.6a6 6 0 01-5-5.9z"/>
      </svg>
      <span v-else class="rec-dot"></span>
    </button>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'

const emit = defineEmits(['text'])
defineProps({ disabled: { type: Boolean, default: false } })

const recording = ref(false)
const connecting = ref(false)
const liveText = ref('')

let ws = null
let audioCtx = null
let mediaStream = null
let processor = null
let sourceNode = null

async function start() {
  connecting.value = true
  liveText.value = ''
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
  } catch {
    connecting.value = false
    alert('无法访问麦克风，请检查权限')
    return
  }

  // 建立到后端的 WebSocket
  const token = localStorage.getItem('ia_token') || ''
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/api/ws/stt?token=${encodeURIComponent(token)}`)

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'partial' || msg.type === 'final') {
        liveText.value = msg.text          // 后端返回累计全文，直接显示
      } else if (msg.type === 'error') {
        liveText.value = '识别出错：' + msg.text
      }
    } catch { /* 忽略 */ }
  }
  ws.onerror = () => { /* 连接错误在 onclose 处理 */ }
  ws.onclose = () => { stopAudio() }

  // 等连接就绪再开麦
  await new Promise((res) => {
    ws.onopen = res
    setTimeout(res, 2500)
  })

  startAudio()
  recording.value = true
  connecting.value = false
}

function startAudio() {
  audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 })
  sourceNode = audioCtx.createMediaStreamSource(mediaStream)
  processor = audioCtx.createScriptProcessor(2048, 1, 1)
  processor.onaudioprocess = (e) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    const f32 = e.inputBuffer.getChannelData(0)
    const i16 = new Int16Array(f32.length)
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]))
      i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    ws.send(i16.buffer)
  }
  sourceNode.connect(processor)
  processor.connect(audioCtx.destination)
}

function stopAudio() {
  recording.value = false
  connecting.value = false
  if (processor) { processor.disconnect(); processor.onaudioprocess = null }
  if (sourceNode) sourceNode.disconnect()
  if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop())
  if (audioCtx) { audioCtx.close(); audioCtx = null }
}

function stop() {
  stopAudio()
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('END')                        // 通知后端结束
    setTimeout(() => { if (ws) ws.close() }, 1200)  // 等最终结果回来
  } else if (ws) {
    ws.close()
  }
  // 把识别到的文字交给父组件
  if (liveText.value.trim()) {
    emit('text', liveText.value.trim())
  }
  // 气泡停留一会再消失
  setTimeout(() => { liveText.value = '' }, 2500)
}

function toggle() {
  if (recording.value) stop()
  else start()
}

onBeforeUnmount(() => {
  stopAudio()
  if (ws) ws.close()
})
</script>

<style scoped>
.voice-wrap { position: relative; display: inline-flex; }

.voice-btn {
  flex: 0 0 auto; width: 38px; height: 38px; border-radius: 8px; display: grid; place-items: center;
  color: var(--ink-soft); border: 1px solid var(--line); background: transparent; cursor: pointer;
  transition: color .15s, border-color .15s, background .15s;
}
.voice-btn:hover:not(:disabled) { color: var(--seal); border-color: var(--seal); }
.voice-btn:disabled { color: var(--ink-faint); cursor: not-allowed; }
.voice-btn.recording { color: #14100C; background: var(--seal); border-color: var(--seal);
  box-shadow: 0 0 0 4px rgba(244,157,112,.18); animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 50% { box-shadow: 0 0 0 8px rgba(244,157,112,.08); } }
.rec-dot { width: 12px; height: 12px; border-radius: 3px; background: #14100C; }

/* 实时识别气泡 */
.voice-pop {
  position: absolute; bottom: calc(100% + 10px); left: 0; width: 300px; z-index: 60;
  background: var(--card-solid); backdrop-filter: blur(14px) saturate(120%);
  border: 1px solid var(--line); border-radius: 10px; padding: 11px 13px;
  box-shadow: 0 12px 30px rgba(0,0,0,.45);
}
.vp-head { display: flex; align-items: center; gap: 7px; font-size: 11.5px; color: var(--ink-faint); margin-bottom: 6px; }
.vp-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ink-faint); }
.vp-dot.on { background: var(--seal); animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: .25 } }
.vp-text { font-size: 13.5px; line-height: 1.7; color: var(--ink); max-height: 120px; overflow-y: auto; word-break: break-word; }

.vp-enter-active, .vp-leave-active { transition: opacity .2s ease, transform .2s ease; }
.vp-enter-from, .vp-leave-to { opacity: 0; transform: translateY(6px); }
</style>
