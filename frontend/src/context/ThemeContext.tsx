import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

// Kept in sync with the inline script in index.html, which applies the
// persisted/system theme before first paint to avoid a flash of the wrong
// theme — that script reads the SAME storage key.
const STORAGE_KEY = "lavoro_esterno_theme";

export type ThemePreference = "light" | "dark" | "system";

interface ThemeContextValue {
  // What the user picked (persisted). "system" means "follow the OS".
  preference: ThemePreference;
  // What's actually rendered right now (never "system" — always resolved).
  resolvedTheme: "light" | "dark";
  setPreference: (preference: ThemePreference) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function resolve(preference: ThemePreference): "light" | "dark" {
  return preference === "system" ? (systemPrefersDark() ? "dark" : "light") : preference;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  });

  const resolvedTheme = useMemo(() => resolve(preference), [preference]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolvedTheme === "dark");
  }, [resolvedTheme]);

  // Only relevant when preference === "system": re-resolve if the OS theme
  // changes while the app is open (e.g. sunset-triggered OS dark mode).
  useEffect(() => {
    if (preference !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      document.documentElement.classList.toggle("dark", systemPrefersDark());
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  function setPreference(next: ThemePreference) {
    setPreferenceState(next);
    if (next === "system") {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, next);
    }
  }

  // The toggle button only ever switches between light/dark (not "system")
  // — flips relative to what's currently rendered, so it does something
  // sensible even when the current preference is "system".
  function toggle() {
    setPreference(resolvedTheme === "dark" ? "light" : "dark");
  }

  return (
    <ThemeContext.Provider value={{ preference, resolvedTheme, setPreference, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
