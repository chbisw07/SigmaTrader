import { createTheme } from '@mui/material/styles'

export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#2dd4bf' }, // teal
    secondary: { main: '#22c55e' }, // green
    background: {
      default: '#07140f',
      paper: '#0b1f18',
    },
  },
  typography: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
  },
  shape: { borderRadius: 12 },
})

