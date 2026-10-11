import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('ia_token') || '',
    username: localStorage.getItem('ia_username') || '',
  }),
  actions: {
    login(token, username) {
      this.token = token
      this.username = username
      localStorage.setItem('ia_token', token)
      localStorage.setItem('ia_username', username)
    },
    logout() {
      this.token = ''
      this.username = ''
      localStorage.removeItem('ia_token')
      localStorage.removeItem('ia_username')
    },
  },
})
