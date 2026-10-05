// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TalentId from "../pages/TalentId";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import api from "../api/client";


function mockLists(devices = []) {
  api.get.mockImplementation((url) => {
    if (url === "/talent-id/sites") {
      return Promise.resolve({
        data: {
          items: [
            {
              id: "site-1",
              name: "Bogotá Principal",
              code: "BOG",
              timezone: "America/Bogota",
              active: true,
            },
            {
              id: "site-2",
              name: "Medellín",
              code: "MDE",
              timezone: "America/Bogota",
              active: true,
            },
          ],
        },
      });
    }
    if (url === "/talent-id/schedules") {
      return Promise.resolve({
        data: {
          items: [
            {
              id: "schedule-1",
              name: "Administrativo",
              start_time: "08:30:00",
              end_time: "18:00:00",
              tolerance_minutes: 10,
              active: true,
            },
          ],
        },
      });
    }
    if (url === "/talent-id/devices") {
      return Promise.resolve({ data: { items: devices } });
    }
    return Promise.reject(new Error(`Unexpected GET ${url}`));
  });
}


describe("Talent ID administration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLists();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it("shows the current pilot infrastructure", async () => {
    render(<TalentId />);

    expect((await screen.findAllByText("Bogotá Principal")).length).toBeGreaterThan(0);
    expect(screen.getByText("Administrativo")).toBeInTheDocument();
    expect(screen.getByText("Sedes activas")).toBeInTheDocument();
    expect(screen.getByText("Horarios activos")).toBeInTheDocument();
    expect(screen.getByText("Kioscos activos")).toBeInTheDocument();
    expect(screen.getByText("Credenciales de kioscos")).toBeInTheDocument();
  });

  it("creates a site with the configured timezone", async () => {
    api.post.mockResolvedValue({ data: { id: "site-3" } });
    render(<TalentId />);

    await screen.findAllByText("Bogotá Principal");

    fireEvent.change(screen.getByLabelText("Nombre de sede"), {
      target: { value: "Cali" },
    });
    fireEvent.change(screen.getByLabelText("Código"), {
      target: { value: "clo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear sede" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/sites",
        {
          name: "Cali",
          code: "CLO",
          timezone: "America/Bogota",
        },
      );
    });
  });

  it("provisions a kiosk and has one copy button per credential", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/talent-id/devices") {
        return Promise.resolve({
          data: {
            device: {
              id: "device-1",
              site_id: "site-1",
              name: "Recepción",
              active: true,
            },
            device_secret: "one-time-secret",
            secret_shown_once: true,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<TalentId />);

    await screen.findAllByText("Bogotá Principal");
    fireEvent.change(screen.getByLabelText("Sede del kiosco"), {
      target: { value: "site-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generar credenciales" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/devices",
        {
          site_id: "site-1",
          name: "Recepción",
        },
      );
    });

    expect(await screen.findByText("one-time-secret")).toBeInTheDocument();
    expect(screen.getByText("device-1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copiar ID" }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("device-1");
    });

    fireEvent.click(screen.getByRole("button", { name: "Copiar secret" }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("one-time-secret");
    });
  });

  it("edits a registered kiosk and can rotate its secret", async () => {
    mockLists([
      {
        id: "device-existing",
        site_id: "site-1",
        name: "Recepción vieja",
        active: true,
        last_seen_at: null,
      },
    ]);
    api.patch.mockResolvedValue({ data: {} });
    api.post.mockImplementation((url) => {
      if (url === "/talent-id/devices/device-existing/rotate-secret") {
        return Promise.resolve({
          data: {
            device: {
              id: "device-existing",
              site_id: "site-2",
              name: "Recepción norte",
              active: true,
            },
            device_secret: "rotated-secret",
            secret_shown_once: true,
            rotated: true,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<TalentId />);
    expect(await screen.findByText("Recepción vieja")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    fireEvent.change(screen.getByLabelText("Nombre"), {
      target: { value: "Recepción norte" },
    });
    fireEvent.change(screen.getByLabelText("Sede"), {
      target: { value: "site-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith(
        "/talent-id/devices/device-existing",
        {
          site_id: "site-2",
          name: "Recepción norte",
        },
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Regenerar secret" }));
    fireEvent.click(screen.getByRole("button", { name: "Sí, regenerar" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/devices/device-existing/rotate-secret",
      );
    });
    expect(await screen.findByText("rotated-secret")).toBeInTheDocument();
  });

  it("revokes a kiosk through the delete credential action", async () => {
    mockLists([
      {
        id: "device-delete",
        site_id: "site-1",
        name: "Tablet temporal",
        active: true,
        last_seen_at: null,
      },
    ]);
    api.delete.mockResolvedValue({ data: { revoked: true } });

    render(<TalentId />);
    expect(await screen.findByText("Tablet temporal")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Eliminar acceso" }));
    fireEvent.click(screen.getByRole("button", { name: "Sí, eliminar acceso" }));

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith(
        "/talent-id/devices/device-delete",
      );
    });
  });
});
