// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Jobs from "../pages/Jobs";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("../context/SessionContext", () => ({
  useSession: vi.fn(),
}));

import api from "../api/client";
import { useSession } from "../context/SessionContext";

const JOBS = [
  { job_id: "job-1", title: "Backend Developer", description: "Python APIs REST", candidate_count: 2, created_at: "2026-09-01T10:00:00Z" },
  { job_id: "job-2", title: "Frontend Developer", description: "React y TypeScript", candidate_count: 0, created_at: "2026-09-02T12:00:00Z" },
];

const CANDIDATES = [
  { candidate_id: "c-1", name: "Ana Pérez", email: "ana@test.com", filename: "Ana-Perez.pdf" },
  { candidate_id: "c-2", name: "Carlos Gómez", email: null, filename: null },
];

function jobsPage(items = JOBS) {
  return {
    items,
    page: 1,
    page_size: 12,
    total: items.length,
    total_pages: items.length ? 1 : 0,
  };
}

function renderJobs() {
  return render(
    <MemoryRouter>
      <Jobs />
    </MemoryRouter>
  );
}

describe("Jobs page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSession.mockReturnValue({
      hasPermission: (permission) => permission === "employees.create",
    });
    api.get.mockImplementation((url) => {
      if (url === "/jobs/page") return Promise.resolve({ data: jobsPage() });
      if (url === "/jobs/job-1/candidates") return Promise.resolve({ data: CANDIDATES });
      return Promise.resolve({ data: [] });
    });
    api.delete.mockResolvedValue({ data: { detail: "Vacante eliminada." } });
    api.post.mockResolvedValue({ data: {} });
    api.put.mockResolvedValue({ data: {} });
  });

  it("renders vacantes", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");
    expect(screen.getByText("Frontend Developer")).toBeInTheDocument();
  });

  it("each vacante has Ver, Agregar candidatos, Editar, Eliminar buttons", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");
    expect(screen.getAllByRole("button", { name: /^ver$/i })).toHaveLength(JOBS.length);
    expect(screen.getAllByText("Agregar candidatos").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Editar").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Eliminar").length).toBeGreaterThanOrEqual(1);
  });

  it("click Ver opens dialog with full job info", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Ver")[0]);

    await waitFor(() => {
      expect(screen.getByText("Información de la vacante")).toBeInTheDocument();
    });
    expect(screen.getByText("Descripción y requisitos")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent("Python APIs REST");
    expect(screen.getByText("Candidatos asignados")).toBeInTheDocument();
  });

  it("Ver calls GET /jobs/job-1/candidates with page=1 page_size=100", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Ver")[0]);

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith("/jobs/job-1/candidates", {
        params: { page: 1, page_size: 100 },
      });
    });
  });

  it("modal lists candidates Ana and Carlos", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Ver")[0]);

    await waitFor(() => {
      expect(screen.getByText("Ana Pérez")).toBeInTheDocument();
    });
    expect(screen.getByText("Carlos Gómez")).toBeInTheDocument();
  });

  it("vacante sin candidatos shows empty message", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/jobs/page") return Promise.resolve({ data: jobsPage() });
      if (url === "/jobs/job-2/candidates") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });

    renderJobs();
    await screen.findByText("Frontend Developer");

    const verButtons = screen.getAllByText("Ver");
    fireEvent.click(verButtons[1]);

    await waitFor(() => {
      expect(screen.getByText("No hay candidatos asignados a esta vacante.")).toBeInTheDocument();
    });
  });

  it("candidates request failed shows error and Reintentar", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/jobs/page") return Promise.resolve({ data: jobsPage() });
      if (url === "/jobs/job-1/candidates") return Promise.reject(new Error("Network error"));
      return Promise.resolve({ data: [] });
    });

    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Ver")[0]);

    await waitFor(() => {
      expect(screen.getByText("No fue posible cargar los candidatos de esta vacante.")).toBeInTheDocument();
    });
    expect(screen.getByText("Reintentar")).toBeInTheDocument();
  });

  it("click Eliminar opens modal, does NOT call api.delete immediately", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);

    await waitFor(() => {
      expect(screen.getByText("¿qué deseas eliminar?")).toBeInTheDocument();
    });
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("delete modal has exactly three options", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);

    await waitFor(() => {
      expect(screen.getByText("¿qué deseas eliminar?")).toBeInTheDocument();
    });
    expect(screen.getByText("Borrar solo la vacante")).toBeInTheDocument();
    expect(screen.getByText("Borrar vacante y candidatos")).toBeInTheDocument();
    expect(screen.getByText("Cancelar")).toBeInTheDocument();
  });

  it("Borrar solo la vacante calls api.delete with delete_candidates=false", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);

    await waitFor(() => {
      expect(screen.getByText("Borrar solo la vacante")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Borrar solo la vacante"));

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith("/jobs/job-1", { params: { delete_candidates: false } });
    });
  });

  it("Borrar vacante y candidatos calls api.delete with delete_candidates=true", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);

    await waitFor(() => {
      expect(screen.getByText("Borrar vacante y candidatos")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Borrar vacante y candidatos"));

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith("/jobs/job-1", { params: { delete_candidates: true } });
    });
  });

  it("Cancelar closes modal and does NOT call api.delete", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);

    await waitFor(() => {
      expect(screen.getByText("Cancelar")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Cancelar"));

    await waitFor(() => {
      expect(screen.queryByText("¿qué deseas eliminar?")).not.toBeInTheDocument();
    });
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("during deleting, actions are disabled", async () => {
    let resolveDelete;
    api.delete.mockReturnValueOnce(new Promise((r) => { resolveDelete = r; }));

    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);
    await waitFor(() => { expect(screen.getByText("Borrar solo la vacante")).toBeInTheDocument(); });

    fireEvent.click(screen.getByText("Borrar solo la vacante"));

    await waitFor(() => {
      expect(screen.getByText("Eliminando…")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /^Borrar solo la vacante/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Borrar vacante y candidatos/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Cancelar$/i })).toBeDisabled();

    resolveDelete({ data: { detail: "Vacante eliminada." } });
  });

  it("error delete shows error in modal", async () => {
    api.delete.mockRejectedValueOnce({ response: { data: { detail: "Error al eliminar." } } });

    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);
    await waitFor(() => { expect(screen.getByText("Borrar solo la vacante")).toBeInTheDocument(); });

    fireEvent.click(screen.getByText("Borrar solo la vacante"));

    await waitFor(() => {
      expect(screen.getByText("Error al eliminar.")).toBeInTheDocument();
    });
    expect(screen.getByText("¿qué deseas eliminar?")).toBeInTheDocument();
  });

  it("success delete solo vacante: closes modal, refreshes list, shows message", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);
    await waitFor(() => { expect(screen.getByText("Borrar solo la vacante")).toBeInTheDocument(); });

    fireEvent.click(screen.getByText("Borrar solo la vacante"));

    await waitFor(() => {
      expect(screen.getByText("Vacante eliminada. Los candidatos se conservaron.")).toBeInTheDocument();
    });
    expect(screen.queryByText("¿qué deseas eliminar?")).not.toBeInTheDocument();
  });

  it("success delete con candidatos shows correct message", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);
    await waitFor(() => { expect(screen.getByText("Borrar vacante y candidatos")).toBeInTheDocument(); });

    fireEvent.click(screen.getByText("Borrar vacante y candidatos"));

    await waitFor(() => {
      expect(screen.getByText("Vacante y 2 candidatos eliminados.")).toBeInTheDocument();
    });
  });

  it("does not use window.confirm for job deletion", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Eliminar")[0]);
    await waitFor(() => {
      expect(screen.getByText("¿qué deseas eliminar?")).toBeInTheDocument();
    });

    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("vacante without description offers Editar y enriquecer from detail", async () => {
    const emptyJobs = [
      {
        job_id: "job-empty",
        title: "Líder de Marketing y Crecimiento",
        description: null,
        candidate_count: 0,
        created_at: "2026-09-21T10:00:00Z",
      },
    ];
    api.get.mockImplementation((url) => {
      if (url === "/jobs/page") {
        return Promise.resolve({ data: jobsPage(emptyJobs) });
      }
      if (url === "/jobs/job-empty/candidates") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });

    renderJobs();
    await screen.findByText("Líder de Marketing y Crecimiento");
    fireEvent.click(screen.getByRole("button", { name: /^ver$/i }));

    expect(await screen.findByText("Sin descripción.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /editar y enriquecer/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /enriquecer con ia/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Título de la vacante")).toHaveValue("Líder de Marketing y Crecimiento");
  });

  it("detail modal closes with X button", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Ver")[0]);
    await waitFor(() => {
      expect(screen.getByText("Información de la vacante")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Cerrar detalle de vacante"));

    await waitFor(() => {
      expect(screen.queryByText("Información de la vacante")).not.toBeInTheDocument();
    });
  });

  it("detail modal has role=dialog and aria-modal=true", async () => {
    renderJobs();
    await screen.findByText("Backend Developer");

    fireEvent.click(screen.getAllByText("Ver")[0]);

    await waitFor(() => {
      const dialog = screen.getByRole("dialog", { name: /Backend Developer/i });
      expect(dialog).toBeInTheDocument();
      expect(dialog).toHaveAttribute("aria-modal", "true");
    });
  });

  it("hides Contratar candidato without employees.create permission", async () => {
    useSession.mockReturnValue({
      hasPermission: () => false,
    });

    renderJobs();
    await screen.findByText("Backend Developer");
    fireEvent.click(screen.getAllByText("Ver")[0]);

    await screen.findByText("Ana Pérez");
    expect(screen.queryByRole("button", { name: /Contratar candidato/i })).not.toBeInTheDocument();
  });

  it("hires a candidate and assigns onboarding from the vacancy", async () => {
    api.post.mockResolvedValueOnce({
      data: {
        hired_at: "2026-09-25T18:00:00Z",
        employee: { id: "employee-1" },
        onboarding_assignment: {
          id: "assignment-1",
          course: { id: "course-1", progress_percent: 0 },
        },
      },
    });

    renderJobs();
    await screen.findByText("Backend Developer");
    fireEvent.click(screen.getAllByText("Ver")[0]);

    await screen.findByText("Ana Pérez");
    fireEvent.click(screen.getAllByRole("button", { name: /Contratar candidato/i })[0]);

    expect(await screen.findByRole("heading", { name: "Contratar y crear empleado" })).toBeInTheDocument();
    expect(screen.getByLabelText("Nombre")).toHaveValue("Ana");
    expect(screen.getByLabelText("Apellido")).toHaveValue("Pérez");
    expect(screen.getByLabelText("Correo de acceso")).toHaveValue("ana@test.com");
    expect(screen.getByLabelText("Cargo")).toHaveValue("Backend Developer");

    fireEvent.change(screen.getByLabelText("Área"), {
      target: { value: "Tecnología" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar contratación" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/jobs/job-1/candidates/c-1/hire",
        expect.objectContaining({
          email: "ana@test.com",
          first_name: "Ana",
          last_name: "Pérez",
          job_title: "Backend Developer",
          department: "Tecnología",
        }),
      );
    });
    expect(
      await screen.findByText(/Ana Pérez fue contratado\. Acceso creado y onboarding asignado \(0%\)\./i),
    ).toBeInTheDocument();
  });
});
