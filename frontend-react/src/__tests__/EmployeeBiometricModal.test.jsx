// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EmployeeBiometricModal from "../components/EmployeeBiometricModal";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

import api from "../api/client";


const employee = {
  id: "employee-1",
  first_name: "Ana",
  last_name: "Pérez",
  email: "ana@asiati.com.co",
};


function mockPilotState({
  configured = false,
  eligible = false,
  faceCount = 0,
  consentStatus = "PENDING",
  mobileLinked = false,
} = {}) {
  api.get.mockImplementation((url) => {
    if (url === "/talent-id/sites") {
      return Promise.resolve({
        data: {
          items: [
            {
              id: "site-1",
              name: "Bogotá Principal",
              code: "BOG",
              timezone: "America/Bogota",
              active: true,
            },
          ],
        },
      });
    }
    if (url === "/talent-id/schedules") {
      return Promise.resolve({
        data: {
          items: [
            {
              id: "schedule-1",
              name: "Administrativo",
              start_time: "08:30:00",
              end_time: "18:00:00",
              tolerance_minutes: 10,
              active: true,
            },
          ],
        },
      });
    }
    if (url === "/talent-id/employees/employee-1/attendance") {
      return Promise.resolve({
        data: {
          employee_id: "employee-1",
          configured,
          site_id: configured ? "site-1" : null,
          schedule_id: configured ? "schedule-1" : null,
          attendance_eligible: eligible,
        },
      });
    }
    if (url === "/talent-id/employees/employee-1/biometrics") {
      return Promise.resolve({
        data: {
          employee_id: "employee-1",
          enrolled: faceCount > 0,
          provider: faceCount > 0 ? "aws_rekognition" : null,
          face_count: faceCount,
          active: faceCount > 0,
          enrolled_at: faceCount > 0 ? "2026-10-05T14:00:00+00:00" : null,
        },
      });
    }
    if (url === "/talent-id/employees/employee-1/consent") {
      return Promise.resolve({
        data: {
          employee_id: "employee-1",
          status: consentStatus,
          signed_at: consentStatus === "PENDING" ? null : "2026-10-05T13:55:00+00:00",
          document_version: "1.0",
          has_signed_document: consentStatus !== "PENDING",
        },
      });
    }
    if (url === "/talent-id/employees/employee-1/mobile-devices") {
      return Promise.resolve({
        data: {
          items: mobileLinked
            ? [{
                id: "mobile-1",
                employee_id: "employee-1",
                label: "Mi celular",
                active: true,
                created_at: "2026-10-05T13:50:00+00:00",
                last_used_at: null,
              }]
            : [],
          total: mobileLinked ? 1 : 0,
        },
      });
    }
    return Promise.reject(new Error(`Unexpected GET ${url}`));
  });
}


describe("EmployeeBiometricModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("configures attendance before biometric enrollment", async () => {
    mockPilotState();
    api.put.mockResolvedValue({
      data: {
        employee_id: "employee-1",
        site_id: "site-1",
        schedule_id: "schedule-1",
        attendance_eligible: true,
      },
    });

    render(
      <EmployeeBiometricModal
        employee={employee}
        open
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Biometría y asistencia" })).toBeInTheDocument();
    expect(screen.getByLabelText("Sede")).toHaveValue("site-1");
    expect(screen.getByLabelText("Horario")).toHaveValue("schedule-1");

    fireEvent.click(screen.getByLabelText(/Incluir empleado en reportes de asistencia/i));
    fireEvent.click(screen.getByRole("button", { name: "Guardar asistencia" }));

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        "/talent-id/employees/employee-1/attendance",
        {
          site_id: "site-1",
          schedule_id: "schedule-1",
          attendance_eligible: true,
        },
      );
    });
    expect(await screen.findByText("Configuración de asistencia guardada.")).toBeInTheDocument();
  });

  it("uploads an authorized image and becomes kiosk-ready with two references", async () => {
    mockPilotState({
      configured: true,
      eligible: true,
      faceCount: 1,
      consentStatus: "AUTHORIZED",
    });
    api.post.mockResolvedValue({
      data: {
        employee_id: "employee-1",
        provider: "aws_rekognition",
        face_count: 2,
        active: true,
        enrolled_at: "2026-10-05T14:05:00+00:00",
      },
    });

    render(
      <EmployeeBiometricModal
        employee={employee}
        open
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Ana Pérez");

    const file = new File(["jpeg-bytes"], "ana-perez.jpg", { type: "image/jpeg" });
    fireEvent.change(screen.getByLabelText("Fotografía del empleado"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Agregar otra fotografía" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledTimes(1);
      expect(api.post.mock.calls[0][0]).toBe(
        "/talent-id/employees/employee-1/biometrics/enroll",
      );
      expect(api.post.mock.calls[0][1]).toBeInstanceOf(FormData);
    });

    expect(await screen.findByText("Listo para kiosco")).toBeInTheDocument();
    expect(screen.getByText("Rostro agregado. Ya hay múltiples referencias para iniciar la prueba en kiosco.")).toBeInTheDocument();
  });


  it("blocks enrollment until the employee signs consent", async () => {
    mockPilotState({ configured: true, eligible: true, consentStatus: "PENDING" });

    render(
      <EmployeeBiometricModal
        employee={employee}
        open
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText(/autorización biométrica: pendiente/i)).toBeInTheDocument();
    expect(
      screen.getByText(/no es posible enrolar el rostro hasta que exista una autorización biométrica vigente/i),
    ).toBeInTheDocument();

    const file = new File(["jpeg-bytes"], "ana-perez.jpg", { type: "image/jpeg" });
    fireEvent.change(screen.getByLabelText("Fotografía del empleado"), {
      target: { files: [file] },
    });

    expect(screen.getByRole("button", { name: "Enrolar rostro" })).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("shows and revokes the linked non-biometric phone", async () => {
    mockPilotState({
      configured: true,
      eligible: true,
      consentStatus: "DENIED",
      mobileLinked: true,
    });
    api.delete.mockResolvedValue({ data: { revoked: true } });

    render(
      <EmployeeBiometricModal
        employee={employee}
        open
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText(/alternativa no biométrica: celular vinculado/i)).toBeInTheDocument();
    expect(screen.getByText("Listo para kiosco")).toBeInTheDocument();
    expect(screen.getByText("QR móvil")).toBeInTheDocument();
    expect(screen.getByText("Listo")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Revocar celular" }));

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith(
        "/talent-id/employees/employee-1/mobile-devices/mobile-1",
      );
    });
    expect(await screen.findByText(/celular revocado/i)).toBeInTheDocument();
  });


  it("rejects unsupported images before calling the backend", async () => {
    mockPilotState({ configured: true, eligible: true });

    render(
      <EmployeeBiometricModal
        employee={employee}
        open
        onClose={vi.fn()}
      />,
    );

    await screen.findByText("Ana Pérez");

    const file = new File(["not-an-image"], "employee.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Fotografía del empleado"), {
      target: { files: [file] },
    });

    expect(await screen.findByText("La fotografía debe ser JPEG o PNG.")).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });
});
