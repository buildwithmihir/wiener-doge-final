// Set these in Vercel (Environment Variables), then redeploy:
//   VITE_SUPPORT_URL = https://t.me/<support username>
//   VITE_HELP_URL    = link of the help guide (falls back to the support link until it is set)
export const SUPPORT_URL = (import.meta.env.VITE_SUPPORT_URL as string | undefined) || 'https://t.me/YOUR_SUPPORT_USERNAME'
export const HELP_URL = (import.meta.env.VITE_HELP_URL as string | undefined) || SUPPORT_URL