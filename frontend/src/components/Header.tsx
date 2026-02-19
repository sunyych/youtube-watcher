import { useState, useRef, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faBars, faTimes } from '@fortawesome/free-solid-svg-icons'
import './Header.css'

interface HeaderProps {
  title: string
  onLogout: () => void
}

const Header: React.FC<HeaderProps> = ({ title, onLogout }) => {
  const { t } = useTranslation()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const navRef = useRef<HTMLDivElement>(null)

  const closeMenu = () => setMenuOpen(false)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuOpen && navRef.current && !navRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [menuOpen])

  const navLinks = (
    <>
      <span className="header-username">
        {localStorage.getItem('username') || t('app.user')}
      </span>
      <Link to="/" className={location.pathname === '/' ? 'active' : ''} onClick={closeMenu}>
        {t('history.nav.home')}
      </Link>
      <Link to="/history" className={location.pathname === '/history' ? 'active' : ''} onClick={closeMenu}>
        {t('history.title')}
      </Link>
      <Link to="/tasks" className={location.pathname === '/tasks' ? 'active' : ''} onClick={closeMenu}>
        {t('history.nav.tasks', 'Tasks')}
      </Link>
      <Link to="/playlist" className={location.pathname === '/playlist' ? 'active' : ''} onClick={closeMenu}>
        {t('history.nav.playlist')}
      </Link>
      <Link to="/subscriptions" className={location.pathname === '/subscriptions' ? 'active' : ''} onClick={closeMenu}>
        {t('subscriptions.title')}
      </Link>
      <Link to="/settings" className={location.pathname === '/settings' ? 'active' : ''} onClick={closeMenu}>
        {t('history.nav.settings')}
      </Link>
      <button type="button" className="header-logout-button" onClick={() => { closeMenu(); onLogout() }}>
        {t('history.nav.logout')}
      </button>
    </>
  )

  return (
    <header className="app-header">
      <h1 className="header-title">{title}</h1>
      <div className="header-nav-wrap" ref={navRef}>
        <button
          type="button"
          className="header-menu-toggle"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={menuOpen ? 'true' : 'false'}
          onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v) }}
        >
          {menuOpen ? <FontAwesomeIcon icon={faTimes} /> : <FontAwesomeIcon icon={faBars} />}
        </button>
        <nav className={`header-nav ${menuOpen ? 'header-nav-open' : ''}`}>
          {navLinks}
        </nav>
      </div>
    </header>
  )
}

export default Header