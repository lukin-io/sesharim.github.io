/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./_layouts/**/*.html",
    "./_includes/**/*.html",
    "./_posts/**/*.md",
    "./*.html",
    "./blog.html",
    "./index.html",
    "./contacts.html",
    "./tools.html",
    "./services.html",
    "./projects.html",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        display: ['Space Grotesk', 'sans-serif'],
        mono: ['IBM Plex Mono', 'monospace'],
      },
      colors: {
        'palette': {
          'dark-brown': '#582f0e',
          'brown': '#7f4f24',
          'medium-brown': '#936639',
          'tan': '#a68a64',
          'light-tan': '#b6ad90',
          'sage': '#c2c5aa',
          'olive': '#a4ac86',
          'dark-olive': '#656d4a',
          'darker-olive': '#414833',
          'darkest': '#333d29',
        },
      },
    },
  },
  plugins: [],
}

