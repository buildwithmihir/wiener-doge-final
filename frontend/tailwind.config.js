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
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: '#e6f0ff' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: '#ffffff' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--foreground))' },
        muted: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--muted-foreground))' },
        // black scale (names kept so existing components keep working)
        ink: { 950: '#000000', 900: '#0a0a0a', 800: '#111111', 700: '#1a1a1a', 600: '#262626' },
        // "neon" names kept, but now blue / cyan (no more purple)
        neon: { blue: '#3b82f6', violet: '#0ea5e9', cyan: '#22d3ee' },
        up: { DEFAULT: '#19e5a0', soft: 'rgba(25,229,160,0.14)' },
        down: { DEFAULT: '#ff5577', soft: 'rgba(255,85,119,0.14)' },
        gold: '#f5b942',
        silver: '#c7ccd9',
        bronze: '#e8924d',
        platinum: '#67e8f9',
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
        'pulse-ring': { '0%': { boxShadow: '0 0 0 0 rgba(59,130,246,0.45)' }, '100%': { boxShadow: '0 0 0 12px rgba(59,130,246,0)' } },
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
        card: '0 10px 40px -12px rgba(0,0,0,0.9), inset 0 1px 0 rgba(255,255,255,0.06)',
        'glow-blue': '0 0 30px rgba(59,130,246,0.55)',
        glow: '0 0 24px rgba(59,130,246,0.3)',
        'glow-up': '0 0 22px rgba(34,227,160,0.25)',
        'glow-down': '0 0 22px rgba(255,77,109,0.25)',
      },
    },
  },
  plugins: [animate],
}