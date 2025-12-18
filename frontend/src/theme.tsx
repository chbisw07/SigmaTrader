import { alpha, createTheme, type Theme } from '@mui/material/styles'

export type ThemeId =
  | 'dark'
  | 'light'
  | 'lightComfort'
  | 'lightHighContrast'
  | 'lightSapphire'
  | 'lightMint'
  | 'amber'

export const THEME_IDS: ThemeId[] = [
  'dark',
  'light',
  'lightComfort',
  'lightHighContrast',
  'lightSapphire',
  'lightMint',
  'amber',
]

type SigmaThemeTokens = {
  mode: 'light' | 'dark'
  primary: string
  secondary: string
  backgroundDefault: string
  backgroundPaper: string
  textPrimary: string
  textSecondary: string
  appBarGradient: string
  drawerBg: string
}

function createSigmaTheme(tokens: SigmaThemeTokens): Theme {
  const base = createTheme({
    palette: {
      mode: tokens.mode,
      primary: { main: tokens.primary },
      secondary: { main: tokens.secondary },
      background: {
        default: tokens.backgroundDefault,
        paper: tokens.backgroundPaper,
      },
      text: {
        primary: tokens.textPrimary,
        secondary: tokens.textSecondary,
      },
      divider:
        tokens.mode === 'dark'
          ? alpha('#ffffff', 0.12)
          : alpha('#0f172a', 0.12),
      action: {
        hover:
          tokens.mode === 'dark'
            ? alpha('#ffffff', 0.06)
            : alpha('#0f172a', 0.04),
        selected:
          tokens.mode === 'dark'
            ? alpha('#ffffff', 0.10)
            : alpha(tokens.primary, 0.10),
      },
    },
    shape: { borderRadius: 12 },
    typography: {
      fontFamily:
        '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
      h4: { fontWeight: 750, letterSpacing: -0.4 },
      h5: { fontWeight: 720, letterSpacing: -0.3 },
      h6: { fontWeight: 700, letterSpacing: -0.2 },
      subtitle1: { fontWeight: 650 },
      subtitle2: { fontWeight: 650 },
      button: { textTransform: 'none', fontWeight: 650 },
    },
  })

  const isDark = base.palette.mode === 'dark'

  return createTheme(base, {
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundColor: base.palette.background.default,
          },
        },
      },
      MuiAppBar: {
        defaultProps: { color: 'transparent' },
        styleOverrides: {
          root: {
            color: '#fff',
            backgroundImage: tokens.appBarGradient,
            boxShadow: isDark
              ? `0 10px 30px ${alpha('#000', 0.35)}`
              : `0 10px 30px ${alpha('#0f172a', 0.12)}`,
            borderBottom: `1px solid ${alpha('#ffffff', isDark ? 0.08 : 0.18)}`,
            '& .MuiTypography-root': {
              color: 'inherit',
            },
            '& .MuiIconButton-root': {
              color: 'inherit',
            },
          },
        },
      },
      MuiToolbar: {
        styleOverrides: {
          root: {
            minHeight: 64,
          },
        },
      },
      MuiDrawer: {
        styleOverrides: {
          paper: {
            backgroundColor: tokens.drawerBg,
            borderRight: `1px solid ${alpha(
              isDark ? '#ffffff' : '#0f172a',
              isDark ? 0.10 : 0.10,
            )}`,
          },
        },
      },
      MuiListItemButton: {
        styleOverrides: {
          root: {
            borderRadius: 10,
            margin: '4px 8px',
            '&.active': {
              backgroundColor: base.palette.action.selected,
            },
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: 10,
          },
          contained: {
            boxShadow: 'none',
            '&:hover': {
              boxShadow: isDark
                ? `0 10px 24px ${alpha('#000', 0.25)}`
                : `0 10px 24px ${alpha(base.palette.primary.main, 0.22)}`,
            },
          },
        },
      },
      MuiTextField: {
        defaultProps: {
          variant: 'outlined',
        },
      },
      MuiDataGrid: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            borderColor: alpha(isDark ? '#ffffff' : '#0f172a', isDark ? 0.12 : 0.12),
            '--DataGrid-rowBorderColor': alpha(
              isDark ? '#ffffff' : '#0f172a',
              isDark ? 0.08 : 0.08,
            ),
            backgroundColor: base.palette.background.paper,
          },
          columnHeaders: {
            backgroundColor: alpha(
              isDark ? '#ffffff' : base.palette.primary.main,
              isDark ? 0.04 : 0.06,
            ),
            borderBottom: `1px solid ${alpha(
              isDark ? '#ffffff' : '#0f172a',
              isDark ? 0.10 : 0.10,
            )}`,
          },
          cell: {
            borderBottom: `1px solid ${alpha(
              isDark ? '#ffffff' : '#0f172a',
              isDark ? 0.06 : 0.06,
            )}`,
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: 999,
            fontWeight: 650,
          },
        },
      },
    },
  })
}

