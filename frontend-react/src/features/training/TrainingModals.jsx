// eslint-disable-next-line no-unused-vars
import React from "react";

import { LoadingState } from "../../components/ui/StatePanel";
import { lessonTypeIcon, lessonTypeLabel } from "./trainingUtils";

export function TrainingPreviewModal({
  open,
  onClose,
  loading,
  employees,
  employeeId,
  onChangeEmployee,
  data,
}) {
  if (!open) return null;

  return (
    <div className="modal-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="modal training-preview-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="training-preview-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">Vista previa</span>
            <h2 id="training-preview-title">Así verá la ruta el empleado</h2>
            <p>La vista respeta los módulos configurados por cargo y área.</p>
          </div>
          <button
            className="btn-close"
            type="button"
            aria-label="Cerrar vista previa"
            onClick={onClose}
            disabled={loading}
          >
            ×
          </button>
        </div>

        {employees.length > 0 && (
          <div className="form-group">
            <label htmlFor="training-preview-employee">Previsualizar como</label>
            <select
              id="training-preview-employee"
              value={employeeId}
              onChange={(event) => void onChangeEmployee(event.target.value)}
              disabled={loading}
            >
              <option value="">Vista general</option>
              {employees.map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {[employee.first_name, employee.last_name].filter(Boolean).join(" ") || employee.email}
                  {employee.job_title ? ` · ${employee.job_title}` : ""}
                </option>
              ))}
            </select>
          </div>
        )}

        {loading ? (
          <LoadingState label="Preparando vista previa…" compact />
        ) : data ? (
          <div className="training-preview-body">
            {data.preview_employee && (
              <div className="training-preview-person">
                <strong>
                  {[data.preview_employee.first_name, data.preview_employee.last_name].filter(Boolean).join(" ")
                    || data.preview_employee.email}
                </strong>
                <span>
                  {[data.preview_employee.job_title, data.preview_employee.department].filter(Boolean).join(" · ")}
                </span>
              </div>
            )}

            <div className="training-preview-summary">
              <div>
                <span>Etapas visibles</span>
                <strong>{data.module_count}</strong>
              </div>
              <div>
                <span>Actividades</span>
                <strong>{data.lesson_count}</strong>
              </div>
              <div>
                <span>Tiempo conocido</span>
                <strong>~{data.quality?.known_minutes ?? data.estimated_minutes ?? 0} min</strong>
              </div>
            </div>

            <div className="training-preview-route">
              {data.modules?.map((module) => (
                <article key={module.id}>
                  <div>
                    <span>{module.position}</span>
                    <div>
                      <strong>{module.title}</strong>
                      <small>
                        {module.lesson_count} obligatorias
                        {module.audience_job_title ? ` · ${module.audience_job_title}` : ""}
                        {module.audience_department ? ` · ${module.audience_department}` : ""}
                      </small>
                    </div>
                  </div>
                  <ul>
                    {module.lessons?.map((lesson) => (
                      <li key={lesson.id}>
                        <span>{lessonTypeIcon(lesson.content_type)}</span>
                        <div>
                          <strong>{lesson.title}</strong>
                          <small>
                            {lessonTypeLabel(lesson.content_type)}
                            {lesson.estimated_minutes ? ` · ~${lesson.estimated_minutes} min` : " · duración por confirmar"}
                            {lesson.is_optional ? " · opcional" : ""}
                          </small>
                        </div>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>

            {data.has_quiz && (
              <div className="training-preview-quiz">
                <span>?</span>
                <div>
                  <strong>Evaluación final</strong>
                  <small>{data.quality?.quiz_question_count || 0} preguntas</small>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </section>
    </div>
  );
}

export function CreateTrainingCourseModal({
  open,
  onClose,
  form,
  onChange,
  onSubmit,
  saving,
}) {
  if (!open) return null;

  return (
    <div className="modal-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="modal training-course-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-course-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">Nuevo contenido</span>
            <h2 id="create-course-title">Crear curso</h2>
            <p>Comienza con la información general. Después podrás agregar módulos y videos.</p>
          </div>
          <button className="btn-close" type="button" aria-label="Cerrar" onClick={onClose}>×</button>
        </div>
        <form onSubmit={onSubmit}>
          <div className="form-group">
            <label htmlFor="training-course-title">Título</label>
            <input
              id="training-course-title"
              value={form.title}
              onChange={(event) => onChange({ title: event.target.value })}
              placeholder="Ej. Inducción ASIATI"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="training-course-description">Descripción</label>
            <textarea
              id="training-course-description"
              rows="4"
              value={form.description}
              onChange={(event) => onChange({ description: event.target.value })}
              placeholder="Objetivo y contexto del curso"
            />
          </div>
          <label className="training-onboarding-toggle">
            <input
              type="checkbox"
              checked={form.is_onboarding}
              onChange={(event) => onChange({ is_onboarding: event.target.checked })}
            />
            <span>
              <strong>Curso de inducción</strong>
              <small>Al asignarlo, el empleado entrará automáticamente en onboarding.</small>
            </span>
          </label>
          <div className="form-actions">
            <button className="btn btn-secondary" type="button" onClick={onClose}>Cancelar</button>
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? "Creando…" : "Crear curso"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
