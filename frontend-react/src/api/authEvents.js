// Evento global que avisa que la sesión venció y no pudo renovarse.
// El cliente HTTP lo emite; SessionProvider lo escucha y limpia la sesión para
// que las rutas protegidas redirijan a Login conservando la ruta de origen.
export const AUTH_EXPIRED_EVENT = "auth:expired";

export function emitAuthExpired(detail = {}) {
  if (typeof window === "undefined" || typeof window.dispatchEvent !== "function") return;
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail }));
}

export function onAuthExpired(handler) {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(AUTH_EXPIRED_EVENT, handler);
  return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
}
