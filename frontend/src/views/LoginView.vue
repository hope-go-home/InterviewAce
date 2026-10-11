<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <div class="seal">求</div>
        <h1>InterviewAce</h1>
        <p class="sub">求职助手 · 题库研习</p>
      </div>
      <div class="form">
        <label>用户名<input v-model="username" placeholder="admin" @keyup.enter="submit" /></label>
        <label>密码<input v-model="password" type="password" placeholder="••••••" @keyup.enter="submit" /></label>
        <label v-if="mode === 'register'">确认密码<input v-model="password2" type="password" placeholder="再输一次" @keyup.enter="submit" /></label>
        <button @click="submit" :disabled="loading">{{ loading ? '请稍候…' : (mode === 'login' ? '进入题库' : '注册并进入') }}</button>
        <p v-if="error" class="error">{{ error }}</p>
        <p v-if="msg" class="okmsg">{{ msg }}</p>
      </div>
      <p class="switch">
        <template v-if="mode === 'login'">没有账号？<a @click="switchMode('register')">注册一个</a></template>
        <template v-else>已有账号？<a @click="switchMode('login')">直接登录</a></template>
      </p>
      <p class="hint">首次使用默认 admin / admin123</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const username = ref('')
const password = ref('')
const password2 = ref('')
const loading = ref(false)
const error = ref('')
const msg = ref('')
const mode = ref('login')
const router = useRouter()
const auth = useAuthStore()

function switchMode(m) {
  mode.value = m
  error.value = ''; msg.value = ''
}

async function submit() {
  error.value = ''; msg.value = ''
  if (!username.value || !password.value) { error.value = '请输入用户名和密码'; return }
  if (mode.value === 'register' && password.value !== password2.value) {
    error.value = '两次密码不一致'; return
  }
  loading.value = true
  try {
    if (mode.value === 'register') {
      await api.post('/auth/register', { username: username.value, password: password.value })
      msg.value = '注册成功，正在登录…'
    }
    const { data } = await api.post('/auth/login', { username: username.value, password: password.value })
    auth.login(data.token, data.username)
    router.push('/chat')
  } catch (e) {
    error.value = e.response?.data?.detail || (mode.value === 'login' ? '登录失败' : '注册失败')
    msg.value = ''
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: transparent; }
.login-card { width: 380px; }

.brand { text-align: center; margin-bottom: 34px; }
.seal {
  width: 64px; height: 64px; margin: 0 auto 18px; display: grid; place-items: center;
  background: var(--seal); color: var(--paper); font-family: var(--font-display);
  font-size: 30px; font-weight: 700; border-radius: 8px;
  box-shadow: 0 1px 0 rgba(255,255,255,.08), 0 6px 18px rgba(176,58,46,.16);
}
h1 { font-family: var(--font-display); font-size: 30px; font-weight: 600; letter-spacing: .5px; }
.sub { margin-top: 8px; color: var(--ink-soft); font-size: 13.5px; }

.form { display: flex; flex-direction: column; gap: 16px; }
label { display: flex; flex-direction: column; gap: 7px; font-size: 13px; color: var(--ink-soft); }
input {
  padding: 12px 13px; font-size: 14.5px; color: var(--ink);
  background: var(--card-solid); border: 1px solid var(--line); border-radius: var(--radius); outline: none;
  transition: border-color .15s;
}
input:focus { border-color: var(--accent); }
button {
  margin-top: 6px; padding: 13px; font-size: 14.5px; font-weight: 500; letter-spacing: .5px;
  background: var(--ink); color: var(--paper); border: none; border-radius: var(--radius);
  transition: background .15s;
}
button:hover { background: var(--accent); }
button:disabled { background: var(--ink-faint); cursor: not-allowed; }
.error { color: var(--seal); font-size: 13px; text-align: center; }
.okmsg { color: var(--ok); font-size: 13px; text-align: center; }
.switch { margin-top: 16px; text-align: center; font-size: 13px; color: var(--ink-soft); }
.switch a { color: var(--accent); cursor: pointer; }
.switch a:hover { text-decoration: underline; }
.hint { margin-top: 18px; text-align: center; color: var(--ink-faint); font-size: 12.5px; }
</style>
