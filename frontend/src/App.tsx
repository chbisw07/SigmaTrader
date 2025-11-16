import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import MainLayout from './layouts/MainLayout'
import { AppRoutes } from './routes/AppRoutes'
import { AuthPage } from './views/AuthPage'
import { fetchCurrentUser, type CurrentUser } from './services/auth'

function App() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    let active = true
    const run = async () => {
      try {
        const user = await fetchCurrentUser()
        if (!active) return
        setCurrentUser(user)
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
  }

  const isAuthRoute = location.pathname === '/auth'

  if (!authChecked) {
    return null
  }

  if (!currentUser && !isAuthRoute) {
    navigate('/auth', { replace: true })
    return null
  }

  if (!currentUser && isAuthRoute) {
    return <AuthPage onAuthSuccess={handleAuthSuccess} />
  }

  return (
    <MainLayout currentUser={currentUser} onAuthChange={setCurrentUser}>
      <AppRoutes />
    </MainLayout>
  )
}

export default App
