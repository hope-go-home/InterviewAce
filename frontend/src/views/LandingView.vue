<template>
  <div class="landing">
    <div class="frame">
      <header class="nav">
        <router-link class="brand" to="/" aria-label="求职助手首页">
          <span class="brand__seal">求</span>
          <span class="brand__word">求职助手</span>
        </router-link>
        <nav class="links">
          <router-link to="/chat">题库问答</router-link>
          <router-link to="/bank">题库总览</router-link>
          <router-link to="/practice">答题练习</router-link>
          <router-link to="/interview">模拟面试</router-link>
          <router-link to="/me">我的</router-link>
        </nav>
        <router-link class="cta" to="/login">开始使用</router-link>
        <label class="burger" for="menu" aria-label="菜单" @click="menuOpen = !menuOpen">
          <svg viewBox="0 0 17 12" fill="none"><path d="M1 1h15M1 6h15M1 11h15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
        </label>
      </header>

      <transition name="sheet">
        <div v-if="menuOpen" class="sheet" @click.self="menuOpen = false">
          <router-link to="/chat" @click="menuOpen = false">题库问答</router-link>
          <router-link to="/bank" @click="menuOpen = false">题库总览</router-link>
          <router-link to="/practice" @click="menuOpen = false">答题练习</router-link>
          <router-link class="sheet-cta" to="/login" @click="menuOpen = false">开始使用</router-link>
        </div>
      </transition>

      <main class="hero">
        <div class="hero__copy">
          <h1 class="h1">刷题 · 模拟 · 复盘<br>一站搞定<span class="accent">求职面试</span></h1>
          <p class="hero__sub">覆盖 9 大知识域 · 7800+ 面试真题 · 混合检索带引用作答</p>
        </div>

        <form class="card" @submit.prevent="go">
          <input ref="inputEl" v-model="q" class="qinput" type="text"
                 placeholder="输入一道面试题，或者你的目标岗位…" aria-label="输入面试题或目标岗位">
          <div class="tools">
            <div class="chips">
              <button type="button" class="chip" @click="goChip('resume')">
                <svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 1.5h5.5L13 5v9.5H4zM9.5 2v3h3"/></svg>
                <span>上传简历</span>
              </button>
              <button type="button" class="chip" @click="goChip('image')">
                <svg viewBox="0 0 16 16" fill="currentColor"><path d="M1.5 2.5h13v11h-13zM5 6a1.2 1.2 0 100 2.4A1.2 1.2 0 005 6zm8.5 6L9.5 8l-3 3.5L4 9.5l-2.5 3z"/></svg>
                <span>图片题目</span>
              </button>
              <button type="button" class="chip" @click="goChip('voice')">
                <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 1.5a2 2 0 00-2 2v4a2 2 0 104 0v-4a2 2 0 00-2-2zM3.5 7.5a4.5 4.5 0 009 0H14a6 6 0 01-5 5.9v1.6H7v-1.6a6 6 0 01-5-5.9z"/></svg>
                <span>语音输入</span>
              </button>
            </div>
            <div class="right">
              <span class="model">全知识域
                <svg viewBox="0 0 8 8" fill="none"><path d="M1.5 3l2.5 2.5L6.5 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
              </span>
              <button type="submit" class="send" aria-label="开始">
                <svg viewBox="0 0 14 14" fill="none"><path d="M7 12V2M2.5 6.5L7 2l4.5 4.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>
          </div>
        </form>
      </main>

      <footer class="proof">
        <p class="proof__cap">混合检索 · RRF 融合 · 重排打分 · 引用溯源</p>
        <div class="proof__logos">
          <span class="plogo">RAG</span><span class="plogo">LangGraph</span><span class="plogo">Milvus</span>
        </div>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const inputEl = ref(null)
const q = ref('')
const menuOpen = ref(false)

function go() {
  const query = q.value.trim()
  if (!auth.token) { router.push('/login'); return }
  router.push(query ? `/chat?q=${encodeURIComponent(query)}` : '/chat')
}
function goChip(act) {
  if (!auth.token) { router.push('/login'); return }
  if (act === 'resume') router.push('/resume')
  else router.push(`/chat?mode=${act}`)
}
</script>

<style scoped>
/* 落地页 —— 与全站一致的纸面风 */
.landing{
  position:fixed; inset:0; overflow:auto; z-index:30;
  background: transparent;
  background-image:
    radial-gradient(1100px 500px at 50% -8%, rgba(176,58,46,.05), transparent 60%),
    radial-gradient(900px 480px at 88% 108%, rgba(46,74,122,.05), transparent 60%);
  font-family: var(--font-body);
}
.frame{ min-height:100%; display:flex; flex-direction:column;
  padding: 26px clamp(20px,4vw,64px) 30px; }

/* 导航 */
.nav{ display:flex; align-items:center; justify-content:space-between; position:relative }
.brand{ display:flex; align-items:center; gap:12px; }
.brand__seal{ width:38px; height:38px; border-radius:9px; background:var(--seal); color:var(--paper);
  display:grid; place-items:center; font-family:var(--font-display); font-weight:700; font-size:22px;
  box-shadow:0 1px 0 rgba(0,0,0,.2), 0 6px 16px rgba(176,58,46,.16); }
