import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import './Header.css'

interface HeaderProps {
  title: string
  onLogout: () => void
}

const Header: React.FC<HeaderProps> = ({ title, onLogout }) => {
  const { t } = useTranslation()
  const location = useLocation()

  return (
    <header className="app-header">
      <h1 className="header-title">{title}</h1>
      <nav className="header-nav">
        <span className="header-username">
          {localStorage.getItem('username') || t('app.user')}
        </span>
        <Link 
          to="/" 
          className={location.pathname === '/' ? 'active' : ''}
        >
          {t('history.nav.home')}
        </Link>
        <Link 
          to="/history" 
          className={location.pathname === '/history' ? 'active' : ''}
        >
          {t('history.title')}
        </Link>
        <Link 
          to="/tasks" 
          className={location.pathname === '/tasks' ? 'active' : ''}
        >
          {t('history.nav.tasks', 'Tasks')}
        </Link>
        <Link 
          to="/playlist" 
          className={location.pathname === '/playlist' ? 'active' : ''}
        >
          {t('history.nav.playlist')}
        </Link>
        <Link 
          to="/settings" 
          className={location.pathname === '/settings' ? 'active' : ''}
        >
          {t('history.nav.settings')}
        </Link>
        <button 
          className="header-logout-button"
          onClick={onLogout}
        >
          {t('history.nav.logout')}
        </button>
      </nav>
    </header>
  )
}

export default Header