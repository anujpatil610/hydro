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
          900: "#0c1116", // app background
          800: "#121a22", // card background
          700: "#1b2733", // elevated / borders
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
