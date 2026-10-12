// @vitest-environment jsdom
import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Ranking from "../pages/Ranking";
import api from "../api/client";

vi.mock("../context/SessionContext", () => ({
  useSession: () => ({ hasPermission: (code) => code === "employees.create" }),
}));

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("Ranking application initiation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation((url) => {
      if (url === "/jobs") return Promise.resolve({ data: [
        { job_id: "job-1", title: "Desarrollador", status: "ACTIVE", work_mode: "REMOTE" },
      ] });
      if (url === "/candidates/cand-1") return Promise.resolve({
        data: { candidate_id: "cand-1", name: "Ana Pérez", email: "ana@example.com" },
      });
      if (url.includes("/ranking/cost-estimate")) return Promise.resolve({
        data: { available_candidate_count: 1 },
      });
      if (url.includes("/ranking")) return Promise.resolve({
        data: {
          candidates: [{
            candidate_id: "cand-1",
            candidate_name: "Ana Pérez",
            match_score: 90,
            position: 1,
            status: "COMPLETED",
            recommendation: "STRONG_MATCH",
            strengths: [],
            gaps: [],
          }],
          ranking_generated_at: "2026-10-10T10:00:00Z",
          ranking_version: 1,
          ranking_scope: "all",
          ranking_total: 1,
          total: 1,
          total_pages: 1,
          page: 1,
          pending_candidates: 0,
        },
      });
      return Promise.resolve({ data: [] });
    });
  });

  it("links the ranked candidate to the selected job and displays one-time credentials", async () => {
    api.post.mockResolvedValue({
      data: {
        employee: { id: "emp-1", first_name: "Ana", last_name: "Pérez" },
        application_status: "SELECTED",
        credentials: {
          username: "aperez",
          temporary_password: "Temporary123A",
          must_change_password: true,
        },
      },
    });
    render(<MemoryRouter><Ranking /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: "Iniciar postulación" }));
    const dialog = await screen.findByRole("dialog", { name: "Iniciar postulación" });
    await waitFor(() => expect(within(dialog).getByLabelText("Correo").value).toBe("ana@example.com"));

    fireEvent.click(within(dialog).getByRole("button", { name: "Iniciar postulación" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/jobs/job-1/candidates/cand-1/start-application",
      expect.objectContaining({
        username: "aperez",
        email: "ana@example.com",
      }),
    ));
    expect(await screen.findByText("Temporary123A")).toBeInTheDocument();
  });
});
