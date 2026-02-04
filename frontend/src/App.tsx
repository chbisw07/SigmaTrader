import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import MainLayout from './layouts/MainLayout'
import { AppRoutes } from './routes/AppRoutes'
import { AuthPage } from './views/AuthPage'
import { fetchCurrentUser, type CurrentUser } from './services/auth'
import { useAppTheme } from './themeContext'
import { isValidThemeId, type ThemeId } from './theme'

function App() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const location = useLocation()
  const { setThemeId } = useAppTheme()

  useEffect(() => {
    let active = true
    const run = async () => {
      try {
        const user = await fetchCurrentUser()
        if (!active) return
        setCurrentUser(user)
        if (user?.theme_id && isValidThemeId(user.theme_id)) {
          setThemeId(user.theme_id as ThemeId)
        }
      } catch {
        if (!active) return
        setCurrentUser(null)
      } finally {
        if (active) setAuthChecked(true)
      }
    }
    void run()
    return () => {
      active = false
    }
  }, [])

  const handleAuthSuccess = (user: CurrentUser) => {
    setCurrentUser(user)
    if (user.theme_id && isValidThemeId(user.theme_id)) {
      setThemeId(user.theme_id as ThemeId)
    }
  }

  const isAuthRoute = location.pathname === '/auth'

  if (!authChecked) {
    return null
  }

  if (!currentUser && !isAuthRoute) {
    return <Navigate to="/auth" replace />
  }

  if (!currentUser && isAuthRoute) {
    return <AuthPage onAuthSuccess={handleAuthSuccess} />
  }

  return (
    <MainLayout currentUser={currentUser!} onAuthChange={setCurrentUser}>
      <AppRoutes />
    </MainLayout>
  )
}

export default App
