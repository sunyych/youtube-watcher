import './LanguageSelector.css'

interface LanguageSelectorProps {
  value?: string
  onChange: (language: string) => void
}

const languages = [
  { code: '', name: '自动检测' },
  { code: 'zh', name: '中文' },
  { code: 'en', name: 'English' },
  { code: 'ja', name: '日本語' },
  { code: 'ko', name: '한국어' },
  { code: 'es', name: 'Español' },
  { code: 'fr', name: 'Français' },
  { code: 'de', name: 'Deutsch' },
  { code: 'ru', name: 'Русский' },
]

const LanguageSelector: React.FC<LanguageSelectorProps> = ({ value = '', onChange }) => {
  return (
    <select
      className="language-selector"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {languages.map((lang) => (
        <option key={lang.code} value={lang.code}>
          {lang.name}
        </option>
      ))}
    </select>
  )
}

export default LanguageSelector
