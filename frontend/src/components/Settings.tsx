import { useTranslation } from 'react-i18next'
import i18n from '../i18n/config'
import Header from './Header'
import './Settings.css'

interface SettingsProps {
  onLogout: () => void
}

const Settings: React.FC<SettingsProps> = ({ onLogout }) => {
  const { t } = useTranslation()

  const handleLanguageChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newLanguage = e.target.value
    i18n.changeLanguage(newLanguage)
    localStorage.setItem('language', newLanguage)
  }

  return (
    <div className="settings-page page-with-header">
      <Header title={t('settings.title')} onLogout={onLogout} />

      <div className="settings-content">
        <div className="settings-section">
          <h2>{t('settings.language.title')}</h2>
          <p className="settings-note">{t('settings.language.description')}</p>
          <select
            value={i18n.language}
            onChange={handleLanguageChange}
            className="language-select"
          >
            <option value="en">{t('settings.language.english')}</option>
            <option value="zh">{t('settings.language.chinese')}</option>
          </select>
        </div>

        <div className="settings-section">
          <h2>{t('settings.password.title')}</h2>
          <p className="settings-note">
            {t('settings.password.note')}
          </p>
        </div>

        <div className="settings-section">
          <h2>{t('settings.llm.title')}</h2>
          <p className="settings-note">
            {t('settings.llm.note')}
            <ul>
              <li>{t('settings.llm.items.ollamaUrl')}</li>
              <li>{t('settings.llm.items.vllmUrl')}</li>
              <li>{t('settings.llm.items.llmModel')}</li>
            </ul>
          </p>
        </div>

        <div className="settings-section">
          <h2>{t('settings.hardware.title')}</h2>
          <p className="settings-note">
            {t('settings.hardware.note')}
          </p>
        </div>
      </div>
    </div>
  )
}

export default Settings
