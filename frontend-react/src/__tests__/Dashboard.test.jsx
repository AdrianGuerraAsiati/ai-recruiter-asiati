// eslint-disable-next-line no-unused-vars
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Dashboard from "../pages/Dashboard";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
  },
}));

vi.mock("../context/SessionContext", () => ({
  useSession: vi.fn(),
}));

import api from "../api/client";
import { useSession } from "../context/SessionContext";


function renderPage() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}


function mockAdministrativeSession(role) {
  useSession.mockReturnValue({
    principal: {
      roles: [role],
      profile: {
        id: `${role.toLowerCase()}-1`,
        first_name: role === "SUPER_ADMIN" ? "Natalí" : "Administrador",
      },
    },
    hasPermission: (permission) => [
      "jobs.read",
      "candidates.read",
      "employees.read",
    ].includes(permission),
  });
}


describe("Administrative dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation((url) => {
      if (url === "/jobs") {
        return Promise.resolve({
          data: [
            { job_id: "job-1", title: "Uno", candidate_count: 2 },
            { job_id: "job-2", title: "Dos", candidate_count: 0 },
          ],
        });
      }
      if (url === "/candidates") {
        return Promise.resolve({
          data: {
            items: [{ id: "candidate-1", name: "Ana" }],
            total: 37,
            page: 1,
            page_size: 20,
            pages: 2,
          },
        });
      }
      if (url === "/jobs/coverage/summary") return Promise.resolve({ data: { coverage_percent: 50, covered_jobs: 1, total_active_jobs: 2, pipeline_depth: 1.5, counts: {low: 0, critical: 1, pending: 0}, jobs: [] } });
      if (url === "/employees/summary") {
        return Promise.resolve({
          data: {
            employees_total: 8,
            active: 7,
            disabled: 1,
            onboarding: {
              total: 5,
              pending: 1,
              in_progress: 2,
              completed: 2,
              completion_percent: 40,
            },
          },
        });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
  });

  it("uses the paginated candidate total and real vacancy coverage", async () => {
    mockAdministrativeSession("ADMIN");
    renderPage();

    expect(await screen.findByText("Candidatos registrados")).toBeInTheDocument();
    expect(screen.getByText("37")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("excludes paused vacancies from active count and coverage", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/jobs/coverage/summary") return Promise.resolve({ data: { coverage_percent: 0, covered_jobs: 0, total_active_jobs: 1, pipeline_depth: 0, counts: {low: 0, critical: 0, pending: 1}, jobs: [] } });
      if (url === "/jobs") {
        return Promise.resolve({
          data: [
            { job_id: "job-active", title: "Activa sin candidatos", status: "ACTIVE", candidate_count: 0 },
            { job_id: "job-paused", title: "Pausada con candidatos", status: "PAUSED", candidate_count: 10 },
          ],
        });
      }
      if (url === "/candidates") {
        return Promise.resolve({ data: { items: [], total: 37, page: 1, page_size: 20, pages: 2 } });
      }
      if (url === "/employees/summary") {
        return Promise.resolve({
          data: {
            employees_total: 8,
            active: 7,
            disabled: 1,
            onboarding: { total: 5, pending: 1, in_progress: 2, completed: 2, completion_percent: 40 },
          },
        });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });

    mockAdministrativeSession("ADMIN");
    renderPage();

    const activeLabel = await screen.findByText("Vacantes activas");
    expect(activeLabel.closest("article")).toHaveTextContent("1");
    expect(screen.getByText("0%")).toBeInTheDocument();
    expect(screen.getByText("Pausada")).toBeInTheDocument();
  });

  it.each(["ADMIN"])(
    "shows onboarding metrics to %s users with employee read permission",
    async (role) => {
      mockAdministrativeSession(role);
      renderPage();

      expect(await screen.findByText("Onboarding del equipo")).toBeInTheDocument();
      expect(screen.getByText("Empleados activos")).toBeInTheDocument();
      expect(screen.getByText("Pendientes")).toBeInTheDocument();
      expect(screen.getByText("En progreso")).toBeInTheDocument();
      expect(screen.getByText("Completados")).toBeInTheDocument();

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith("/employees/summary");
      });
    },
  );
});
