import { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Login from './components/Login'
import ChatInterface from './components/ChatInterface'
import HistoryPage from './components/HistoryPage'
import Settings from './components/Settings'
import PlaylistPage from './components/PlaylistPage'
import VideoPlayer from './components/VideoPlayer'
import PlaylistPlayerPage from './components/PlaylistPlayerPage'
import PlaylistReadingPage from './components/PlaylistReadingPage'
import TaskStatusPage from './components/TaskStatusPage'
import SubscriptionsPage from './components/SubscriptionsPage'
import './i18n/config'
import './App.css'

type Theme = 'light' | 'dark'

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  localStorage.setItem('theme', theme)
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check if user is authenticated
    const token = localStorage.getItem('token')
    setIsAuthenticated(!!token)

    // Apply saved theme (default: light)
    const savedTheme = (localStorage.getItem('theme') as Theme | null) ?? 'light'
    applyTheme(savedTheme === 'dark' ? 'dark' : 'light')

    setLoading(false)
  }, [])

  const handleLogin = () => {
    setIsAuthenticated(true)
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('user_id')
    setIsAuthenticated(false)
  }

  if (loading) {
    return <div>Loading...</div>
  }

  return (
    <Router>
      <Routes>
        <Route
          path="/login"
          element={
            isAuthenticated ? (
              <Navigate to="/" replace />
            ) : (
              <Login onLogin={handleLogin} />
            )
          }
        />
        <Route
          path="/"
          element={
            isAuthenticated ? (
              <ChatInterface onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/history"
          element={
            isAuthenticated ? (
              <HistoryPage onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/tasks"
          element={
            isAuthenticated ? (
              <TaskStatusPage onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/settings"
          element={
            isAuthenticated ? (
              <Settings onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/subscriptions"
          element={
            isAuthenticated ? (
              <SubscriptionsPage onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/playlist"
          element={
            isAuthenticated ? (
              <PlaylistPage onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/playlist/:playlistId/play"
          element={
            isAuthenticated ? (
              <PlaylistPlayerPage onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/playlist/:playlistId/play/:videoId"
          element={
            isAuthenticated ? (
              <PlaylistPlayerPage onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/playlist/:playlistId/read"
          element={
            isAuthenticated ? (
              <PlaylistReadingPage onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route
          path="/player/:videoId"
          element={
            isAuthenticated ? (
              <VideoPlayer onLogout={handleLogout} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
      </Routes>
    </Router>
  )
}

export default App
