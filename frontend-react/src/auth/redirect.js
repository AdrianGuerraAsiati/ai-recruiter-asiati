const DEFAULT_AFTER_LOGIN = "/dashboard";

// Solo se permite volver a rutas internas de la app (evita redirecciones
// abiertas tipo "//evil.example" o "/\\evil.example").
export function resolvePostLoginPath(from) {
  const path = typeof from === "string"
    ? from
    : from && typeof from === "object"
      ? `${from.pathname || ""}${from.search || ""}${from.hash || ""}`
      : "";
  if (!path.startsWith("/") || path.startsWith("//") || path.startsWith("/\\")) {
    return DEFAULT_AFTER_LOGIN;
  }
  if (path === "/" || path === "/login" || path.startsWith("/login?") || path.startsWith("/register")) {
    return DEFAULT_AFTER_LOGIN;
  }
  return path;
}
