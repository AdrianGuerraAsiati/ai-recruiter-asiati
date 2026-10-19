// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Documents from "../pages/Documents";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}));

vi.mock("../context/SessionContext", () => ({
  useSession: vi.fn(),
}));

import api from "../api/client";
import { useSession } from "../context/SessionContext";

const requirements = [
  {
    id: "doc-1",
    document_type: "IDENTITY",
    label: "Documento de identidad",
    kind: "FILE",
    description: "Copia legible.",
    original_filename: "cedula.pdf",
    content_type: "application/pdf",
    size_bytes: 1200,
    uploaded_at: "2026-10-08T14:00:00Z",
    review_status: "PENDING_REVIEW",
    review_comment: null,
  },
  {
    id: "value-1",
    document_type: "RESIDENCE_ADDRESS",
    label: "Dirección de residencia",
    kind: "TEXT",
    description: "Dirección actual.",
    value_text: "Calle 100 # 10-20",
    uploaded_at: "2026-10-08T14:00:00Z",
    review_status: "CHANGES_REQUESTED",
    review_comment: "Agrega la ciudad.",
  },
];

function portfolio(items = requirements) {
  return {
    employee: {
      id: "employee-1",
      first_name: "Ana",
      last_name: "Pérez",
      email: "ana@asiati.com.co",
    },
    items,
    total: 13,
    summary: {
      total: 13,
      submitted: 2,
      approved: 0,
      pending_review: 1,
      changes_requested: 1,
      missing: 11,
      approval_percent: 0,
      status: "CHANGES_REQUESTED",
    },
  };
}

