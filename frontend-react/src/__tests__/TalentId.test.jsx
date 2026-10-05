// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TalentId from "../pages/TalentId";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

import api from "../api/client";


function mockLists(devices = []) {
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
            {
              id: "site-2",
              name: "Medellín",
              code: "MDE",
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
    if (url === "/talent-id/devices") {
      return Promise.resolve({ data: { items: devices } });
    }
    if (url === "/employees") {
      return Promise.resolve({
        data: {
          items: [
            {
              id: "employee-1",
              first_name: "Ana",
              last_name: "Torres",
              email: "ana@asiati.com.co",
              job_title: "Analista",
              department: "Operaciones",
              status: "ACTIVE",
            },
          ],
        },
      });
    }
    if (url === "/talent-id/employees/employee-1/attendance") {
      return Promise.resolve({
        data: {
          employee_id: "employee-1",
          configured: true,
          site_id: "site-1",
          schedule_id: "schedule-1",
          attendance_eligible: true,
        },
      });
    }
    if (url === "/talent-id/employees/employee-1/biometrics") {
      return Promise.resolve({
        data: {
          employee_id: "employee-1",
          enrolled: false,
          face_count: 0,
          active: false,
          enrolled_at: null,
        },
      });
    }
    return Promise.reject(new Error(`Unexpected GET ${url}`));
  });
}


