// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AttendanceSettings from "../pages/TalentId";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from "../api/client";


function mockCatalogs() {
  api.get.mockImplementation((url) => {
    if (url === "/talent-id/sites") {
      return Promise.resolve({
        data: {
          items: [{
            id: "site-1",
            name: "Bogotá Principal",
            code: "BOG",
            timezone: "America/Bogota",
            active: true,
          }],
        },
      });
    }
    if (url === "/talent-id/schedules") {
      return Promise.resolve({
        data: {
          items: [{
            id: "schedule-1",
            name: "Administrativo",
            start_time: "08:30:00",
            end_time: "18:00:00",
            tolerance_minutes: 10,
            active: true,
          }],
        },
      });
    }
    return Promise.reject(new Error(`Unexpected GET ${url}`));
  });
}


describe("Attendance settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCatalogs();
  });

  it("shows only site and schedule configuration for fingerprint reports", async () => {
    render(<AttendanceSettings />);

    expect(await screen.findByRole("heading", { name: "Sedes y horarios" })).toBeInTheDocument();
    expect(await screen.findByText("Bogotá Principal")).toBeInTheDocument();
    expect(await screen.findByText("Administrativo")).toBeInTheDocument();
    expect(screen.getByText(/reconocimiento facial y QR móvil están suspendidos/i)).toBeInTheDocument();

    expect(screen.queryByText("Fotos para reconocimiento facial")).not.toBeInTheDocument();
    expect(screen.queryByText("Credenciales de kioscos")).not.toBeInTheDocument();
  });

  it("creates a site used to associate fingerprint reports", async () => {
    api.post.mockResolvedValue({ data: { id: "site-2" } });
    render(<AttendanceSettings />);

    await screen.findByText("Bogotá Principal");
    fireEvent.change(screen.getByLabelText("Nombre de sede"), {
      target: { value: "Cali" },
    });
    fireEvent.change(screen.getByLabelText("Código"), {
      target: { value: "clo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear sede" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/talent-id/sites", {
        name: "Cali",
        code: "CLO",
        timezone: "America/Bogota",
      });
    });
  });

  it("creates a work schedule for punctuality calculations", async () => {
    api.post.mockResolvedValue({ data: { id: "schedule-2" } });
    render(<AttendanceSettings />);

    await screen.findByText("Administrativo");
    fireEvent.change(screen.getByLabelText("Nombre del horario"), {
      target: { value: "Operativo" },
    });
    fireEvent.change(screen.getByLabelText("Entrada"), {
      target: { value: "07:00" },
    });
    fireEvent.change(screen.getByLabelText("Salida"), {
      target: { value: "16:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear horario" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/talent-id/schedules", {
        name: "Operativo",
        start_time: "07:00",
        end_time: "16:00",
        tolerance_minutes: 10,
      });
    });
  });
});
