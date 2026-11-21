import { createContext, useContext, useState, useEffect } from "react";

const ThemeContext = createContext();

function readStoredTheme() {
  try {
    return window.localStorage.getItem("theme");
  } catch {
    // Almacenamiento bloqueado (modo privado, políticas del navegador).
    return null;
  }
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    const saved = readStoredTheme();
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("theme", theme);
    } catch {
      // Persistir el tema es opcional; no debe tumbar la app.
    }
  }, [theme]);

  function toggleTheme() {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
  return useContext(ThemeContext);
}
