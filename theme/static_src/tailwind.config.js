
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    '../templates/**/*.html',
    './src/**/*.css',
    '../../contracts/templates/**/*.html',
  ],
  theme: {
    extend: {
      colors: {
        // Design system colors
        bg: '#FFFFFF',
        ink: '#0B0B0C',
        muted: '#6B7280',
        stroke: '#E5E7EB',
        accent: '#0E9F6E',
        warn: '#F59E0B',
        danger: '#DC2626',
        card: '#FFFFFF',
        
        // Semantic colors
        primary: '#0E9F6E',
        secondary: '#6B7280',
        success: '#10B981',
        warning: '#F59E0B',
        error: '#DC2626',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        'base': ['14px', '16px'],
        'h1': ['32px', '36px'],
        'h2': ['24px', '28px'],
      },
      fontWeight: {
        'titles': '600',
        'labels': '500',
      },
      maxWidth: {
        'content': '1200px',
      },
      spacing: {
        '0.5': '4px',
        '1': '8px',
        '1.5': '12px',
        '2': '16px',
        '3': '24px',
        '4': '32px',
        '5': '40px',
        '6': '48px',
        '8': '64px',
        '10': '80px',
        '12': '96px',
        '16': '128px',
        '20': '160px',
        '24': '192px',
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
        'elevated': '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
      },
    },
  },
  plugins: [],
};
