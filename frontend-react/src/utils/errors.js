function normalizeDetail(detail) {
  if (!detail) return "";

  if (typeof detail === "string") return detail.trim();

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item.trim();
        if (item && typeof item === "object") {
          const location = Array.isArray(item.loc) ? item.loc.filter(Boolean).join(" → ") : "";
          const message = String(item.msg || item.message || "").trim();
          if (location && message) return `${location}: ${message}`;
          return message;
        }
        return "";
      })
      .filter(Boolean);
    return messages.join(" · ");
  }

  if (typeof detail === "object") {
    return String(detail.message || detail.error || "").trim();
  }

  return "";
}

function statusMessage(status, action, resource) {
  const target = resource ? ` de ${resource}` : "";

  if (status === 400) {
    return `La solicitud para ${action}${target} contiene datos que el servidor no puede procesar. Revisa los campos e inténtalo de nuevo.`;
  }
  if (status === 401) {
    return `Tu sesión venció mientras intentábamos ${action}${target}. Inicia sesión de nuevo para continuar.`;
  }
  if (status === 403) {
    return `Tu usuario no tiene permiso para ${action}${target}. Si necesitas realizar esta acción, solicita el acceso correspondiente.`;
  }
  if (status === 404) {
    return `No encontramos ${resource || "el recurso solicitado"}. Puede haber sido eliminado o actualizado por otro usuario. Recarga la vista y vuelve a intentarlo.`;
  }
  if (status === 409) {
    return `No se puede ${action}${target} porque su estado cambió o existe un conflicto con otra operación. Recarga la información antes de reintentar.`;
  }
  if (status === 413) {
    return `El archivo o contenido enviado para ${action}${target} supera el tamaño permitido. Reduce su tamaño y vuelve a intentarlo.`;
  }
  if (status === 422) {
    return `Hay datos inválidos para ${action}${target}. Revisa los campos marcados y corrige sus valores.`;
  }
  if (status === 429) {
    return `Se alcanzó temporalmente el límite de solicitudes al intentar ${action}${target}. Espera un momento y vuelve a intentarlo.`;
  }
  if (status >= 500) {
    return `El servicio encargado de ${action}${target} respondió con un error interno. Tus cambios no se confirmaron; vuelve a intentarlo y, si persiste, repórtalo indicando esta acción.`;
  }

  return "";
}

export function getApiErrorMessage(
  error,
  {
    action = "completar la operación",
    resource = "",
    fallback = "",
    statusMessages = {},
  } = {},
) {
  const detail = normalizeDetail(
    error?.response?.data?.detail
      ?? error?.response?.data?.error
      ?? error?.response?.data?.message,
  );

  if (detail) return detail;

  if (error?.code === "ERR_CANCELED") return "";

  if (!error?.response) {
    return `No se pudo ${action}${resource ? ` de ${resource}` : ""} porque no hubo respuesta del servidor. Comprueba tu conexión y vuelve a intentarlo.`;
  }

  const status = Number(error.response.status || 0);
  const custom = statusMessages?.[status];
  if (typeof custom === "function") return custom(error);
  if (typeof custom === "string" && custom.trim()) return custom.trim();

  const byStatus = statusMessage(status, action, resource);
  if (byStatus) return byStatus;

  if (fallback) return fallback;

  return `No se pudo ${action}${resource ? ` de ${resource}` : ""}. El servidor respondió con un estado inesperado${status ? ` (${status})` : ""}; vuelve a intentarlo.`;
}

export default getApiErrorMessage;
