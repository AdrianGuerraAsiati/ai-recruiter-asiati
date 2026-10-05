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

  it("lists employees and lets an admin open the create flow", async () => {
    renderPage();

    expect(await screen.findByText("Ana Pérez")).toBeInTheDocument();
    expect(screen.getByText("employee@asiati.com.co")).toBeInTheDocument();
    expect(screen.getByText("En progreso", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("42% completado")).toBeInTheDocument();
    expect(screen.getByText("Onboarding activos")).toBeInTheDocument();
    expect(screen.getByText("Onboarding completados")).toBeInTheDocument();
    expect(screen.getByText("Ingreso: 2026-09-24")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /crear empleado/i }));

    expect(screen.getByRole("heading", { name: "Crear empleado" })).toBeInTheDocument();
    expect(screen.getByLabelText("Rol inicial")).toBeInTheDocument();
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

  it("creates employees as EMPLOYEE from an admin session", async () => {
    api.post.mockResolvedValueOnce({
      data: {
        employee: {
          id: "new-employee",
          username: "lgomez",
          first_name: "Luis",
          last_name: "Gómez",
        },
        credentials: {
          username: "lgomez",
          temporary_password: "TempPass123",
          must_change_password: true,
        },
      },
    });
    renderPage();

    await screen.findByText("Ana Pérez");
    fireEvent.click(screen.getByRole("button", { name: /crear empleado/i }));

    fireEvent.change(screen.getByLabelText("Usuario de Talent"), { target: { value: "lgomez" } });
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Luis" } });
    fireEvent.change(screen.getByLabelText("Apellido"), { target: { value: "Gómez" } });
    fireEvent.change(screen.getByLabelText("Correo de contacto"), { target: { value: "luis@asiati.com.co" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear empleado" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/employees", expect.objectContaining({
        username: "lgomez",
        email: "luis@asiati.com.co",
        first_name: "Luis",
        last_name: "Gómez",
        hire_date: expect.any(String),
        role: "EMPLOYEE",
      }));
    });

    expect(
      await screen.findByRole("link", { name: `${window.location.origin}/` }),
    ).toHaveAttribute("href", `${window.location.origin}/`);
  });

  it("lets an admin edit name, cargo and role while onboarding stays automatic", async () => {
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
        },
      );
    });
  });

  it("shows ADMIN and EMPLOYEE as the only assignable roles", async () => {
    renderPage();

    await screen.findByText("Ana Pérez");
    fireEvent.click(screen.getByRole("button", { name: /crear empleado/i }));

    const roleSelect = screen.getByLabelText("Rol inicial");
    expect(Array.from(roleSelect.options).map((option) => option.value)).toEqual([
      "EMPLOYEE",
      "ADMIN",
    ]);
    expect(Array.from(roleSelect.options).map((option) => option.textContent)).toEqual([
      "Empleado",
      "Administrador",
    ]);
  });

  it("opens Talent ID pilot controls for an active employee", async () => {
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
                status: "ACTIVE",
                roles: ["EMPLOYEE"],
                onboarding_status: "NOT_REQUIRED",
              },
            ],
          },
        });
      }
      if (url === "/talent-id/sites") {
        return Promise.resolve({ data: { items: [] } });
      }
      if (url === "/talent-id/schedules") {
        return Promise.resolve({ data: { items: [] } });
      }
      if (url.endsWith("/attendance")) {
        return Promise.resolve({
          data: {
            configured: false,
            site_id: null,
            schedule_id: null,
            attendance_eligible: false,
          },
        });
      }
      if (url.endsWith("/biometrics")) {
        return Promise.resolve({
          data: {
            enrolled: false,
            face_count: 0,
            active: false,
            enrolled_at: null,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    renderPage();

    await screen.findByText("Ana Pérez");
    fireEvent.click(screen.getByRole("button", { name: "Talent ID" }));

    expect(
      await screen.findByRole("heading", { name: "Biometría y asistencia" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/debe existir al menos una sede y un horario activos/i),
    ).toBeInTheDocument();
  });

});
