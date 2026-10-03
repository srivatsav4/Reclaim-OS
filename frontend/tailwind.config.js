export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { ink: { 950: "#05080F", 900: "#080D16", 800: "#0C1320", 700: "#121B2C" }, accent: { DEFAULT: "#22D3EE", dim: "#0E7490" } },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
                    mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"] },
    },
  },
  plugins: [],
};
