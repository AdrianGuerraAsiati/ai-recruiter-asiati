import React, { useState } from "react";

import {
  lessonTypeIcon,
  lessonTypeLabel,
} from "./trainingUtils";

function moduleDraft(module) {
  return {
    title: module.title || "",
    description: module.description || "",
    audience_job_title: module.audience_job_title || "",
    audience_department: module.audience_department || "",
  };
}

function lessonDraft(lesson) {
  return {
    title: lesson.title || "",
    description: lesson.description || "",
    video_url: lesson.video_source === "managed" ? "" : (lesson.video_url || ""),
    duration_seconds: lesson.duration_seconds || "",
    content_type: lesson.content_type || "VIDEO",
    external_url: lesson.external_url || "",
    estimated_minutes: lesson.estimated_minutes || "",
    checklist_items: (lesson.checklist_items || []).join("\n"),
    is_optional: Boolean(lesson.is_optional),
  };
}

export default function TrainingContentEditor({
  course,
  moduleForm,
  onModuleFormChange,
  lessonForm,
  onLessonFormChange,
  onAddModule,
  onAddLesson,
  onUpdateModule,
  onUpdateLesson,
  onUploadLessonVideo,
  uploadingLessonId,
  saving,
}) {
  const [editingModuleId, setEditingModuleId] = useState("");
  const [moduleEdit, setModuleEdit] = useState(null);
  const [editingLessonId, setEditingLessonId] = useState("");
  const [lessonEdit, setLessonEdit] = useState(null);

  const canEditExisting = course.status === "DRAFT" || Boolean(course.managed_by_system);
  const canCreateContent = course.status === "DRAFT" && !course.managed_by_system;

  function beginModuleEdit(module) {
    setEditingModuleId(module.id);
    setModuleEdit(moduleDraft(module));
  }

  async function saveModule(event, module) {
    event.preventDefault();
    if (!moduleEdit) return;
    await onUpdateModule(module.id, {
      title: moduleEdit.title.trim(),
      description: moduleEdit.description.trim() || null,
      audience_job_title: moduleEdit.audience_job_title.trim() || null,
      audience_department: moduleEdit.audience_department.trim() || null,
    });
    setEditingModuleId("");
    setModuleEdit(null);
  }

  function beginLessonEdit(lesson) {
    setEditingLessonId(lesson.id);
    setLessonEdit(lessonDraft(lesson));
  }

  async function saveLesson(event, lesson) {
    event.preventDefault();
    if (!lessonEdit) return;
    const duration = lessonEdit.duration_seconds
      ? Number.parseInt(lessonEdit.duration_seconds, 10)
      : null;
    const estimatedMinutes = lessonEdit.estimated_minutes
      ? Number.parseInt(lessonEdit.estimated_minutes, 10)
      : null;
    await onUpdateLesson(lesson.id, {
      title: lessonEdit.title.trim(),
      description: lessonEdit.description.trim() || null,
      video_url: lessonEdit.video_url.trim() || null,
      duration_seconds: Number.isInteger(duration) ? duration : null,
      content_type: lessonEdit.content_type,
      external_url: lessonEdit.external_url.trim() || null,
      estimated_minutes: Number.isInteger(estimatedMinutes) ? estimatedMinutes : null,
      checklist_items: lessonEdit.content_type === "CHECKLIST"
        ? lessonEdit.checklist_items
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean)
        : [],
      is_optional: Boolean(lessonEdit.is_optional),
    });
    setEditingLessonId("");
    setLessonEdit(null);
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Contenido</span>
          <h2>Módulos y lecciones</h2>
          {course.managed_by_system && (
            <p className="muted">
              Esta ruta ya viene lista. Puedes editar el contenido existente sin crear la estructura desde cero.
            </p>
          )}
        </div>
      </div>

      <div className="training-module-list">
        {course.modules?.map((module) => (
          <article className="training-module-card" key={module.id}>
            <div className="training-module-header">
              {editingModuleId === module.id && moduleEdit ? (
                <form className="training-inline-form" onSubmit={(event) => saveModule(event, module)}>
                  <strong>Editar módulo {module.position}</strong>
                  <input
                    aria-label={`Editar título de módulo ${module.position}`}
                    value={moduleEdit.title}
                    onChange={(event) => setModuleEdit((current) => ({ ...current, title: event.target.value }))}
                    required
                  />
                  <textarea
                    aria-label={`Editar descripción de módulo ${module.position}`}
                    value={moduleEdit.description}
                    onChange={(event) => setModuleEdit((current) => ({ ...current, description: event.target.value }))}
                    rows="3"
                  />
                  {!course.managed_by_system && (
                    <div className="training-inline-grid">
                      <input
                        aria-label={`Editar cargo objetivo de módulo ${module.position}`}
                        placeholder="Cargo específico (opcional)"
                        value={moduleEdit.audience_job_title}
                        onChange={(event) => setModuleEdit((current) => ({ ...current, audience_job_title: event.target.value }))}
                      />
                      <input
                        aria-label={`Editar área objetivo de módulo ${module.position}`}
                        placeholder="Área específica (opcional)"
                        value={moduleEdit.audience_department}
                        onChange={(event) => setModuleEdit((current) => ({ ...current, audience_department: event.target.value }))}
                      />
                    </div>
                  )}
                  <div className="training-inline-grid">
                    <button className="btn btn-primary" type="submit" disabled={saving}>Guardar módulo</button>
                    <button
                      className="btn btn-secondary"
                      type="button"
                      disabled={saving}
                      onClick={() => {
                        setEditingModuleId("");
                        setModuleEdit(null);
                      }}
                    >
                      Cancelar
                    </button>
                  </div>
                </form>
              ) : (
                <div>
                  <span>Módulo {module.position}</span>
                  <h3>{module.title}</h3>
                  {module.description && <p>{module.description}</p>}
                  {(module.audience_job_title || module.audience_department) && (
                    <small className="training-audience-badge">
                      Solo para: {module.audience_job_title || "cualquier cargo"}
                      {module.audience_department ? ` · ${module.audience_department}` : ""}
                    </small>
                  )}
                </div>
              )}
              <div>
                <strong>{module.lessons?.length || 0} lecciones</strong>
                {canEditExisting && editingModuleId !== module.id && (
                  <button
                    className="btn btn-secondary"
                    type="button"
                    onClick={() => beginModuleEdit(module)}
                    disabled={saving}
                  >
                    Editar módulo
                  </button>
                )}
              </div>
            </div>

            <div className="training-lesson-list">
              {module.lessons?.map((lesson) => (
                <div className="training-lesson-row training-lesson-admin-row" key={lesson.id}>
                  {editingLessonId === lesson.id && lessonEdit ? (
                    <form className="training-inline-form" onSubmit={(event) => saveLesson(event, lesson)}>
                      <strong>Editar lección</strong>
                      <input
                        aria-label={`Editar título de lección ${lesson.title}`}
                        value={lessonEdit.title}
                        onChange={(event) => setLessonEdit((current) => ({ ...current, title: event.target.value }))}
                        required
                      />
                      <textarea
                        aria-label={`Editar descripción de lección ${lesson.title}`}
                        value={lessonEdit.description}
                        onChange={(event) => setLessonEdit((current) => ({ ...current, description: event.target.value }))}
                        rows="3"
                      />
                      <div className="training-inline-grid training-content-type-grid">
                        <select
                          aria-label={`Editar tipo de lección ${lesson.title}`}
                          value={lessonEdit.content_type}
                          onChange={(event) => setLessonEdit((current) => ({ ...current, content_type: event.target.value }))}
                        >
                          <option value="VIDEO">Video</option>
                          <option value="ARTICLE">Lectura</option>
                          <option value="RESOURCE">Recurso externo</option>
                          <option value="CHECKLIST">Checklist</option>
                        </select>
                        <input
                          aria-label={`Editar tiempo estimado de lección ${lesson.title}`}
                          type="number"
                          min="1"
                          max="1440"
                          value={lessonEdit.estimated_minutes}
                          onChange={(event) => setLessonEdit((current) => ({ ...current, estimated_minutes: event.target.value }))}
                          placeholder="Tiempo estimado (min)"
                        />
                      </div>
                      {lessonEdit.content_type === "VIDEO" && (
                        <div className="training-inline-grid">
                          <input
                            aria-label={`Editar URL de video de lección ${lesson.title}`}
                            type="url"
                            placeholder={lesson.video_source === "managed" ? "Video administrado en S3" : "https://..."}
                            value={lessonEdit.video_url}
                            disabled={lesson.video_source === "managed"}
                            onChange={(event) => setLessonEdit((current) => ({ ...current, video_url: event.target.value }))}
                          />
                          <input
                            aria-label={`Editar duración de lección ${lesson.title}`}
                            type="number"
                            min="1"
                            value={lessonEdit.duration_seconds}
                            onChange={(event) => setLessonEdit((current) => ({ ...current, duration_seconds: event.target.value }))}
                            placeholder="Duración (segundos)"
                          />
                        </div>
                      )}
                      {lessonEdit.content_type === "RESOURCE" && (
                        <input
                          aria-label={`Editar URL de recurso de lección ${lesson.title}`}
                          type="url"
                          value={lessonEdit.external_url}
                          onChange={(event) => setLessonEdit((current) => ({ ...current, external_url: event.target.value }))}
                          placeholder="https://..."
                          required
                        />
                      )}
                      {lessonEdit.content_type === "CHECKLIST" && (
                        <textarea
                          aria-label={`Editar checklist de lección ${lesson.title}`}
                          value={lessonEdit.checklist_items}
                          onChange={(event) => setLessonEdit((current) => ({ ...current, checklist_items: event.target.value }))}
                          rows="5"
                        />
                      )}
                      <label className="training-optional-toggle">
                        <input
                          type="checkbox"
                          checked={lessonEdit.is_optional}
                          onChange={(event) => setLessonEdit((current) => ({ ...current, is_optional: event.target.checked }))}
                        />
                        <span>Contenido opcional (no bloquea el avance)</span>
                      </label>
                      <div className="training-inline-grid">
                        <button className="btn btn-primary" type="submit" disabled={saving}>Guardar lección</button>
                        <button
                          className="btn btn-secondary"
                          type="button"
                          disabled={saving}
                          onClick={() => {
                            setEditingLessonId("");
                            setLessonEdit(null);
                          }}
                        >
                          Cancelar
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <span className="training-play" aria-hidden="true">{lessonTypeIcon(lesson.content_type)}</span>
                      <div className="training-lesson-admin-copy">
                        <strong>{lesson.title}</strong>
                        <small>
                          {lessonTypeLabel(lesson.content_type)}
                          {lesson.estimated_minutes ? ` · ~${lesson.estimated_minutes} min` : ""}
                          {lesson.is_optional ? " · opcional" : ""}
                        </small>
                        {lesson.video_url && (
                          <small>
                            {lesson.video_source === "managed"
                              ? "Video privado en S3"
                              : "Video por URL externa"}
                          </small>
                        )}
                        {lesson.external_url && <small>Recurso externo configurado</small>}
                        {lesson.content_type === "CHECKLIST" && lesson.checklist_items?.length > 0 && (
                          <small>{lesson.checklist_items.length} puntos de checklist</small>
                        )}
                        {lesson.video_size_bytes ? (
                          <small>{Math.max(1, Math.round(lesson.video_size_bytes / (1024 * 1024)))} MB</small>
                        ) : null}
                      </div>
                      {canEditExisting && (
                        <div>
                          <button
                            className="btn btn-secondary"
                            type="button"
                            onClick={() => beginLessonEdit(lesson)}
                            disabled={saving}
                          >
                            Editar lección
                          </button>
                          {lesson.content_type === "VIDEO" && (
                            <label className={`training-video-upload-button ${uploadingLessonId === lesson.id ? "is-uploading" : ""}`}>
                              <span>
                                {uploadingLessonId === lesson.id
                                  ? "Subiendo…"
                                  : lesson.video_url
                                    ? "Reemplazar video"
                                    : "Subir video"}
                              </span>
                              <input
                                aria-label={lesson.video_url ? `Reemplazar video de ${lesson.title}` : `Subir video de ${lesson.title}`}
                                type="file"
                                accept="video/mp4,video/webm,video/ogg"
                                disabled={Boolean(uploadingLessonId)}
                                onChange={(event) => {
                                  const file = event.target.files?.[0];
                                  event.target.value = "";
                                  void onUploadLessonVideo(lesson.id, file);
                                }}
                              />
                            </label>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>

            {canCreateContent && (
              <form className="training-inline-form" onSubmit={(event) => onAddLesson(event, module.id)}>
                <strong>Nueva lección</strong>
                <input
                  aria-label={`Título de lección para ${module.title}`}
                  placeholder="Título de la lección"
                  value={lessonForm(module.id).title}
                  onChange={(event) => onLessonFormChange(module.id, { title: event.target.value })}
                  required
                />
                <textarea
                  aria-label={`Descripción de lección para ${module.title}`}
                  placeholder="Descripción breve"
                  value={lessonForm(module.id).description}
                  onChange={(event) => onLessonFormChange(module.id, { description: event.target.value })}
                  rows="2"
                />
                <div className="training-inline-grid training-content-type-grid">
                  <select
                    aria-label={`Tipo de contenido para ${module.title}`}
                    value={lessonForm(module.id).content_type}
                    onChange={(event) => onLessonFormChange(module.id, { content_type: event.target.value })}
                  >
                    <option value="VIDEO">Video</option>
                    <option value="ARTICLE">Lectura</option>
                    <option value="RESOURCE">Recurso externo</option>
                    <option value="CHECKLIST">Checklist</option>
                  </select>
                  <input
                    aria-label={`Tiempo estimado para ${module.title}`}
                    type="number"
                    min="1"
                    max="1440"
                    placeholder="Tiempo estimado (min)"
                    value={lessonForm(module.id).estimated_minutes}
                    onChange={(event) => onLessonFormChange(module.id, { estimated_minutes: event.target.value })}
                  />
                </div>
                {lessonForm(module.id).content_type === "VIDEO" && (
                  <div className="training-inline-grid">
                    <input
                      aria-label={`URL de video para ${module.title}`}
                      type="url"
                      placeholder="https://.../video.mp4"
                      value={lessonForm(module.id).video_url}
                      onChange={(event) => onLessonFormChange(module.id, { video_url: event.target.value })}
                    />
                    <input
                      aria-label={`Duración de lección para ${module.title}`}
                      type="number"
                      min="1"
                      placeholder="Duración (segundos)"
                      value={lessonForm(module.id).duration_seconds}
                      onChange={(event) => onLessonFormChange(module.id, { duration_seconds: event.target.value })}
                    />
                  </div>
                )}
                {lessonForm(module.id).content_type === "RESOURCE" && (
                  <input
                    aria-label={`URL de recurso para ${module.title}`}
                    type="url"
                    placeholder="https://..."
                    value={lessonForm(module.id).external_url}
                    onChange={(event) => onLessonFormChange(module.id, { external_url: event.target.value })}
                    required
                  />
                )}
                {lessonForm(module.id).content_type === "CHECKLIST" && (
                  <textarea
                    aria-label={`Puntos de checklist para ${module.title}`}
                    placeholder={"Un punto por línea\nEj. Tengo acceso al correo\nSé quién es mi líder"}
                    value={lessonForm(module.id).checklist_items}
                    onChange={(event) => onLessonFormChange(module.id, { checklist_items: event.target.value })}
                    rows="5"
                  />
                )}
                <label className="training-optional-toggle">
                  <input
                    type="checkbox"
                    checked={lessonForm(module.id).is_optional}
                    onChange={(event) => onLessonFormChange(module.id, { is_optional: event.target.checked })}
                  />
                  <span>Contenido opcional (no bloquea el avance)</span>
                </label>
                <button className="btn btn-secondary" type="submit" disabled={saving}>
                  Agregar lección
                </button>
              </form>
            )}
          </article>
        ))}
      </div>

      {canCreateContent && (
        <form className="training-module-form" onSubmit={onAddModule}>
          <span className="eyebrow">Nuevo módulo</span>
          <div className="training-inline-grid">
            <input
              aria-label="Título del módulo"
              placeholder="Ej. Bienvenida a ASIATI"
              value={moduleForm.title}
              onChange={(event) => onModuleFormChange({ title: event.target.value })}
              required
            />
            <input
              aria-label="Descripción del módulo"
              placeholder="Descripción breve"
              value={moduleForm.description}
              onChange={(event) => onModuleFormChange({ description: event.target.value })}
            />
          </div>
          <div className="training-inline-grid">
            <input
              aria-label="Cargo objetivo del módulo"
              placeholder="Cargo específico (opcional)"
              value={moduleForm.audience_job_title}
              onChange={(event) => onModuleFormChange({ audience_job_title: event.target.value })}
            />
            <input
              aria-label="Área objetivo del módulo"
              placeholder="Área específica (opcional)"
              value={moduleForm.audience_department}
              onChange={(event) => onModuleFormChange({ audience_department: event.target.value })}
            />
          </div>
          <p className="training-form-note">
            Si dejas cargo y área vacíos, el módulo será visible para todos los empleados asignados.
          </p>
          <button className="btn btn-secondary" type="submit" disabled={saving}>
            + Agregar módulo
          </button>
        </form>
      )}
    </section>
  );
}
