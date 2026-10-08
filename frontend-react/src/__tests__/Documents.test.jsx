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
    expect(screen.getByText("En revisión")).toBeInTheDocument();
    expect(screen.getByText("Requiere cambios")).toBeInTheDocument();
    expect(screen.getByText("Agrega la ciudad.")).toBeInTheDocument();
    expect(screen.getByText("Aprobados")).toBeInTheDocument();
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
});
