import type { Config } from "tailwindcss";

/** Design system "soft professional" — los colores apuntan a las variables CSS
 *  definidas en app/globals.css, así el modo oscuro funciona automáticamente. */
const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-plex-mono)", "IBM Plex Mono", "ui-monospace", "monospace"],
      },
      colors: {
        brand: {
          50: "var(--brand-50)", 100: "var(--brand-100)", 200: "var(--brand-200)",
          300: "var(--brand-300)", 400: "var(--brand-400)", 500: "var(--brand-500)",
          600: "var(--brand-600)", 700: "var(--brand-700)", 800: "var(--brand-800)",
          900: "var(--brand-900)",
          DEFAULT: "var(--brand)",
        },
        canvas:  "var(--canvas)",
        surface: { DEFAULT: "var(--surface)", 2: "var(--surface-2)" },
        n: {
          100: "var(--n-100)", 200: "var(--n-200)", 300: "var(--n-300)",
          400: "var(--n-400)", 500: "var(--n-500)", 600: "var(--n-600)",
          700: "var(--n-700)", 900: "var(--n-900)",
        },
        // Legacy — se mantienen para clases Tailwind ya escritas en pantallas
        gray: {
          50: "var(--surface-2)", 100: "var(--n-100)", 200: "var(--n-200)",
          300: "var(--n-300)", 400: "var(--n-400)", 500: "var(--n-500)",
          600: "var(--n-600)", 700: "var(--n-700)", 800: "var(--n-700)",
          900: "var(--n-900)",
        },
        red: {
          100: "var(--st-rechazada-bg)", 400: "#c8623f",
          500: "var(--danger)", 600: "var(--danger)", 700: "#7a3220",
        },
        success: { DEFAULT: "var(--success)", light: "var(--success)", fill: "var(--st-aprobada-bg)" },
        warning: { DEFAULT: "var(--warning)", light: "var(--warning)", fill: "var(--st-cotizando-bg)" },
        danger:  { DEFAULT: "var(--danger)",  fill: "var(--st-rechazada-bg)" },
        info:    { DEFAULT: "var(--info)",    light: "var(--brand-500)", fill: "var(--st-encurso-bg)" },
      },
      spacing: {
        "0.5": "2px", "1": "4px", "2": "8px", "3": "12px", "4": "16px",
        "5": "20px", "6": "24px", "8": "32px", "10": "40px", "12": "48px",
        "16": "64px", "20": "80px", "24": "96px",
      },
      borderRadius: {
        none: "0px",
        sm:   "var(--r-sm)",
        md:   "var(--r-md)",
        lg:   "var(--r-lg)",
        xl:   "var(--r-xl)",
        pill: "var(--r-pill)",
      },
      fontSize: {
        "2xs":   ["11px", { lineHeight: "1.4" }],
        xs:      ["12px", { lineHeight: "1.5" }],
        sm:      ["13px", { lineHeight: "1.5" }],
        base:    ["15px", { lineHeight: "1.6" }],
        md:      ["15px", { lineHeight: "1.6" }],
        lg:      ["16px", { lineHeight: "1.5" }],
        xl:      ["20px", { lineHeight: "1.3" }],
        "2xl":   ["26px", { lineHeight: "1.2" }],
        "3xl":   ["34px", { lineHeight: "1.1" }],
        "4xl":   ["44px", { lineHeight: "1.05" }],
        "5xl":   ["56px", { lineHeight: "1.0" }],
        caption: ["12px", { lineHeight: "1.5" }],
        display: ["34px", { lineHeight: "1.1" }],
      },
      letterSpacing: {
        tighter: "-0.03em", tight: "-0.015em", normal: "0em",
        wide: "0.01em", wider: "0.02em", widest: "0.04em",
      },
      boxShadow: {
        card:  "var(--shadow-card)",
        pop:   "var(--shadow-pop)",
        modal: "var(--shadow-modal)",
      },
    },
  },
  plugins: [],
};

export default config;
