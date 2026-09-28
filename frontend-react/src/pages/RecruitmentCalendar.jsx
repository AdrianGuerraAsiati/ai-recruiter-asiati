// eslint-disable-next-line no-unused-vars
import React, { useEffect, useMemo, useState } from "react";
import api from "../api/client";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../utils/errors";
import PageHeader from "../components/ui/PageHeader";
import {
  EmptyState,
  FeedbackMessage,
  LoadingState,
} from "../components/ui/StatePanel";
import "./RecruitmentCalendar.css";

const KIND_LABELS = {
  PHONE_CALL: "Llamada telefónica",
  ONSITE_INTERVIEW: "Entrevista presencial",
};

const STATUS_LABELS = {
  SCHEDULED: "Programada",
  COMPLETED: "Realizada",
  CANCELED: "Cancelada",
};

const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

function monthStart(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addMonths(date, amount) {
  return new Date(date.getFullYear(), date.getMonth() + amount, 1);
}

function addDays(date, amount) {
  const next = new Date(date);
  next.setDate(next.getDate() + amount);
  return next;
}

function startOfCalendarGrid(date) {
  const first = monthStart(date);
  const mondayOffset = (first.getDay() + 6) % 7;
  return addDays(first, -mondayOffset);
}

function isoLocalInput(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function defaultWindow(kind = "PHONE_CALL", day = new Date()) {
  const start = new Date(day);
  start.setHours(9, 0, 0, 0);
  if (start < new Date()) {
    start.setTime(Date.now() + 60 * 60 * 1000);
    start.setMinutes(0, 0, 0);
  }
  const end = new Date(start);
  end.setMinutes(end.getMinutes() + (kind === "ONSITE_INTERVIEW" ? 60 : 30));
  return {
    starts_at: isoLocalInput(start),
    ends_at: isoLocalInput(end),
  };
}

function sameDay(left, right) {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate();
}

function formatTime(value) {
  return new Intl.DateTimeFormat("es-CO", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatLongDate(value) {
  return new Intl.DateTimeFormat("es-CO", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function applicationValue(application) {
  return `${application.job.job_id}::${application.candidate.candidate_id}`;
}

function RecruitmentCalendar() {
  const { hasPermission } = useSession();
  const canManage = hasPermission("candidates.manage");
  const [cursor, setCursor] = useState(() => monthStart(new Date()));
  const [events, setEvents] = useState([]);
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingEvent, setEditingEvent] = useState(null);
  const [form, setForm] = useState(() => ({
    application: "",
    kind: "PHONE_CALL",
    ...defaultWindow(),
    location: "",
    notes: "",
  }));

  const gridStart = useMemo(() => startOfCalendarGrid(cursor), [cursor]);
  const gridDays = useMemo(
    () => Array.from({ length: 42 }, (_, index) => addDays(gridStart, index)),
    [gridStart],
  );
  const rangeEnd = useMemo(() => addDays(gridStart, 42), [gridStart]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [eventsResponse, applicationsResponse] = await Promise.all([
        api.get("/recruitment-calendar/events", {
          params: {
            start: gridStart.toISOString(),
            end: rangeEnd.toISOString(),
          },
        }),
        api.get("/recruitment-calendar/applications"),
      ]);
      setEvents(Array.isArray(eventsResponse.data?.items) ? eventsResponse.data.items : []);
      setApplications(
        Array.isArray(applicationsResponse.data?.items)
          ? applicationsResponse.data.items
          : [],
      );
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, {
        action: "cargar la agenda",
        resource: "agenda de selección",
        fallback: "La agenda no se pudo actualizar. Reintenta para confirmar las citas programadas.",
      }));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gridStart.getTime(), rangeEnd.getTime()]);

  function openNew(day = new Date()) {
    const window = defaultWindow("PHONE_CALL", day);
    setEditingEvent(null);
    setForm({
      application: applications[0] ? applicationValue(applications[0]) : "",
      kind: "PHONE_CALL",
      ...window,
      location: "",
      notes: "",
    });
    setEditorOpen(true);
  }

  function openEdit(event) {
    setEditingEvent(event);
    setForm({
      application: `${event.job_id}::${event.candidate_id}`,
      kind: event.kind,
      starts_at: isoLocalInput(new Date(event.starts_at)),
      ends_at: isoLocalInput(new Date(event.ends_at)),
      location: event.location || "",
      notes: event.notes || "",
    });
    setEditorOpen(true);
  }

  function changeKind(kind) {
    setForm((current) => {
      const start = new Date(current.starts_at);
      const end = new Date(start);
      end.setMinutes(end.getMinutes() + (kind === "ONSITE_INTERVIEW" ? 60 : 30));
      return {
        ...current,
        kind,
        ends_at: isoLocalInput(end),
      };
    });
  }

  async function saveEvent(event) {
    event.preventDefault();
    if (!form.application) return;
    const [jobId, candidateId] = form.application.split("::");
    setSaving(true);
    setError("");
    try {
      const payload = {
        kind: form.kind,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
        location: form.location || null,
        notes: form.notes || null,
      };
      if (editingEvent) {
        await api.put(`/recruitment-calendar/events/${editingEvent.id}`, payload);
      } else {
        await api.post("/recruitment-calendar/events", {
          ...payload,
          job_id: jobId,
          candidate_id: candidateId,
        });
      }
      setEditorOpen(false);
      setEditingEvent(null);
      await load();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, {
        action: editingEvent ? "actualizar la cita" : "agendar la cita",
        resource: "agenda de selección",
        fallback: "La cita no se guardó. Revisa candidato, fecha y hora antes de reintentar.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function setEventStatus(event, status) {
    setSaving(true);
    setError("");
    try {
      await api.put(`/recruitment-calendar/events/${event.id}`, { status });
      await load();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, {
        action: "actualizar la cita",
        resource: "agenda de selección",
        fallback: "No se pudo cambiar el estado de la cita.",
      }));
    } finally {
      setSaving(false);
    }
  }

  const eventsByDay = useMemo(() => {
    const map = new Map();
    events.forEach((event) => {
      const key = new Date(event.starts_at).toDateString();
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(event);
    });
    return map;
  }, [events]);

  const upcoming = useMemo(
    () => events
      .filter((event) => event.status === "SCHEDULED" && new Date(event.ends_at) >= new Date())
      .sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at))
      .slice(0, 8),
    [events],
  );

  const monthLabel = new Intl.DateTimeFormat("es-CO", {
    month: "long",
    year: "numeric",
  }).format(cursor);

  return (
    <div className="page recruitment-calendar-page">
      <PageHeader
        eyebrow="Reclutamiento"
        title="Agenda de selección"
        description="Programa llamadas telefónicas y entrevistas presenciales de los candidatos que ya avanzaron en el proceso."
        className="split-header"
        actions={canManage ? (
          <button className="btn btn-primary" type="button" onClick={() => openNew()}>
            Agendar cita
          </button>
        ) : null}
      />

      {error && (
        <FeedbackMessage title="Hay un problema con la agenda">{error}</FeedbackMessage>
      )}

      <div className="recruitment-calendar-layout">
        <section className="panel recruitment-calendar-panel">
          <div className="recruitment-calendar-toolbar">
            <div>
              <span className="eyebrow">Calendario</span>
              <h2 className="calendar-month-title">{monthLabel}</h2>
            </div>
            <div className="calendar-nav-actions">
              <button className="btn btn-secondary" type="button" onClick={() => setCursor(addMonths(cursor, -1))}>
                Anterior
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setCursor(monthStart(new Date()))}>
                Hoy
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setCursor(addMonths(cursor, 1))}>
                Siguiente
              </button>
            </div>
          </div>

          {loading ? (
            <LoadingState label="Cargando agenda…" compact />
          ) : (
            <div className="recruitment-calendar-grid" role="grid" aria-label={`Agenda ${monthLabel}`}>
              {WEEKDAYS.map((day) => (
                <div className="calendar-weekday" role="columnheader" key={day}>{day}</div>
              ))}
              {gridDays.map((day) => {
                const dayEvents = eventsByDay.get(day.toDateString()) || [];
                const outsideMonth = day.getMonth() !== cursor.getMonth();
                const today = sameDay(day, new Date());
                return (
                  <div
                    className={`calendar-day ${outsideMonth ? "is-outside" : ""} ${today ? "is-today" : ""}`}
                    role="gridcell"
                    key={day.toISOString()}
                  >
                    <div className="calendar-day-header">
                      <span>{day.getDate()}</span>
                      {canManage && !outsideMonth && (
                        <button type="button" aria-label={`Agendar el ${day.getDate()}`} onClick={() => openNew(day)}>+</button>
                      )}
                    </div>
                    <div className="calendar-day-events">
                      {dayEvents.map((event) => (
                        <button
                          className={`calendar-event calendar-event--${event.kind.toLowerCase()} ${event.status !== "SCHEDULED" ? "is-muted" : ""}`}
                          type="button"
                          key={event.id}
                          onClick={() => openEdit(event)}
                          title={`${KIND_LABELS[event.kind]} · ${event.candidate.name}`}
                        >
                          <strong>{formatTime(event.starts_at)}</strong>
                          <span>{event.candidate.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <aside className="panel recruitment-upcoming-panel">
          <span className="eyebrow">Seguimiento</span>
          <h2>Próximas citas</h2>
          {upcoming.length === 0 ? (
            <EmptyState
              compact
              icon="calendar"
              title="No hay citas próximas"
              description="Cuando programes una llamada o entrevista aparecerá aquí."
            />
          ) : (
            <div className="recruitment-upcoming-list">
              {upcoming.map((event) => (
                <article className="recruitment-upcoming-item" key={event.id}>
                  <div>
                    <span className="calendar-event-kind">{KIND_LABELS[event.kind]}</span>
                    <strong>{event.candidate.name}</strong>
                    <small>{event.job.title}</small>
                  </div>
                  <time>{formatLongDate(event.starts_at)}</time>
                  {event.location && <small>{event.location}</small>}
                  {canManage && (
                    <div className="calendar-item-actions">
                      <button className="btn btn-secondary btn-sm" type="button" onClick={() => openEdit(event)}>
                        Editar
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        type="button"
                        disabled={saving}
                        onClick={() => void setEventStatus(event, "COMPLETED")}
                      >
                        Marcar realizada
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </aside>
      </div>

      {editorOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => !saving && setEditorOpen(false)}>
          <section className="modal recruitment-calendar-modal" role="dialog" aria-modal="true" aria-labelledby="calendar-editor-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <span className="eyebrow">{editingEvent ? "Editar cita" : "Nueva cita"}</span>
                <h2 id="calendar-editor-title">{editingEvent ? KIND_LABELS[editingEvent.kind] : "Agendar proceso"}</h2>
              </div>
              <button className="btn btn-ghost" type="button" onClick={() => setEditorOpen(false)} disabled={saving}>Cerrar</button>
            </div>

            <form onSubmit={saveEvent}>
              <div className="form-group">
                <label htmlFor="calendar-application">Candidato y vacante</label>
                <select
                  id="calendar-application"
                  value={form.application}
                  disabled={Boolean(editingEvent)}
                  required
                  onChange={(event) => setForm((current) => ({ ...current, application: event.target.value }))}
                >
                  <option value="">Selecciona una postulación</option>
                  {applications.map((application) => (
                    <option value={applicationValue(application)} key={application.id}>
                      {application.candidate.name} · {application.job.title}
                    </option>
                  ))}
                </select>
                {!editingEvent && applications.length === 0 && (
                  <p className="training-form-note">Primero marca al candidato como Seleccionado en Postulaciones.</p>
                )}
              </div>

              <div className="calendar-form-grid">
                <div className="form-group">
                  <label htmlFor="calendar-kind">Tipo</label>
                  <select id="calendar-kind" value={form.kind} onChange={(event) => changeKind(event.target.value)}>
                    <option value="PHONE_CALL">Llamada telefónica</option>
                    <option value="ONSITE_INTERVIEW">Entrevista presencial</option>
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="calendar-location">Lugar</label>
                  <input
                    id="calendar-location"
                    value={form.location}
                    placeholder={form.kind === "PHONE_CALL" ? "Opcional" : "Oficina ASIATI, sala…"}
                    onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="calendar-start">Inicio</label>
                  <input id="calendar-start" type="datetime-local" value={form.starts_at} required onChange={(event) => setForm((current) => ({ ...current, starts_at: event.target.value }))} />
                </div>
                <div className="form-group">
                  <label htmlFor="calendar-end">Fin</label>
                  <input id="calendar-end" type="datetime-local" value={form.ends_at} required onChange={(event) => setForm((current) => ({ ...current, ends_at: event.target.value }))} />
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="calendar-notes">Notas</label>
                <textarea
                  id="calendar-notes"
                  value={form.notes}
                  placeholder="Indicaciones para la llamada o la visita…"
                  onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
                />
              </div>

              <div className="modal-footer recruitment-calendar-modal-actions">
                {editingEvent?.status === "SCHEDULED" && (
                  <button className="btn btn-danger" type="button" disabled={saving} onClick={() => void setEventStatus(editingEvent, "CANCELED").then(() => setEditorOpen(false))}>
                    Cancelar cita
                  </button>
                )}
                {editingEvent?.status && editingEvent.status !== "SCHEDULED" && (
                  <span className="calendar-status-note">{STATUS_LABELS[editingEvent.status]}</span>
                )}
                <button className="btn btn-secondary" type="button" disabled={saving} onClick={() => setEditorOpen(false)}>
                  Volver
                </button>
                <button className="btn btn-primary" type="submit" disabled={saving || !form.application}>
                  {saving ? "Guardando…" : editingEvent ? "Guardar cambios" : "Agendar"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

export default RecruitmentCalendar;
