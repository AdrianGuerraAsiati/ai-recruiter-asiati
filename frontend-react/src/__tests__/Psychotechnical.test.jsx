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

const catalog = [
  {
    key: "COMMON_SENSE_GTH_F016",
    name: "Sentido común organizacional",
    code: "GTH-F-016",
    source_version: "00",
    question_count: 10,
    duration_minutes: 12,
    description: "Situaciones laborales para observar criterio organizacional.",
  },
  {
    key: "TEMPERAMENT_GTH_F017",
    name: "Temperamento laboral",
    code: "GTH-F-017",
    source_version: "00",
    question_count: 30,
    duration_minutes: 18,
    description: "Cuestionario descriptivo de estilos laborales.",
  },
];

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
      if (url === "/psychotechnical/catalog") {
        return Promise.resolve({ data: { items: catalog } });
      }
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
                test_name: "Sentido común organizacional",
                test_code: "GTH-F-016",
                status: "COMPLETED",
                expires_at: "2026-10-10T15:00:00Z",
                completed_at: "2026-10-06T15:00:00Z",
                duration_seconds: 600,
                score_total: 90,
                dimension_scores: {
                  RESULT: {
                    label: "Sentido común organizacional",
                    score: 90,
                    correct: 9,
                    total: 10,
                    band: "Excelente criterio organizacional y responsabilidad",
                  },
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

  it("shows the ASIATI source catalog and completed results separately from Ranking IA", async () => {
    renderPage();

    expect(await screen.findByText("Ana Pérez")).toBeInTheDocument();
    expect(screen.getByText("Sentido común organizacional")).toBeInTheDocument();
    expect(screen.getByText("GTH-F-016")).toBeInTheDocument();
    expect(screen.getByText("90%")).toBeInTheDocument();
    expect(screen.getByText(/se conserva separado del Ranking IA/i)).toBeInTheDocument();
  });

  it("assigns a selected ASIATI test and exposes a candidate-specific link", async () => {
    api.post.mockResolvedValueOnce({
      data: {
        assignment: { id: "assessment-2" },
        token: "secret-test-token",
      },
    });

    renderPage();
    await screen.findByText("Ana Pérez");

    fireEvent.click(screen.getAllByRole("button", { name: "Asignar prueba" })[0]);
    fireEvent.change(screen.getByLabelText("Prueba"), {
      target: { value: "TEMPERAMENT_GTH_F017" },
    });
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
          test_key: "TEMPERAMENT_GTH_F017",
          expires_days: 7,
        },
      );
    });

    const linkInput = await screen.findByLabelText("Enlace de la prueba");
    expect(linkInput.value).toContain("/psychotechnical/take/secret-test-token");
  });
});