describe("Talent ID administration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLists();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it("shows the current pilot infrastructure", async () => {
    render(<TalentId />);

    expect((await screen.findAllByText("Bogotá Principal")).length).toBeGreaterThan(0);
    expect(screen.getByText("Administrativo")).toBeInTheDocument();
    expect(screen.getByText("Sedes activas")).toBeInTheDocument();
    expect(screen.getByText("Horarios activos")).toBeInTheDocument();
    expect(screen.getByText("Kioscos activos")).toBeInTheDocument();
    expect(screen.getByText("Empleados activos")).toBeInTheDocument();
    expect(screen.getByText("Fotos para reconocimiento facial")).toBeInTheDocument();
    expect(screen.getByText("Credenciales de kioscos")).toBeInTheDocument();
  });

  it("creates a site with the configured timezone", async () => {
    api.post.mockResolvedValue({ data: { id: "site-3" } });
    render(<TalentId />);

    await screen.findAllByText("Bogotá Principal");

    fireEvent.change(screen.getByLabelText("Nombre de sede"), {
      target: { value: "Cali" },
    });
    fireEvent.change(screen.getByLabelText("Código"), {
      target: { value: "clo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear sede" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/sites",
        {
          name: "Cali",
          code: "CLO",
          timezone: "America/Bogota",
        },
      );
    });
  });

  it("selects an employee and uploads multiple recognition photos", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/talent-id/employees/employee-1/biometrics/enroll") {
        return Promise.resolve({
          data: {
            employee_id: "employee-1",
            provider: "aws_rekognition",
            face_count: 2,
            active: true,
            enrolled_at: "2026-10-05T15:00:00Z",
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    api.get.mockImplementation((url) => {
      if (url === "/talent-id/sites") {
        return Promise.resolve({ data: { items: [{ id: "site-1", name: "Bogotá Principal", code: "BOG", timezone: "America/Bogota", active: true }] } });
      }
      if (url === "/talent-id/schedules") {
        return Promise.resolve({ data: { items: [{ id: "schedule-1", name: "Administrativo", start_time: "08:30:00", end_time: "18:00:00", tolerance_minutes: 10, active: true }] } });
      }
      if (url === "/talent-id/devices") return Promise.resolve({ data: { items: [] } });
      if (url === "/employees") {
        return Promise.resolve({ data: { items: [{ id: "employee-1", first_name: "Ana", last_name: "Torres", email: "ana@asiati.com.co", job_title: "Analista", department: "Operaciones", status: "ACTIVE" }] } });
      }
      if (url === "/talent-id/employees/employee-1/attendance") {
        return Promise.resolve({ data: { configured: true, attendance_eligible: true, site_id: "site-1", schedule_id: "schedule-1" } });
      }
      if (url === "/talent-id/employees/employee-1/biometrics") {
        return Promise.resolve({ data: { enrolled: true, face_count: 2, active: true, enrolled_at: "2026-10-05T15:00:00Z" } });
      }
      if (url === "/talent-id/employees/employee-1/consent") {
        return Promise.resolve({
          data: {
            status: "AUTHORIZED",
            signed_at: "2026-10-05T14:55:00Z",
            document_version: "1.1",
            has_signed_document: true,
          },
        });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });

    render(<TalentId />);
    await screen.findByText("Fotos para reconocimiento facial");

    fireEvent.change(screen.getByLabelText("Empleado"), {
      target: { value: "employee-1" },
    });

    expect(await screen.findByText("Ana Torres")).toBeInTheDocument();
    expect(screen.getByText("Asistencia habilitada")).toBeInTheDocument();

    const photoOne = new File(["face-one"], "frontal.jpg", { type: "image/jpeg" });
    const photoTwo = new File(["face-two"], "lateral.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Fotos del empleado"), {
      target: { files: [photoOne, photoTwo] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Agregar fotos" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledTimes(2);
    });
    expect(api.post.mock.calls[0][0]).toBe("/talent-id/employees/employee-1/biometrics/enroll");
    expect(api.post.mock.calls[0][1]).toBeInstanceOf(FormData);
    expect(await screen.findByText("2 fotos registradas para reconocimiento facial.")).toBeInTheDocument();
  });

  it("blocks admin enrollment when employee consent is pending", async () => {
    render(<TalentId />);
    await screen.findByText("Fotos para reconocimiento facial");

    fireEvent.change(screen.getByLabelText("Empleado"), {
      target: { value: "employee-1" },
    });

    expect(await screen.findByText(/Autorización biométrica: Pendiente/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Talento Humano no puede autorizar en su nombre/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Fotos del empleado")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Agregar fotos" })).toBeDisabled();
  });

  it("lets an admin complete a missing employee name from Talent ID", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/talent-id/sites") {
        return Promise.resolve({ data: { items: [{ id: "site-1", name: "Bogotá Principal", active: true }] } });
      }
      if (url === "/talent-id/schedules") {
        return Promise.resolve({ data: { items: [{ id: "schedule-1", name: "Administrativo", start_time: "08:30:00", end_time: "18:00:00", active: true }] } });
      }
      if (url === "/talent-id/devices") return Promise.resolve({ data: { items: [] } });
      if (url === "/employees") {
        return Promise.resolve({
          data: {
            items: [{
              id: "employee-missing-name",
              email: "talentohumano@asiati.com.co",
              first_name: null,
              last_name: null,
              job_title: "Talento Humano",
              status: "ACTIVE",
            }],
          },
        });
      }
      if (url === "/talent-id/employees/employee-missing-name/attendance") {
        return Promise.resolve({ data: { configured: true, attendance_eligible: true, site_id: "site-1", schedule_id: "schedule-1" } });
      }
      if (url === "/talent-id/employees/employee-missing-name/biometrics") {
        return Promise.resolve({ data: { enrolled: false, face_count: 0, active: false } });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
    api.put.mockResolvedValue({
      data: {
        id: "employee-missing-name",
        first_name: "Talento",
        last_name: "Humano",
      },
    });

    render(<TalentId />);

    await screen.findByText("Fotos para reconocimiento facial");
    const employeeSelect = screen.getByLabelText("Empleado");
    expect(Array.from(employeeSelect.options).map((option) => option.textContent)).toContain(
      "Sin nombre · talentohumano@asiati.com.co · Talento Humano",
    );

    fireEvent.change(employeeSelect, { target: { value: "employee-missing-name" } });
    expect(await screen.findByText("Completar nombre del empleado")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Nombre", { selector: "#talent-id-employee-first-name" }), {
      target: { value: "Talento" },
    });
    fireEvent.change(screen.getByLabelText("Apellido", { selector: "#talent-id-employee-last-name" }), {
      target: { value: "Humano" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar nombre" }));

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        "/employees/employee-missing-name",
        { first_name: "Talento", last_name: "Humano" },
      );
    });
  });

  it("configures pending attendance inline before biometric upload", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/talent-id/sites") {
        return Promise.resolve({ data: { items: [{ id: "site-1", name: "Bogotá Principal", code: "BOG", active: true }] } });
      }
      if (url === "/talent-id/schedules") {
        return Promise.resolve({ data: { items: [{ id: "schedule-1", name: "Administrativo", start_time: "08:30:00", end_time: "18:00:00", active: true }] } });
      }
      if (url === "/talent-id/devices") return Promise.resolve({ data: { items: [] } });
      if (url === "/employees") {
        return Promise.resolve({ data: { items: [{ id: "employee-1", first_name: "Ana", last_name: "Torres", email: "ana@asiati.com.co", status: "ACTIVE" }] } });
      }
      if (url === "/talent-id/employees/employee-1/attendance") {
        return Promise.resolve({ data: { configured: false, site_id: null, schedule_id: null, attendance_eligible: false } });
      }
      if (url === "/talent-id/employees/employee-1/biometrics") {
        return Promise.resolve({ data: { enrolled: false, face_count: 0, active: false } });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
    api.put.mockResolvedValue({
      data: {
        employee_id: "employee-1",
        site_id: "site-1",
        schedule_id: "schedule-1",
        attendance_eligible: true,
      },
    });

    render(<TalentId />);
    await screen.findByText("Fotos para reconocimiento facial");
    fireEvent.change(screen.getByLabelText("Empleado"), { target: { value: "employee-1" } });

    expect(await screen.findByText("Configuración de marcación")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Habilitar marcación de asistencia/i));
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
    expect(await screen.findByText("Asistencia habilitada")).toBeInTheDocument();
  });

  it("provisions a kiosk and has one copy button per credential", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/talent-id/devices") {
        return Promise.resolve({
          data: {
            device: {
              id: "device-1",
              site_id: "site-1",
              name: "Recepción",
              active: true,
            },
            device_secret: "one-time-secret",
            secret_shown_once: true,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<TalentId />);

    await screen.findAllByText("Bogotá Principal");
    fireEvent.change(screen.getByLabelText("Sede del kiosco"), {
      target: { value: "site-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generar credenciales" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/devices",
        {
          site_id: "site-1",
          name: "Recepción",
        },
      );
    });

    expect(await screen.findByText("one-time-secret")).toBeInTheDocument();
    expect(screen.getByText("device-1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copiar ID" }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("device-1");
    });

    fireEvent.click(screen.getByRole("button", { name: "Copiar secret" }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("one-time-secret");
    });
  });

  it("edits a registered kiosk and can rotate its secret", async () => {
    mockLists([
      {
        id: "device-existing",
        site_id: "site-1",
        name: "Recepción vieja",
        active: true,
        last_seen_at: null,
      },
    ]);
    api.patch.mockResolvedValue({ data: {} });
    api.post.mockImplementation((url) => {
      if (url === "/talent-id/devices/device-existing/rotate-secret") {
        return Promise.resolve({
          data: {
            device: {
              id: "device-existing",
              site_id: "site-2",
              name: "Recepción norte",
              active: true,
            },
            device_secret: "rotated-secret",
            secret_shown_once: true,
            rotated: true,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<TalentId />);
    expect(await screen.findByText("Recepción vieja")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    fireEvent.change(screen.getByLabelText("Nombre"), {
      target: { value: "Recepción norte" },
    });
    fireEvent.change(screen.getByLabelText("Sede"), {
      target: { value: "site-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith(
        "/talent-id/devices/device-existing",
        {
          site_id: "site-2",
          name: "Recepción norte",
        },
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Regenerar secret" }));
    fireEvent.click(screen.getByRole("button", { name: "Sí, regenerar" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/devices/device-existing/rotate-secret",
      );
    });
    expect(await screen.findByText("rotated-secret")).toBeInTheDocument();
  });

  it("revokes a kiosk through the delete credential action", async () => {
    mockLists([
      {
        id: "device-delete",
        site_id: "site-1",
        name: "Tablet temporal",
        active: true,
        last_seen_at: null,
      },
    ]);
    api.delete.mockResolvedValue({ data: { revoked: true } });

    render(<TalentId />);
    expect(await screen.findByText("Tablet temporal")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Eliminar acceso" }));
    fireEvent.click(screen.getByRole("button", { name: "Sí, eliminar acceso" }));

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith(
        "/talent-id/devices/device-delete",
      );
    });
  });
});
