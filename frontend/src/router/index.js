import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  // 打开即登录：未登录 → /login，已登录 → /chat
  { path: '/', redirect: () => {
      const authed = !!localStorage.getItem('ia_token')
      return authed ? '/chat' : '/login'
    } },
  { path: '/chat', component: () => import('../views/ChatView.vue') },
  { path: '/chat/:sessionId', component: () => import('../views/ChatView.vue') },
  { path: '/bank', component: () => import('../views/BankView.vue') },
  { path: '/practice', component: () => import('../views/PracticeView.vue') },
  { path: '/resume', component: () => import('../views/ResumeView.vue') },
  { path: '/me', component: () => import('../views/ProfileView.vue') },
  { path: '/interview', component: () => import('../views/InterviewLobbyView.vue') },
  { path: '/interview/:id', component: () => import('../views/InterviewRoomView.vue') },
  { path: '/interview/:id/report', component: () => import('../views/InterviewReportView.vue') },
  // 落地页保留可选访问（对外展示用）
  { path: '/welcome', component: () => import('../views/LandingView.vue'), meta: { public: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.token) return '/login'
})

export default router
