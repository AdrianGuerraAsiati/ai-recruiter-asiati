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
      report_events: 2,
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
        check_in_method: "REPORT",
        check_out_method: "REPORT",
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
    expect(screen.getByLabelText("Empleado", { selector: "#attendance-employee" })).toBeInTheDocument();
    expect(await screen.findByText("Ana Torres")).toBeInTheDocument();
    expect(screen.getByText("Llegada tarde")).toBeInTheDocument();
    expect(screen.getByText("+7 min")).toBeInTheDocument();
  });

  it("lets admins upload the biometric clock XLS report", async () => {
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
      if (url === "/talent-id/sites") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "site-1",
                name: "Bogotá Principal",
                code: "BOG",
                active: true,
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
    api.post.mockResolvedValueOnce({
      data: {
        filename: "REPORTE.xls",
        site_name: "Bogotá Principal",
        rows_total: 2188,
        source_users: 46,
        matched_employees: 45,
        imported_events: 2100,
        duplicate_events: 50,
        unsupported_rows: 18,
        unsupported_codes: { 2: 18 },
        unmatched_rows: 20,
        ambiguous_rows: 0,
        attendance_not_enabled_rows: 0,
        site_mismatch_rows: 0,
        unmatched_people: [],
        date_range: {
          from: "2025-12-20T06:57:45",
          to: "2026-01-16T14:31:02",
        },
      },
    });

    renderPage();

    const fileInput = await screen.findByLabelText("Reporte .xls");
    const file = new File(["fake-binary"], "REPORTE.xls", {
      type: "application/vnd.ms-excel",
    });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Cargar reporte" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledTimes(1);
    });

    const [url, body] = api.post.mock.calls[0];
    expect(url).toBe("/talent-id/attendance/import-report");
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("site_id")).toBe("site-1");
    expect(body.get("report").name).toBe("REPORTE.xls");

    expect(await screen.findByText("2188")).toBeInTheDocument();
    expect(screen.getByText(/2 \(18\)/)).toBeInTheDocument();
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
