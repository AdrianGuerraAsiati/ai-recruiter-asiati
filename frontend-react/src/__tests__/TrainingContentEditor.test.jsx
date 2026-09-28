// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TrainingContentEditor from "../features/training/TrainingContentEditor";

const lessonDraft = {
  title: "",
  description: "",
  video_url: "",
  duration_seconds: "",
  content_type: "VIDEO",
  external_url: "",
  estimated_minutes: "",
  checklist_items: "",
  is_optional: false,
};

function renderEditor(overrides = {}) {
  const props = {
    course: {
      status: "DRAFT",
      modules: [
        {
          id: "module-1",
          position: 1,
          title: "Bienvenida",
          description: "Primeros pasos",
          audience_job_title: null,
          audience_department: null,
          lessons: [
            {
              id: "lesson-1",
              title: "Introducción",
              content_type: "VIDEO",
              estimated_minutes: 5,
              is_optional: false,
              video_url: null,
              external_url: null,
              checklist_items: [],
              video_size_bytes: null,
            },
          ],
        },
      ],
    },
    moduleForm: {
      title: "",
      description: "",
      audience_job_title: "",
      audience_department: "",
    },
    onModuleFormChange: vi.fn(),
    lessonForm: vi.fn(() => lessonDraft),
    onLessonFormChange: vi.fn(),
    onAddModule: vi.fn((event) => event.preventDefault()),
    onAddLesson: vi.fn((event) => event.preventDefault()),
    onUploadLessonVideo: vi.fn(),
    uploadingLessonId: "",
    saving: false,
    ...overrides,
  };

  render(<TrainingContentEditor {...props} />);
  return props;
}

describe("TrainingContentEditor", () => {
  it("keeps module and lesson editing controlled by the parent", () => {
    const props = renderEditor();

    expect(screen.getByText("Bienvenida")).toBeInTheDocument();
    expect(screen.getByText("Introducción")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Título de lección para Bienvenida"), {
      target: { value: "Cultura ASIATI" },
    });
    expect(props.onLessonFormChange).toHaveBeenCalledWith(
      "module-1",
      { title: "Cultura ASIATI" },
    );

    fireEvent.submit(screen.getByRole("button", { name: "Agregar lección" }).closest("form"));
    expect(props.onAddLesson).toHaveBeenCalledTimes(1);
    expect(props.onAddLesson.mock.calls[0][1]).toBe("module-1");

    fireEvent.change(screen.getByLabelText("Título del módulo"), {
      target: { value: "Seguridad" },
    });
    expect(props.onModuleFormChange).toHaveBeenCalledWith({ title: "Seguridad" });

    fireEvent.submit(screen.getByRole("button", { name: /Agregar módulo/ }).closest("form"));
    expect(props.onAddModule).toHaveBeenCalledTimes(1);
  });

  it("delegates lesson video uploads without retaining the file input value", () => {
    const props = renderEditor();
    const file = new File(["video"], "intro.mp4", { type: "video/mp4" });

    fireEvent.change(screen.getByLabelText("Subir video"), {
      target: { files: [file] },
    });

    expect(props.onUploadLessonVideo).toHaveBeenCalledWith("lesson-1", file);
  });

  it("renders published content read-only", () => {
    renderEditor({
      course: {
        status: "PUBLISHED",
        modules: [
          {
            id: "module-1",
            position: 1,
            title: "Bienvenida",
            lessons: [
              {
                id: "lesson-1",
                title: "Lectura inicial",
                content_type: "ARTICLE",
                estimated_minutes: 4,
                is_optional: true,
              },
            ],
          },
        ],
      },
    });

    expect(screen.getByText("Lectura inicial")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Agregar lección" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Agregar módulo/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Subir video")).not.toBeInTheDocument();
  });
});
