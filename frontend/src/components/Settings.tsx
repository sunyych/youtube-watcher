import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n/config'
import Header from './Header'
import { authApi } from '../services/api'
import './Settings.css'

interface SettingsProps {
  onLogout: () => void
}

type Theme = 'light' | 'dark'

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  localStorage.setItem('theme', theme)
}

const SUMMARY_LANGUAGE_OPTIONS = [
  { value: '中文', labelKey: 'settings.summaryLanguage.chinese' },
  { value: 'English', labelKey: 'settings.summaryLanguage.english' },
]

const Settings: React.FC<SettingsProps> = ({ onLogout }) => {
  const { t } = useTranslation()
  const [theme, setTheme] = useState<Theme>('light')
  const [summaryLanguage, setSummaryLanguage] = useState<string>('中文')
  const [summaryLanguageSaving, setSummaryLanguageSaving] = useState(false)
  const [summaryLanguageSaved, setSummaryLanguageSaved] = useState(false)
  const [showFeedbackButton, setShowFeedbackButton] = useState(true)
  const [feedbackButtonSaving, setFeedbackButtonSaving] = useState(false)
  const [feedbackButtonSaved, setFeedbackButtonSaved] = useState(false)

  useEffect(() => {
    const savedTheme = (localStorage.getItem('theme') as Theme | null) ?? 'light'
    const normalized = savedTheme === 'dark' ? 'dark' : 'light'
    setTheme(normalized)
    applyTheme(normalized)
  }, [])

  useEffect(() => {
    authApi.getProfile().then((profile) => {
      setSummaryLanguage(profile.summary_language || '中文')
      setShowFeedbackButton(profile.show_feedback_button ?? true)
    }).catch(() => {
      setSummaryLanguage('中文')
      setShowFeedbackButton(true)
    })
  }, [])

  const handleLanguageChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newLanguage = e.target.value
    i18n.changeLanguage(newLanguage)
    localStorage.setItem('language', newLanguage)
  }

  const handleThemeToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextTheme: Theme = e.target.checked ? 'dark' : 'light'
    setTheme(nextTheme)
    applyTheme(nextTheme)
  }

  const handleSummaryLanguageChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newLang = e.target.value
    setSummaryLanguage(newLang)
    setSummaryLanguageSaving(true)
    setSummaryLanguageSaved(false)
    try {
      await authApi.updateSummaryLanguage(newLang)
      setSummaryLanguageSaved(true)
      setTimeout(() => setSummaryLanguageSaved(false), 2000)
    } catch {
      setSummaryLanguage(summaryLanguage)
    } finally {
      setSummaryLanguageSaving(false)
    }
  }

  const handleFeedbackButtonToggle = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.checked
    setShowFeedbackButton(next)
    setFeedbackButtonSaving(true)
    setFeedbackButtonSaved(false)
    try {
      await authApi.updateFeedbackButton(next)
      setFeedbackButtonSaved(true)
      setTimeout(() => setFeedbackButtonSaved(false), 2000)
    } catch {
      setShowFeedbackButton(!next)
    } finally {
      setFeedbackButtonSaving(false)
    }
  }

  return (
    <div className="settings-page page-with-header">
      <Header title={t('settings.title')} onLogout={onLogout} />

      <div className="settings-content">
        <div className="settings-section">
          <h2>{t('settings.theme.title')}</h2>
          <p className="settings-note">{t('settings.theme.description')}</p>
          <label className="theme-toggle">
            <span className="theme-toggle-label">{t('settings.theme.dark')}</span>
            <input
              type="checkbox"
              checked={theme === 'dark'}
              onChange={handleThemeToggle}
              aria-label={t('settings.theme.title')}
            />
            <span className="theme-toggle-switch" aria-hidden="true" />
          </label>
        </div>

        <div className="settings-section">
          <h2>{t('settings.extension.title')}</h2>
          <p className="settings-note">{t('settings.extension.note')}</p>
          <a className="download-link" href="/chrome-extension.crx" download>
            {t('settings.extension.download')}
          </a>
        </div>

        <div className="settings-section">
          <h2>{t('settings.language.title')}</h2>
          <p className="settings-note">{t('settings.language.description')}</p>
          <select
            value={i18n.language}
            onChange={handleLanguageChange}
            className="language-select"
            aria-label={t('settings.language.title')}
          >
            <option value="en">{t('settings.language.english')}</option>
            <option value="zh">{t('settings.language.chinese')}</option>
          </select>
        </div>

        <div className="settings-section">
          <h2>{t('settings.summaryLanguage.title')}</h2>
          <p className="settings-note">{t('settings.summaryLanguage.description')}</p>
          <select
            value={summaryLanguage}
            onChange={handleSummaryLanguageChange}
            className="language-select"
            disabled={summaryLanguageSaving}
            aria-label={t('settings.summaryLanguage.title')}
          >
            {SUMMARY_LANGUAGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.labelKey)}
              </option>
            ))}
          </select>
          {summaryLanguageSaving && (
            <span className="settings-inline-note">{t('settings.summaryLanguage.saving')}</span>
          )}
          {summaryLanguageSaved && (
            <span className="settings-inline-note settings-saved">{t('settings.summaryLanguage.saved')}</span>
          )}
        </div>

        <div className="settings-section">
          <h2>{t('settings.feedbackButton.title')}</h2>
          <p className="settings-note">{t('settings.feedbackButton.description')}</p>
          <label className="theme-toggle">
            <span className="theme-toggle-label">{t('settings.feedbackButton.label')}</span>
            <input
              type="checkbox"
              checked={showFeedbackButton}
              onChange={handleFeedbackButtonToggle}
              disabled={feedbackButtonSaving}
              aria-label={t('settings.feedbackButton.title')}
            />
            <span className="theme-toggle-switch" aria-hidden="true" />
          </label>
          {feedbackButtonSaving && (
            <span className="settings-inline-note">{t('settings.summaryLanguage.saving')}</span>
          )}
          {feedbackButtonSaved && (
            <span className="settings-inline-note settings-saved">{t('settings.summaryLanguage.saved')}</span>
          )}
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