describe("Employee document review workspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSession.mockReturnValue({
      principal: { profile: { id: "employee-1" } },
      hasPermission: (permission) => [
        "employee_documents.read_own",
        "employee_documents.upload_own",
      ].includes(permission),
    });
    api.get.mockResolvedValue({ data: portfolio() });
    api.put.mockResolvedValue({ data: portfolio() });
  });

  it("shows review status and admin comments to the employee", async () => {
    render(<Documents />);

    expect(await screen.findByText("Documento de identidad")).toBeInTheDocument();
    expect(screen.getAllByText("En revisión").length).toBeGreaterThan(0);
    expect(screen.getByText("Requiere cambios")).toBeInTheDocument();
    expect(screen.getByText("Agrega la ciudad.")).toBeInTheDocument();
    expect(screen.getByText("Aprobados")).toBeInTheDocument();
  });

  it("shows an accessible file picker with a selected filename", async () => {
    render(<Documents />);
    await screen.findByText("Documento de identidad");
    const input = screen.getByLabelText("Seleccionar archivo para Documento de identidad");
    expect(input).toHaveAttribute("type", "file");
    const file = new File(["test"], "documento-nuevo.pdf", { type: "application/pdf" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(screen.getByText("documento-nuevo.pdf")).toBeInTheDocument();
    expect(screen.getByText("Cambiar archivo")).toBeInTheDocument();
  });

  it("lets the employee resubmit complementary information", async () => {
    render(<Documents />);
    await screen.findByText("Dirección de residencia");

    const field = screen.getByLabelText("Dirección de residencia");
    fireEvent.change(field, { target: { value: "Calle 100 # 10-20, Bogotá" } });
    fireEvent.click(screen.getByRole("button", { name: "Actualizar y enviar" }));

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith("/employee-documents/me/value", {
        document_type: "RESIDENCE_ADDRESS",
        value: "Calle 100 # 10-20, Bogotá",
      });
    });
  });

  it("shows the selected profile UUID only to authorized HR and copies that exact ID", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1" } },
      hasPermission: (permission) => [
        "employee_documents.read_own",
        "employee_documents.read_all",
        "employee_documents.review",
      ].includes(permission),
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    api.get.mockImplementation((url) => {
      if (url === "/employees") {
        return Promise.resolve({
          data: { items: [{ id: "employee-1", first_name: "Ana", last_name: "Pérez" }] },
        });
      }
      if (url === "/employee-documents/me") {
        return Promise.resolve({ data: portfolio([]) });
      }
      if (url === "/employee-documents/employees/employee-1") {
        return Promise.resolve({ data: portfolio() });
      }
      return Promise.resolve({ data: {} });
    });

    render(<Documents />);
    await screen.findByRole("option", { name: "Ana Pérez" });
    fireEvent.change(screen.getByLabelText("Empleado a consultar"), {
      target: { value: "employee-1" },
    });
    expect(await screen.findByText("UUID del perfil en ADN360")).toBeInTheDocument();
    expect(screen.getByTestId("selected-profile-uuid")).toHaveTextContent("employee-1");
    fireEvent.click(screen.getByRole("button", { name: "Copiar UUID del perfil" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("employee-1"));
    expect(await screen.findByRole("status")).toHaveTextContent("ID copiado");
  });

  it("does not expose the admin UUID copy control in the applicant's own documents", async () => {
    render(<Documents />);
    await screen.findByText("Documento de identidad");
    expect(screen.queryByText("UUID del perfil en ADN360")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copiar UUID del perfil" })).not.toBeInTheDocument();
  });

  it("lets an admin approve each submitted requirement", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1" } },
      hasPermission: (permission) => [
        "employee_documents.read_own",
        "employee_documents.upload_own",
        "employee_documents.read_all",
        "employee_documents.review",
      ].includes(permission),
    });
    api.get.mockImplementation((url) => {
      if (url === "/employees") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "employee-1",
                first_name: "Ana",
                last_name: "Pérez",
                email: "ana@asiati.com.co",
              },
            ],
          },
        });
      }
      if (url === "/employee-documents/me") {
        return Promise.resolve({ data: portfolio([]) });
      }
      if (url === "/employee-documents/employees/employee-1") {
        return Promise.resolve({ data: portfolio() });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockResolvedValue({ data: portfolio() });

    render(<Documents />);

    await screen.findByRole("option", { name: "Ana Pérez" });
    fireEvent.change(screen.getByLabelText("Empleado a consultar"), {
      target: { value: "employee-1" },
    });

    expect(await screen.findByText("Documento de identidad")).toBeInTheDocument();
    const approveButtons = screen.getAllByRole("button", { name: /dar visto bueno/i });
    fireEvent.click(approveButtons[0]);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/employee-documents/doc-1/review", {
        status: "APPROVED",
        comment: null,
      });
    });
  });

  it("requires a comment before requesting corrections", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1" } },
      hasPermission: (permission) => [
        "employee_documents.read_own",
        "employee_documents.upload_own",
        "employee_documents.read_all",
        "employee_documents.review",
      ].includes(permission),
    });
    api.get.mockImplementation((url) => {
      if (url === "/employees") {
        return Promise.resolve({
          data: {
            items: [{ id: "employee-1", first_name: "Ana", last_name: "Pérez" }],
          },
        });
      }
      if (url === "/employee-documents/me") {
        return Promise.resolve({ data: portfolio([]) });
      }
      if (url === "/employee-documents/employees/employee-1") {
        return Promise.resolve({
          data: portfolio([{ ...requirements[0], review_comment: null }]),
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<Documents />);
    await screen.findByRole("option", { name: "Ana Pérez" });
    fireEvent.change(screen.getByLabelText("Empleado a consultar"), {
      target: { value: "employee-1" },
    });

    await screen.findByText("Documento de identidad");
    fireEvent.click(screen.getByRole("button", { name: "Solicitar corrección" }));

    expect(
      await screen.findByText("Escribe un comentario para indicar qué debe corregir el empleado."),
    ).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });
  it("prepares approved HR-only contracts in Odoo Sign staging without sending emails", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1" } },
      hasPermission: (permission) => [
        "employee_documents.read_own",
        "employee_documents.read_all",
        "employee_documents.review",
      ].includes(permission),
    });
    const contract = {
      id: "contract-1",
      document_type: "EMPLOYMENT_CONTRACT",
      label: "Contrato laboral",
      kind: "FILE",
      admin_only: true,
      description: "Contrato preparado por Talento Humano",
      original_filename: "contrato.pdf",
      size_bytes: 100,
      review_status: "APPROVED",
      odoo_sign_status: "NOT_PREPARED",
    };
    const staged = {
      ready: true,
      enabled: true,
      status: "NOT_PREPARED",
      staging_only: true,
      message: "Odoo Sign staging disponible.",
    };
    api.get.mockImplementation((url) => {
      if (url === "/employees") return Promise.resolve({
        data: { items: [{ id: "employee-1", first_name: "Ana", last_name: "Pérez" }] },
      });
      if (url === "/employee-documents/employees/employee-1")
        return Promise.resolve({ data: portfolio([contract]) });
      if (url === "/employee-documents/employees/employee-1/contract/sign")
        return Promise.resolve({ data: staged });
      return Promise.resolve({ data: portfolio([]) });
    });
    api.post.mockResolvedValue({
      data: {
        ...staged,
        ready: false,
        status: "PREPARED",
        template_url: "https://odoo-staging.example.invalid/web#id=812&model=sign.template",
      },
    });
    render(<Documents />);
    await screen.findByRole("option", { name: "Ana Pérez" });
    fireEvent.change(screen.getByLabelText("Empleado a consultar"), {
      target: { value: "employee-1" },
    });
    const prepare = await screen.findByRole("button", { name: "Preparar en Odoo Sign" });
    await waitFor(() => expect(prepare).toBeEnabled());
    fireEvent.click(prepare);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/employee-documents/employees/employee-1/contract/sign/prepare",
      { confirm: true },
    ));
    expect(await screen.findByRole("link", { name: /Abrir plantilla en Odoo staging/i }))
      .toHaveAttribute("target", "_blank");
  });

  it("tracks already-linked signatures without requiring an Odoo request ID from HR", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1" } },
      hasPermission: (permission) => [
        "employee_documents.read_own",
        "employee_documents.read_all",
        "employee_documents.review",
      ].includes(permission),
    });
    const contract = {
      id: "contract-1", document_type: "EMPLOYMENT_CONTRACT",
      label: "Contrato laboral", description: "Contrato de prueba",
      admin_only: true, kind: "FILE", original_filename: "contrato.pdf",
      size_bytes: 200, review_status: "APPROVED", odoo_sign_status: "PREPARED",
    };
    const base = "/employee-documents/employees/employee-1/contract/sign/request";
    api.get.mockImplementation((url) => {
      if (url === "/employees") return Promise.resolve({
        data: { items: [{ id: "employee-1", first_name: "Ana", last_name: "Pérez" }] },
      });
      if (url === "/employee-documents/employees/employee-1")
        return Promise.resolve({ data: portfolio([contract]) });
      if (url === "/employee-documents/employees/employee-1/contract/sign")
        return Promise.resolve({ data: {
          template_url: "https://odoo-staging.example.invalid/web#id=812&model=sign.template",
          status: "PREPARED", ready: false,
        } });
      if (url === base) return Promise.resolve({ data: {
        linked: true, request_id: 139, status: "PARTIALLY_SIGNED",
        employee: "completed", representative: "sent",
      } });
      return Promise.resolve({ data: {} });
    });
    api.post.mockResolvedValue({ data: {
      linked: true, request_id: 139, status: "SIGNED",
      employee: "completed", representative: "completed",
    } });
    render(<Documents />);
    await screen.findByRole("option", { name: "Ana Pérez" });
    fireEvent.change(screen.getByLabelText("Empleado a consultar"), {
      target: { value: "employee-1" },
    });
    expect(await screen.findByText("Firma parcial")).toBeInTheDocument();
    expect(screen.getByText("Firmado")).toBeInTheDocument();
    expect(screen.queryByLabelText("ID de solicitud en Odoo staging")).not.toBeInTheDocument();
    expect(screen.queryByText("Vincular solicitud de prueba")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Actualizar estado de firmas" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(base + "/refresh"));
    expect(await screen.findByText("Firmada por ambas partes")).toBeInTheDocument();
  });

  it("displays request #140 as pending even if the dispatch status is stale UNKNOWN", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1" } },
      hasPermission: (permission) => [
        "employee_documents.read_all", "employee_documents.review",
      ].includes(permission),
    });
    const contract = {
      id: "contract-1", document_type: "EMPLOYMENT_CONTRACT",
      label: "Contrato laboral", description: "Contrato de prueba",
      admin_only: true, kind: "FILE", original_filename: "contrato.pdf",
      size_bytes: 200, review_status: "APPROVED", odoo_sign_status: "PREPARED",
    };
    const base = "/employee-documents/employees/employee-1/contract/sign/request";
    api.get.mockImplementation((url) => {
      if (url === "/employees") return Promise.resolve({
        data: { items: [{ id: "employee-1", first_name: "Ana", last_name: "Pérez" }] },
      });
      if (url === "/employee-documents/employees/employee-1")
        return Promise.resolve({ data: portfolio([contract]) });
      if (url === "/employee-documents/employees/employee-1/contract/sign")
        return Promise.resolve({ data: {
          template_url: "https://odoo-staging.example.invalid/web#id=812",
          status: "PREPARED", ready: false,
        } });
      if (url === base + "/send-status")
        return Promise.resolve({ data: { enabled: true, status: "UNKNOWN" } });
      if (url === base) return Promise.resolve({ data: {
        linked: true, request_id: 140, status: "PENDING_SIGNATURE",
        employee: "sent", representative: "sent",
        checked_at: "2026-10-19T19:27:18.679915+00:00",
        signed_pdf_archived: false,
      } });
      return Promise.resolve({ data: { archived: false } });
    });
    api.post.mockResolvedValue({ data: {
      linked: true, request_id: 140, status: "PARTIALLY_SIGNED",
      employee: "completed", representative: "sent",
      signed_pdf_archived: false,
    } });

    render(<Documents />);
    await screen.findByRole("option", { name: "Ana Pérez" });
    fireEvent.change(screen.getByLabelText("Empleado a consultar"), {
      target: { value: "employee-1" },
    });
    expect(await screen.findByText("Pendiente de firma")).toBeInTheDocument();
    expect(screen.getByText(/Solicitud de Odoo Sign #140/)).toBeInTheDocument();
    expect(screen.getAllByText("Solicitud enviada")).toHaveLength(2);
    expect(screen.queryByText("Resultado de envío incierto: no vuelvas a enviarlo.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reconciliar solicitud con Odoo" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enviar a Odoo Sign (prueba)" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Actualizar estado de firmas" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(base + "/refresh"));
    expect(await screen.findByText("Firma parcial")).toBeInTheDocument();
    expect(screen.getByText("Firmado")).toBeInTheDocument();
    expect(screen.getByText("Solicitud enviada")).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it("places two signature fields from the fictional PDF entirely in ADN360", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1" } },
      hasPermission: (p) => [
        "employee_documents.read_own", "employee_documents.read_all",
        "employee_documents.review",
      ].includes(p),
    });
    const contract = {
      id: "contract-1", document_type: "EMPLOYMENT_CONTRACT",
      label: "Contrato laboral", description: "Documento ficticio",
      admin_only: true, kind: "FILE",
      original_filename: "ADN360_contrato_ficticio_prueba_Odoo_Sign.pdf",
      size_bytes: 700, review_status: "APPROVED", odoo_sign_status: "PREPARED",
    };
    const fieldsPath = "/employee-documents/employees/employee-1/contract/sign/fields";
    api.get.mockImplementation((url) => {
      if (url === "/employees") return Promise.resolve({
        data: { items: [{ id: "employee-1", first_name: "Ana", last_name: "Pérez" }] },
      });
      if (url === "/employee-documents/employees/employee-1")
        return Promise.resolve({ data: portfolio([contract]) });
      if (url === "/employee-documents/employees/employee-1/contract/sign")
        return Promise.resolve({ data: {
          template_url: "https://odoo-staging.example.invalid/web#id=129",
          status: "PREPARED", ready: false,
        } });
      if (url === fieldsPath) return Promise.resolve({ data: {
        configured: false, can_apply: true, roles: ["Empleado", "Representante legal"],
      } });
      return Promise.resolve({ data: {} });
    });
    api.post.mockImplementation((url) => {
      if (url === fieldsPath) return Promise.resolve({
        data: { configured: true, can_apply: false },
      });
      return Promise.resolve({ data: {} });
    });
    render(<Documents />);
    await screen.findByRole("option", { name: "Ana Pérez" });
    fireEvent.change(screen.getByLabelText("Empleado a consultar"), {
      target: { value: "employee-1" },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Detectar dos campos de firma" }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(fieldsPath));
    fireEvent.click(await screen.findByRole("button", { name: "Colocar ambas firmas en Odoo" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      fieldsPath, { confirm: true },
    ));
    expect(await screen.findByText(/Ambas firmas obligatorias están configuradas/)).toBeInTheDocument();
    expect(screen.queryByLabelText("ID de solicitud en Odoo staging")).not.toBeInTheDocument();
  });

  it("requires staging preview and explicit confirmation before one-time Sign send", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1" } },
      hasPermission: (p) => [
        "employee_documents.read_own", "employee_documents.read_all", "employee_documents.review",
      ].includes(p),
    });
    const contract = {
      id: "contract-1", document_type: "EMPLOYMENT_CONTRACT",
      label: "Contrato laboral", description: "Contrato de prueba",
      admin_only: true, kind: "FILE", original_filename: "contrato.pdf",
      size_bytes: 200, review_status: "APPROVED", odoo_sign_status: "PREPARED",
    };
    const base = "/employee-documents/employees/employee-1/contract/sign/request";
    api.get.mockImplementation((url) => {
      if (url === "/employees") return Promise.resolve({
        data: { items: [{ id: "employee-1", first_name: "Ana", last_name: "Pérez" }] },
      });
      if (url === "/employee-documents/employees/employee-1")
        return Promise.resolve({ data: portfolio([contract]) });
      if (url === "/employee-documents/employees/employee-1/contract/sign")
        return Promise.resolve({ data: {
          template_url: "https://odoo-staging.example.invalid/web#id=812",
          status: "PREPARED", ready: false,
        } });
      if (url === base + "/send-status")
        return Promise.resolve({ data: { enabled: true, status: "NOT_SENT" } });
      if (url === base)
        return Promise.resolve({ data: { linked: false, request_id: null } });
      return Promise.resolve({ data: {} });
    });
    api.post.mockImplementation((url) => {
      if (url === base + "/automatic-preview") return Promise.resolve({ data: { validated: true } });
      if (url === base + "/automatic-send") return Promise.resolve({ data: {
        status: "SENT", request_id: 139,
      } });
      return Promise.resolve({ data: {} });
    });
    render(<Documents />);
    await screen.findByRole("option", { name: "Ana Pérez" });
    fireEvent.change(screen.getByLabelText("Empleado a consultar"), {
      target: { value: "employee-1" },
    });
    await screen.findByText("Firmantes de prueba configurados");
    expect(screen.queryByLabelText("ID de contacto de empleado ficticio")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("ID de solicitud en Odoo staging")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enviar a Odoo Sign (prueba)" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Validar solicitud antes de enviar" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      base + "/automatic-preview",
    ));
    const confirm = await screen.findByLabelText("Confirmo el envío único a contactos ficticios de Odoo staging");
    expect(screen.getByRole("button", { name: "Enviar a Odoo Sign (prueba)" })).toBeDisabled();
    fireEvent.click(confirm);
    fireEvent.click(screen.getByRole("button", { name: "Enviar a Odoo Sign (prueba)" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      base + "/automatic-send",
      { confirm: true },
    ));
    expect(await screen.findByText(/Solicitud de firma creada en Odoo staging/)).toBeInTheDocument();
  });

});