.brand__word{ font-family:var(--font-display); font-weight:600; font-size:20px; letter-spacing:.01em; color:var(--ink) }
.links{ position:absolute; left:50%; transform:translateX(-50%); display:flex; gap:34px }
.links a{ font-size:14.5px; color:var(--ink-soft); transition:color .15s; }
.links a:hover{ color:var(--ink) }
.cta{ padding:10px 20px; background:var(--ink); color:var(--paper); border-radius:8px;
  font-size:14px; font-weight:500; letter-spacing:1px; transition:background .15s }
.cta:hover{ background:var(--accent) }
.burger{ display:none }

/* hero */
.hero{ flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:26px; padding:6vh 0 4vh; }
.h1{ font-family:var(--font-display); font-weight:600; text-align:center; color:var(--ink);
  font-size:clamp(30px,4.4vw,50px); line-height:1.28; letter-spacing:.01em; margin:0 }
.h1 .accent{ color:var(--seal) }
.hero__sub{ text-align:center; font-size:clamp(12.5px,1.4vw,15px); color:var(--ink-soft);
  letter-spacing:.02em; margin-top:16px }

/* composer 卡片（纸面风） */
.card{ width:min(680px,92%); background:var(--card-solid); border:1px solid var(--line);
  border-radius:14px; padding:18px 18px 16px;
  box-shadow:0 1px 0 rgba(0,0,0,.2), 0 14px 34px -18px rgba(0,0,0,.45) }
.qinput{ width:100%; border:none; outline:none; background:transparent;
  font-size:15px; color:var(--ink); padding:4px 6px 14px; font-family:inherit }
.qinput::placeholder{ color:var(--ink-faint) }
.tools{ display:flex; align-items:center; gap:10px; border-top:1px solid var(--line-soft); padding-top:14px }
.chips{ display:flex; align-items:center; gap:8px; flex-wrap:wrap }
.chip{ height:32px; border-radius:8px; display:inline-flex; align-items:center; gap:6px;
  padding:0 13px; font-size:12.5px; font-weight:500; color:var(--ink-soft);
  background:var(--paper-2); border:1px solid var(--line-soft); cursor:pointer;
  transition:border-color .15s, color .15s, background .15s }
.chip:hover{ border-color:var(--accent); color:var(--accent); background:var(--accent-bg) }
.chip svg{ width:13px; height:13px }
.right{ margin-left:auto; display:flex; align-items:center; gap:12px }
.model{ font-size:12px; color:var(--ink-faint); display:inline-flex; align-items:center; gap:5px }
.model svg{ width:9px; height:9px }
.send{ width:38px; height:38px; border-radius:50%; display:flex; align-items:center; justify-content:center;
  background:var(--ink); cursor:pointer; transition:background .15s, transform .12s }
.send svg{ width:15px; height:15px }
.send:hover{ background:var(--seal) }
.send:active{ transform:scale(.94) }

/* footer */
.proof{ display:flex; flex-direction:column; align-items:center; gap:12px }
.proof__cap{ font-size:13px; color:var(--ink-soft); margin:0; letter-spacing:.01em }
.proof__logos{ display:flex; gap:34px }
.plogo{ font-family:var(--font-mono); font-size:12px; color:var(--ink-faint); letter-spacing:.02em }

/* 入场 */
@media (prefers-reduced-motion:no-preference){
  .brand,.links,.cta{ animation:fadeDown .5s ease both }
  .hero__copy{ animation:fadeUp .6s ease .1s both }
  .card{ animation:fadeUp .6s ease .25s both }
  .proof{ animation:fadeUp .6s ease .4s both }
}
@keyframes fadeDown{ from{ opacity:0; transform:translateY(-8px) } }
@keyframes fadeUp{ from{ opacity:0; transform:translateY(10px) } }

/* 移动端 */
@media (max-width:720px){
  .links,.nav .cta{ display:none }
  .burger{ display:flex; width:38px; height:38px; border-radius:9px; align-items:center; justify-content:center;
    background:var(--card-solid); border:1px solid var(--line); cursor:pointer; color:var(--ink) }
  .burger svg{ width:17px; height:12px }
  .hero{ gap:20px }
  .tools{ flex-direction:column; align-items:stretch; gap:12px }
  .right{ margin-left:0; justify-content:flex-end }
}
.sheet{ position:fixed; left:16px; right:16px; top:70px; z-index:40;
  background:var(--card-solid); border:1px solid var(--line); border-radius:12px;
  box-shadow:0 16px 40px -14px rgba(0,0,0,.5);
  display:flex; flex-direction:column; padding:8px; gap:2px }
.sheet a{ padding:12px 14px; border-radius:8px; font-size:15px; color:var(--ink) }
.sheet a:hover{ background:var(--paper-2) }
.sheet .sheet-cta{ background:var(--ink); color:var(--paper); text-align:center; font-weight:500; margin-top:6px }
.sheet-enter-active,.sheet-leave-active{ transition:opacity .2s ease, transform .2s ease }
.sheet-enter-from,.sheet-leave-to{ opacity:0; transform:translateY(-6px) }
</style>
