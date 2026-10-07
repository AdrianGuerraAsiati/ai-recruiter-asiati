// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Ranking from "../pages/Ranking";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from "../api/client";

function renderRanking() {
  return render(
    <MemoryRouter>
      <Ranking />
    </MemoryRouter>,
  );
}

async function confirmRecalculation() {
  fireEvent.click(screen.getByRole("button", { name: "Recalcular ranking" }));
  expect(await screen.findByRole("heading", { name: "Evaluación masiva" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Iniciar evaluación" }));
}

const EMPTY_RANKING = {
  data: {
    candidates: [],
    ranking_generated_at: null,
    ranking_version: null,
    ranking_scope: "all",
    ranking_total: 0,
    total: 0,
    total_pages: 0,
    page: 1,
    page_size: 10,
    pending_candidates: 0,
  },
};

const CANDIDATES_RANKING = {
  data: {
    candidates: [
      { candidate_id: "c1", candidate_name: "Ana", position: 1, status: "COMPLETED", match_score: 85, recommendation: "GOOD_MATCH", strengths: ["Python"], gaps: [], applied_to_job: true },
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
    score_min: 85,
    score_max: 85,
  },
};

const SCOPE_MISMATCH_RANKING = {
  data: {
    candidates: [],
    ranking_generated_at: "2026-09-08T10:00:00Z",
    ranking_version: 2,
    ranking_scope: "assigned",
    scope_mismatch: true,
    ranking_total: 0,
    total: 0,
    total_pages: 0,
    page: 1,
    page_size: 10,
    pending_candidates: 0,
  },
};

const ALL_CANDIDATES_RANKING = {
  data: {
    candidates: [
      { candidate_id: "c1", candidate_name: "Ana", position: 1, status: "COMPLETED", match_score: 85, recommendation: "GOOD_MATCH", strengths: ["Python"], gaps: [] },
      { candidate_id: "c2", candidate_name: "Bob", position: 2, status: "COMPLETED", match_score: 75, recommendation: "GOOD_MATCH", strengths: ["Java"], gaps: [] },
      { candidate_id: "c3", candidate_name: "Carlos", position: 3, status: "COMPLETED", match_score: 65, recommendation: "PARTIAL_MATCH", strengths: ["JS"], gaps: [] },
      { candidate_id: "c4", candidate_name: "Diana", position: 4, status: "COMPLETED", match_score: 55, recommendation: "LOW_MATCH", strengths: ["Go"], gaps: [] },
      { candidate_id: "c5", candidate_name: "Eva", position: 5, status: "COMPLETED", match_score: 45, recommendation: "LOW_MATCH", strengths: ["Rust"], gaps: [] },
    ],
    ranking_generated_at: "2026-09-06T12:00:00Z",
    ranking_version: 1,
    ranking_scope: "all",
    scope_mismatch: false,
    ranking_total: 5,
    total: 5,
    total_pages: 1,
    page: 1,
    page_size: 10,
    pending_candidates: 0,
    score_min: 45,
    score_max: 85,
  },
};

const COST_ESTIMATE = {
  data: {
    mode: "exhaustive",
    candidate_count: 5,
    deep_candidate_count: 5,
    shallow_candidate_count: 0,
    input_tokens_estimated: 22500,
    output_tokens_estimated: 3000,
    estimated_cost_usd: 0.0143,
    estimated_cost_with_margin_usd: 0.0179,
    margin_percent: 25,
    nova_input_usd_per_million: 0.30,
    nova_output_usd_per_million: 2.50,
    input_tokens_per_deep_candidate: 4500,
    output_tokens_per_deep_candidate: 600,
    max_deep_requests_per_minute: 2000,
    theoretical_min_seconds: 1,
    target_seconds: null,
    available_candidate_count: 5,
    excluded_banned_count: 0,
    disclaimer: "Esta es una estimación de planeación.",
  },
};

const PAGINATED_RANKING = {
  data: {
    candidates: Array.from({ length: 10 }, (_, i) => ({
      candidate_id: `c${i + 1}`,
      candidate_name: `Candidate ${i + 1}`,
      position: i + 1,
      status: "COMPLETED",
      match_score: 90 - i,
      recommendation: "GOOD_MATCH",
      strengths: [],
      gaps: [],
    })),
    ranking_generated_at: "2026-09-06T12:00:00Z",
    ranking_version: 1,
    ranking_scope: "all",
    scope_mismatch: false,
    ranking_total: 25,
    total: 10,
    total_pages: 3,
    page: 1,
    page_size: 10,
    pending_candidates: 0,
    score_min: 81,
    score_max: 90,
  },
};

describe("Ranking page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("alert", vi.fn());
    vi.stubGlobal("confirm", vi.fn(() => true));
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") {
        return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      }
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        return Promise.resolve(EMPTY_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
  });

  it("shows active jobs even when they have no candidates", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/jobs") {
        return Promise.resolve({
          data: [
            { job_id: "job-empty", title: "Vacante vacía", candidate_count: 0, status: "ACTIVE" },
            { job_id: "job-active", title: "Vacante con candidatos", candidate_count: 2, status: "ACTIVE" },
          ],
        });
      }
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve(EMPTY_RANKING);
      return Promise.resolve({ data: [] });
    });

    renderRanking();

    expect(await screen.findByRole("option", { name: "Vacante vacía · 0 postulantes directos" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Vacante con candidatos · 2 postulantes directos" })).toBeInTheDocument();
  });

  it("shows the evaluable country pool even with zero direct applicants", async () => {
    api.get.mockImplementation((url, config) => {
      if (url === "/jobs") {
        return Promise.resolve({
          data: [{
            job_id: "job-bde",
            title: "BDE",
            candidate_count: 0,
            status: "ACTIVE",
            work_mode: "ONSITE",
            country_code: "CO",
          }],
        });
      }
      if (url.includes("/cost-estimate")) {
        expect(config?.params).toEqual({ mode: "fast", scope: "all" });
        return Promise.resolve({
          data: {
            ...COST_ESTIMATE.data,
            available_candidate_count: 433,
          },
        });
      }
      if (url.includes("/ranking")) return Promise.resolve(EMPTY_RANKING);
      return Promise.resolve({ data: [] });
    });

    renderRanking();

    expect(await screen.findByText(/433 elegibles/)).toBeInTheDocument();
    expect(screen.getAllByText("433").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Los postulantes directos no limitan el ranking/),
    ).toBeInTheDocument();
  });

  it("shows active jobs when candidate_count is missing and hides paused jobs", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/jobs") {
        return Promise.resolve({
          data: [
            { job_id: "job-unknown", title: "Vacante sin conteo", status: "ACTIVE" },
            { job_id: "job-active", title: "Vacante activa", candidate_count: 1, status: "ACTIVE" },
            { job_id: "job-paused", title: "Vacante pausada", candidate_count: 4, status: "PAUSED" },
          ],
        });
      }
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve(EMPTY_RANKING);
      return Promise.resolve({ data: [] });
    });

    renderRanking();

    expect(await screen.findByRole("option", { name: "Vacante activa · 1 postulante directo" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Vacante sin conteo · 0 postulantes directos" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Vacante pausada/ })).not.toBeInTheDocument();
  });

  it("keeps empty active vacancies visible and rankable against the Talent base", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/jobs") {
        return Promise.resolve({
          data: [
            { job_id: "job-empty-1", title: "Vacante vacía 1", candidate_count: 0, status: "ACTIVE" },
            { job_id: "job-empty-2", title: "Vacante vacía 2", candidate_count: 0, status: "ACTIVE" },
          ],
        });
      }
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve(EMPTY_RANKING);
      return Promise.resolve({ data: [] });
    });

    renderRanking();

    expect(await screen.findByRole("option", { name: "Vacante vacía 1 · 0 postulantes directos" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Vacante vacía 2 · 0 postulantes directos" })).toBeInTheDocument();
    expect(await screen.findByText("Ranking listo para generar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Evaluar candidatos" })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Actualizar ranking" })).not.toBeDisabled();
  });

  // ============================================================
  // TEST 1 — TRES BOTONES
  // ============================================================

  it("shows all three action buttons and not obsolete ones", async () => {
    renderRanking();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Evaluar candidatos" })).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Actualizar ranking" })).toBeInTheDocument();
    expect(screen.queryByText("Aplicó a esta vacante")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recalcular ranking" })).toBeInTheDocument();
    expect(screen.queryByText("Calcular evaluaciones")).not.toBeInTheDocument();
    expect(screen.queryByText("Generar ranking")).not.toBeInTheDocument();
    expect(screen.queryByText("Ver ranking")).not.toBeInTheDocument();
    expect(screen.queryByText("Fuente de candidatos")).not.toBeInTheDocument();
    expect(screen.getByText(/Toda la base de Talent/i)).toBeInTheDocument();
  });

  // ============================================================
  // TEST 2 — EVALUAR CANDIDATOS
  // ============================================================

  it("sends correct POST when clicking Evaluar candidatos", async () => {
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 2, evaluated: 2, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Evaluar candidatos" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Evaluar candidatos" }));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/jobs/job-1/ranking/recalculate-async",
        null,
        { params: { mode: "incremental", scope: "all" } },
      );
    });
  });

  // ============================================================
  // TEST 3 — EVALUAR IGNORA rankingScope
  // ============================================================

  it("Evaluar candidatos always uses the all-candidates scope", async () => {
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve({ data: { candidates: [], ranking_generated_at: null, ranking_version: null, ranking_scope: "all", ranking_total: 0, total: 0, total_pages: 0, page: 1, page_size: 10, pending_candidates: 0 } });
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 3, evaluated: 3, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Evaluar candidatos" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Evaluar candidatos" }));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/jobs/job-1/ranking/recalculate-async",
        null,
        { params: { mode: "incremental", scope: "all" } },
      );
    });
  });

  // ============================================================
  // TEST 4 — ACTUALIZAR NO HACE POST
  // ============================================================

  it("Actualizar ranking only calls GET, never POST", async () => {
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Actualizar ranking" })).not.toBeDisabled(); });
    api.post.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Actualizar ranking" }));
    await waitFor(() => {
      expect(api.post).not.toHaveBeenCalled();
      expect(
        api.get.mock.calls.some(
          ([url, config]) =>
            url === "/jobs/job-1/ranking" &&
            config?.params?.page === 1,
        ),
      ).toBe(true);
    });
  });

  // ============================================================
  // TEST 5 — ACTUALIZAR RESPETA SCOPE
  // ============================================================

  it("Actualizar ranking always reads the all-candidates scope", async () => {
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve({ data: { candidates: [], ranking_generated_at: null, ranking_version: null, ranking_scope: "all", ranking_total: 0, total: 0, total_pages: 0, page: 1, page_size: 10, pending_candidates: 0 } });
      return Promise.resolve({ data: [] });
    });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Actualizar ranking" })).not.toBeDisabled(); });
    api.post.mockClear();
    api.get.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Actualizar ranking" }));
    await waitFor(() => {
      expect(api.post).not.toHaveBeenCalled();
      expect(
        api.get.mock.calls.some(
          ([url, config]) =>
            url === "/jobs/job-1/ranking" &&
            config?.params?.scope === "all",
        ),
      ).toBe(true);
    });
  });

  // ============================================================
  // TEST 6 — RECALCULAR CANCELADO
  // ============================================================

  it("Recalcular ranking can be cancelled from the cost disclaimer", async () => {
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Recalcular ranking" }));
    expect(await screen.findByRole("heading", { name: "Evaluación masiva" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("heading", { name: "Evaluación masiva" })).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  // ============================================================
  // TEST 7 — RECALCULAR CONFIRMADO
  // ============================================================

  it("sends correct POST when confirming Recalcular ranking", async () => {
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 1, evaluated: 1, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    await confirmRecalculation();
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/jobs/job-1/ranking/recalculate-async",
        null,
        { params: { mode: "full", scope: "all" } },
      );
    });
  });

  // ============================================================
  // TEST 8 — RECALCULAR IGNORA rankingScope
  // ============================================================

  it("Recalcular ranking always uses the all-candidates scope", async () => {
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve({ data: { candidates: [], ranking_generated_at: null, ranking_version: null, ranking_scope: "all", ranking_total: 0, total: 0, total_pages: 0, page: 1, page_size: 10, pending_candidates: 0 } });
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 1, evaluated: 1, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    await confirmRecalculation();
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/jobs/job-1/ranking/recalculate-async",
        null,
        { params: { mode: "full", scope: "all" } },
      );
    });
  });

  // ============================================================
  // TEST 9 — LOADING EVALUAR
  // ============================================================

  it("Evaluar candidatos shows loading and disables all buttons", async () => {
    let resolvePost;
    api.post.mockImplementation(() => new Promise((resolve) => { resolvePost = resolve; }));
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve(EMPTY_RANKING);
      return Promise.resolve({ data: [] });
    });
    renderRanking();
    const evalBtn = await screen.findByRole("button", { name: "Evaluar candidatos" });
    expect(evalBtn).not.toBeDisabled();
    fireEvent.click(evalBtn);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Evaluando candidatos..." })).toBeDisabled();
    });
    expect(screen.getByRole("button", { name: "Actualizar ranking" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Recalcular ranking" })).toBeDisabled();
    resolvePost({ data: { task_id: "task-1", status: "PENDING", total_candidates: 0, evaluated: 0, failed: 0 } });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Evaluar candidatos" })).not.toBeDisabled();
    });
  });

  // ============================================================
  // TEST 10 — LOADING ACTUALIZAR
  // ============================================================

  it("Actualizar ranking shows loading and disables all buttons", async () => {
    let resolveGet;
    let rankingCount = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCount += 1;
        if (rankingCount <= 1) {
          return Promise.resolve(EMPTY_RANKING);
        }
        return new Promise((resolve) => { resolveGet = resolve; });
      }
      return Promise.resolve({ data: [] });
    });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Actualizar ranking" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Actualizar ranking" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Actualizando ranking..." })).toBeDisabled();
    });
    expect(screen.getByRole("button", { name: "Evaluar candidatos" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Recalcular ranking" })).toBeDisabled();
    resolveGet(EMPTY_RANKING);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Actualizar ranking" })).not.toBeDisabled();
    });
  });

  // ============================================================
  // TEST 11 — LOADING RECALCULAR
  // ============================================================

  it("Recalcular ranking shows loading and disables all buttons", async () => {
    let resolvePost;
    api.post.mockImplementation(() => new Promise((resolve) => { resolvePost = resolve; }));
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve(EMPTY_RANKING);
      return Promise.resolve({ data: [] });
    });
    renderRanking();
    const recalcBtn = await screen.findByRole("button", { name: "Recalcular ranking" });
    expect(recalcBtn).not.toBeDisabled();
    await confirmRecalculation();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Recalculando ranking..." })).toBeDisabled();
    });
    expect(screen.getByRole("button", { name: "Evaluar candidatos" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Actualizar ranking" })).toBeDisabled();
    resolvePost({ data: { task_id: "task-1", status: "PENDING", total_candidates: 1, evaluated: 1, failed: 0 } });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled();
    });
  });

  // ============================================================
  // TEST 12 — REFRESH POST EVALUACIÓN
  // ============================================================

  it("Evaluar candidatos refreshes ranking with page=1 after success", async () => {
    let rankingCalls = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(CANDIDATES_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 1, evaluated: 1, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Evaluar candidatos" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Evaluar candidatos" }));
    await waitFor(() => {
      const rankingCall = api.get.mock.calls.find(([url]) => url === "/jobs/job-1/ranking");
      expect(rankingCall).toBeDefined();
      expect(rankingCall[1].params.page).toBe(1);
    });
  });

  // ============================================================
  // TEST 13 — REFRESH POST RECÁLCULO
  // ============================================================

  it("Recalcular ranking refreshes ranking with page=1 after success", async () => {
    let rankingCalls = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(CANDIDATES_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 1, evaluated: 1, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    await confirmRecalculation();
    await waitFor(() => {
      const rankingCall = api.get.mock.calls.find(([url]) => url === "/jobs/job-1/ranking");
      expect(rankingCall).toBeDefined();
      expect(rankingCall[1].params.page).toBe(1);
    });
  });

  // ============================================================
  // TEST 14 — NO MODAL DE MODO
  // ============================================================

  it("does not show mode modal after clicking Actualizar or Recalcular", async () => {
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 1, evaluated: 1, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Actualizar ranking" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Actualizar ranking" }));
    await waitFor(() => { expect(screen.getByText("Ranking actualizado.")).toBeInTheDocument(); });
    expect(screen.queryByText("Solo nuevos candidatos")).not.toBeInTheDocument();
    expect(screen.queryByText("Recalcular todo")).not.toBeInTheDocument();
    expect(screen.queryByText("¿Cómo quieres actualizar el ranking?")).not.toBeInTheDocument();
    await confirmRecalculation();
    expect(screen.queryByText("¿Cómo quieres actualizar el ranking?")).not.toBeInTheDocument();
  });

  // ============================================================
  // TEST 15 — FEEDBACK
  // ============================================================

  it("shows correct feedback messages for each action", async () => {
    let rankingCalls = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(CANDIDATES_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 2, evaluated: 2, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Evaluar candidatos" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Evaluar candidatos" }));
    await waitFor(() => { expect(screen.getByText("Evaluación completada y ranking actualizado.")).toBeInTheDocument(); });

    fireEvent.click(screen.getByRole("button", { name: "Actualizar ranking" }));
    await waitFor(() => { expect(screen.getByText("Ranking actualizado.")).toBeInTheDocument(); });

    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 1, evaluated: 1, failed: 0 } });
    await confirmRecalculation();
    await waitFor(() => { expect(screen.getByText("Ranking recalculado correctamente.")).toBeInTheDocument(); });
  });

  it("shows useful feedback when persisted ranking scope does not match", async () => {
    api.get.mockImplementation((url, config) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") {
        return Promise.resolve({
          data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1 }],
        });
      }

      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        const scope = config?.params?.scope || "assigned";

        if (scope === "all") {
          return Promise.resolve(SCOPE_MISMATCH_RANKING);
        }

        return Promise.resolve(EMPTY_RANKING);
      }

      return Promise.resolve({ data: [] });
    });

    renderRanking();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Actualizar ranking" }),
      ).not.toBeDisabled();
    });

    await waitFor(() => {
      expect(
        screen.getByText(
          /El ranking guardado pertenece al alcance anterior/i,
        ),
      ).toBeInTheDocument();
    });
  });

  // ============================================================
  // NEW TESTS FOR FALSE POSITIVE FIXES
  // ============================================================

  // TEST 1: scope=all + Recalcular
  it("Recalcular ranking with scope=all sends correct POST", async () => {
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve(ALL_CANDIDATES_RANKING);
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 5, evaluated: 5, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    await confirmRecalculation();
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/jobs/job-1/ranking/recalculate-async",
        null,
        { params: { mode: "full", scope: "all" } },
      );
    });
  });

  // TEST 2: scope=all + Evaluar
  it("Evaluar candidatos with scope=all sends correct POST", async () => {
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) return Promise.resolve(ALL_CANDIDATES_RANKING);
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 5, evaluated: 5, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Evaluar candidatos" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Evaluar candidatos" }));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/jobs/job-1/ranking/recalculate-async",
        null,
        { params: { mode: "incremental", scope: "all" } },
      );
    });
  });

  // TEST 3: POST success + GET success = success message
  it("shows success when POST and GET both succeed with candidates", async () => {
    let rankingCalls = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(ALL_CANDIDATES_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 5, evaluated: 5, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    await confirmRecalculation();
    await waitFor(() => { expect(screen.getByText("Ranking recalculado correctamente.")).toBeInTheDocument(); });
  });

  // TEST 4: POST success + GET scope_mismatch = NO success message
  it("does NOT show success when POST succeeds but GET returns scope_mismatch", async () => {
    let rankingCalls = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(SCOPE_MISMATCH_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 5, evaluated: 5, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    // Change scope to "all" to trigger scope_mismatch (ranking was generated for "assigned")
    await confirmRecalculation();
    await waitFor(() => {
      expect(screen.queryByText("Ranking recalculado correctamente.")).not.toBeInTheDocument();
      const messages = screen.getAllByText(/El ranking guardado pertenece al alcance anterior/i);
      expect(messages.length).toBeGreaterThan(0);
    });
  });

  // TEST 5: POST reports candidates but GET returns empty ranking_total
  it("shows error when POST reports candidates but GET returns empty ranking", async () => {
    let rankingCalls = 0;
    const EMPTY_GET_RANKING = {
      data: {
        candidates: [],
        ranking_generated_at: "2026-09-08T10:00:00Z",
        ranking_version: 1,
        ranking_scope: "all",
        scope_mismatch: false,
        ranking_total: 0,
        total: 0,
        total_pages: 0,
        page: 1,
        page_size: 10,
        pending_candidates: 0,
      },
    };
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(EMPTY_GET_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 5, evaluated: 5, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    await confirmRecalculation();
    await waitFor(() => {
      expect(screen.queryByText("Ranking recalculado correctamente.")).not.toBeInTheDocument();
      expect(screen.getByText(/El recálculo terminó, pero no hay candidatos elegibles para esta vacante según país y modalidad/i)).toBeInTheDocument();
    });
  });

  // TEST 6: POST scope=all with total_candidates=0
  it("shows correct message when POST scope=all returns total_candidates=0", async () => {
    let rankingCalls = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(EMPTY_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 0, evaluated: 0, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    await confirmRecalculation();
    await waitFor(() => {
      expect(screen.getByText("El recálculo terminó, pero no hay candidatos elegibles para esta vacante según país y modalidad.")).toBeInTheDocument();
    });
  });

  // TEST 7: POST scope=assigned with total_candidates=0
  it("shows correct message when POST scope=assigned returns total_candidates=0", async () => {
    let rankingCalls = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(EMPTY_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 0, evaluated: 0, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    await confirmRecalculation();
    await waitFor(() => {
      expect(screen.getByText("El recálculo terminó, pero no hay candidatos elegibles para esta vacante según país y modalidad.")).toBeInTheDocument();
    });
  });

  // TEST 8: Refresh ranking with scope_mismatch = NO "Ranking actualizado"
  it("does NOT show 'Ranking actualizado' when refresh returns scope_mismatch", async () => {
    api.get.mockImplementation((url, config) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        const scope = config?.params?.scope || "assigned";
        if (scope === "all") return Promise.resolve(SCOPE_MISMATCH_RANKING);
        return Promise.resolve(EMPTY_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Actualizar ranking" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Actualizar ranking" }));
    await waitFor(() => {
      expect(screen.queryByText("Ranking actualizado.")).not.toBeInTheDocument();
      const messages = screen.getAllByText(/El ranking guardado pertenece al alcance anterior/i);
      expect(messages.length).toBeGreaterThan(0);
    });
  });

  // TEST 9: Refresh ranking with valid GET = "Ranking actualizado"
  it("shows 'Ranking actualizado' when refresh returns valid data", async () => {
    let rankingCalls = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(CANDIDATES_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Actualizar ranking" })).not.toBeDisabled(); });
    fireEvent.click(screen.getByRole("button", { name: "Actualizar ranking" }));
    await waitFor(() => { expect(screen.getByText("Ranking actualizado.")).toBeInTheDocument(); });
  });

  // TEST 10: Pagination - ranking_total=25, candidates.length=10 = valid
  it("considers paginated GET with ranking_total > candidates.length as valid", async () => {
    let rankingCalls = 0;
    api.get.mockImplementation((url) => {
      if (url.includes("/cost-estimate")) return Promise.resolve(COST_ESTIMATE);
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Dev Python", candidate_count: 1, work_mode: "REMOTE" }] });
      if (url.includes("/ranking/recalculate-async/")) return Promise.resolve({ data: { task_id: "task-1", status: "COMPLETED", last_error_code: null } });
      if (url.includes("/ranking")) {
        rankingCalls += 1;
        if (rankingCalls <= 1) return Promise.resolve(EMPTY_RANKING);
        return Promise.resolve(PAGINATED_RANKING);
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValueOnce({ data: { task_id: "task-1", status: "PENDING", total_candidates: 25, evaluated: 25, failed: 0 } });
    renderRanking();
    await waitFor(() => { expect(screen.getByRole("button", { name: "Recalcular ranking" })).not.toBeDisabled(); });
    await confirmRecalculation();
    await waitFor(() => { expect(screen.getByText("Ranking recalculado correctamente.")).toBeInTheDocument(); });
  });

});
