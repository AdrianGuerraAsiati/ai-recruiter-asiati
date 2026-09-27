// eslint-disable-next-line no-unused-vars
import React from "react";

import { EmptyState } from "../../components/ui/StatePanel";

export function TrainingCourseSidebar({
  courses,
  selectedCourseId,
  onSelectCourse,
}) {
  return (
    <aside className="panel training-course-sidebar">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Administración</span>
          <h2>Cursos</h2>
        </div>
        <span className="training-count">{courses.length}</span>
      </div>

      {courses.length === 0 ? (
        <EmptyState
          compact
          icon="training"
          title="Aún no hay cursos"
          description="Crea el primer curso de inducción o capacitación."
        />
      ) : (
        <div className="training-course-list">
          {courses.map((course) => (
            <button
              className={`training-course-row ${course.id === selectedCourseId ? "active" : ""}`}
              key={course.id}
              type="button"
              onClick={() => onSelectCourse(course.id)}
            >
              <span>
                <strong>{course.title}</strong>
                <small>{course.module_count} módulos · {course.lesson_count} lecciones</small>
                {course.is_onboarding && <small className="training-onboarding-label">Inducción</small>}
              </span>
              <b className={`training-status training-status-${course.status.toLowerCase()}`}>
                {course.status === "PUBLISHED"
                  ? "Publicado"
                  : course.status === "ARCHIVED"
                    ? "Archivado"
                    : "Borrador"}
              </b>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}


export function TrainingCourseOverview({
  course,
  saving,
  onPreview,
  onPublish,
}) {
  return (
    <section className="panel training-course-overview">
      <div>
        <span className="eyebrow">Editor de curso</span>
        <h2>{course.title}</h2>
        <p>{course.description || "Sin descripción."}</p>
        {course.is_onboarding && (
          <span className="training-onboarding-badge">Curso de inducción</span>
        )}
      </div>
      <div className="training-course-overview-actions">
        <button className="btn btn-secondary" type="button" onClick={onPreview}>
          Vista previa
        </button>
        <span className={`training-status training-status-${String(course.status || "DRAFT").toLowerCase()}`}>
          {course.status === "PUBLISHED"
            ? "Publicado"
            : course.status === "ARCHIVED"
              ? "Archivado"
              : "Borrador"}
        </span>
        {course.status === "DRAFT" && (
          <button
            className="btn btn-primary"
            type="button"
            onClick={onPublish}
            disabled={saving}
          >
            Publicar curso
          </button>
        )}
      </div>
    </section>
  );
}


function qualityIssueTitle(issue) {
  if (issue.code === "LONG_ACTIVITY") return "Actividad extensa";
  if (issue.code === "UNKNOWN_DURATION") return "Duración pendiente";
  if (issue.code === "MISSING_VIDEO") return "Video pendiente";
  if (issue.code === "LONG_JOURNEY") return "Ruta extensa";
  if (issue.code === "MISSING_QUIZ") return "Evaluación pendiente";
  return "Sugerencia";
}


export function TrainingQualityPanel({ quality }) {
  if (!quality) return null;

  return (
    <section className="panel training-quality-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Control de calidad</span>
          <h2>Experiencia de onboarding</h2>
        </div>
        <span className={`training-quality-status ${quality.warning_count ? "has-warnings" : "is-ready"}`}>
          {quality.warning_count
            ? `${quality.warning_count} por revisar`
            : "Sin alertas"}
        </span>
      </div>

      <div className="training-quality-summary">
        <div>
          <span>Actividades obligatorias</span>
          <strong>{quality.required_activity_count}</strong>
        </div>
        <div>
          <span>Tiempo conocido</span>
          <strong>~{quality.known_minutes} min</strong>
        </div>
        <div>
          <span>Preguntas de quiz</span>
          <strong>{quality.quiz_question_count}</strong>
        </div>
      </div>

      {quality.issues?.length > 0 ? (
        <div className="training-quality-issues">
          {quality.issues.map((issue, index) => (
            <div
              className={`training-quality-issue is-${issue.severity}`}
              key={`${issue.code}-${issue.lesson_id || issue.module_id || index}`}
            >
              <span aria-hidden="true">{issue.severity === "warning" ? "!" : "i"}</span>
              <div>
                <strong>{qualityIssueTitle(issue)}</strong>
                <p>{issue.message}</p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="training-quality-ready">
          La ruta mantiene una estructura ligera con los datos configurados actualmente.
        </div>
      )}
    </section>
  );
}
