import { describe, expect, it } from "vitest";

import { getApiErrorMessage } from "../utils/errors";

describe("getApiErrorMessage", () => {
  it("prioritizes a backend detail message", () => {
    expect(
      getApiErrorMessage(
        { response: { status: 422, data: { detail: "El correo ya está registrado." } } },
        { action: "crear el empleado", resource: "empleados" },
      ),
    ).toBe("El correo ya está registrado.");
  });

  it("explains network failures with the attempted action", () => {
    expect(
      getApiErrorMessage(
        { code: "ERR_NETWORK" },
        { action: "cargar el ranking", resource: "ranking" },
      ),
    ).toContain("no hubo respuesta del servidor");
  });

  it("explains forbidden actions instead of returning a generic message", () => {
    expect(
      getApiErrorMessage(
        { response: { status: 403, data: {} } },
        { action: "consultar las calificaciones", resource: "Dirección" },
      ),
    ).toContain("no tiene permiso");
  });

  it("makes server errors explicit and warns that changes were not confirmed", () => {
    expect(
      getApiErrorMessage(
        { response: { status: 500, data: {} } },
        { action: "guardar la vacante", resource: "vacantes" },
      ),
    ).toContain("Tus cambios no se confirmaron");
  });
});
