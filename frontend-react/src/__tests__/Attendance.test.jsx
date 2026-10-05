// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Attendance from "../pages/Attendance";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
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
      <Attendance />
    </MemoryRouter>,
  );
}


function reportData() {
  return {
    range: { start_date: "2026-10-01", end_date: "2026-10-05", days: 5 },
    summary: {
      employees_with_activity: 1,
      days_with_activity: 1,
      check_ins: 1,
      check_outs: 1,
      late_arrivals: 1,
      incomplete_days: 0,
      on_time_rate: 0,
      average_worked_minutes: 480,
    },
    rows: [
      {
        employee_id: "employee-1",
        employee_name: "Ana Torres",
        employee_email: "ana@asiati.com.co",
        date: "2026-10-05",
        site_name: "Bogotá",
        schedule_name: "Administrativo",
        check_in: "2026-10-05T08:47:00-05:00",
        check_out: "2026-10-05T16:47:00-05:00",
        late_minutes: 7,
        worked_minutes: 480,
        status: "LATE",
      },
    ],
  };
}


describe("Attendance dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows all-team filters and daily detail to admins", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1", first_name: "Admin" } },
      hasPermission: (permission) => permission === "talent_id.attendance.read_all",
    });
    api.get.mockImplementation((url) => {
      if (url === "/employees") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "employee-1",
                first_name: "Ana",
                last_name: "Torres",
                email: "ana@asiati.com.co",
                status: "ACTIVE",
              },
            ],
          },
        });
      }
      if (url === "/talent-id/attendance/report") {
        return Promise.resolve({ data: reportData() });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });

    renderPage();

    expect(await screen.findByRole("heading", { name: "Asistencia del equipo" })).toBeInTheDocument();
    expect(screen.getByLabelText("Empleado")).toBeInTheDocument();
    expect(await screen.findByText("Ana Torres")).toBeInTheDocument();
    expect(screen.getByText("Llegada tarde")).toBeInTheDocument();
    expect(screen.getByText("+7 min")).toBeInTheDocument();
  });

  it("lets admins record an audited manual attendance contingency", async () => {
    useSession.mockReturnValue({
      principal: { profile: { id: "admin-1", first_name: "Admin" } },
      hasPermission: (permission) => (
        permission === "talent_id.attendance.read_all"
        || permission === "talent_id.manage"
      ),
    });
    api.get.mockImplementation((url) => {
      if (url === "/employees") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "employee-1",
                first_name: "Ana",
                last_name: "Torres",
                email: "ana@asiati.com.co",
                status: "ACTIVE",
              },
            ],
          },
        });
      }
      if (url === "/talent-id/attendance/report") {
        return Promise.resolve({ data: reportData() });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
    api.post.mockResolvedValue({
      data: {
        id: "manual-event-1",
        employee_id: "employee-1",
        event_type: "CHECK_IN",
        method: "MANUAL",
        created: true,
      },
    });

    renderPage();

    const employeeSelect = await screen.findByLabelText("Empleado", {
      selector: "#manual-attendance-employee",
    });
    fireEvent.change(employeeSelect, { target: { value: "employee-1" } });
    fireEvent.change(screen.getByLabelText("Motivo"), {
      target: { value: "Falla temporal del kiosco" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Registrar contingencia" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/attendance/manual",
        {
          employee_id: "employee-1",
          event_type: "check_in",
          reason: "Falla temporal del kiosco",
        },
      );
    });
    expect(await screen.findByText(/marcación manual registrada/i)).toBeInTheDocument();
  });

  it("shows only the own attendance view to employees", async () => {
    useSession.mockReturnValue({
      principal: {
        profile: {
          id: "employee-1",
          first_name: "Ana",
          last_name: "Torres",
        },
      },
      hasPermission: () => false,
    });
    api.get.mockResolvedValue({ data: reportData() });

    renderPage();

    expect(await screen.findByRole("heading", { name: "Mi asistencia" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Empleado")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        "/talent-id/attendance/report",
        expect.objectContaining({
          params: expect.objectContaining({
            start_date: expect.any(String),
            end_date: expect.any(String),
          }),
        }),
      );
    });
  });
});
