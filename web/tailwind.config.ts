import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        leaf: "#6ee7a0", // primary / healthy / accent
        blueprint: "#7ac8ff", // secondary / data / chart lines
        ink: {
          950: "#0a0f14", // page ground
          900: "#0c1116", // app background
          850: "#0d141b", // hero / panel
          800: "#121a22", // card background
          700: "#1b2733", // elevated / borders
        },
      },
      fontFamily: {
        sans: ['"Hanken Grotesk Variable"', "system-ui", "sans-serif"],
        serif: ["Spectral", "Georgia", "serif"],
        mono: ['"Geist Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
