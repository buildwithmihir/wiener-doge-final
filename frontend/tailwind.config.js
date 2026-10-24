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
      keyframes: {
        'fade-up': { '0%': { opacity: '0', transform: 'translateY(8px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        'sheet-up': { '0%': { transform: 'translateY(100%)' }, '100%': { transform: 'translateY(0)' } },
        'fade-in': { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        'pop': { '0%': { transform: 'scale(0.6)', opacity: '0' }, '60%': { transform: 'scale(1.15)' }, '100%': { transform: 'scale(1)', opacity: '1' } },
        'pulse-ring': { '0%': { boxShadow: '0 0 0 0 rgba(79,140,255,0.45)' }, '100%': { boxShadow: '0 0 0 12px rgba(79,140,255,0)' } },
        'shimmer': { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
      },
      animation: {
        'fade-up': 'fade-up 0.32s cubic-bezier(0.22,1,0.36,1) both',
        'sheet-up': 'sheet-up 0.3s cubic-bezier(0.22,1,0.36,1) both',
        'fade-in': 'fade-in 0.2s ease-out both',
        'pop': 'pop 0.28s cubic-bezier(0.34,1.56,0.64,1) both',
        'pulse-ring': 'pulse-ring 0.6s ease-out',
        'shimmer': 'shimmer 2.4s linear infinite',
      },
      boxShadow: {
        'glow-blue': '0 0 26px rgba(79,140,255,0.55)',
        glow: '0 0 24px rgba(79,140,255,0.28)',
        'glow-up': '0 0 22px rgba(34,227,160,0.25)',
        'glow-down': '0 0 22px rgba(255,77,109,0.25)',
      },
    },
  },
  plugins: [],
}
