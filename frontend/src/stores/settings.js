import { defineStore } from 'pinia'

// 岗位列表
export const POSITIONS = [
  { key: 'ai_app_dev', name: 'AI 应用开发' },
  { key: 'python_backend', name: 'Python 后端' },
  { key: 'algorithm', name: 'AI 算法' },
]

// 级别列表
export const LEVELS = [
  { key: 'intern', name: '实习' },
  { key: 'campus', name: '校招' },
  { key: 'social', name: '社招' },
]

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    position: localStorage.getItem('ia_position') || 'ai_app_dev',
    level: localStorage.getItem('ia_level') || 'campus',
  }),
  actions: {
    setPosition(p) { this.position = p; localStorage.setItem('ia_position', p) },
    setLevel(l) { this.level = l; localStorage.setItem('ia_level', l) },
  },
})
