// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TrainingAssignmentsPanel from "../features/training/TrainingAssignmentsPanel";

function renderPanel(overrides = {}) {
  const props = {
    course: { status: "PUBLISHED" },
    employees: [
      {
        id: "employee-1",
        first_name: "Ana",
        last_name: "Pérez",
        email: "ana@example.com",
      },
    ],
    employeeId: "",
    onEmployeeChange: vi.fn(),
    onAssignCourse: vi.fn((event) => event.preventDefault()),
    saving: false,
    canAssign: true,
    canViewResults: true,
    assignments: [],
    ...overrides,
  };

  render(<TrainingAssignmentsPanel {...props} />);
  return props;
}

describe("TrainingAssignmentsPanel", () => {
  it("keeps employee selection and assignment controlled by the parent", () => {
    const props = renderPanel();

    fireEvent.change(screen.getByLabelText("Empleado para asignar"), {
      target: { value: "employee-1" },
    });
    expect(props.onEmployeeChange).toHaveBeenCalledWith("employee-1");

    fireEvent.submit(screen.getByRole("button", { name: "Asignar curso" }).closest("form"));
    expect(props.onAssignCourse).toHaveBeenCalledTimes(1);
  });

  it("blocks assignment while the course is unpublished", () => {
    renderPanel({ course: { status: "DRAFT" } });

    expect(screen.getByRole("button", { name: "Asignar curso" })).toBeDisabled();
    expect(screen.getByText("Publica el curso antes de asignarlo.")).toBeInTheDocument();
  });

  it("shows automatic distribution for the system-managed onboarding", () => {
    renderPanel({
      course: {
        status: "PUBLISHED",
        managed_by_system: true,
      },
    });

    expect(screen.getByRole("heading", { name: "Progreso del equipo" })).toBeInTheDocument();
    expect(
      screen.getByText(/se asigna automáticamente a todos los empleados activos/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Empleado para asignar")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Asignar curso" })).not.toBeInTheDocument();
  });

  it("renders assignment progress and quiz results when permitted", () => {
    renderPanel({
      assignments: [
        {
          id: "assignment-1",
          status: "COMPLETED",
          employee: {
            first_name: "Luis",
            last_name: "Gómez",
            email: "luis@example.com",
            job_title: "Analista",
            department: "Operaciones",
          },
          course: { progress_percent: 100 },
          quiz_result: {
            latest_score: 92,
            passed: true,
            attempt_count: 1,
          },
        },
      ],
    });

    expect(screen.getByText("Luis Gómez")).toBeInTheDocument();
    expect(screen.getByText("Analista")).toBeInTheDocument();
    expect(screen.getByText("Quiz: 92% · aprobado")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("Completado")).toBeInTheDocument();
  });

  it("hides results when the permission is absent", () => {
    renderPanel({
      canViewResults: false,
      assignments: [
        {
          id: "assignment-1",
          status: "IN_PROGRESS",
          employee: {
            first_name: "Luis",
            last_name: "Gómez",
            email: "luis@example.com",
          },
          course: { progress_percent: 40 },
          quiz_result: null,
        },
      ],
    });

    expect(screen.queryByText("Luis Gómez")).not.toBeInTheDocument();
    expect(screen.queryByText("40%")).not.toBeInTheDocument();
  });
});
