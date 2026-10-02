// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import JobHireModal from "../features/jobs/JobHireModal";

const FORM = {
  username: "ana.perez",
  email: "ana@test.com",
  first_name: "Ana",
  last_name: "Pérez",
  job_title: "Backend Developer",
  department: "Tecnología",
  hire_date: "2026-09-28",
};

function renderModal(overrides = {}) {
  const props = {
    candidate: { candidate_id: "c-1", name: "Ana Pérez" },
    jobTitle: "Backend Developer",
    form: FORM,
    hiring: false,
    error: "",
    onClose: vi.fn(),
    onFormChange: vi.fn(),
    onSubmit: vi.fn((event) => event.preventDefault()),
    ...overrides,
  };
  render(<JobHireModal {...props} />);
  return props;
}

describe("JobHireModal", () => {
  it("renders nothing without a candidate", () => {
    const { container } = render(
      <JobHireModal
        candidate={null}
        jobTitle="Vacante"
        form={FORM}
        hiring={false}
        error=""
        onClose={vi.fn()}
        onFormChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders candidate, vacancy and controlled form values", () => {
    renderModal();

    expect(screen.getByText("Ana Pérez")).toBeInTheDocument();
    expect(screen.getByText("Backend Developer")).toBeInTheDocument();
    expect(screen.getByLabelText("Nombre")).toHaveValue("Ana");
    expect(screen.getByLabelText("Usuario de Talent")).toHaveValue("ana.perez");
    expect(screen.getByLabelText("Correo de contacto")).toHaveValue("ana@test.com");
    expect(screen.getByLabelText("Fecha de ingreso")).toHaveValue("2026-09-28");
  });

  it("delegates field changes and submit", () => {
    const props = renderModal();

    fireEvent.change(screen.getByLabelText("Área"), {
      target: { value: "Producto" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Confirmar contratación" }).closest("form"));

    expect(props.onFormChange).toHaveBeenCalledWith("department", "Producto");
    expect(props.onSubmit).toHaveBeenCalledTimes(1);
  });

  it("renders errors and disables controls while hiring", () => {
    renderModal({ hiring: true, error: "No se pudo contratar." });

    expect(screen.getByRole("alert")).toHaveTextContent("No se pudo contratar.");
    expect(screen.getByRole("button", { name: "Cerrar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Contratando…" })).toBeDisabled();
  });

  it("delegates cancel when idle", () => {
    const props = renderModal();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });
});
