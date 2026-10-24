import animate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border) / 0.1)',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--foreground))' },
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: '#dbe4ff' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: '#ffffff' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--foreground))' },
        muted: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--muted-foreground))' },
        ink: { 950: '#050716', 900: '#090c24', 800: '#0e1233', 700: '#151a47', 600: '#212862' },
        neon: { blue: '#5b7cff', violet: '#8b5cf6', cyan: '#2ee6ff' },
        up: { DEFAULT: '#19e5a0', soft: 'rgba(25,229,160,0.14)' },
        down: { DEFAULT: '#ff5577', soft: 'rgba(255,85,119,0.14)' },
        gold: '#f5b942',
        silver: '#b8c4e6',
        bronze: '#e8924d',
        platinum: '#a78bfa',
      },
      fontFamily: {
        display: ['"Sora Variable"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['"Plus Jakarta Sans Variable"', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
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
        card: '0 10px 40px -12px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.05)',
        'glow-blue': '0 0 30px rgba(91,124,255,0.6)',
        glow: '0 0 24px rgba(91,124,255,0.35)',
        'glow-up': '0 0 22px rgba(34,227,160,0.25)',
        'glow-down': '0 0 22px rgba(255,77,109,0.25)',
      },
    },
  },
  plugins: [animate],
}
