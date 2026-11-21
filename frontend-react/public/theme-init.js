// Aplica el tema antes del primer render para evitar el destello de tema claro.
// Vive en /public (en lugar de un script inline) porque la CSP de producción
// solo permite scripts del propio origen.
(function () {
  var theme;
  try {
    theme = window.localStorage.getItem("theme");
  } catch {
    // Almacenamiento bloqueado: se usa la preferencia del sistema.
  }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();