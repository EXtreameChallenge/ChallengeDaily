/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // ─── 全部通过 CSS 变量支持深色模式 ───
        'cd-bg': 'var(--cd-bg)',
        'cd-bg-secondary': 'var(--cd-bg-secondary)',
        'cd-bg-tertiary': 'var(--cd-bg-tertiary)',
        'cd-sidebar': 'var(--cd-sidebar)',
        'cd-border': 'var(--cd-border)',
        'cd-border-light': 'var(--cd-border-light)',
        'cd-text': 'var(--cd-text)',
        'cd-text-secondary': 'var(--cd-text-secondary)',
        'cd-text-tertiary': 'var(--cd-text-tertiary)',
        'cd-green': 'var(--cd-green)',
        'cd-green-light': 'var(--cd-green-light)',
        'cd-green-dark': 'var(--cd-green-dark)',
        'cd-blue': 'var(--cd-blue)',
        'cd-blue-light': 'var(--cd-blue-light)',
        'cd-orange': 'var(--cd-orange)',
        'cd-orange-light': 'var(--cd-orange-light)',
        'cd-red': 'var(--cd-red)',
        'cd-red-light': 'var(--cd-red-light)',
        'cd-purple': 'var(--cd-purple)',
        'cd-purple-light': 'var(--cd-purple-light)',
        'cd-yellow': 'var(--cd-yellow)',
        'cd-gold': 'var(--cd-gold)',
        'cd-card': 'var(--cd-card)',
        'cd-bg-card': 'color-mix(in srgb, var(--cd-card) calc(<alpha-value> * 100%), transparent)',
        'cd-bg-input': 'color-mix(in srgb, var(--cd-bg-input) calc(<alpha-value> * 100%), transparent)',
        'cd-accent': 'color-mix(in srgb, var(--cd-green) calc(<alpha-value> * 100%), transparent)',
        'gold': 'color-mix(in srgb, var(--cd-gold) calc(<alpha-value> * 100%), transparent)',
        'cd-hover': 'var(--cd-hover)',
        'cd-selected': 'var(--cd-selected)',
        'cd-scrollbar': 'var(--cd-scrollbar)',
        'cd-scrollbar-hover': 'var(--cd-scrollbar-hover)',
      },
      fontFamily: {
        sans: ['"Fraunces"', '"FZQingKeBenYueSong"', '"Microsoft YaHei"', '"PingFang SC"', 'ui-serif', 'serif'],
        display: ['"Fraunces"', '"FZQingKeBenYueSong"', '"Microsoft YaHei"', 'ui-serif', 'serif'],
        brand: ['"Fraunces"', '"FZQingKeBenYueSong"', '"Microsoft YaHei"', '"PingFang SC"', 'ui-serif', 'serif'],
        serif: ['"Fraunces"', '"FZQingKeBenYueSong"', '"Microsoft YaHei"', 'ui-serif', 'serif'],
        mono: ['"Anthropic Mono"', '"JetBrains Mono"', '"Fira Code"', 'Consolas', 'monospace'],
      },
      borderRadius: {
        'xl2': '12px',
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
