// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import api from "../api/client";
import TalentIdDeviceManager from "../components/TalentIdDeviceManager";
import TalentIdFaceEnrollment from "../components/TalentIdFaceEnrollment";
import PageHeader from "../components/ui/PageHeader";
import { EmptyState, FeedbackMessage, LoadingState, MetricCard } from "../components/ui/StatePanel";
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


function TalentId() {
  const [sites, setSites] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [devices, setDevices] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [readiness, setReadiness] = useState(null);
  const [siteForm, setSiteForm] = useState(() => emptySiteForm());
  const [scheduleForm, setScheduleForm] = useState(() => emptyScheduleForm());

  const loadAll = useCallback(async (options = {}) => {
    const silent = options?.silent === true;
    if (!silent) setLoading(true);
    setError("");

    try {
      const [sitesResponse, schedulesResponse, devicesResponse, employeesResponse, readinessResponse] = await Promise.all([
        api.get("/talent-id/sites"),
        api.get("/talent-id/schedules"),
        api.get("/talent-id/devices"),
        api.get("/employees", { params: { status: "ACTIVE" } }),
        api.get("/talent-id/readiness"),
      ]);
      setSites(sitesResponse.data?.items || []);
      setSchedules(schedulesResponse.data?.items || []);
      setDevices(devicesResponse.data?.items || []);
      setEmployees(employeesResponse.data?.items || []);
      setReadiness(readinessResponse.data || null);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar la configuración de Talent ID",
        resource: "Talent ID",
        fallback: "No se pudo cargar sedes, horarios, empleados y kioscos.",
      }));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      api.get("/talent-id/sites"),
      api.get("/talent-id/schedules"),
      api.get("/talent-id/devices"),
      api.get("/employees", { params: { status: "ACTIVE" } }),
      api.get("/talent-id/readiness"),
    ])
      .then(([sitesResponse, schedulesResponse, devicesResponse, employeesResponse, readinessResponse]) => {
        if (cancelled) return;
        setSites(sitesResponse.data?.items || []);
        setSchedules(schedulesResponse.data?.items || []);
        setDevices(devicesResponse.data?.items || []);
        setEmployees(employeesResponse.data?.items || []);
        setReadiness(readinessResponse.data || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(getApiErrorMessage(err, {
          action: "cargar la configuración de Talent ID",
          resource: "Talent ID",
          fallback: "No se pudo cargar sedes, horarios, empleados y kioscos.",
        }));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const activeSites = useMemo(
    () => sites.filter((site) => site.active !== false),
    [sites],
  );
  const activeSchedules = useMemo(
    () => schedules.filter((schedule) => schedule.active !== false),
    [schedules],
  );
  const activeDevices = useMemo(
    () => devices.filter((device) => device.active !== false),
    [devices],
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
      setFeedback("Sede creada. Ya puede asignarse a empleados y kioscos.");
      await loadAll({ silent: true });
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "crear la sede",
        resource: "Talent ID",
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
        resource: "Talent ID",
        fallback: "No se pudo crear el horario. Revisa horas y tolerancia.",
      }));
    } finally {
      setSaving("");
    }
  }

  return (
    <div className="page talent-id-page">
      <PageHeader
        eyebrow="Asistencia · Talent ID"
        title="Administración de Talent ID"
        description="Configura sedes, jornadas, fotos de reconocimiento y credenciales de los kioscos de asistencia facial desde un solo lugar."
        actions={(
          <button className="btn btn-secondary" type="button" onClick={loadAll} disabled={loading}>
            Actualizar
          </button>
        )}
        className="split-header"
      />

      {error && <FeedbackMessage title="Talent ID requiere atención">{error}</FeedbackMessage>}
      {feedback && <div className="talent-id-success" role="status">{feedback}</div>}

      {readiness && (
        <section
          className={`panel talent-id-readiness ${readiness.ready_for_pilot ? "is-ready" : "needs-attention"}`}
          aria-label="Preparación de Talent ID"
        >
          <div className="talent-id-readiness-heading">
            <div>
              <span className="eyebrow">Preparación del piloto</span>
              <h2>{readiness.ready_for_pilot ? "Configuración técnica lista" : "Faltan configuraciones para el piloto"}</h2>
              <p>
                {readiness.ready_for_pilot
                  ? "Biometría, firma electrónica, QR móvil, sede, horario y kiosco tienen la configuración mínima."
                  : "Completa los puntos pendientes antes de probar el flujo de punta a punta."}
              </p>
            </div>
            <span className={`status-pill ${readiness.ready_for_pilot ? "" : "status-disabled"}`}>
              <i /> {readiness.ready_for_pilot ? "Listo" : "Pendiente"}
            </span>
          </div>

          {(readiness.issues?.length > 0 || readiness.warnings?.length > 0) && (
            <div className="talent-id-readiness-items">
              {(readiness.issues || []).map((item) => (
                <span key={item} className="talent-id-readiness-item is-issue">{item}</span>
              ))}
              {(readiness.warnings || []).map((item) => (
                <span key={item} className="talent-id-readiness-item is-warning">{item}</span>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="metrics-grid talent-id-metrics" aria-label="Estado de Talent ID">
        <MetricCard icon="employee" label="Sedes activas" value={activeSites.length} detail="Disponibles para asistencia" tone="blue" />
        <MetricCard icon="calendar" label="Horarios activos" value={activeSchedules.length} detail="Disponibles para empleados" tone="cyan" />
        <MetricCard icon="profile" label="Kioscos activos" value={activeDevices.length} detail={`${devices.length} dispositivos registrados`} tone="violet" />
        <MetricCard icon="users" label="Empleados activos" value={employees.length} detail="Disponibles para enrolamiento" />
      </section>

      {loading ? (
        <LoadingState label="Cargando Talent ID…" />
      ) : (
        <div className="talent-id-admin-grid">
          <section className="panel talent-id-admin-card">
            <span className="eyebrow">1 · Ubicación</span>
            <h2>Sedes</h2>
            <p className="muted">Cada kiosco pertenece a una sede y solo registra asistencia de empleados asignados a ella.</p>

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
                <EmptyState compact title="Aún no hay sedes" description="Crea la sede del piloto para continuar." />
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
            <p className="muted">Define la jornada que luego se asignará a cada empleado desde el directorio.</p>

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
                <EmptyState compact title="Aún no hay horarios" description="Crea el horario del piloto para continuar." />
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

          <TalentIdFaceEnrollment
            employees={employees}
            sites={sites}
            schedules={schedules}
            onEmployeeUpdated={() => loadAll({ silent: true })}
          />

          <TalentIdDeviceManager
            sites={sites}
            devices={devices}
            onRefresh={loadAll}
            onError={setError}
            onFeedback={setFeedback}
          />
        </div>
      )}
    </div>
  );
}

export default TalentId;
