export type MonacoLikeEditor = {
  focus?: () => void
  trigger?: (source: string, handlerId: string, payload: unknown) => void
  getValue?: () => string
}

export function appendDslText(prev: string, text: string): string {
  const t = String(text ?? '')
  if (!t) return prev ?? ''
  const p = String(prev ?? '')
  if (!p.trim()) return t
  if (p.endsWith('\n')) return `${p}${t}`
  return `${p}\n${t}`
}

export function insertIntoMonacoEditor(editor: MonacoLikeEditor | null, text: string): string | null {
  if (!editor) return null
  if (typeof editor.trigger !== 'function') return null
  try {
    if (typeof editor.focus === 'function') editor.focus()
    editor.trigger('dsl-expr-help', 'type', { text })
    if (typeof editor.getValue === 'function') return editor.getValue()
  } catch {
    // ignore
  }
  return null
}

export function insertIntoInputAtCursor(
  el: HTMLInputElement | HTMLTextAreaElement | null,
  text: string,
): string | null {
  if (!el) return null
  const value = String(el.value ?? '')
  const t = String(text ?? '')
  if (!t) return value
  const start = typeof el.selectionStart === 'number' ? el.selectionStart : value.length
  const end = typeof el.selectionEnd === 'number' ? el.selectionEnd : value.length
  return value.slice(0, start) + t + value.slice(end)
}

