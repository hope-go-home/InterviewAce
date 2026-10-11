<template>
  <div class="picker">
    <select :value="settings.position" @change="settings.setPosition($event.target.value)" title="岗位">
      <option v-for="p in POSITIONS" :key="p.key" :value="p.key">{{ p.name }}</option>
    </select>
    <select :value="settings.level" @change="settings.setLevel($event.target.value)" title="级别">
      <option v-for="l in LEVELS" :key="l.key" :value="l.key">{{ l.name }}</option>
    </select>
  </div>
</template>

<script setup>
import { useSettingsStore, POSITIONS, LEVELS } from '../stores/settings'
const settings = useSettingsStore()
</script>

<style scoped>
.picker { display: flex; gap: 8px; }
select {
  padding: 6px 9px; font-size: 12.5px; background: var(--card-solid); color: var(--ink);
  border: 1px solid var(--line); border-radius: 6px; outline: none; cursor: pointer;
}
select:focus { border-color: var(--accent); }
</style>
