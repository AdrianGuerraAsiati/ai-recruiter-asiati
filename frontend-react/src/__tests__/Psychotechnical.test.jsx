// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Psychotechnical from "../pages/Psychotechnical";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from "../api/client";

function renderPage(initial = "/psychotechnical") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Psychotechnical />
    </MemoryRouter>,
  );
}

describe("Psychotechnical recruiter workspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation((url) => {
      if (url === "/psychotechnical/assignments") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "assessment-1",
                candidate_id: "candidate-1",
                candidate_name: "Ana Pérez",
                candidate_email: "ana@example.com",
                job_id: "job-1",
                job_title: "Analista de Datos",
                status: "COMPLETED",
                expires_at: "2026-10-10T15:00:00Z",
                completed_at: "2026-10-06T15:00:00Z",
                duration_seconds: 600,
                score_total: 83,
                dimension_scores: {
                  LOGICAL: { label: "Razonamiento lógico", score: 67 },
                  NUMERICAL: { label: "Razonamiento numérico", score: 100 },
                },
              },
            ],
          },
        });
      }
      if (url === "/jobs") return Promise.resolve({ data: [] });
      if (String(url).startsWith("/candidates?")) {
        return Promise.resolve({
          data: {
            items: [
              {
                candidate_id: "candidate-2",
                name: "Carlos Ruiz",
                email: "carlos@example.com",
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: { items: [] } });
    });
    api.post.mockResolvedValue({ data: {} });
  });

  it("shows completed objective results without mixing them into ranking", async () => {
    renderPage();

    expect(await screen.findByText("Ana Pérez")).toBeInTheDocument();
    expect(screen.getByText("83%")).toBeInTheDocument();
    expect(screen.getByText("Razonamiento lógico")).toBeInTheDocument();
    expect(screen.getByText(/no toman decisiones de contratación automáticamente/i)).toBeInTheDocument();
  });

  it("assigns a test and exposes a candidate-specific link", async () => {
    api.post.mockResolvedValueOnce({
      data: {
        assignment: { id: "assessment-2" },
        token: "secret-test-token",
      },
    });

    renderPage();
    await screen.findByText("Ana Pérez");

    fireEvent.click(screen.getByRole("button", { name: "Asignar prueba" }));
    fireEvent.change(screen.getByLabelText("Candidato"), {
      target: { value: "Carlos" },
    });

    const candidate = await screen.findByRole("button", { name: /Carlos Ruiz/i });
    fireEvent.click(candidate);
    fireEvent.click(screen.getByRole("button", { name: "Generar enlace" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/psychotechnical/assignments",
        {
          candidate_id: "candidate-2",
          job_id: null,
          expires_days: 7,
        },
      );
    });

    expect(await screen.findByLabelText("Enlace de la prueba")).toHaveValue(
      expect.stringContaining("/psychotechnical/take/secret-test-token"),
    );
  });
});
