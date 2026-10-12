// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Employees from "../pages/Employees";

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


function renderPage() {
  return render(
    <MemoryRouter>
      <Employees />
    </MemoryRouter>,
  );
}


describe("Employees administration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSession.mockReturnValue({
      hasRole: (role) => role === "ADMIN",
      hasPermission: (permission) => [
        "training.results.read",
        "employees.roles.manage",
        "talent_id.manage",
      ].includes(permission),
    });
    api.get.mockResolvedValue({
      data: {
        items: [
          {
            id: "employee-1",
            email: "employee@asiati.com.co",
            first_name: "Ana",
            last_name: "Pérez",
            job_title: "Comercial",
            department: "Ventas",
            country_code: "CO",
            company_name: "ASIATI Colombia",
            hire_date: "2026-09-24",
            onboarding_status: "IN_PROGRESS",
            onboarding_required: true,
            onboarding: {
              assignment_id: "assignment-1",
              course_id: "course-1",
              course_title: "Onboarding ASIATI",
              progress_percent: 42,
            },
            status: "ACTIVE",
            roles: ["EMPLOYEE"],
          },
        ],
      },
    });
  });

  it("lists employees and directs hiring to the Applications view", async () => {
    renderPage();

    expect(await screen.findByText("Ana Pérez")).toBeInTheDocument();
    expect(screen.getByText("employee@asiati.com.co")).toBeInTheDocument();
    expect(screen.getByText("En progreso", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("42% completado")).toBeInTheDocument();
    expect(screen.getByText("Onboarding activos")).toBeInTheDocument();
    expect(screen.getByText("Onboarding completados")).toBeInTheDocument();
    expect(screen.getByText("Ingreso: 2026-09-24")).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "Crear empleado" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir a postulaciones para contratar" })).toHaveAttribute("href", "/applications");
  });

  it("filters the directory by onboarding status", async () => {
    renderPage();
    await screen.findByText("Ana Pérez");

    fireEvent.change(screen.getByLabelText("Filtrar por onboarding"), {
      target: { value: "IN_PROGRESS" },
    });

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        "/employees",
        {
          params: {
            onboarding_status: "IN_PROGRESS",
          },
        },
      );
    });
  });

  it("opens detailed onboarding progress for HR", async () => {
    const employeeResponse = {
      items: [
        {
          id: "employee-1",
          email: "employee@asiati.com.co",
          first_name: "Ana",
          last_name: "Pérez",
          job_title: "Comercial",
          department: "Ventas",
          hire_date: "2026-09-24",
          onboarding_status: "IN_PROGRESS",
          onboarding_required: true,
          onboarding: {
            assignment_id: "assignment-1",
            course_id: "course-1",
            course_title: "Onboarding ASIATI",
            progress_percent: 42,
          },
          status: "ACTIVE",
          roles: ["EMPLOYEE"],
        },
      ],
    };
    api.get.mockImplementation((url) => {
      if (url === "/employees") {
        return Promise.resolve({ data: employeeResponse });
      }
      if (url === "/training/courses/course-1/assignments/employee-1") {
        return Promise.resolve({
          data: {
            assignment_id: "assignment-1",
            assignment_status: "ASSIGNED",
            course: {
              id: "course-1",
              title: "Onboarding ASIATI",
              progress_percent: 42,
              completed_lessons: 8,
              lesson_count: 19,
              modules: [
                {
                  id: "module-1",
                  title: "Módulo 1 · Bienvenida a ASIATI",
                  completed_lessons: 1,
                  lesson_count: 1,
                  progress_percent: 100,
                },
                {
                  id: "module-2",
                  title: "Módulo 2 · Conoce ASIATI",
                  completed_lessons: 0,
                  lesson_count: 1,
                  progress_percent: 0,
                },
              ],
            },
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    renderPage();

    await screen.findByText("Ana Pérez");
    fireEvent.click(screen.getByRole("button", { name: "Ver detalle" }));

    expect(
      await screen.findByRole("heading", { name: "Ana Pérez" }),
    ).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(
      "/training/courses/course-1/assignments/employee-1",
    );
    expect(screen.getByText("8/19")).toBeInTheDocument();
    expect(screen.getByText("Módulo 1 · Bienvenida a ASIATI")).toBeInTheDocument();
    expect(screen.getByText("Módulo 2 · Conoce ASIATI")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("does not provide a direct employee creation action", async () => {
    renderPage();
    await screen.findByText("Ana Pérez");
    expect(screen.queryByRole("button", { name: "Crear empleado" })).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("lets an admin edit profile and fingerprint-report attendance together", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/employees") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "employee-1",
                email: "employee@asiati.com.co",
                first_name: "Ana",
                last_name: "Pérez",
                job_title: "Comercial",
                department: "Ventas",
                hire_date: "2026-09-24",
                onboarding_status: "IN_PROGRESS",
                onboarding_required: true,
                onboarding: null,
                status: "ACTIVE",
                roles: ["EMPLOYEE"],
              },
            ],
          },
        });
      }
      if (url === "/talent-id/sites") {
        return Promise.resolve({
          data: { items: [{ id: "site-1", name: "Bogotá Principal", code: "BOG", active: true }] },
        });
      }
      if (url === "/talent-id/schedules") {
        return Promise.resolve({
          data: { items: [{ id: "schedule-1", name: "Administrativo", start_time: "08:30:00", end_time: "18:00:00", active: true }] },
        });
      }
      if (url === "/talent-id/employees/employee-1/attendance") {
        return Promise.resolve({
          data: {
            configured: false,
            site_id: null,
            schedule_id: null,
            attendance_eligible: false,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.put.mockResolvedValue({ data: {} });
    renderPage();

    await screen.findByText("Ana Pérez");
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));

    expect(screen.getByRole("heading", { name: "Editar integrante" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Nombre", { selector: "#employee-edit-first-name" }), {
      target: { value: "Ana María" },
    });
    fireEvent.change(screen.getByLabelText("Apellido", { selector: "#employee-edit-last-name" }), {
      target: { value: "Pérez Gómez" },
    });
    fireEvent.change(screen.getByLabelText("Cargo"), {
      target: { value: "Líder comercial" },
    });
    fireEvent.change(screen.getByLabelText("Rol"), {
      target: { value: "ADMIN" },
    });
    expect(screen.getByText("Asignación automática")).toBeInTheDocument();
    expect(await screen.findByText("Configuración de asistencia")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Incluir empleado en reportes de asistencia/i));
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        "/employees/employee-1/role",
        { role: "ADMIN" },
      );
      expect(api.put).toHaveBeenCalledWith(
        "/employees/employee-1",
        {
          first_name: "Ana María",
          last_name: "Pérez Gómez",
          job_title: "Líder comercial",
          department: "Ventas",
          country_code: null,
          company_name: null,
        },
      );
      expect(api.put).toHaveBeenCalledWith(
        "/talent-id/employees/employee-1/attendance",
        {
          site_id: "site-1",
          schedule_id: "schedule-1",
          attendance_eligible: true,
        },
      );
    });
  });

  it("still allows admins to change the role of an existing employee", async () => {
    renderPage();
    await screen.findByText("Ana Pérez");
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    const roleSelect = screen.getByLabelText("Rol");
    expect(Array.from(roleSelect.options).map((option) => option.value)).toEqual([
      "EMPLOYEE", "ADMIN",
    ]);
  });

  it("shows and edits employee country and company", async () => {
    renderPage();
    await screen.findByText("Ana Pérez");

    expect(screen.getByText(/Ventas · ASIATI Colombia · Colombia/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    fireEvent.change(screen.getByLabelText("País"), {
      target: { value: "CL" },
    });
    fireEvent.change(screen.getByLabelText("Empresa"), {
      target: { value: "ASIATI Chile" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        "/employees/employee-1",
        expect.objectContaining({
          country_code: "CL",
          company_name: "ASIATI Chile",
        }),
      );
    });
  });

});
