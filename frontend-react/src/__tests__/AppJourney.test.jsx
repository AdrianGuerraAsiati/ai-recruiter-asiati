// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const clientState = vi.hoisted(() => ({
  token: null,
  get: vi.fn(),
  post: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("../api/client", () => ({
  default: {
    get: clientState.get,
    post: clientState.post,
  },
  getAccessToken: () => clientState.token,
  setAccessToken: (token) => {
    clientState.token = token;
  },
  clearAccessToken: () => {
    clientState.token = null;
  },
  refreshAccessToken: clientState.refresh,
}));

import App from "../App";


const principal = {
  email: "admin@asiati.com.co",
  roles: ["ADMIN"],
  permissions: [
    "jobs.read",
    "jobs.manage",
    "candidates.read",
    "candidates.manage",
    "candidates.evaluate",
    "ranking.read",
    "ranking.recalculate",
    "employees.read",
    "training.read",
    "training.manage",
    "training.assign",
    "training.results.read",
    "profile.read_own",
  ],
  profile: {
    id: "admin-1",
    first_name: "Katherine",
    last_name: "Admin",
  },
};


describe("application journey", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clientState.token = null;
    window.history.pushState({}, "", "/login");

    clientState.refresh.mockRejectedValue(new Error("anonymous"));
    clientState.post.mockImplementation((url) => {
      if (url === "/auth/login") {
        return Promise.resolve({ data: { access_token: "access-token" } });
      }
      return Promise.reject(new Error(`Unexpected POST ${url}`));
    });
    clientState.get.mockImplementation((url) => {
      if (url === "/auth/me") {
        return Promise.resolve({ data: principal });
      }
      if (url === "/jobs") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/candidates") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/employees/summary") {
        return Promise.resolve({
          data: {
            employees_total: 2,
            active: 2,
            disabled: 0,
            onboarding: {
              total: 1,
              pending: 0,
              in_progress: 1,
              completed: 0,
              completion_percent: 50,
            },
          },
        });
      }
      if (url === "/candidates?page=1&page_size=20") {
        return Promise.resolve({
          data: {
            items: [],
            total: 0,
            pages: 0,
          },
        });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
  });

  it("moves from anonymous login to admin dashboard and candidate directory", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Bienvenido de nuevo" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Correo electrónico"), {
      target: { value: "admin@asiati.com.co" },
    });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "secret-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Iniciar sesión/i }));

    expect(await screen.findByText("Vacantes activas")).toBeInTheDocument();
    expect(screen.getByText("Onboarding del equipo")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Candidatos" }));

    expect(
      await screen.findByRole("heading", { name: "Candidatos" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Aún no hay candidatos registrados"),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(clientState.post).toHaveBeenCalledWith("/auth/login", {
        email: "admin@asiati.com.co",
        password: "secret-password",
      });
      expect(clientState.get).toHaveBeenCalledWith("/auth/me");
      expect(clientState.get).toHaveBeenCalledWith(
        "/candidates?page=1&page_size=20",
      );
    });
  });
});
