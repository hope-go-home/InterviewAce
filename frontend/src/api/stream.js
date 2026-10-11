/**
 * SSE 流式请求（fetch + ReadableStream 手动分包）
 * 后端事件：session / thinking / sources / stats / token / answer / done / error
 */
export async function streamQA(question, sessionId, handlers, imageBase64 = null, opts = {}) {
  const token = localStorage.getItem('ia_token')

  const body = { question, session_id: sessionId }
  if (imageBase64) body.image_base64 = imageBase64
  if (opts.position) body.position = opts.position
  if (opts.level) body.level = opts.level

  const resp = await fetch('/api/qa/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    handlers.onError?.(err.detail || `HTTP ${resp.status}`)
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE 帧以双换行分隔
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const eventMatch = frame.match(/^event: (.+)$/m)
      const dataMatch = frame.match(/^data: (.*)$/m)
      if (!eventMatch || !dataMatch) continue
      const event = eventMatch[1].trim()
      let data
      try { data = JSON.parse(dataMatch[1]) } catch { continue }

      switch (event) {
        case 'session': handlers.onSession?.(data.session_id); break
        case 'thinking': handlers.onThinking?.(data); break
        case 'sources': handlers.onSources?.(data); break
        case 'stats': handlers.onStats?.(data); break
        case 'token': handlers.onToken?.(data.content); break
        case 'answer': handlers.onAnswer?.(data); break
        case 'done': handlers.onDone?.(); break
        case 'error': handlers.onError?.(data.message); break
      }
    }
  }
}
