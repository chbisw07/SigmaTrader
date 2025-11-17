import { createTheme, type Theme } from '@mui/material/styles'

export type ThemeId = 'dark' | 'light' | 'amber'

export const THEME_IDS: ThemeId[] = ['dark', 'light', 'amber']

export const THEMES: Record<ThemeId, Theme> = {
  dark: createTheme({
    palette: {
      mode: 'dark',
      primary: { main: '#90caf9' }, // soft blue
      secondary: { main: '#f48fb1' }, // muted pink accent
      background: {
        default: '#0b0f19',
        paper: '#151b2c',
      },
      text: {
        primary: '#e3f2fd',
        secondary: '#9fa8da',
      },
    },
  }),
  light: createTheme({
    palette: {
      mode: 'light',
      primary: { main: '#1565c0' }, // rich blue
      secondary: { main: '#ff9800' }, // subtle orange accent
      background: {
        default: '#f4f6fb',
        paper: '#ffffff',
      },
      text: {
        primary: '#1f2933',
        secondary: '#5f6c80',
      },
    },
  }),
  amber: createTheme({
    palette: {
      mode: 'dark',
      primary: { main: '#ffb300' }, // amber
      secondary: { main: '#ff7043' }, // warm coral accent
      background: {
        default: '#121010',
        paper: '#1d1309',
      },
      text: {
        primary: '#fff3e0',
        secondary: '#ffcc80',
      },
    },
  }),
}

export const DEFAULT_THEME_ID: ThemeId = 'dark'

export function isValidThemeId(id: string | null | undefined): id is ThemeId {
  return THEME_IDS.includes(id as ThemeId)
}
