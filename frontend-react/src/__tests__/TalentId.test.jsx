// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TalentId from "../pages/TalentId";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from "../api/client";


function mockLists() {
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
      return Promise.resolve({ data: { items: [] } });
    }
    return Promise.reject(new Error(`Unexpected GET ${url}`));
  });
}


describe("Talent ID administration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLists();
  });

  it("shows the current pilot infrastructure", async () => {
    render(<TalentId />);

    expect(await screen.findByText("Bogotá Principal")).toBeInTheDocument();
    expect(screen.getByText("Administrativo")).toBeInTheDocument();
    expect(screen.getByText("Sedes activas")).toBeInTheDocument();
    expect(screen.getByText("Horarios activos")).toBeInTheDocument();
    expect(screen.getByText("Kioscos activos")).toBeInTheDocument();
  });

  it("creates a site with the configured timezone", async () => {
    api.post.mockResolvedValue({ data: { id: "site-2" } });
    render(<TalentId />);

    await screen.findByText("Bogotá Principal");

    fireEvent.change(screen.getByLabelText("Nombre de sede"), {
      target: { value: "Medellín" },
    });
    fireEvent.change(screen.getByLabelText("Código"), {
      target: { value: "mde" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear sede" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/sites",
        {
          name: "Medellín",
          code: "MDE",
          timezone: "America/Bogota",
        },
      );
    });
  });

  it("provisions a kiosk and exposes the secret only from the creation response", async () => {
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

    await screen.findByText("Bogotá Principal");
    expect(screen.getByLabelText("Sede del kiosco")).toHaveValue("site-1");

    fireEvent.click(
      screen.getByRole("button", { name: "Generar credenciales del kiosco" }),
    );

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
    expect(screen.getByText(/se muestran una sola vez/i)).toBeInTheDocument();
  });
});
