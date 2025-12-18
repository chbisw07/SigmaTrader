import Box from '@mui/material/Box'
import { useTheme } from '@mui/material/styles'
import Editor, { useMonaco } from '@monaco-editor/react'
import { useEffect, useMemo } from 'react'

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
  operands?: string[]
  customIndicators?: CustomIndicatorForDsl[]
  onCtrlEnter?: () => void
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
  operands = [],
  customIndicators = [],
  onCtrlEnter,
}: DslEditorProps) {
  const theme = useTheme()
  const monaco = useMonaco()

  const completions = useMemo(() => {
    const uniqOperands = Array.from(
      new Set(
        (operands ?? [])
          .map((x) => String(x || '').trim())
          .filter(Boolean),
      ),
    )

    const sources = ['open', 'high', 'low', 'close', 'volume']

    const keywordItems = [
      { label: 'AND', insertText: 'AND' },
      { label: 'OR', insertText: 'OR' },
      { label: 'NOT', insertText: 'NOT' },
      { label: 'CROSSES_ABOVE', insertText: 'CROSSES_ABOVE' },
      { label: 'CROSSES_BELOW', insertText: 'CROSSES_BELOW' },
      { label: 'MOVING_UP', insertText: 'MOVING_UP' },
      { label: 'MOVING_DOWN', insertText: 'MOVING_DOWN' },
    ]

    const builtinFnItems = [
      { label: 'OPEN', snippet: 'OPEN("${1:1d}")' },
      { label: 'HIGH', snippet: 'HIGH("${1:1d}")' },
      { label: 'LOW', snippet: 'LOW("${1:1d}")' },
      { label: 'CLOSE', snippet: 'CLOSE("${1:1d}")' },
      { label: 'VOLUME', snippet: 'VOLUME("${1:1d}")' },
      { label: 'PRICE', snippet: 'PRICE("${1:1d}")' },

      { label: 'SMA', snippet: 'SMA(${1:close}, ${2:14}, "${3:1d}")' },
      { label: 'EMA', snippet: 'EMA(${1:close}, ${2:14}, "${3:1d}")' },
      { label: 'RSI', snippet: 'RSI(${1:close}, ${2:14}, "${3:1d}")' },
      { label: 'STDDEV', snippet: 'STDDEV(${1:close}, ${2:14}, "${3:1d}")' },
      { label: 'MAX', snippet: 'MAX(${1:close}, ${2:14}, "${3:1d}")' },
      { label: 'MIN', snippet: 'MIN(${1:close}, ${2:14}, "${3:1d}")' },
      { label: 'AVG', snippet: 'AVG(${1:close}, ${2:14}, "${3:1d}")' },
      { label: 'SUM', snippet: 'SUM(${1:close}, ${2:14}, "${3:1d}")' },

      { label: 'RET', snippet: 'RET(${1:close}, "${2:1d}")' },
      { label: 'ATR', snippet: 'ATR(${1:14}, "${2:1d}")' },

      { label: 'LAG', snippet: 'LAG(${1:close}, ${2:1})' },
      { label: 'ROC', snippet: 'ROC(${1:close}, ${2:14})' },
      { label: 'Z_SCORE', snippet: 'Z_SCORE(${1:close}, ${2:20})' },
      { label: 'BOLLINGER', snippet: 'BOLLINGER(${1:close}, ${2:20}, ${3:2})' },
      { label: 'CROSSOVER', snippet: 'CROSSOVER(${1:a}, ${2:b})' },
      { label: 'CROSSUNDER', snippet: 'CROSSUNDER(${1:a}, ${2:b})' },

      { label: 'ABS', snippet: 'ABS(${1:x})' },
      { label: 'SQRT', snippet: 'SQRT(${1:x})' },
      { label: 'LOG', snippet: 'LOG(${1:x})' },
      { label: 'EXP', snippet: 'EXP(${1:x})' },
      { label: 'POW', snippet: 'POW(${1:x}, ${2:y})' },
    ]

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
          if (!onCtrlEnter) return
          editor.addCommand(
            // Ctrl+Enter on Windows/Linux, Cmd+Enter on macOS.
            editorMonaco.KeyMod.CtrlCmd | editorMonaco.KeyCode.Enter,
            () => onCtrlEnter(),
          )
        }}
        options={{
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          lineNumbers: 'off',
          fontSize: 13,
          tabCompletion: 'on',
          quickSuggestions: true,
          suggestOnTriggerCharacters: true,
          snippetSuggestions: 'inline',
          padding: { top: 8, bottom: 8 },
          renderLineHighlight: 'none',
          scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
        }}
      />
    </Box>
  )
}
