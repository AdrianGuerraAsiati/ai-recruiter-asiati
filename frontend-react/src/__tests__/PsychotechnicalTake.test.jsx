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
        test_key: "COMMON_SENSE_GTH_F016",
        test_name: "Sentido común organizacional",
        test_code: "GTH-F-016",
        source_version: "00",
        test_description: "Situaciones laborales para observar criterio organizacional.",
        duration_minutes: 12,
        question_count: 2,
      },
    });
    api.post.mockImplementation((url) => {
      if (url.endsWith("/start")) {
        return Promise.resolve({
          data: {
            assignment: {
              status: "IN_PROGRESS",
              candidate_name: "Ana Pérez",
              test_key: "COMMON_SENSE_GTH_F016",
              test_name: "Sentido común organizacional",
              test_code: "GTH-F-016",
            },
            questions: [
              {
                id: "SC01",
                prompt: "¿Qué haces ante una visita sin identificación?",
                options: [
                  { id: "A", label: "Permitir ingreso" },
                  { id: "C", label: "Verificar con el área correspondiente" },
                ],
              },
              {
                id: "SC02",
                prompt: "¿Qué haces con información confidencial recibida por error?",
                options: [
                  { id: "A", label: "Compartirla" },
                  { id: "C", label: "Informar al remitente" },
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

  it("allows the attention test without a countdown and requires all answers", async () => {
    api.get.mockResolvedValueOnce({
      data: {
        status: "PENDING",
        candidate_name: "Ana Pérez",
        test_key: "ATTENTION_DETAIL_V00",
        test_name: "Atención al detalle",
        test_code: "ATENCIÓN-DETALLE",
        question_count: 2,
        duration_seconds: 440,
      },
    });
    api.post.mockImplementation((url) => {
      if (url.endsWith("/start")) {
        return Promise.resolve({
          data: {
            assignment: {
              test_key: "ATTENTION_DETAIL_V00",
              test_name: "Atención al detalle",
              duration_seconds: 440,
            },
            questions: [
              { id: "AD01", section: "ALPHANUMERIC", prompt: "Selecciona A09RT3", options: [{ id: "A", label: "A09RT3" }, { id: "B", label: "A90RT3" }] },
              { id: "AD02", section: "LETTERS", prompt: "Compara ABC", options: [{ id: "A", label: "Iguales" }, { id: "B", label: "Diferentes" }] },
            ],
          },
        });
      }
      return Promise.resolve({ data: { status: "COMPLETED" } });
    });
    renderPage();
    expect(await screen.findByText("Sin límite de tiempo")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Comenzar prueba" }));
    expect(await screen.findByText(/Selecciona A09RT3/)).toBeInTheDocument();
    expect(screen.queryByText(/tiempo restante|tiempo finalizado/i)).not.toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Enviar prueba" });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByLabelText("A09RT3"));
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Iguales"));
    expect(submit).toBeEnabled();
  });

  it("explains the complementary and non-clinical scope before starting", async () => {
    renderPage();

    expect(await screen.findByText("Sentido común organizacional")).toBeInTheDocument();
    expect(screen.getByText(/no realiza diagnósticos clínicos/i)).toBeInTheDocument();
    expect(screen.getByText(/no determina por sí solo una contratación/i)).toBeInTheDocument();
  });

  it("collects every common-sense answer before allowing submission", async () => {
    renderPage();
    await screen.findByText("Sentido común organizacional");

    fireEvent.click(screen.getByRole("button", { name: "Comenzar prueba" }));

    expect(await screen.findByText(/visita sin identificación/i)).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Enviar prueba" });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByLabelText("Verificar con el área correspondiente"));
    fireEvent.click(screen.getByLabelText("Informar al remitente"));

    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/public/psychotechnical/token-123/submit",
        {
          answers: [
            { question_id: "SC01", option_id: "C" },
            { question_id: "SC02", option_id: "C" },
          ],
        },
      );
    });

    expect(await screen.findByText("Prueba completada")).toBeInTheDocument();
  });
});
