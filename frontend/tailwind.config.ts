import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ["IBM Plex Mono", "Courier New", "monospace"],
        sans: ["IBM Plex Mono", "Courier New", "monospace"],
      },
      colors: {
        bg: {
          primary:   "#060610",
          secondary: "#0a0a18",
          card:      "#0d0d1a",
          border:    "#1a1a2e",
        },
        stark: {
          base:    "#ffffff",
          surface: "#f5f5f5",
          inverse: "#0d0d0d",
        },
        warm: {
          base:    "#f4f0e8",
          surface: "#ece8df",
          inverse: "#1a1410",
        },
        gray: {
          900: "#1a1a1a",
          800: "#2e2e2e",
          700: "#484848",
          600: "#606060",
          500: "#7a7a7a",
          400: "#9a9a9a",
          300: "#c0c0c0",
          200: "#d8d8d8",
          100: "#ebebeb",
          50:  "#f5f5f5",
        },
        red: {
          700: "#7a1e14",
          600: "#9e2618",
          500: "#c0392b",
          400: "#d4503f",
          100: "#fce8e6",
          50:  "#fef4f3",
        },
        success: {
          DEFAULT: "#1a6e45",
          light:   "#21894f",
          fill:    "#e6f4ec",
        },
        warning: {
          DEFAULT: "#92400e",
          light:   "#b45309",
          fill:    "#fef3c7",
        },
        info: {
          DEFAULT: "#1e40af",
          light:   "#2563eb",
          fill:    "#dbeafe",
        },
      },
      spacing: {
        "0.5": "2px",
        "1":   "4px",
        "2":   "8px",
        "3":   "12px",
        "4":   "16px",
        "5":   "20px",
        "6":   "24px",
        "8":   "32px",
        "10":  "40px",
        "12":  "48px",
        "16":  "64px",
        "20":  "80px",
        "24":  "96px",
      },
      borderRadius: {
        none: "0px",
        sm:   "2px",
        md:   "4px",
      },
      fontSize: {
        "2xs": ["9px",  { lineHeight: "1.4" }],
        "xs":  ["10px", { lineHeight: "1.4", letterSpacing: "0.2em" }],
        "sm":  ["11px", { lineHeight: "1.5" }],
        "base":["12px", { lineHeight: "1.6" }],
        "md":  ["13px", { lineHeight: "1.55" }],
        "lg":  ["16px", { lineHeight: "1.35" }],
        "xl":  ["20px", { lineHeight: "1.2" }],
        "2xl": ["28px", { lineHeight: "1.1" }],
        "3xl": ["36px", { lineHeight: "1.1" }],
        "4xl": ["48px", { lineHeight: "1.0" }],
        "5xl": ["64px", { lineHeight: "1.0" }],
      },
      letterSpacing: {
        tighter: "-0.04em",
        tight:   "-0.02em",
        normal:  "0em",
        wide:    "0.06em",
        wider:   "0.12em",
        widest:  "0.20em",
      },
    },
  },
  plugins: [],
};

export default config;
