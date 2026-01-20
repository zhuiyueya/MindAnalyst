import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'

const defaultLocale = 'zh-CN'
const savedLocale = typeof localStorage !== 'undefined' ? localStorage.getItem('lang') : null

export const i18n = createI18n({
  legacy: false,
  locale: savedLocale || defaultLocale,
  fallbackLocale: defaultLocale,
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS
  },
  globalInjection: true
})
