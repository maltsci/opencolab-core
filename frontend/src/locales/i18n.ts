import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import enUS from './en-US.json';
import zhCN from './zh-CN.json';

const SUPPORTED_LANGUAGES = ['en-US', 'zh-CN'] as const;

function resolveInitialLanguage() {
  const savedLanguage = localStorage.getItem('lang');
  if (savedLanguage && SUPPORTED_LANGUAGES.includes(savedLanguage as (typeof SUPPORTED_LANGUAGES)[number])) {
    return savedLanguage;
  }

  const browserLanguage = navigator.language.toLowerCase();
  if (browserLanguage.startsWith('zh')) {
    return 'zh-CN';
  }

  return 'en-US';
}

i18n.use(initReactI18next).init({
  resources: {
    'en-US': { translation: enUS },
    'zh-CN': { translation: zhCN },
  },
  lng: resolveInitialLanguage(),
  fallbackLng: 'en-US',
  interpolation: { escapeValue: false },
});

export default i18n;
