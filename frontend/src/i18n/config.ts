import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import enTranslations from './locales/en.json'
import zhTranslations from './locales/zh.json'

// Get saved language preference or default to 'en'
const getSavedLanguage = () => {
  if (typeof window !== 'undefined' && window.localStorage) {
    return localStorage.getItem('language') || 'en'
  }
  return 'en'
}

const savedLanguage = getSavedLanguage()

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        translation: enTranslations,
      },
      zh: {
        translation: zhTranslations,
      },
    },
    lng: savedLanguage,
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false,
    },
  })

export default i18n
