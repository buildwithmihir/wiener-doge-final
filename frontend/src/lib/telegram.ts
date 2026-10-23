// Thin, safe wrapper around the Telegram Mini App SDK (window.Telegram.WebApp).
// Outside Telegram (a normal browser) every call is a harmless no-op.

interface TelegramWebApp {
  initData: string
  ready(): void
  expand(): void
  close(): void
  setHeaderColor?(color: string): void
  setBackgroundColor?(color: string): void
  disableVerticalSwipes?(): void
  HapticFeedback?: { impactOccurred(style: 'light' | 'medium' | 'heavy'): void; notificationOccurred(type: 'success' | 'error' | 'warning'): void }
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

const THEME = '#04061a'

export function getWebApp(): TelegramWebApp | undefined {
  return typeof window === 'undefined' ? undefined : window.Telegram?.WebApp
}

/** The signed login data. Empty when the page is not opened from Telegram. */
export function getInitData(): string {
  return getWebApp()?.initData ?? ''
}

export function initTelegram(): void {
  const app = getWebApp()
  if (!app) return
  app.ready()
  app.expand()
  app.disableVerticalSwipes?.()
  app.setHeaderColor?.(THEME)
  app.setBackgroundColor?.(THEME)
}

export function haptic(kind: 'light' | 'success' | 'error'): void {
  const feedback = getWebApp()?.HapticFeedback
  if (!feedback) return
  if (kind === 'light') feedback.impactOccurred('light')
  else feedback.notificationOccurred(kind)
}
