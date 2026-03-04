/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#09090b', // Void Black
        surface: '#18181b',    // Zinc 900
        border: '#27272a',     // Zinc 800
        'text-primary': '#e4e4e7', // Zinc 200
        'text-secondary': '#a1a1aa', // Zinc 400
        primary: '#ccff00',    // Acid Lime
        secondary: '#ff3366',  // Signal Red
        tertiary: '#00f0ff',   // Cyan
      },
      fontFamily: {
        sans: ['Space Grotesk', 'sans-serif'],
        mono: ['IBM Plex Mono', 'monospace'],
      },
      boxShadow: {
        'glow': '0 0 10px rgba(204, 255, 0, 0.5)',
      }
    },
  },
  plugins: [],
}
