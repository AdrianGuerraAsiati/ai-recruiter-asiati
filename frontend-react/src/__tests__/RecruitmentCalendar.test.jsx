// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RecruitmentCalendar from "../pages/RecruitmentCalendar";

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


describe("RecruitmentCalendar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSession.mockReturnValue({
      hasPermission: (permission) => [
        "candidates.read",
        "candidates.manage",
      ].includes(permission),
    });

    const startsAt = new Date();
    startsAt.setDate(startsAt.getDate() + 1);
    startsAt.setHours(10, 0, 0, 0);
    const endsAt = new Date(startsAt);
    endsAt.setMinutes(endsAt.getMinutes() + 30);

    api.get.mockImplementation((url) => {
      if (url === "/recruitment-calendar/events") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "event-1",
                job_id: "job-1",
                candidate_id: "candidate-1",
                kind: "PHONE_CALL",
                starts_at: startsAt.toISOString(),
                ends_at: endsAt.toISOString(),
                location: null,
                notes: null,
                status: "SCHEDULED",
                candidate: {
                  candidate_id: "candidate-1",
                  name: "Ana Pérez",
                  email: "ana@example.com",
                },
                job: {
                  job_id: "job-1",
                  title: "Ejecutivo Comercial SR",
                },
              },
            ],
          },
        });
      }
      if (url === "/recruitment-calendar/applications") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "application-1",
                application_status: "SELECTED",
                candidate: {
                  candidate_id: "candidate-1",
                  name: "Ana Pérez",
                  email: "ana@example.com",
                },
                job: {
                  job_id: "job-1",
                  title: "Ejecutivo Comercial SR",
                },
              },
            ],
          },
        });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
    api.post.mockResolvedValue({ data: { id: "event-2" } });
    api.put.mockResolvedValue({ data: { id: "event-1" } });
  });

  it("shows scheduled recruiting events and upcoming context", async () => {
    render(<RecruitmentCalendar />);

    expect(await screen.findByRole("heading", { name: "Agenda de selección" })).toBeInTheDocument();
    expect((await screen.findAllByText("Ana Pérez")).length).toBeGreaterThan(0);
    expect(screen.getByText("Ejecutivo Comercial SR")).toBeInTheDocument();
    expect(screen.getByText("Llamada telefónica")).toBeInTheDocument();
  });

  it("creates a phone call for an eligible application", async () => {
    render(<RecruitmentCalendar />);

    await screen.findByText("Ana Pérez");
    fireEvent.click(screen.getByRole("button", { name: "Agendar cita" }));

    fireEvent.change(screen.getByLabelText("Candidato y vacante"), {
      target: { value: "job-1::candidate-1" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Agendar" }).closest("form"));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/recruitment-calendar/events",
        expect.objectContaining({
          job_id: "job-1",
          candidate_id: "candidate-1",
          kind: "PHONE_CALL",
        }),
      );
    });
  });

  it("hides write controls without candidates.manage", async () => {
    useSession.mockReturnValue({
      hasPermission: (permission) => permission === "candidates.read",
    });

    render(<RecruitmentCalendar />);

    await screen.findByText("Ana Pérez");
    expect(screen.queryByRole("button", { name: "Agendar cita" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
  });
});
