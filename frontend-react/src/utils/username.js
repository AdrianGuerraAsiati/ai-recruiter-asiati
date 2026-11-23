function words(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
}

// Sugiere "nombre.apellido" a partir del perfil; el administrador puede cambiarlo.
export function suggestUsername(employee = {}) {
  const first = words(employee.first_name)[0];
  const last = words(employee.last_name)[0];
  let candidate = [first, last].filter(Boolean).join(".");
  if (!first || !last) {
    const fallback = [employee.first_name, employee.last_name].filter(Boolean).join(" ")
      || String(employee.email || "").split("@")[0];
    candidate = words(fallback).slice(0, 2).join(".");
  }
  return candidate.replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, "").slice(0, 40);
}
