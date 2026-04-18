/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0a",
        card: "#1a1a1a",
        accent: "#00ff88",
      },
    },
  },
  plugins: [],
};
