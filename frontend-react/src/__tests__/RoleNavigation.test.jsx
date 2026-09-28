// eslint-disable-next-line no-unused-vars
import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Navbar from "../components/Navbar";

vi.mock("../api/client", () => ({
  default: {
    post: vi.fn(),
  },
}));

vi.mock("../components/BrandMark", () => ({
  default: () => <span>ASIATI</span>,
}));

vi.mock("../components/ThemeToggle", () => ({
  default: () => <button type="button">Tema</button>,
}));

vi.mock("../context/SessionContext", () => ({
  useSession: vi.fn(),
}));

import { useSession } from "../context/SessionContext";


function renderRole(role, permissions) {
  useSession.mockReturnValue({
    principal: {
      email: "persona@asiati.com.co",
      roles: [role],
      permissions,
      profile: { first_name: "Ana", last_name: "Pérez" },
    },
    hasPermission: (permission) => permissions.includes(permission),
    clearSession: vi.fn(),
  });

  return render(
    <MemoryRouter>
      <Navbar />
    </MemoryRouter>,
  );
}


describe("role navigation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the employee workspace only", () => {
    renderRole("EMPLOYEE", [
      "training.read",
      "training.progress.read_own",
      "profile.read_own",
    ]);

    expect(screen.getByText("Inicio")).toBeInTheDocument();
    expect(screen.getByText("Capacitación")).toBeInTheDocument();
    expect(screen.getByText("Mi progreso")).toBeInTheDocument();
    expect(screen.getByText("Mi perfil")).toBeInTheDocument();

    expect(screen.queryByText("Vacantes")).not.toBeInTheDocument();
    expect(screen.queryByText("Postulaciones")).not.toBeInTheDocument();
    expect(screen.queryByText("Candidatos")).not.toBeInTheDocument();
    expect(screen.queryByText("Agenda")).not.toBeInTheDocument();
    expect(screen.queryByText("Empleados")).not.toBeInTheDocument();
    expect(screen.queryByText("Calificación")).not.toBeInTheDocument();
    expect(screen.queryByText("Integraciones")).not.toBeInTheDocument();
  });

  it("shows recruiting and people management to ADMIN without Direction", () => {
    renderRole("ADMIN", [
      "jobs.read",
      "candidates.read",
      "ranking.read",
      "employees.read",
      "training.read",
      "training.results.read",
      "profile.read_own",
    ]);

    for (const label of [
      "Inicio",
      "Vacantes",
      "Postulaciones",
      "Agenda",
      "Candidatos",
      "Ranking IA",
      "Empleados",
      "Capacitación",
      "Mi perfil",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }

    expect(screen.queryByText("Mi progreso")).not.toBeInTheDocument();
    expect(screen.queryByText("Calificación")).not.toBeInTheDocument();
    expect(screen.queryByText("Integraciones")).not.toBeInTheDocument();
  });

  it("adds Direction-only scoring and system integrations to SUPER_ADMIN", () => {
    renderRole("SUPER_ADMIN", [
      "jobs.read",
      "candidates.read",
      "ranking.read",
      "employees.read",
      "training.read",
      "training.progress.read_own",
      "profile.read_own",
      "employee_scores.read",
      "integrations.manage",
    ]);

    expect(screen.getByText("Postulaciones")).toBeInTheDocument();
    expect(screen.getByText("Agenda")).toBeInTheDocument();
    expect(screen.getByText("Calificación")).toBeInTheDocument();
    expect(screen.getByText("Integraciones")).toBeInTheDocument();
    expect(screen.queryByText("Mi progreso")).not.toBeInTheDocument();
  });
});
