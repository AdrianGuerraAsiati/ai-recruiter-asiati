// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import JobDeleteModal from "../features/jobs/JobDeleteModal";

const JOB = {
  job_id: "job-1",
  title: "Backend Developer",
  candidate_count: 2,
};

function renderModal(overrides = {}) {
  const props = {
    job: JOB,
    deleting: false,
    error: "",
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    ...overrides,
  };

  render(<JobDeleteModal {...props} />);
  return props;
}

describe("JobDeleteModal", () => {
  it("renders nothing without a target job", () => {
    const { container } = render(
      <JobDeleteModal
        job={null}
        deleting={false}
        error=""
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders target information and delegates both delete modes", () => {
    const props = renderModal();

    expect(screen.getByText("Backend Developer")).toBeInTheDocument();
    expect(screen.getByText("Esta vacante tiene 2 candidatos asignados."))
      .toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Borrar solo la vacante/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Borrar vacante y candidatos/i }));

    expect(props.onConfirm).toHaveBeenNthCalledWith(1, false);
    expect(props.onConfirm).toHaveBeenNthCalledWith(2, true);
  });

  it("disables destructive and close controls while deleting", () => {
    renderModal({ deleting: true });

    expect(screen.getByRole("button", { name: /^Borrar solo la vacante/i }))
      .toBeDisabled();
    expect(screen.getByRole("button", { name: /^Borrar vacante y candidatos/i }))
      .toBeDisabled();
    expect(screen.getByRole("button", { name: "Cerrar modal de eliminación" }))
      .toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
    expect(screen.getByText("Eliminando…")).toBeInTheDocument();
  });

  it("disables deleting candidates when the vacancy has none", () => {
    renderModal({ job: { ...JOB, candidate_count: 0 } });

    expect(screen.getByRole("button", { name: /^Borrar vacante y candidatos/i }))
      .toBeDisabled();
  });

  it("renders errors and delegates cancel", () => {
    const props = renderModal({ error: "No se pudo eliminar." });

    expect(screen.getByRole("alert")).toHaveTextContent("No se pudo eliminar.");
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(props.onClose).toHaveBeenCalledTimes(1);
  });
});
