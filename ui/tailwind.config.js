/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#1a1a1a",
          secondary: "#222222",
          card: "#2a2a2a",
        },
        text: {
          primary: "#f0ece3",
          muted: "#888888",
          dim: "#555555",
        },
        accent: {
          primary: "#d97757",
          hover: "#c96442",
          dim: "#3d2218",
        },
        border: "#333333",
        status: {
          active: "#4caf7d",
          idle: "#888888",
          stuck: "#e05252",
          restarting: "#d97757",
        },
      },
    },
  },
  plugins: [],
};
