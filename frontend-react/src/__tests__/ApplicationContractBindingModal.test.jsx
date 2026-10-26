// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ApplicationContractBindingModal from "../components/ApplicationContractBindingModal";
import api from "../api/client";

vi.mock("../api/client", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

const application = {
  id: "application-1",
  application_status: "SELECTED",
  candidate: { candidate_id: "candidate-1", name: "Ana Pérez" },
  job: { job_id: "job-1", title: "Backend Developer", company_name: "ASIATI Colombia" },
  access: { profile_id: "profile-1" },
};

const bindingReady = {
  enabled: true,
  bound: false,
  valid: false,
  can_bind: true,
  document_approved: true,
  status: "CONTRACT_READY_TO_BIND",
  message: "Contrato aprobado y listo para vincular.",
};

describe("ApplicationContractBindingModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation((url) => Promise.resolve({ data:
      url.includes("/contract/binding")
        ? bindingReady
        : { items: [{ id: 23, name: "ASIATI Colombia", country: "Colombia" }] },
    }));
    api.post.mockResolvedValue({ data: {
      bound: true, already_bound: false, odoo_company_id: 23,
    } });
  });

  it("binds the approved contract to this application and continues to its document dossier", async () => {
    const onContinue = vi.fn();
    render(<ApplicationContractBindingModal
      application={application}
      onClose={vi.fn()}
      onContinue={onContinue}
    />);

    const dialog = await screen.findByRole("dialog", { name: /Vincular contrato/i });
    fireEvent.change(within(dialog).getByLabelText("Empresa Odoo"), {
      target: { value: "23" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Vincular contrato" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/jobs/job-1/candidates/candidate-1/contract/bind",
      { odoo_company_id: 23 },
    ));
    expect(await within(dialog).findByText(/vinculación quedó registrada/i)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /Continuar a Documentos/i }));
    expect(onContinue).toHaveBeenCalledWith("profile-1");
  });

  it("does not allow binding until the contract PDF has been approved", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data:
      url.includes("/contract/binding")
        ? {
          enabled: true, bound: false, valid: false, can_bind: false,
          document_approved: false, status: "CONTRACT_NOT_APPROVED",
          message: "Primero carga y aprueba el contrato desde Documentos.",
        }
        : { items: [{ id: 23, name: "ASIATI Colombia", country: "Colombia" }] },
    }));
    render(<ApplicationContractBindingModal
      application={application}
      onClose={vi.fn()}
      onContinue={vi.fn()}
    />);

    const dialog = await screen.findByRole("dialog", { name: /Vincular contrato/i });
    expect(await within(dialog).findByText(/Primero carga y aprueba el contrato/i)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Vincular contrato" })).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("shows an existing binding as immutable and offers the document dossier", async () => {
    api.get.mockImplementation((url) => Promise.resolve({ data: url.includes("/contract/binding")
      ? {
        enabled: true, bound: true, valid: true, can_bind: false,
        document_approved: true, status: "APPLICATION_CONTRACT_BOUND",
        odoo_company_id: 23, message: "Contrato vinculado a la empresa Odoo seleccionada.",
      }
      : { items: [{ id: 23, name: "ASIATI Colombia", country: "Colombia" }] },
    }));
    const onContinue = vi.fn();
    render(<ApplicationContractBindingModal
      application={application}
      onClose={vi.fn()}
      onContinue={onContinue}
    />);

    const dialog = await screen.findByRole("dialog", { name: /Vincular contrato/i });
    expect(await within(dialog).findByText(/vinculado a la empresa Odoo/i)).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Empresa Odoo")).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: /Continuar a Documentos/i }));
    expect(onContinue).toHaveBeenCalledWith("profile-1");
    expect(api.post).not.toHaveBeenCalled();
  });
});
