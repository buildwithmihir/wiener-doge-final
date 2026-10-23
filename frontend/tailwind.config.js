/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#04061a', 900: '#070b24', 800: '#0b1236', 700: '#111a4a', 600: '#1b2766' },
        neon: { blue: '#4f8cff', violet: '#8b5cf6', cyan: '#38d6ff' },
        up: { DEFAULT: '#22e3a0', soft: 'rgba(34,227,160,0.14)' },
        down: { DEFAULT: '#ff4d6d', soft: 'rgba(255,77,109,0.14)' },
        gold: '#f5b942',
        silver: '#b8c4e6',
        bronze: '#e8924d',
        platinum: '#a78bfa',
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
      boxShadow: {
        glow: '0 0 24px rgba(79,140,255,0.28)',
        'glow-up': '0 0 22px rgba(34,227,160,0.25)',
        'glow-down': '0 0 22px rgba(255,77,109,0.25)',
      },
    },
  },
  plugins: [],
}
