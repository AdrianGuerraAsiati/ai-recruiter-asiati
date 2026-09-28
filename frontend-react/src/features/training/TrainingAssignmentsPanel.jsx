// eslint-disable-next-line no-unused-vars
import React from "react";

import { ProgressBar } from "../../components/ui/StatePanel";

export default function TrainingAssignmentsPanel({
  course,
  employees,
  employeeId,
  onEmployeeChange,
  onAssignCourse,
  saving,
  canViewResults,
  assignments,
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Distribución</span>
          <h2>Asignar a un empleado</h2>
        </div>
      </div>

      <form className="training-assignment-form" onSubmit={onAssignCourse}>
        <select
          aria-label="Empleado para asignar"
          value={employeeId}
          onChange={(event) => onEmployeeChange(event.target.value)}
          required
        >
          <option value="">Selecciona un empleado</option>
          {employees.map((employee) => (
            <option key={employee.id} value={employee.id}>
              {[employee.first_name, employee.last_name].filter(Boolean).join(" ") || employee.email}
            </option>
          ))}
        </select>
        <button
          className="btn btn-primary"
          type="submit"
          disabled={saving || course.status !== "PUBLISHED"}
        >
          Asignar curso
        </button>
      </form>

      {course.status !== "PUBLISHED" && (
        <p className="training-form-note">Publica el curso antes de asignarlo.</p>
      )}

      {canViewResults && assignments.length > 0 && (
        <div className="training-results-list">
          {assignments.map((assignment) => (
            <div className="training-result-row" key={assignment.id}>
              <div>
                <strong>
                  {[assignment.employee.first_name, assignment.employee.last_name].filter(Boolean).join(" ")
                    || assignment.employee.email}
                </strong>
                <small>
                  {assignment.employee.job_title
                    || assignment.employee.department
                    || assignment.employee.email}
                </small>
                {assignment.quiz_result && (
                  <small>
                    Quiz: {assignment.quiz_result.latest_score ?? "—"}%
                    {assignment.quiz_result.passed
                      ? " · aprobado"
                      : assignment.quiz_result.attempt_count
                        ? " · pendiente"
                        : " · sin intento"}
                  </small>
                )}
              </div>
              <div className="training-result-progress">
                <span>{assignment.course.progress_percent}%</span>
                <ProgressBar value={assignment.course.progress_percent} />
              </div>
              <span className="training-status training-status-published">
                {assignment.status === "COMPLETED" ? "Completado" : "En curso"}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
