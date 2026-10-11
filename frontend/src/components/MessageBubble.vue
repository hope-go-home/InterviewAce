<template>
  <div class="bubble" :class="[msg.role, { fallback: msg.is_fallback }]">
    <!-- 联网兜底标记 -->
    <div v-if="msg.is_fallback" class="fallback-tag">
      ⚠️ 题库未收录 · 以下为联网检索作答（已记录，将补充进题库）
    </div>

    <!-- 思考过程 -->
    <ThinkPanel v-if="msg.thinking?.length" :steps="msg.thinking" />

    <!-- 检索来源 -->
    <SourceCard v-if="msg.sources?.length" :sources="msg.sources" :stats="msg.stats" />

    <!-- 正文 -->
    <div class="content" v-html="rendered"></div>

    <!-- 用户消息带的图片 -->
    <div v-if="msg.image" class="user-img"><img :src="msg.image" alt="题目图片"></div>

    <!-- 相似真题 -->
    <div v-if="msg.similar?.length" class="similar">
      <div class="similar-title">相似真题</div>
      <div v-for="(q, i) in msg.similar" :key="i" class="similar-item">
        <span class="meta">{{ q.domain }} · 难度{{ q.difficulty }}</span>
        <span class="q">{{ q.question }}</span>
      </div>
    </div>

    <span v-if="msg.streaming" class="cursor">▍</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import ThinkPanel from './ThinkPanel.vue'
import SourceCard from './SourceCard.vue'

const props = defineProps({ msg: { type: Object, required: true } })

const rendered = computed(() => {
  if (!props.msg.content) return ''
  return DOMPurify.sanitize(marked.parse(props.msg.content))
})
</script>

<style scoped>
.bubble { padding: 22px 0; }

/* 用户提问：右对齐一条题签 */
.user .content {
  font-size: 15.5px; font-weight: 500;
  padding: 12px 16px; background: var(--card-solid);
  border: 1px solid var(--line); border-left: 3px solid var(--seal);
  border-radius: 0 var(--radius) var(--radius) 0;
}

/* AI 作答：文档流 */
.assistant .content { font-size: 15px; line-height: 1.8; }
.assistant .content :deep(h1), .assistant .content :deep(h2), .assistant .content :deep(h3) {
  font-family: var(--font-display); font-weight: 600; margin: 16px 0 8px; line-height: 1.4;
}
.assistant .content :deep(h2) { font-size: 17px; }
.assistant .content :deep(h3) { font-size: 15.5px; }
.assistant .content :deep(p) { margin: 9px 0; }
.assistant .content :deep(ul), .assistant .content :deep(ol) { padding-left: 22px; margin: 9px 0; }
.assistant .content :deep(li) { margin: 4px 0; }
.assistant .content :deep(strong) { font-weight: 600; }
.assistant .content :deep(code) {
  font-family: var(--font-mono); font-size: 13px;
  background: var(--paper-2); padding: 1.5px 6px; border-radius: 4px;
}
.assistant .content :deep(pre) {
  background: var(--pre-bg); color: var(--pre-text); padding: 14px 16px; border-radius: var(--radius);
  overflow-x: auto; margin: 12px 0; font-size: 13px; line-height: 1.6;
}
.assistant .content :deep(pre code) { background: none; padding: 0; color: inherit; }
.assistant .content :deep(blockquote) {
  border-left: 3px solid var(--line); padding: 2px 0 2px 14px;
  margin: 12px 0; color: var(--ink-soft);
}
.assistant .content :deep(table) { border-collapse: collapse; margin: 12px 0; font-size: 13.5px; }
.assistant .content :deep(th), .assistant .content :deep(td) {
  border: 1px solid var(--line); padding: 7px 12px; text-align: left;
}
.assistant .content :deep(th) { background: var(--paper-2); font-weight: 600; }
.assistant .content :deep(hr) { border: none; border-top: 1px solid var(--line-soft); margin: 16px 0; }

.similar { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line-soft); }
.similar-title {
  font-family: var(--font-display); font-size: 13.5px; font-weight: 600;
  color: var(--ink-soft); margin-bottom: 6px;
}
.similar-item { display: flex; gap: 12px; align-items: baseline; padding: 5px 0; font-size: 13.5px; }
.similar-item .meta { flex: 0 0 auto; font-size: 11.5px; color: var(--ink-faint); font-family: var(--font-mono); }
.similar-item .q { color: var(--ink); }

.cursor { display: inline-block; color: var(--seal); animation: blink 1.1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }

/* 用户消息里的图片 */
.user-img { margin-top: 8px; }
.user-img img { max-width: 320px; max-height: 240px; border-radius: 8px; border: 1px solid var(--line); }

/* 联网兜底答案：印章红左边框 */
.bubble.fallback .content {
  border-left: 3px solid var(--seal); padding-left: 14px;
}
.fallback-tag {
  display: inline-block; margin-bottom: 10px; padding: 4px 11px;
  font-size: 12px; color: var(--seal);
  background: rgba(176,58,46,.07); border: 1px solid rgba(176,58,46,.25);
  border-radius: 6px;
}
</style>
