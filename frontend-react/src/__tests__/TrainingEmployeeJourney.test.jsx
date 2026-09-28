// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TrainingEmployeeJourney from "../features/training/TrainingEmployeeJourney";

function buildProps() {
  const lesson = {
    id: "lesson-1",
    title: "Bienvenida",
    description: "Conoce la ruta.",
    video_url: null,
    external_url: null,
    content_type: "ARTICLE",
    estimated_minutes: 5,
    is_optional: false,
    completed: false,
  };
  const module = {
    id: "module-1",
    title: "Módulo 1",
    position: 1,
    completed_lessons: 0,
    lesson_count: 1,
    estimated_minutes: 5,
    has_unknown_duration: false,
    is_complete: false,
    lessons: [lesson],
  };
  const course = {
    id: "course-1",
    title: "Curso ASIATI",
    description: "Ruta de prueba",
    is_onboarding: true,
    progress_percent: 0,
    completed_lessons: 0,
    lesson_count: 1,
    remaining_minutes: 5,
    has_unknown_remaining_duration: false,
    has_quiz: false,
    next_lesson_id: lesson.id,
    modules: [module],
  };
  const assignment = {
    id: "assignment-1",
    status: "ASSIGNED",
    course,
    quiz_result: null,
  };

  return {
    canManage: false,
    myAssignments: [assignment],
    selectedAssignmentId: assignment.id,
    setSelectedAssignmentId: vi.fn(),
    detailLoading: false,
    employeeCourse: { course },
    currentRecommendedSession: {
      items: [lesson],
      minutes: 5,
      hasUnknownDuration: false,
    },
    selectedAssignment: assignment,
    setActiveLessonId: vi.fn(),
    expandedModuleIds: [module.id],
    activeModuleId: module.id,
    toggleJourneyModule: vi.fn(),
    activeLessonId: lesson.id,
    activeJourneyLesson: { ...lesson, module },
    checklistSavingLessonId: "",
    updateChecklistItem: vi.fn(),
    previousJourneyLesson: null,
    nextJourneyLesson: null,
    completeLesson: vi.fn(),
    saving: false,
    nextRequiredJourneyLesson: null,
    openFinalQuiz: vi.fn(),
    employeeQuiz: null,
    quizAnswers: {},
    setQuizAnswers: vi.fn(),
    quizResult: null,
    submitQuiz: vi.fn(),
  };
}

describe("TrainingEmployeeJourney", () => {
  it("keeps navigation and lesson actions controlled by the parent", () => {
    const props = buildProps();

    render(<TrainingEmployeeJourney {...props} />);

    expect(screen.getByRole("heading", { name: "Mis cursos" })).toBeInTheDocument();
    expect(screen.getAllByText("Ruta de prueba").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Continuar ahora/ }));
    expect(props.setActiveLessonId).toHaveBeenCalledWith("lesson-1");

    fireEvent.click(screen.getByRole("button", { name: /Módulo 1/ }));
    expect(props.toggleJourneyModule).toHaveBeenCalledWith("module-1");

    fireEvent.click(screen.getByRole("button", { name: "Marcar completada" }));
    expect(props.completeLesson).toHaveBeenCalledWith("lesson-1");
  });

  it("renders the empty assignment state without course detail", () => {
    const props = buildProps();

    render(
      <TrainingEmployeeJourney
        {...props}
        myAssignments={[]}
        selectedAssignmentId=""
        selectedAssignment={null}
        employeeCourse={null}
        currentRecommendedSession={{ items: [], minutes: 0, hasUnknownDuration: false }}
        activeModuleId=""
        activeLessonId=""
        activeJourneyLesson={null}
      />,
    );

    expect(screen.getByText("Aún no tienes cursos asignados")).toBeInTheDocument();
  });
});
