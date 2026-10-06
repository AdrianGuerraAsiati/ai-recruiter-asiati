// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PsychotechnicalTake from "../pages/PsychotechnicalTake";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from "../api/client";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/psychotechnical/take/token-123"]}>
      <Routes>
        <Route path="/psychotechnical/take/:token" element={<PsychotechnicalTake />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Public psychotechnical flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({
      data: {
        status: "PENDING",
        candidate_name: "Ana Pérez",
        test_name: "Razonamiento y atención",
        test_description: "Prueba laboral objetiva.",
        duration_minutes: 20,
        question_count: 2,
        dimensions: ["Razonamiento lógico"],
      },
    });
    api.post.mockImplementation((url) => {
      if (url.endsWith("/start")) {
        return Promise.resolve({
          data: {
            assignment: {
              status: "IN_PROGRESS",
              candidate_name: "Ana Pérez",
              test_name: "Razonamiento y atención",
            },
            questions: [
              {
                id: "L1",
                dimension: "LOGICAL",
                prompt: "2, 4, 8, __",
                options: [
                  { id: "A", label: "10" },
                  { id: "B", label: "16" },
                ],
              },
              {
                id: "L2",
                dimension: "LOGICAL",
                prompt: "A, C, F, __",
                options: [
                  { id: "A", label: "I" },
                  { id: "B", label: "J" },
                ],
              },
            ],
          },
        });
      }
      if (url.endsWith("/submit")) {
        return Promise.resolve({ data: { status: "COMPLETED" } });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it("explains the non-clinical scope before starting", async () => {
    renderPage();

    expect(await screen.findByText("Razonamiento y atención")).toBeInTheDocument();
    expect(screen.getByText(/No evalúa salud mental/i)).toBeInTheDocument();
    expect(screen.getByText(/no determina por sí solo/i)).toBeInTheDocument();
  });

  it("collects every answer before allowing submission", async () => {
    renderPage();
    await screen.findByText("Razonamiento y atención");

    fireEvent.click(screen.getByRole("button", { name: "Comenzar prueba" }));

    expect(await screen.findByText("2, 4, 8, __")).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Enviar prueba" });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByLabelText("16"));
    fireEvent.click(screen.getByLabelText("J"));

    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/public/psychotechnical/token-123/submit",
        {
          answers: [
            { question_id: "L1", option_id: "B" },
            { question_id: "L2", option_id: "B" },
          ],
        },
      );
    });

    expect(await screen.findByText("Prueba completada")).toBeInTheDocument();
  });
});
