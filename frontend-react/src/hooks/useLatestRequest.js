import { useMemo, useRef } from "react";

/**
 * "La última solicitud gana": cada llamada a `begin()` invalida las anteriores
 * y devuelve `isCurrent()`, que solo es verdadero mientras no se haya iniciado
 * otra solicitud (o llamado `invalidate()`). Úsalo para descartar respuestas
 * tardías que pisarían datos más recientes (búsquedas, cambio de selección).
 */
export default function useLatestRequest() {
  const latestRef = useRef(0);

  return useMemo(() => ({
    begin() {
      latestRef.current += 1;
      const requestId = latestRef.current;
      return () => latestRef.current === requestId;
    },
    invalidate() {
      latestRef.current += 1;
    },
  }), []);
}
