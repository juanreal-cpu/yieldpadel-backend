/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "surface-container": "#1c1f2a",
        "tertiary": "#ffb873",
        "on-secondary-fixed-variant": "#005236",
        "tertiary-fixed": "#ffdcbf",
        "on-tertiary": "#4b2800",
        "on-tertiary-fixed-variant": "#6a3b00",
        "secondary-fixed-dim": "#4edea3",
        "on-tertiary-container": "#5b3200",
        "tertiary-fixed-dim": "#ffb873",
        "primary-fixed-dim": "#4cd7f6",
        "surface-tint": "#4cd7f6",
        "border-subtle": "#1E293B",
        "error-container": "#93000a",
        "outline": "#869397",
        "surface-dim": "#0f131d",
        "surface-container-highest": "#313540",
        "text-primary": "#FFFFFF",
        "status-warning": "#F59E0B",
        "text-muted": "#9CA3AF",
        "primary-fixed": "#acedff",
        "background": "#0f131d",
        "on-secondary-container": "#00311f",
        "on-tertiary-fixed": "#2d1600",
        "on-secondary-fixed": "#002113",
        "outline-variant": "#3d494c",
        "on-secondary": "#003824",
        "surface-bright": "#353944",
        "error": "#ffb4ab",
        "on-surface": "#dfe2f1",
        "surface-container-lowest": "#0a0e18",
        "secondary-container": "#00a572",
        "surface-container-high": "#262a35",
        "inverse-primary": "#00687a",
        "on-primary-container": "#00424f",
        "on-error": "#690005",
        "surface": "#0f131d",
        "surface-card": "#111827",
        "on-primary-fixed": "#001f26",
        "on-background": "#dfe2f1",
        "secondary-fixed": "#6ffbbe",
        "secondary": "#4edea3",
        "primary-container": "#06b6d4",
        "on-error-container": "#ffdad6",
        "on-primary": "#003640",
        "tertiary-container": "#e89337",
        "inverse-surface": "#dfe2f1",
        "surface-container-low": "#171b26",
        "surface-variant": "#313540",
        "inverse-on-surface": "#2c303b",
        "on-primary-fixed-variant": "#004e5c",
        "on-surface-variant": "#bcc9cd",
        "primary": "#4cd7f6"
      },
      borderRadius: {
        DEFAULT: "0.125rem",
        lg: "0.25rem",
        xl: "0.5rem",
        full: "0.75rem"
      },
      spacing: {
        "margin-mobile": "16px",
        gutter: "16px",
        "sidebar-width": "280px",
        "margin-desktop": "32px",
        unit: "4px"
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"]
      }
    }
  },
  plugins: [],
}