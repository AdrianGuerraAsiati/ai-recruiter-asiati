// eslint-disable-next-line no-unused-vars
import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Progress from "../pages/Progress";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
  },
}));

vi.mock("../context/SessionContext", () => ({
  useSession: vi.fn(),
}));

import api from "../api/client";
import { useSession } from "../context/SessionContext";


describe("employee progress", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSession.mockReturnValue({
      principal: {
        profile: { first_name: "Ana" },
      },
    });
  });

  it("shows own course progress and evaluation results", async () => {
    api.get.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: "assignment-1",
            status: "COMPLETED",
            quiz_result: {
              attempt_count: 2,
              best_score: 92,
              latest_score: 92,
              passed: true,
            },
            course: {
              title: "Onboarding ASIATI",
              completed_lessons: 8,
              lesson_count: 8,
              progress_percent: 100,
            },
          },
        ],
      },
    });

    render(
      <MemoryRouter>
        <Progress />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Onboarding ASIATI")).toBeInTheDocument();
    expect(screen.getByText("Evaluaciones aprobadas")).toBeInTheDocument();
    expect(screen.getByText(/Evaluación: 92% · Aprobada/)).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/training/me");
  });
});
