import { useTheme } from "../context/ThemeContext";
import Icon from "./ui/Icon";

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      className="theme-toggle"
      type="button"
      onClick={toggleTheme}
      aria-label={theme === "light" ? "Cambiar a modo oscuro" : "Cambiar a modo claro"}
      title={theme === "light" ? "Modo oscuro" : "Modo claro"}
    >
      <span className="theme-toggle-icon" aria-hidden="true">
        <Icon name={theme === "light" ? "moon" : "sun"} size={18} />
      </span>
    </button>
  );
}

export default ThemeToggle;
