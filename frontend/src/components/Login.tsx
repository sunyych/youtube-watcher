import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { authApi } from '../services/api'
import './Login.css'

interface LoginProps {
  onLogin: () => void
}

const Login: React.FC<LoginProps> = ({ onLogin }) => {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isRegister, setIsRegister] = useState(false)
  const [allowRegistration, setAllowRegistration] = useState(true)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const cfg = await authApi.getConfig()
        if (cancelled) return
        setAllowRegistration(!!cfg.allow_registration)
        if (!cfg.allow_registration) {
          setIsRegister(false)
        }
      } catch {
        // If config cannot be fetched, default to allowing registration.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    
    if (!username.trim() || !password.trim()) {
      setError(t('login.error.empty'))
      return
    }
    
    setLoading(true)

    try {
      let response
      if (isRegister) {
        response = await authApi.register(username.trim(), password)
      } else {
        response = await authApi.login(username.trim(), password)
      }
      localStorage.setItem('token', response.access_token)
      localStorage.setItem('username', response.username)
      localStorage.setItem('user_id', response.user_id.toString())
      onLogin()
    } catch (err: any) {
      setError(err.response?.data?.detail || (isRegister ? t('login.error.registerFailed') : t('login.error.loginFailed')))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-box">
        <h1>{t('login.title')}</h1>
        <p className="subtitle">{isRegister ? t('login.registerSubtitle') : t('login.subtitle')}</p>
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder={t('login.username')}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
            autoFocus
          />
          <input
            type="password"
            placeholder={t('login.password')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
          />
          {error && <div className="error">{error}</div>}
          <button type="submit" disabled={loading || !username.trim() || !password.trim()}>
            {loading ? (isRegister ? t('login.registering') : t('login.loggingIn')) : (isRegister ? t('login.register') : t('login.login'))}
          </button>
          <div className="login-footer">
            {allowRegistration && (
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setIsRegister(!isRegister)
                  setError('')
                }}
                disabled={loading}
              >
                {isRegister ? t('login.hasAccount') : t('login.noAccount')}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  )
}

export default Login
