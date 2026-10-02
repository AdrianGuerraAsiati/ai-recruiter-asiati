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
    activeLessonId: lesson.id,
    activeJourneyLesson: { ...lesson, module },
    checklistSavingLessonId: "",
    updateChecklistItem: vi.fn(),
    previousJourneyLesson: null,
    nextJourneyLesson: null,
    completeLesson: vi.fn(),
    updateVideoProgress: vi.fn().mockResolvedValue(null),
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

    const { container } = render(<TrainingEmployeeJourney {...props} />);

    expect(screen.getByRole("heading", { name: "Mis cursos" })).toBeInTheDocument();
    expect(container.querySelector(".training-learning-layout")).toHaveClass("is-single-course");
    expect(container.querySelector(".training-assignment-card")).not.toBeInTheDocument();
    expect(screen.getAllByText("Ruta de prueba").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Continuar ahora/ }));
    expect(props.setActiveLessonId).toHaveBeenCalledWith("lesson-1");

    props.setActiveLessonId.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /Módulo 1/ }));
    expect(props.setActiveLessonId).toHaveBeenCalledWith("lesson-1");

    fireEvent.click(screen.getByRole("button", { name: "✓ Marcar lección como completada" }));
    expect(props.completeLesson).toHaveBeenCalledWith("lesson-1");
  });

  it("separates lesson confirmation from navigation", () => {
    const props = buildProps();
    const completedLesson = {
      ...props.activeJourneyLesson,
      completed: true,
    };
    const nextLesson = {
      id: "lesson-2",
      title: "Siguiente lección",
      content_type: "ARTICLE",
      completed: false,
      is_optional: false,
    };

    render(
      <TrainingEmployeeJourney
        {...props}
        activeJourneyLesson={completedLesson}
        nextRequiredJourneyLesson={nextLesson}
      />,
    );

    expect(screen.getByText("Lección completada")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Marcar lección como completada/ }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continuar →" }));
    expect(props.setActiveLessonId).toHaveBeenCalledWith("lesson-2");
  });

  it("switches team videos from the member list without requiring Continue", () => {
    const props = buildProps();
    const jersson = {
      ...props.activeJourneyLesson,
      id: "team-jersson",
      title: "Jersson",
      video_url: "https://cdn.example.com/team/jersson.mp4",
      completed: true,
    };
    const valentina = {
      ...props.activeJourneyLesson,
      id: "team-valentina",
      title: "Valentina",
      video_url: "https://cdn.example.com/team/valentina.mp4",
      completed: false,
    };
    const teamModule = {
      ...props.employeeCourse.course.modules[0],
      id: "module-team",
      title: "Módulo 3 · Conoce al equipo",
      position: 3,
      lesson_count: 2,
      completed_lessons: 1,
      lessons: [jersson, valentina],
    };
    const teamCourse = {
      ...props.employeeCourse.course,
      modules: [teamModule],
      lesson_count: 2,
      completed_lessons: 1,
      next_lesson_id: valentina.id,
    };

    render(
      <TrainingEmployeeJourney
        {...props}
        employeeCourse={{ course: teamCourse }}
        activeLessonId={jersson.id}
        activeJourneyLesson={{ ...jersson, module: teamModule }}
        nextRequiredJourneyLesson={valentina}
      />,
    );

    expect(screen.getByText("Video completado")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continuar →" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Valentina/i }));
    expect(props.setActiveLessonId).toHaveBeenCalledWith("team-valentina");
  });

  it("uses team-specific completion controls without sequential navigation", () => {
    const props = buildProps();
    const teamLesson = {
      ...props.activeJourneyLesson,
      id: "team-laura",
      title: "Laura",
      video_url: "https://cdn.example.com/team/laura.mp4",
      content_type: "VIDEO",
      video_progress: {
        watched_percent: 0,
        watched_seconds: 0,
        completion_threshold_percent: 80,
      },
      completed: false,
    };
    const teamModule = {
      ...props.employeeCourse.course.modules[0],
      id: "module-team",
      title: "Módulo 3 · Conoce al equipo",
      position: 3,
      lessons: [teamLesson],
    };
    const teamCourse = {
      ...props.employeeCourse.course,
      modules: [teamModule],
      next_lesson_id: teamLesson.id,
    };

    render(
      <TrainingEmployeeJourney
        {...props}
        employeeCourse={{ course: teamCourse }}
        activeLessonId={teamLesson.id}
        activeJourneyLesson={{ ...teamLesson, module: teamModule }}
        previousJourneyLesson={{ id: "team-previous" }}
      />,
    );

    expect(screen.getAllByText(/mínimo 80%/i).length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: "✓ Marcar video como visto" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "← Anterior" })).not.toBeInTheDocument();
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
        activeLessonId=""
        activeJourneyLesson={null}
      />,
    );

    expect(screen.getByText("Aún no tienes cursos asignados")).toBeInTheDocument();
  });
});
