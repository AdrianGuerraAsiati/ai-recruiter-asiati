// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import api from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import { EmptyState, FeedbackMessage, LoadingState } from "../components/ui/StatePanel";
import { getApiErrorMessage } from "../utils/errors";
import "../talent-id.css";


function emptySiteForm() {
  return {
    name: "",
    code: "",
    timezone: "America/Bogota",
  };
}


function emptyScheduleForm() {
  return {
    name: "",
    start_time: "08:30",
    end_time: "18:00",
    tolerance_minutes: 10,
  };
}


function AttendanceSettings() {
  const [sites, setSites] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [siteForm, setSiteForm] = useState(() => emptySiteForm());
  const [scheduleForm, setScheduleForm] = useState(() => emptyScheduleForm());

  const loadAll = useCallback(async (options = {}) => {
    const silent = options?.silent === true;
    if (!silent) setLoading(true);
    setError("");

    try {
      const [sitesResponse, schedulesResponse] = await Promise.all([
        api.get("/talent-id/sites"),
        api.get("/talent-id/schedules"),
      ]);
      setSites(sitesResponse.data?.items || []);
      setSchedules(schedulesResponse.data?.items || []);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar la configuración de asistencia",
        resource: "asistencia",
        fallback: "No se pudieron cargar sedes y horarios.",
      }));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadAll();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadAll]);

  const activeSites = useMemo(
    () => sites.filter((site) => site.active !== false),
    [sites],
  );
  const activeSchedules = useMemo(
    () => schedules.filter((schedule) => schedule.active !== false),
    [schedules],
  );

  async function createSite(event) {
    event.preventDefault();
    setSaving("site");
    setError("");
    setFeedback("");

    try {
      await api.post("/talent-id/sites", {
        name: siteForm.name.trim(),
        code: siteForm.code.trim() || null,
        timezone: siteForm.timezone.trim(),
      });
      setSiteForm(emptySiteForm());
      setFeedback("Sede creada. Ya puede asignarse a empleados y usarse al cargar reportes.");
      await loadAll({ silent: true });
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "crear la sede",
        resource: "asistencia",
        fallback: "No se pudo crear la sede. Revisa nombre, código y zona horaria.",
      }));
    } finally {
      setSaving("");
    }
  }

  async function createSchedule(event) {
    event.preventDefault();
    setSaving("schedule");
    setError("");
    setFeedback("");

    try {
      await api.post("/talent-id/schedules", {
        name: scheduleForm.name.trim(),
        start_time: scheduleForm.start_time,
        end_time: scheduleForm.end_time,
        tolerance_minutes: Number(scheduleForm.tolerance_minutes || 0),
      });
      setScheduleForm(emptyScheduleForm());
      setFeedback("Horario creado. Ya puede asignarse a empleados.");
      await loadAll({ silent: true });
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "crear el horario",
        resource: "asistencia",
        fallback: "No se pudo crear el horario. Revisa horas y tolerancia.",
      }));
    } finally {
      setSaving("");
    }
  }

  return (
    <div className="page talent-id-page">
      <PageHeader
        eyebrow="Asistencia · Configuración"
        title="Sedes y horarios"
        description="Configura la sede y jornada que Talent usará para interpretar los reportes exportados por los equipos de huella."
        actions={(
          <button className="btn btn-secondary" type="button" onClick={() => loadAll()} disabled={loading}>
            Actualizar
          </button>
        )}
        className="split-header"
      />

      <div className="talent-id-success">
        La marcación en línea, reconocimiento facial y QR móvil están suspendidos. La fuente oficial de asistencia son los reportes biométricos cargados en la vista Asistencia.
      </div>

      {error && <FeedbackMessage title="La configuración requiere atención">{error}</FeedbackMessage>}
      {feedback && <div className="talent-id-success" role="status">{feedback}</div>}

      {loading ? (
        <LoadingState label="Cargando configuración de asistencia…" />
      ) : (
        <div className="talent-id-admin-grid">
          <section className="panel talent-id-admin-card">
            <span className="eyebrow">1 · Ubicación</span>
            <h2>Sedes</h2>
            <p className="muted">
              Cada reporte se carga contra una sede. Los empleados deben tener esa misma sede asignada para que sus marcaciones se importen.
            </p>

            <form className="talent-id-admin-form" onSubmit={createSite}>
              <div className="form-group">
                <label htmlFor="talent-site-name">Nombre de sede</label>
                <input
                  id="talent-site-name"
                  value={siteForm.name}
                  onChange={(event) => setSiteForm({ ...siteForm, name: event.target.value })}
                  placeholder="Ej. Bogotá Principal"
                  required
                />
              </div>
              <div className="employee-form-grid">
                <div className="form-group">
                  <label htmlFor="talent-site-code">Código</label>
                  <input
                    id="talent-site-code"
                    value={siteForm.code}
                    onChange={(event) => setSiteForm({ ...siteForm, code: event.target.value.toUpperCase() })}
                    placeholder="BOG"
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="talent-site-timezone">Zona horaria</label>
                  <input
                    id="talent-site-timezone"
                    value={siteForm.timezone}
                    onChange={(event) => setSiteForm({ ...siteForm, timezone: event.target.value })}
                    required
                  />
                </div>
              </div>
              <button className="btn btn-primary" type="submit" disabled={saving === "site"}>
                {saving === "site" ? "Creando…" : "Crear sede"}
              </button>
            </form>

            <div className="talent-id-admin-list">
              {activeSites.length === 0 ? (
                <EmptyState compact title="Aún no hay sedes" description="Crea la sede antes de importar reportes." />
              ) : activeSites.map((site) => (
                <article key={site.id} className="talent-id-admin-row">
                  <div>
                    <strong>{site.name}</strong>
                    <small>{site.code || "Sin código"} · {site.timezone}</small>
                  </div>
                  <span className="status-pill"><i /> Activa</span>
                </article>
              ))}
            </div>
          </section>

          <section className="panel talent-id-admin-card">
            <span className="eyebrow">2 · Jornada</span>
            <h2>Horarios</h2>
            <p className="muted">
              El horario permite calcular puntualidad, minutos de retraso y jornadas completas después de importar el reporte.
            </p>

            <form className="talent-id-admin-form" onSubmit={createSchedule}>
              <div className="form-group">
                <label htmlFor="talent-schedule-name">Nombre del horario</label>
                <input
                  id="talent-schedule-name"
                  value={scheduleForm.name}
                  onChange={(event) => setScheduleForm({ ...scheduleForm, name: event.target.value })}
                  placeholder="Ej. Administrativo"
                  required
                />
              </div>
              <div className="employee-form-grid">
                <div className="form-group">
                  <label htmlFor="talent-schedule-start">Entrada</label>
                  <input
                    id="talent-schedule-start"
                    type="time"
                    value={scheduleForm.start_time}
                    onChange={(event) => setScheduleForm({ ...scheduleForm, start_time: event.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="talent-schedule-end">Salida</label>
                  <input
                    id="talent-schedule-end"
                    type="time"
                    value={scheduleForm.end_time}
                    onChange={(event) => setScheduleForm({ ...scheduleForm, end_time: event.target.value })}
                    required
                  />
                </div>
              </div>
              <div className="form-group">
                <label htmlFor="talent-schedule-tolerance">Tolerancia en minutos</label>
                <input
                  id="talent-schedule-tolerance"
                  type="number"
                  min="0"
                  max="180"
                  value={scheduleForm.tolerance_minutes}
                  onChange={(event) => setScheduleForm({ ...scheduleForm, tolerance_minutes: event.target.value })}
                />
              </div>
              <button className="btn btn-primary" type="submit" disabled={saving === "schedule"}>
                {saving === "schedule" ? "Creando…" : "Crear horario"}
              </button>
            </form>

            <div className="talent-id-admin-list">
              {activeSchedules.length === 0 ? (
                <EmptyState compact title="Aún no hay horarios" description="Crea un horario para calcular puntualidad." />
              ) : activeSchedules.map((schedule) => (
                <article key={schedule.id} className="talent-id-admin-row">
                  <div>
                    <strong>{schedule.name}</strong>
                    <small>
                      {String(schedule.start_time || "").slice(0, 5)}–{String(schedule.end_time || "").slice(0, 5)}
                      {" · "}{schedule.tolerance_minutes || 0} min tolerancia
                    </small>
                  </div>
                  <span className="status-pill"><i /> Activo</span>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default AttendanceSettings;
