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
    api.get.mockImplementation((url) => Promise.resolve({ data:
      url.includes("/hire-readiness")
        ? { enabled: false, ready: true, status: "LEGACY_FLOW" }
        : { items: [application], total: 1, pages: 1 },
    }));
    api.post.mockResolvedValue({ data: { application_status: "HIRED", employee_created: false, credentials: null } });
    api.put.mockResolvedValue({ data: {} });
  });

  it("permits hiring only from an existing application with portal access", async () => {
    mount();
    expect(await screen.findByText("Ana Pérez")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Revisar documentos" }))
      .toHaveAttribute("href", "/documents?employee_id=profile-1");
    expect(screen.getByText(/aperez · Credenciales/i)).toBeInTheDocument();
    const hiredOption = within(screen.getByRole("combobox", { name: "Estado de Ana Pérez" })).getByRole("option", { name: "Contratado" });
    expect(hiredOption).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Crear empleado" }));
    const dialog = screen.getByRole("dialog", { name: "Crear empleado" });
    expect(within(dialog).getByLabelText("Usuario de ADN360").value).toBe("aperez");
    const confirm = within(dialog).getByRole("button", { name: "Confirmar contratación" });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/jobs/job-1/candidates/candidate-1/hire",
      expect.objectContaining({ username: "aperez", email: "ana@example.com" }),
    ));
    expect(await screen.findByText(/Contratación confirmada y onboarding asignado/)).toBeInTheDocument();
  });

  it("submits an Odoo-verified company ID instead of arbitrary company text", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data:
      url === "/jobs/hiring/signature-flow"
        ? { enabled: true }
        : url === "/odoo/companies"
          ? { items: [{ id: 23, name: "Marca Contratante", country: "Colombia" }] }
          : url.includes("/hire-readiness")
            ? { enabled: true, ready: true, status: "SIGNED_CONTRACT_ARCHIVED" }
            : { items: [application], total: 1, pages: 1 },
    }));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Crear empleado" }));
    const dialog = screen.getByRole("dialog", { name: "Crear empleado" });
    expect(await within(dialog).findByRole("option", { name: "Marca Contratante · Colombia" })).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Empresa contratante en Odoo"), {
      target: { value: "23" },
    });
    fireEvent.change(within(dialog).getByLabelText("Tipo de contrato"), {
      target: { value: "indefinido" },
    });
    fireEvent.change(within(dialog).getByLabelText("Fecha de inicio contractual"), {
      target: { value: "2026-10-20" },
    });
    fireEvent.change(within(dialog).getByLabelText("Salario mensual"), {
      target: { value: "2000000" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirmar contratación" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/jobs/job-1/candidates/candidate-1/hire",
      expect.objectContaining({
        odoo_company_id: 23,
        company_name: "Marca Contratante",
      }),
    ));
  });

  it("prevents hiring before the required two signatures and archive", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data:
      url.includes("/hire-readiness")
        ? { enabled: true, ready: false,
            message: "Debes obtener ambas firmas y archivar el PDF final antes de crear el empleado." }
        : { items: [application], total: 1, pages: 1 },
    }));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Crear empleado" }));
    const dialog = screen.getByRole("dialog", { name: "Crear empleado" });
    expect(await within(dialog).findByText(/Debes obtener ambas firmas/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Confirmar contratación" })).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("prepares a candidate contract dossier without creating Cognito access", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data:
      url === "/jobs/hiring/signature-flow"
        ? { enabled: true }
        : { items: [{ ...application, access: null, application_status: "SELECTED" }], total: 1, pages: 1 },
    }));
    api.post.mockResolvedValue({ data: {
      profile_id: "prehire-1", employee_created: false, access_provisioned: false,
    } });
    mount();
    const prepare = await screen.findByRole("button", { name: "Preparar contrato" });
    fireEvent.click(prepare);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/jobs/job-1/candidates/candidate-1/contract/prepare-dossier",
    ));
    expect(api.post).not.toHaveBeenCalledWith(expect.stringMatching(/start-application/), expect.anything());
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

  it("exposes application-specific contract binding only when the feature is enabled", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data:
      url === "/jobs/hiring/signature-flow"
        ? { enabled: true, binding_enabled: true }
        : url === "/odoo/companies"
          ? { items: [{ id: 23, name: "ASIATI Colombia", country: "Colombia" }] }
          : url.includes("/contract/binding")
            ? { enabled: true, bound: false, valid: false, can_bind: true,
                document_approved: true, status: "CONTRACT_READY_TO_BIND",
                message: "Contrato aprobado y listo para vincular." }
            : url.includes("/hire-readiness")
              ? { enabled: true, ready: false, status: "APPLICATION_CONTRACT_BINDING_REQUIRED" }
              : { items: [application], total: 1, pages: 1 },
    }));
    mount();

    const bind = await screen.findByRole("button", { name: "Vincular contrato" });
    fireEvent.click(bind);
    const dialog = await screen.findByRole("dialog", { name: /Vincular contrato/i });
    expect(within(dialog).getByText(/Ana Pérez/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Desarrollador/)).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      "/jobs/job-1/candidates/candidate-1/contract/binding",
    ));
  });

  it("does not expose contract binding for an application outside SELECTED or OFFER", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data:
      url === "/jobs/hiring/signature-flow"
        ? { enabled: true, binding_enabled: true }
        : { items: [{ ...application, application_status: "APPLIED" }], total: 1, pages: 1 },
    }));
    mount();
    await screen.findByText("Ana Pérez");
    expect(screen.queryByRole("button", { name: "Vincular contrato" })).not.toBeInTheDocument();
  });

});
