/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#f5f0e8",
          secondary: "#ede8df",
          card: "#ffffff",
          sidebar: "#e8e3da",
          terminal: "#f0ebe2",
        },
        text: {
          primary: "#1a1a1a",
          secondary: "#3d3d3d",
          muted: "#6b6b6b",
          dim: "#999999",
          terminal: "#2d2d2d",
          code: "#c96442",
        },
        accent: {
          primary: "#d97757",
          hover: "#c96442",
          dim: "#fce8e0",
          light: "#fdf3ee",
        },
        border: "#ddd8cf",
        status: {
          active: "#2d7a4f",
          idle: "#999999",
          stuck: "#c0392b",
          restarting: "#d97757",
        },
      },
    },
  },
  plugins: [],
};
