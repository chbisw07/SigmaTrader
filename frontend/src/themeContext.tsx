/* eslint-disable react-refresh/only-export-components */
import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

import {
  DEFAULT_THEME_ID,
  THEMES,
  type ThemeId,
  isValidThemeId,
} from './theme'

type ThemeContextValue = {
  themeId: ThemeId
  setThemeId: (id: ThemeId) => void
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

const STORAGE_KEY = 'st_theme_id'

function getInitialThemeId(): ThemeId {
  if (typeof window === 'undefined') return DEFAULT_THEME_ID
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored && isValidThemeId(stored)) return stored
  return DEFAULT_THEME_ID
}

export function AppThemeProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeIdState] = useState<ThemeId>(getInitialThemeId)

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, themeId)
    }
  }, [themeId])

  const setThemeId = (id: ThemeId) => {
    setThemeIdState(id)
  }

  const value = useMemo(
    () => ({
      themeId,
      setThemeId,
    }),
    [themeId],
  )

  const muiTheme = useMemo(() => THEMES[themeId], [themeId])

  return (
    <ThemeContext.Provider value={value}>
      <ThemeProvider theme={muiTheme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ThemeContext.Provider>
  )
}

export function useAppTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) {
    throw new Error('useAppTheme must be used within AppThemeProvider')
  }
  return ctx
}
