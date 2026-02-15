import Box from '@mui/material/Box'
import { useTheme } from '@mui/material/styles'
import Editor, { useMonaco } from '@monaco-editor/react'
import { useEffect, useMemo, useRef } from 'react'

import { BUILTIN_DSL_FUNCTIONS, DSL_KEYWORDS, DSL_SOURCES } from '../services/dslCatalog'

type CustomIndicatorForDsl = {
  id: number
  name: string
  params: string[]
  description?: string | null
}

const REGISTERED_LANGS = new Set<string>()
const PROVIDERS = new Map<string, { dispose: () => void }>()

type DslEditorProps = {
  languageId: string
  value: string
  onChange: (next: string) => void
  height?: number
  fontSize?: number
  paddingY?: number
  operands?: string[]
  customIndicators?: CustomIndicatorForDsl[]
  onCtrlEnter?: () => void
  onEditorMount?: (editor: any) => void
}

function _snippetForCustomIndicator(ci: CustomIndicatorForDsl): string {
  const params = Array.isArray(ci.params) ? ci.params : []
  if (params.length === 0) return `${ci.name}()`
  const args = params.map((p, idx) => `\${${idx + 1}:${p}}`).join(', ')
  return `${ci.name}(${args})`
}

export function DslEditor({
  languageId,
  value,
  onChange,
  height = 160,
  fontSize = 13,
  paddingY = 8,
  operands = [],
  customIndicators = [],
  onCtrlEnter,
  onEditorMount,
}: DslEditorProps) {
  const theme = useTheme()
  const monaco = useMonaco()
  const ctrlEnterRef = useRef<(() => void) | undefined>(onCtrlEnter)

  useEffect(() => {
    ctrlEnterRef.current = onCtrlEnter
  }, [onCtrlEnter])

  const completions = useMemo(() => {
    const uniqOperands = Array.from(
      new Set(
        (operands ?? [])
          .map((x) => String(x || '').trim())
          .filter(Boolean),
      ),
    )

    const sources = DSL_SOURCES.map((s) => s.expr)

    const keywordItems = DSL_KEYWORDS.map((k) => ({ label: k.expr, insertText: k.expr }))

    const builtinFnItems = BUILTIN_DSL_FUNCTIONS.map((fn) => ({
      label: fn.name,
      snippet: fn.snippet,
    }))

    const customFnItems = (customIndicators ?? [])
      .map((ci) => ({
        label: ci.name,
        snippet: _snippetForCustomIndicator(ci),
        detail: ci.params?.length ? `(${ci.params.join(', ')})` : '()',
        documentation: ci.description || undefined,
      }))
      .sort((a, b) => a.label.localeCompare(b.label))

    return { uniqOperands, sources, keywordItems, builtinFnItems, customFnItems }
  }, [customIndicators, operands])

  useEffect(() => {
    if (!monaco) return

    if (!REGISTERED_LANGS.has(languageId)) {
      monaco.languages.register({ id: languageId })
      monaco.languages.setMonarchTokensProvider(languageId, {
        tokenizer: {
          root: [
            [/[A-Za-z_][A-Za-z0-9_]*/, 'identifier'],
            [/\d+(\.\d+)?/, 'number'],
            [/\"[^\"]*\"|'[^']*'/, 'string'],
            [/[()]/, '@brackets'],
            [/[+\-*/]/, 'operator'],
            [/==|!=|>=|<=|>|</, 'operator'],
            [/,/, 'delimiter'],
          ],
        },
      })
      REGISTERED_LANGS.add(languageId)
    }

    const prev = PROVIDERS.get(languageId)
    if (prev) prev.dispose()

    const disposable = monaco.languages.registerCompletionItemProvider(languageId, {
      triggerCharacters: ['_', '"', "'", '(', ','],
      provideCompletionItems: (model, position) => {
        const word = model.getWordUntilPosition(position)
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        }

        const suggestions: any[] = []

        for (const op of completions.uniqOperands) {
          suggestions.push({
            label: op,
            kind: monaco.languages.CompletionItemKind.Variable,
            insertText: op,
            range,
          })
        }

        for (const s of completions.sources) {
          suggestions.push({
            label: s,
            kind: monaco.languages.CompletionItemKind.Constant,
            insertText: s,
            range,
          })
        }

        for (const k of completions.keywordItems) {
          suggestions.push({
            label: k.label,
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: k.insertText,
            range,
          })
        }

        for (const fn of completions.builtinFnItems) {
          suggestions.push({
            label: fn.label,
            kind: monaco.languages.CompletionItemKind.Function,
            insertText: fn.snippet,
            insertTextRules:
              monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            range,
            detail: 'Built-in',
          })
        }

        for (const fn of completions.customFnItems) {
          suggestions.push({
            label: fn.label,
            kind: monaco.languages.CompletionItemKind.Function,
            insertText: fn.snippet,
            insertTextRules:
              monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            range,
            detail: `Custom ${fn.detail}`,
            documentation: fn.documentation,
          })
        }

        return { suggestions }
      },
    })

    PROVIDERS.set(languageId, disposable)
    return () => {
      disposable.dispose()
      const current = PROVIDERS.get(languageId)
      if (current === disposable) PROVIDERS.delete(languageId)
    }
  }, [completions, languageId, monaco])

  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1,
        overflow: 'hidden',
      }}
    >
      <Editor
        language={languageId}
        theme={theme.palette.mode === 'dark' ? 'vs-dark' : 'vs'}
        height={height}
        value={value}
        onChange={(v) => onChange(v ?? '')}
        onMount={(editor, editorMonaco) => {
          if (onEditorMount) onEditorMount(editor)
          if (!ctrlEnterRef.current) return
          editor.addCommand(
            // Ctrl+Enter on Windows/Linux, Cmd+Enter on macOS.
            editorMonaco.KeyMod.CtrlCmd | editorMonaco.KeyCode.Enter,
            () => {
              if (ctrlEnterRef.current) ctrlEnterRef.current()
            },
          )
        }}
        options={{
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          lineNumbers: 'off',
          fontSize,
          tabCompletion: 'on',
          quickSuggestions: true,
          suggestOnTriggerCharacters: true,
          snippetSuggestions: 'inline',
          padding: { top: paddingY, bottom: paddingY },
          renderLineHighlight: 'none',
          scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
        }}
      />
    </Box>
  )
}
