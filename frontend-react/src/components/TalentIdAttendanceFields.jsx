// eslint-disable-next-line no-unused-vars
import React from "react";


function TalentIdAttendanceFields({
  attendance,
  sites = [],
  schedules = [],
  onChange,
  disabled = false,
  compact = false,
}) {
  const activeSites = sites.filter((item) => item.active !== false);
  const activeSchedules = schedules.filter((item) => item.active !== false);
  const noCatalog = activeSites.length === 0 || activeSchedules.length === 0;

  return (
    <section className={`talent-id-attendance-editor ${compact ? "is-compact" : ""}`}>
      <div className="talent-id-attendance-heading">
        <div>
          <span className="eyebrow">Asistencia</span>
          <h3>Configuración de marcación</h3>
          <p>Define si el empleado puede marcar y desde qué sede y jornada.</p>
        </div>
        <span className={`status-pill ${attendance?.attendance_eligible ? "" : "status-disabled"}`}>
          <i /> {attendance?.attendance_eligible ? "Habilitada" : "Deshabilitada"}
        </span>
      </div>

      {noCatalog ? (
        <div className="talent-id-biometric-blocker">
          Debe existir al menos una sede y un horario activos antes de habilitar asistencia.
        </div>
      ) : (
        <>
          <div className="talent-id-attendance-grid">
            <div className="form-group">
              <label htmlFor="talent-id-attendance-site">Sede</label>
              <select
                id="talent-id-attendance-site"
                value={attendance?.site_id || ""}
                onChange={(event) => onChange?.({
                  ...attendance,
                  site_id: event.target.value,
                })}
                disabled={disabled}
              >
                <option value="">Selecciona una sede</option>
                {activeSites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}{site.code ? ` · ${site.code}` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="talent-id-attendance-schedule">Horario</label>
              <select
                id="talent-id-attendance-schedule"
                value={attendance?.schedule_id || ""}
                onChange={(event) => onChange?.({
                  ...attendance,
                  schedule_id: event.target.value,
                })}
                disabled={disabled}
              >
                <option value="">Selecciona un horario</option>
                {activeSchedules.map((schedule) => (
                  <option key={schedule.id} value={schedule.id}>
                    {schedule.name} · {String(schedule.start_time || "").slice(0, 5)}–{String(schedule.end_time || "").slice(0, 5)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="talent-id-attendance-toggle">
            <input
              id="talent-id-attendance-enabled"
              type="checkbox"
              checked={Boolean(attendance?.attendance_eligible)}
              onChange={(event) => onChange?.({
                ...attendance,
                attendance_eligible: event.target.checked,
              })}
              disabled={disabled}
            />
            <label htmlFor="talent-id-attendance-enabled">
              <strong>Habilitar marcación de asistencia</strong>
              <span>Al activarlo, este empleado podrá ser reconocido y registrar entrada/salida en los kioscos de su sede.</span>
            </label>
          </div>
        </>
      )}
    </section>
  );
}

export default TalentIdAttendanceFields;
