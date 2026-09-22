import type { Config } from "tailwindcss";

// Every color below resolves to a CSS custom property (`--color-*`, defined
// in `src/index.css` as an "R G B" triplet) instead of a literal hex value.
// This is what makes dark mode (`html.dark`, see `src/context/
// ThemeContext.tsx`) apply to the ENTIRE app without touching every
// className: the `.dark` block in index.css just re-assigns the same
// variable names to different values, and every `bg-primary`/`text-
// on-surface`/etc. utility picks up the new value automatically.
// `rgb(var(--color-x) / <alpha-value>)` (not plain `var(--color-x)`) is
// required for Tailwind's opacity modifiers (`bg-primary/10`) to keep
// working — Tailwind substitutes `<alpha-value>` itself.
function withOpacity(variable: string): string {
  return `rgb(var(${variable}) / <alpha-value>)`;
}

// Design tokens sourced verbatim from `desing/lavoro_esterno_core/DESIGN.md`
// (light values) so every mockup screen can be reproduced pixel-for-pixel;
// dark values live only in `src/index.css` (`html.dark`), not here.
const config: Config = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: withOpacity("--color-surface"),
        "surface-dim": withOpacity("--color-surface-dim"),
        "surface-bright": withOpacity("--color-surface-bright"),
        "surface-container-lowest": withOpacity("--color-surface-container-lowest"),
        "surface-container-low": withOpacity("--color-surface-container-low"),
        "surface-container": withOpacity("--color-surface-container"),
        "surface-container-high": withOpacity("--color-surface-container-high"),
        "surface-container-highest": withOpacity("--color-surface-container-highest"),
        "on-surface": withOpacity("--color-on-surface"),
        "on-surface-variant": withOpacity("--color-on-surface-variant"),
        "inverse-surface": withOpacity("--color-inverse-surface"),
        "inverse-on-surface": withOpacity("--color-inverse-on-surface"),
        outline: withOpacity("--color-outline"),
        "outline-variant": withOpacity("--color-outline-variant"),
        "surface-tint": withOpacity("--color-surface-tint"),
        primary: withOpacity("--color-primary"),
        "on-primary": withOpacity("--color-on-primary"),
        "primary-container": withOpacity("--color-primary-container"),
        "on-primary-container": withOpacity("--color-on-primary-container"),
        "inverse-primary": withOpacity("--color-inverse-primary"),
        secondary: withOpacity("--color-secondary"),
        "on-secondary": withOpacity("--color-on-secondary"),
        "secondary-container": withOpacity("--color-secondary-container"),
        "on-secondary-container": withOpacity("--color-on-secondary-container"),
        tertiary: withOpacity("--color-tertiary"),
        "on-tertiary": withOpacity("--color-on-tertiary"),
        "tertiary-container": withOpacity("--color-tertiary-container"),
        "on-tertiary-container": withOpacity("--color-on-tertiary-container"),
        error: withOpacity("--color-error"),
        "on-error": withOpacity("--color-on-error"),
        "error-container": withOpacity("--color-error-container"),
        "on-error-container": withOpacity("--color-on-error-container"),
        // "Fixed" roles: same value in light/dark by design, see index.css.
        "primary-fixed": withOpacity("--color-primary-fixed"),
        "primary-fixed-dim": withOpacity("--color-primary-fixed-dim"),
        "on-primary-fixed": withOpacity("--color-on-primary-fixed"),
        "on-primary-fixed-variant": withOpacity("--color-on-primary-fixed-variant"),
        "secondary-fixed": withOpacity("--color-secondary-fixed"),
        "secondary-fixed-dim": withOpacity("--color-secondary-fixed-dim"),
        "on-secondary-fixed": withOpacity("--color-on-secondary-fixed"),
        "on-secondary-fixed-variant": withOpacity("--color-on-secondary-fixed-variant"),
        "tertiary-fixed": withOpacity("--color-tertiary-fixed"),
        "tertiary-fixed-dim": withOpacity("--color-tertiary-fixed-dim"),
        "on-tertiary-fixed": withOpacity("--color-on-tertiary-fixed"),
        "on-tertiary-fixed-variant": withOpacity("--color-on-tertiary-fixed-variant"),
        background: withOpacity("--color-background"),
        "on-background": withOpacity("--color-on-background"),
        "surface-variant": withOpacity("--color-surface-variant"),
        success: withOpacity("--color-success"),
        info: withOpacity("--color-info"),
        warning: withOpacity("--color-warning"),
        muted: withOpacity("--color-muted"),
        border: withOpacity("--color-border"),
      },
      borderRadius: {
        sm: "0.125rem",
        DEFAULT: "0.25rem",
        md: "0.375rem",
        lg: "0.5rem",
        xl: "0.75rem",
        full: "9999px",
      },
      spacing: {
        base: "4px",
        gutter: "16px",
        "margin-page": "24px",
        "sidebar-width": "260px",
        "sidebar-collapsed": "64px",
        "topbar-height": "56px",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      fontSize: {
        "headline-lg": ["30px", { lineHeight: "36px", letterSpacing: "-0.02em", fontWeight: "600" }],
        "headline-md": ["24px", { lineHeight: "32px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "headline-sm": ["18px", { lineHeight: "28px", fontWeight: "600" }],
        "body-lg": ["16px", { lineHeight: "24px", fontWeight: "400" }],
        "body-md": ["14px", { lineHeight: "20px", fontWeight: "400" }],
        "label-sm": ["12px", { lineHeight: "16px", letterSpacing: "0.02em", fontWeight: "500" }],
        "mono-data": ["13px", { lineHeight: "18px", fontWeight: "400" }],
      },
    },
  },
  plugins: [],
};

export default config;
