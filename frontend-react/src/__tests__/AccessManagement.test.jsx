// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccessManagement from "../pages/AccessManagement";
import { suggestUsername } from "../utils/username";

vi.mock("../api/client", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

import api from "../api/client";

const EMPLOYEES = [
  {
    id: "emp-1",
    first_name: "Laura Estefany",
    last_name: "Villarraga Torres",
    email: "laura.villarraga@example.com",
    username: null,
    access_provisioned: false,
    roles: ["EMPLOYEE"],
    status: "ACTIVE",
  },
  {
    id: "emp-2",
    first_name: "Ana",
    last_name: "Pérez",
    email: "ana@example.com",
    username: "ana.perez",
    access_provisioned: true,
    roles: ["EMPLOYEE"],
    status: "ACTIVE",
  },
];

describe("AccessManagement credentials", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { items: EMPLOYEES } });
  });

  it("suggests a normalized nombre.apellido username", () => {
    expect(suggestUsername(EMPLOYEES[0])).toBe("laura.villarraga");
    expect(suggestUsername({ first_name: "José", last_name: "Núñez" })).toBe("jose.nunez");
  });

  it("offers generate credentials for profiles without access and reset for the rest", async () => {
    render(<AccessManagement />);

    expect(await screen.findByRole("button", { name: "Generar credenciales" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nueva contraseña" })).toBeInTheDocument();
  });

  it("generates credentials and shows the temporary password", async () => {
    api.post.mockResolvedValue({
      data: { credentials: { username: "laura.villarraga", temporary_password: "Temp#Pass123", must_change_password: true } },
    });
    render(<AccessManagement />);

    fireEvent.click(await screen.findByRole("button", { name: "Generar credenciales" }));
    expect(screen.getByLabelText("Usuario de Talent")).toHaveValue("laura.villarraga");
    fireEvent.click(screen.getAllByRole("button", { name: "Generar credenciales" }).at(-1));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/employees/emp-1/credentials/generate",
        { username: "laura.villarraga" },
      );
    });
    expect(await screen.findByDisplayValue("Temp#Pass123")).toBeInTheDocument();
  });
});
