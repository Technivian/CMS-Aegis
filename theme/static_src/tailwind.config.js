
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    '../templates/**/*.html',
    '../static/js/**/*.js',
    '../../contracts/templates/**/*.html'
  ],
  theme: {
    extend: {
      colors: {
        // Design System Colors
        bg: '#FFFFFF',
        ink: '#0B0B0C', 
        muted: '#6B7280',
        stroke: '#E5E7EB',
        accent: '#0E9F6E',
        warn: '#F59E0B', 
        danger: '#DC2626',
        card: '#FFFFFF',
        
        // Legacy aliases for existing code
        primary: {
          50: '#F0FDF4',
          500: '#0E9F6E',
          600: '#059669',
          700: '#047857'
        },
        gray: {
          50: '#F9FAFB',
          100: '#F3F4F6',
          200: '#E5E7EB',
          300: '#D1D5DB', 
          400: '#9CA3AF',
          500: '#6B7280',
          600: '#4B5563',
          700: '#374151',
          800: '#1F2937',
          900: '#0B0B0C'
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif']
      },
      fontSize: {
        // Design System Typography
        'base': ['14px', '16px'],
        'h2': ['24px', '28px'],
        'h1': ['32px', '36px']
      },
      fontWeight: {
        titles: '600',
        labels: '500'
      },
      spacing: {
        // 8px spacing scale
        '1': '8px',
        '2': '16px', 
        '3': '24px',
        '4': '32px',
        '5': '40px',
        '6': '48px',
        '8': '64px',
        '10': '80px',
        '12': '96px'
      },
      borderRadius: {
        DEFAULT: '6px',
        'lg': '8px',
        'xl': '12px'
      },
      maxWidth: {
        'content': '1200px'
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
        'elevated': '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)'
      }
    },
  },
  plugins: [],
}
