/** Design tokens for this project — see docs/design-system.md for rationale. */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0F1530",        // primary text / sidebar background
        surface: "#F7F8FA",    // app background
        card: "#FFFFFF",
        muted: "#6B7280",
        signal: {
          DEFAULT: "#12B8A6",  // brand / accent teal
          dark: "#0E9488",
        },
        tier: {
          critical: "#E5484D",
          high: "#F2994A",
          medium: "#F2C94C",
          low: "#27AE60",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [],
}
