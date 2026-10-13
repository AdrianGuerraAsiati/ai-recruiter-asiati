// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Applications from "../pages/Applications";
import api from "../api/client";

vi.mock("../context/SessionContext", () => ({
  useSession: () => ({ hasPermission: (code) => [
    "employees.create",
    "employees.credentials.manage",
    "employee_documents.read_all",
  ].includes(code) }),
}));

vi.mock("../api/client", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

const application = {
  id: "a1",
  application_status: "SELECTED",
  status_changed_at: "2026-10-10T10:00:00Z",
  candidate: {
    candidate_id: "candidate-1",
    name: "Ana Pérez",
    email: "ana@example.com",
    country_code: "CO",
  },
  job: { job_id: "job-1", title: "Desarrollador" },
  access: {
    profile_id: "profile-1",
    username: "aperez",
    email: "ana@example.com",
    provisioned: true,
    status: "ACTIVE",
  },
};

function mount() {
  return render(<MemoryRouter><Applications /></MemoryRouter>);
}

describe("Applications: document access and employee creation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { items: [application], total: 1, pages: 1 } });
    api.post.mockResolvedValue({ data: { application_status: "HIRED", employee_created: false, credentials: null } });
    api.put.mockResolvedValue({ data: {} });
  });

  it("permits hiring only from an existing application with portal access", async () => {
    mount();
    expect(await screen.findByText("Ana pérez")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Revisar documentos" }))
      .toHaveAttribute("href", "/documents?employee_id=profile-1");
    expect(screen.getByText(/aperez · Credenciales/i)).toBeInTheDocument();
    const hiredOption = within(screen.getByRole("combobox", { name: "Estado de Ana Pérez" })).getByRole("option", { name: "Contratado" });
    expect(hiredOption).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Crear empleado" }));
    const dialog = screen.getByRole("dialog", { name: "Crear empleado" });
    expect(within(dialog).getByLabelText("Usuario de Talent").value).toBe("aperez");
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirmar contratación" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/jobs/job-1/candidates/candidate-1/hire",
      expect.objectContaining({ username: "aperez", email: "ana@example.com" }),
    ));
    expect(await screen.findByText(/Contratación confirmada y onboarding asignado/)).toBeInTheDocument();
  });

  it("offers portal credentials before hiring applicants imported without a login", async () => {
    api.get.mockResolvedValue({ data: {
      items: [{ ...application, access: null, application_status: "APPLIED" }],
      total: 1,
      pages: 1,
    } });
    api.post.mockResolvedValue({ data: {
      applicant_access_created: true,
      application_status: "SELECTED",
      employee: { id: "profile-2", first_name: "Ana", last_name: "Pérez" },
      credentials: { username: "aperez", temporary_password: "TemporaryPass123", must_change_password: true },
    } });

    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Crear acceso" }));
    const dialog = await screen.findByRole("dialog", { name: "Iniciar postulación" });
    await waitFor(() => expect(within(dialog).getByLabelText("Correo").value).toBe("ana@example.com"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Iniciar postulación" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/jobs/job-1/candidates/candidate-1/start-application",
      expect.objectContaining({ username: "aperez", email: "ana@example.com" }),
    ));
    expect(await screen.findByText("TemporaryPass123")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear empleado" })).not.toBeInTheDocument();
  });
});
