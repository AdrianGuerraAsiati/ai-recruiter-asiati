// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    onUpdateModule: vi.fn().mockResolvedValue({}),
    onUpdateLesson: vi.fn().mockResolvedValue({}),
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

    expect(screen.getByRole("heading", { name: "Bienvenida" })).toBeInTheDocument();
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

    fireEvent.change(screen.getByLabelText("Subir video de Introducción"), {
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
  it("switches admin modules without stacking the full route", () => {
    renderEditor({
      course: {
        id: "course-1",
        status: "PUBLISHED",
        managed_by_system: true,
        modules: [
          {
            id: "module-1",
            position: 1,
            title: "Módulo 1 · Bienvenida a ASIATI",
            lessons: [
              {
                id: "lesson-1",
                title: "Bienvenida",
                content_type: "ARTICLE",
                estimated_minutes: 2,
                is_optional: false,
              },
            ],
          },
          {
            id: "module-2",
            position: 2,
            title: "Módulo 2 · Entiende el negocio",
            lessons: [
              {
                id: "lesson-2",
                title: "Cómo funciona ASIATI",
                content_type: "ARTICLE",
                estimated_minutes: 3,
                is_optional: false,
              },
            ],
          },
        ],
      },
    });

    expect(document.querySelectorAll(".training-admin-module-tab")).toHaveLength(2);
    expect(screen.getByText("Bienvenida")).toBeInTheDocument();
    expect(screen.queryByText("Cómo funciona ASIATI")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Módulo 2.*Entiende el negocio/i }));

    expect(screen.getByText("Cómo funciona ASIATI")).toBeInTheDocument();
    expect(screen.queryByText("Bienvenida")).not.toBeInTheDocument();
  });

  it("lets admins edit the preloaded published onboarding without showing builders", async () => {
    const props = renderEditor({
      course: {
        status: "PUBLISHED",
        managed_by_system: true,
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
                description: "Video inicial",
                content_type: "VIDEO",
                estimated_minutes: 5,
                duration_seconds: 120,
                is_optional: false,
                video_url: "https://video.example.com/intro.mp4",
                video_source: "external",
                external_url: null,
                checklist_items: [],
                video_size_bytes: null,
              },
            ],
          },
        ],
      },
    });

    expect(screen.queryByRole("button", { name: "Agregar lección" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Agregar módulo/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Editar módulo" }));
    expect(screen.queryByLabelText("Editar cargo objetivo de módulo 1")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Editar área objetivo de módulo 1")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Editar título de módulo 1"), {
      target: { value: "Bienvenida actualizada" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar módulo" }));

    expect(props.onUpdateModule).toHaveBeenCalledWith(
      "module-1",
      expect.objectContaining({ title: "Bienvenida actualizada" }),
    );
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Guardar módulo" })).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Editar lección" }));
    fireEvent.change(screen.getByLabelText("Editar título de lección Introducción"), {
      target: { value: "Tu primer día" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar lección" }));

    expect(props.onUpdateLesson).toHaveBeenCalledWith(
      "lesson-1",
      expect.objectContaining({
        title: "Tu primer día",
        content_type: "VIDEO",
        duration_seconds: 120,
      }),
    );
    await waitFor(() => {
      expect(screen.getByLabelText("Reemplazar video de Introducción")).toBeInTheDocument();
    });
  });
});
