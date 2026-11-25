/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: "rgb(var(--accent) / <alpha-value>)",
        accent2: "rgb(var(--accent-2) / <alpha-value>)",
        ink: { 950: "#040206", 900: "#08050d", 800: "#100b18", 700: "#1a1326" },
      },
      fontFamily: { sans: ["Rubik", "Segoe UI Variable", "Segoe UI", "system-ui", "sans-serif"],
                    mono: ["Cascadia Code", "Consolas", "ui-monospace", "monospace"] },
      boxShadow: { glow: "0 0 24px rgb(var(--accent) / 0.35)", "glow-lg": "0 0 60px rgb(var(--accent) / 0.45)" },
    },
  },
  plugins: [],
};
