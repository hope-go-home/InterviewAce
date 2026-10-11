<template>
  <!-- 全局视频背景（所有页面共享，压在内容下） -->
  <div class="app-bg" aria-hidden="true">
    <video ref="bgVideo" class="app-bg-video" :class="{ 'is-ready': bgReady }"
           autoplay muted loop playsinline preload="auto" tabindex="-1"
           src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260826_124724_bc041163-d651-425f-aea3-2acc1efc2c96.mp4"></video>
    <div class="app-bg-overlay"></div>
  </div>
  <router-view v-slot="{ Component }">
    <KeepAlive>
      <component :is="Component" />
    </KeepAlive>
  </router-view>
</template>

<script setup>
import { onMounted, ref } from 'vue'

const bgVideo = ref(null)
const bgReady = ref(false)

onMounted(() => {
  const v = bgVideo.value
  if (!v) return
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { v.remove(); return }
  if (v.readyState >= 3) bgReady.value = true
  else v.addEventListener('canplay', () => (bgReady.value = true), { once: true })
  v.addEventListener('loadeddata', () => {
    const p = v.play(); if (p && p.catch) p.catch(() => {})
  }, { once: true })
})
</script>

<style>
/* ============ 设计系统：深色玻璃拟态（全站统一） ============ */
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  /* 色板：深色底 + 玻璃面 + 暖橙点缀 */
  --paper:      #0B0E13;   /* 页面底（视频之上压暗） */
  --paper-2:    #141922;   /* 略亮的面 */
  --card:       rgba(255,255,255,.045);  /* 玻璃卡片 */
  --card-solid: rgba(20,25,34,.72);      /* 卡片实底（带一点透明好透背景） */
  --hover:      rgba(255,255,255,.07);
  --ink:        #E8EAF0;   /* 主文字 */
  --ink-soft:   #9BA2B0;   /* 次要文字 */
  --ink-faint:  #67707E;   /* 弱化 */
  --line:       rgba(255,255,255,.09);
  --line-soft:  rgba(255,255,255,.06);
  --seal:       #F49D70;   /* 暖橙：品牌/强调 */
  --accent:     #7C9AFF;   /* 蓝紫：可交互 */
  --accent-bg:  rgba(124,154,255,.12);
  --ok:         #4CC38A;
  --pre-bg:     rgba(10,13,18,.72);   /* 代码块底 */
  --pre-text:   #E6E3DC;

  /* 字体 */
  --font-display: "Noto Serif SC", "STSong", "SimSun", Georgia, serif;
  --font-body: Inter, -apple-system, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  --font-mono: "SFMono-Regular", ui-monospace, "JetBrains Mono", "Consolas", monospace;

  --content-w: 768px;
  --radius: 10px;
}

html, body { height: 100%; }
body {
  background: var(--paper);   /* 视频加载失败时的兜底底色 */
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 15px;
  line-height: 1.75;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
#app { height: 100vh; }

/* ---- 全局视频背景 ---- */
.app-bg { position: fixed; inset: 0; z-index: -1; overflow: hidden; background: var(--paper); }
.app-bg-video {
  width: 100%; height: 100%; object-fit: cover;
  filter: saturate(1.06) contrast(1.05) brightness(.9);
  opacity: 0; transition: opacity .9s ease;
}
.app-bg-video.is-ready { opacity: 1; }
.app-bg-overlay {
  position: absolute; inset: 0;
  background:
    linear-gradient(to bottom, rgba(8,10,14,.42) 0%, rgba(8,10,14,.30) 40%, rgba(8,10,14,.55) 100%);
}
#app { position: relative; }

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: none; }
button { cursor: pointer; font-family: inherit; }

::selection { background: var(--seal); color: #14100C; }
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #2A3140; border-radius: 5px; }
::-webkit-scrollbar-thumb:hover { background: #39425a; }
:focus-visible { outline: 2px solid var(--seal); outline-offset: 2px; border-radius: 4px; }

/* ---- 玻璃拟态：压在视频背景上的可读面板 ---- */
.card, .qcard, .stat-grid, .composer, .modal, .sheet, .sidebar,
.q-item, .q-card, .p-item, .mini-item, .statusbar, .topbar,
.samples button, .chip, .q-toolbar input, .q-toolbar select,
.rh-item, .pq-item, .up-zone {
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
}

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
</style>
