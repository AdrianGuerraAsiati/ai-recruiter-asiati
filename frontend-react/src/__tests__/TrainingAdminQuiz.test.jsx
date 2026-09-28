// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TrainingAdminQuiz from "../features/training/TrainingAdminQuiz";

describe("TrainingAdminQuiz", () => {
  it("keeps quiz creation controlled by the parent", () => {
    const onQuizFormChange = vi.fn();
    const onCreateQuiz = vi.fn((event) => event.preventDefault());

    render(
      <TrainingAdminQuiz
        course={{ status: "DRAFT", quiz: null }}
        quizForm={{ title: "Evaluación final", passing_score: "70" }}
        onQuizFormChange={onQuizFormChange}
        onCreateQuiz={onCreateQuiz}
        questionForm={{ prompt: "", options: ["", "", "", ""], correct_option: "0" }}
        onQuestionFormChange={vi.fn()}
        onQuestionOptionChange={vi.fn()}
        onAddQuestion={vi.fn()}
        saving={false}
      />,
    );

    fireEvent.change(screen.getByLabelText("Título de la evaluación"), {
      target: { value: "Evaluación ASIATI" },
    });
    expect(onQuizFormChange).toHaveBeenCalledWith({ title: "Evaluación ASIATI" });

    fireEvent.click(screen.getByRole("button", { name: /Crear evaluación/ }));
    expect(onCreateQuiz).toHaveBeenCalledTimes(1);
  });

  it("keeps question editing and submission controlled by the parent", () => {
    const onQuestionFormChange = vi.fn();
    const onQuestionOptionChange = vi.fn();
    const onAddQuestion = vi.fn((event) => event.preventDefault());

    render(
      <TrainingAdminQuiz
        course={{
          status: "DRAFT",
          quiz: {
            title: "Evaluación final",
            passing_score: 80,
            question_count: 1,
            questions: [
              {
                id: "question-1",
                position: 1,
                prompt: "¿Cuál es la respuesta?",
                options: ["A", "B", "C", "D"],
                correct_option: 1,
              },
            ],
          },
        }}
        quizForm={{ title: "Evaluación final", passing_score: "80" }}
        onQuizFormChange={vi.fn()}
        onCreateQuiz={vi.fn()}
        questionForm={{
          prompt: "Pregunta nueva",
          options: ["Uno", "Dos", "Tres", "Cuatro"],
          correct_option: "0",
        }}
        onQuestionFormChange={onQuestionFormChange}
        onQuestionOptionChange={onQuestionOptionChange}
        onAddQuestion={onAddQuestion}
        saving={false}
      />,
    );

    expect(screen.getByText("¿Cuál es la respuesta?")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Opción 1"), {
      target: { value: "Primera" },
    });
    expect(onQuestionOptionChange).toHaveBeenCalledWith(0, "Primera");

    fireEvent.change(screen.getByLabelText("Respuesta correcta"), {
      target: { value: "2" },
    });
    expect(onQuestionFormChange).toHaveBeenCalledWith({ correct_option: "2" });

    fireEvent.click(screen.getByRole("button", { name: "Agregar pregunta" }));
    expect(onAddQuestion).toHaveBeenCalledTimes(1);
  });
});
