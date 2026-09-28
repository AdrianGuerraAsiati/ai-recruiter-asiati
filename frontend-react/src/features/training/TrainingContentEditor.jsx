// eslint-disable-next-line no-unused-vars
import React from "react";

import {
  lessonTypeIcon,
  lessonTypeLabel,
} from "./trainingUtils";

export default function TrainingContentEditor({
  course,
  moduleForm,
  onModuleFormChange,
  lessonForm,
  onLessonFormChange,
  onAddModule,
  onAddLesson,
  onUploadLessonVideo,
  uploadingLessonId,
  saving,
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Contenido</span>
          <h2>Módulos y lecciones</h2>
        </div>
      </div>

      <div className="training-module-list">
        {course.modules?.map((module) => (
          <article className="training-module-card" key={module.id}>
            <div className="training-module-header">
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
              <strong>{module.lessons?.length || 0} lecciones</strong>
            </div>

            <div className="training-lesson-list">
              {module.lessons?.map((lesson) => (
                <div className="training-lesson-row training-lesson-admin-row" key={lesson.id}>
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
                  {course.status === "DRAFT" && (
                    <label className={`training-video-upload-button ${uploadingLessonId === lesson.id ? "is-uploading" : ""}`}>
                      <span>
                        {uploadingLessonId === lesson.id
                          ? "Subiendo…"
                          : lesson.video_url
                            ? "Reemplazar video"
                            : "Subir video"}
                      </span>
                      <input
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
              ))}
            </div>

            {course.status === "DRAFT" && (
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

      {course.status === "DRAFT" && (
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
