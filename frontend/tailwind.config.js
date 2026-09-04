/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          navy: '#061838',
          'navy-light': '#0c2759',
          'navy-dark': '#030c1e',
          slate: '#F8FAFC',
          border: '#E2E8F0',
          card: '#FFFFFF',
          muted: '#64748B',
          accent: '#0284C7',
        },
      },
    },
  },
  plugins: [],
};
