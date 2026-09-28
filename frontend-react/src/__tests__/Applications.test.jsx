// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Applications from "../pages/Applications";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

import api from "../api/client";

function renderPage() {
  return render(
    <MemoryRouter>
      <Applications />
    </MemoryRouter>,
  );
}

function application(status = "OFFER") {
  return {
    id: "application-1",
    application_status: status,
    status_changed_at: "2026-09-28T12:00:00Z",
    candidate: {
      candidate_id: "candidate-1",
      name: "Ana Pérez",
      email: "ana@example.com",
    },
    job: {
      job_id: "job-1",
      title: "Backend Developer",
    },
  };
}

describe("Applications hiring boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({
      data: {
        items: [application("OFFER")],
        total: 1,
        pages: 1,
      },
    });
    api.put.mockResolvedValue({ data: {} });
  });

  it("does not allow moving an application to HIRED from the generic stage selector", async () => {
    renderPage();

    const statusSelect = await screen.findByLabelText("Estado de Ana Pérez");
    expect(within(statusSelect).queryByRole("option", { name: "Contratado" })).not.toBeInTheDocument();
    expect(
      screen.getByText(/Para contratar, usa “Contratar candidato” desde Vacantes/i),
    ).toBeInTheDocument();

    fireEvent.change(statusSelect, { target: { value: "SELECTED" } });

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        "/jobs/job-1/candidates/candidate-1/status",
        { status: "SELECTED" },
      );
    });
  });

  it("shows HIRED as a locked terminal stage when already contracted", async () => {
    api.get.mockResolvedValue({
      data: {
        items: [application("HIRED")],
        total: 1,
        pages: 1,
      },
    });

    renderPage();

    const statusSelect = await screen.findByLabelText("Estado de Ana Pérez");
    expect(statusSelect).toBeDisabled();
    expect(within(statusSelect).getByRole("option", { name: "Contratado" })).toBeInTheDocument();
  });
});
