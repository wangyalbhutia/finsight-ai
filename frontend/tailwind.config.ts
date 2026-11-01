import type { Config } from "tailwindcss";
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: { extend: {
    fontFamily: { sans: ["var(--font-inter)","system-ui","sans-serif"] },
    colors: { border: "hsl(var(--border))", background: "hsl(var(--background))", foreground: "hsl(var(--foreground))", card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" }, primary: { DEFAULT: "#0f766e", foreground: "#ffffff" }, muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" } },
    borderRadius: { lg: "1rem", xl: "1.25rem" }
  }},
  plugins: []
};
export default config;
