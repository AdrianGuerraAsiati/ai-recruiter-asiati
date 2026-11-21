// eslint-disable-next-line no-unused-vars
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Ranking from "../pages/Ranking";

vi.mock("../context/SessionContext", () => ({
  useSession: () => ({ hasPermission: () => false }),
}));

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from "../api/client";

const JOBS = [
  { job_id: "job-a", title: "Analista A", candidate_count: 1, work_mode: "REMOTE" },
  { job_id: "job-b", title: "Backend B", candidate_count: 1, work_mode: "REMOTE" },
];

function rankingFor(name) {
  return {
    data: {
      candidates: [
        { candidate_id: `${name}-id`, candidate_name: name, position: 1, status: "COMPLETED", match_score: 80, recommendation: "GOOD_MATCH", strengths: [], gaps: [] },
      ],
      ranking_generated_at: "2026-09-06T12:00:00Z",
      ranking_version: 1,
      ranking_scope: "all",
      ranking_total: 1,
      total: 1,
      total_pages: 1,
      page: 1,
      page_size: 10,
      pending_candidates: 0,
    },
  };
}

function renderRanking() {
  return render(
    <MemoryRouter>
      <Ranking />
    </MemoryRouter>,
  );
}

describe("Ranking stale job protection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("ignores a late ranking response from the previously selected job", async () => {
    let resolveJobA;
    let jobARequests = 0;
    api.get.mockImplementation((url) => {
      if (url === "/jobs") return Promise.resolve({ data: JOBS });
      if (url.includes("/cost-estimate")) return Promise.resolve({ data: { available_candidate_count: 1 } });
      if (url === "/jobs/job-a/ranking") {
        jobARequests += 1;
        return new Promise((resolve) => { resolveJobA = resolve; });
      }
      if (url === "/jobs/job-b/ranking") return Promise.resolve(rankingFor("Beatriz Backend"));
      return Promise.resolve({ data: [] });
    });

    renderRanking();

    const select = await screen.findByRole("combobox", { name: "Vacante para el ranking" });
    await waitFor(() => expect(jobARequests).toBe(1));

    fireEvent.change(select, { target: { value: "job-b" } });
    expect(await screen.findByText("Beatriz Backend")).toBeInTheDocument();

    await act(async () => {
      resolveJobA(rankingFor("Andrea Analista"));
    });

    expect(screen.queryByText("Andrea Analista")).not.toBeInTheDocument();
    expect(screen.getByText("Beatriz Backend")).toBeInTheDocument();
  });

  it("locks the job selector while an evaluation is running", async () => {
    let resolvePost;
    api.post.mockImplementation(() => new Promise((resolve) => { resolvePost = resolve; }));
    api.get.mockImplementation((url) => {
      if (url === "/jobs") return Promise.resolve({ data: JOBS });
      if (url.includes("/cost-estimate")) return Promise.resolve({ data: { available_candidate_count: 1 } });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { status: "COMPLETED" } });
      if (url.includes("/ranking")) return Promise.resolve(rankingFor("Andrea Analista"));
      return Promise.resolve({ data: [] });
    });

    renderRanking();

    const select = await screen.findByRole("combobox", { name: "Vacante para el ranking" });
    await screen.findByText("Andrea Analista");
    expect(select).not.toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Evaluar candidatos" }));
    await waitFor(() => expect(select).toBeDisabled());

    await act(async () => {
      resolvePost({ data: { task_id: "task-1" } });
    });

    await waitFor(() => expect(select).not.toBeDisabled());
    expect(select).toHaveValue("job-a");
  });
});