export const THEMES: Record<ThemeId, Theme> = {
  dark: createSigmaTheme({
    mode: 'dark',
    primary: '#90caf9',
    secondary: '#f48fb1',
    backgroundDefault: '#0b0f19',
    backgroundPaper: '#151b2c',
    textPrimary: '#e6edf7',
    textSecondary: '#a6b0c3',
    appBarGradient: 'linear-gradient(90deg, #0a2a52 0%, #111a3b 55%, #2b1441 100%)',
    drawerBg: '#0b1020',
  }),
  light: createSigmaTheme({
    mode: 'light',
    primary: '#1565c0',
    secondary: '#ff9800',
    backgroundDefault: '#f6f8ff',
    backgroundPaper: '#ffffff',
    textPrimary: '#0f172a',
    textSecondary: '#475569',
    appBarGradient: 'linear-gradient(90deg, #0b2f6b 0%, #1d4ed8 55%, #6d28d9 100%)',
    drawerBg: '#f8fafc',
  }),
  lightComfort: createSigmaTheme({
    mode: 'light',
    primary: '#1976d2',
    secondary: '#26a69a',
    backgroundDefault: '#f5f8ff',
    backgroundPaper: '#ffffff',
    textPrimary: '#0f172a',
    textSecondary: '#475569',
    appBarGradient: 'linear-gradient(90deg, #0b2f6b 0%, #1976d2 55%, #0f766e 100%)',
    drawerBg: '#f8fafc',
  }),
  lightHighContrast: createSigmaTheme({
    mode: 'light',
    primary: '#0d47a1',
    secondary: '#c62828',
    backgroundDefault: '#ffffff',
    backgroundPaper: '#ffffff',
    textPrimary: '#0b1220',
    textSecondary: '#334155',
    appBarGradient: 'linear-gradient(90deg, #0b2f6b 0%, #0d47a1 65%, #7f1d1d 100%)',
    drawerBg: '#f8fafc',
  }),
  lightSapphire: createSigmaTheme({
    mode: 'light',
    primary: '#1d4ed8',
    secondary: '#7c3aed',
    backgroundDefault: '#f6f8ff',
    backgroundPaper: '#ffffff',
    textPrimary: '#0b1220',
    textSecondary: '#42526b',
    appBarGradient: 'linear-gradient(90deg, #0b2f6b 0%, #1d4ed8 55%, #7c3aed 100%)',
    drawerBg: '#f8fafc',
  }),
  lightMint: createSigmaTheme({
    mode: 'light',
    primary: '#0f766e',
    secondary: '#2563eb',
    backgroundDefault: '#f4fbf8',
    backgroundPaper: '#ffffff',
    textPrimary: '#071a17',
    textSecondary: '#3f5f58',
    appBarGradient: 'linear-gradient(90deg, #064e3b 0%, #0f766e 55%, #2563eb 100%)',
    drawerBg: '#f6fbf9',
  }),
  amber: createSigmaTheme({
    mode: 'dark',
    primary: '#ffb300',
    secondary: '#ff7043',
    backgroundDefault: '#121010',
    backgroundPaper: '#1d1309',
    textPrimary: '#fff3e0',
    textSecondary: '#ffcc80',
    appBarGradient: 'linear-gradient(90deg, #1d1309 0%, #3b1f0a 55%, #2c0f0f 100%)',
    drawerBg: '#130d08',
  }),
}

export const DEFAULT_THEME_ID: ThemeId = 'lightMint'

export function isValidThemeId(id: string | null | undefined): id is ThemeId {
  return THEME_IDS.includes(id as ThemeId)
}
