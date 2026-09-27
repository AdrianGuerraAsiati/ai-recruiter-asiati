// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import PageHeader from "../components/ui/PageHeader";
import {
  EmptyState,
  FeedbackMessage,
  LoadingState,
} from "../components/ui/StatePanel";


function employeeName(employee) {
  return [employee?.first_name, employee?.last_name].filter(Boolean).join(" ")
    || employee?.email
    || "Empleado";
}


function EmployeeScores() {
  const [employees, setEmployees] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState(null);
  const [query, setQuery] = useState("");
  const [points, setPoints] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [voidTarget, setVoidTarget] = useState(null);
  const [voidReason, setVoidReason] = useState("");
  const [voiding, setVoiding] = useState(false);

  const loadEmployees = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = query.trim() ? { q: query.trim() } : {};
      const { data } = await api.get("/direction/employee-scores", { params });
      const items = Array.isArray(data?.items) ? data.items : [];
      setEmployees(items);
      setSelectedId((current) => {
        if (current && items.some((item) => item.id === current)) return current;
        return items[0]?.id || "";
      });
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar las calificaciones privadas",
        resource: "calificaciones de Dirección",
        fallback: "No se cargó el listado de puntuaciones. La información no fue modificada; vuelve a consultar la sección.",
      }));
    } finally {
      setLoading(false);
    }
  }, [query]);

  const loadDetail = useCallback(async (employeeId) => {
    if (!employeeId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setError("");
    try {
      const { data } = await api.get(`/direction/employee-scores/${employeeId}`);
      setDetail(data);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar el historial de calificaciones",
        resource: "historial del empleado",
        fallback: "La puntuación actual está visible, pero el historial de movimientos no se pudo consultar. Vuelve a seleccionar el empleado.",
      }));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadEmployees();
    }, 200);
    return () => window.clearTimeout(timeoutId);
  }, [loadEmployees]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadDetail(selectedId);
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadDetail, selectedId]);

  const selectedEmployee = useMemo(
    () => employees.find((employee) => employee.id === selectedId) || detail?.employee,
    [detail, employees, selectedId],
  );

  async function createEvent(event) {
    event.preventDefault();
    const numericPoints = Number(points);
    if (!Number.isInteger(numericPoints) || numericPoints === 0) {
      setError("Ingresa una cantidad de puntos distinta de cero.");
      return;
    }
    if (!description.trim()) {
      setError("Describe el motivo de la calificación.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      await api.post(`/direction/employee-scores/${selectedId}/events`, {
        points: numericPoints,
        description: description.trim(),
      });
      setPoints("");
      setDescription("");
      await Promise.all([loadEmployees(), loadDetail(selectedId)]);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "registrar la calificación",
        resource: "calificaciones de Dirección",
        fallback: "El movimiento no se registró y la puntuación no cambió. Revisa los puntos y la justificación antes de reintentar.",
      }));
    } finally {
      setSaving(false);
    }
  }

  function requestVoidEvent(scoreEvent) {
    setVoidTarget(scoreEvent);
    setVoidReason("");
  }

  function closeVoidDialog() {
    if (voiding) return;
    setVoidTarget(null);
    setVoidReason("");
  }

  async function submitVoidEvent(event) {
    event.preventDefault();
    if (!voidTarget || !voidReason.trim()) return;

    setVoiding(true);
    setError("");
    try {
      await api.post(`/direction/employee-scores/events/${voidTarget.id}/void`, {
        reason: voidReason.trim(),
      });
      setVoidTarget(null);
      setVoidReason("");
      await Promise.all([loadEmployees(), loadDetail(selectedId)]);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "anular el movimiento de puntuación",
        resource: "historial de calificaciones",
        fallback: "El movimiento sigue activo. Recarga el historial antes de intentar anularlo nuevamente.",
      }));
    } finally {
      setVoiding(false);
    }
  }

  return (
    <div className="page direction-score-page">
      <PageHeader
        eyebrow="Dirección · Privado"
        title="Calificación de empleados"
        description="Registra reconocimientos o descuentos con su justificación y conserva el historial completo."
      />

      <div className="direction-privacy-note">
        <strong>Información privada de Dirección</strong>
        <span>Esta sección y sus movimientos no están disponibles para administradores ni empleados.</span>
      </div>

      {error && <FeedbackMessage title="La operación no se completó">{error}</FeedbackMessage>}

      <div className="score-workspace">
        <aside className="panel score-employee-panel">
          <div className="score-employee-heading">
            <div>
              <span className="eyebrow">Equipo</span>
              <h2>Empleados</h2>
            </div>
            <span>{employees.length}</span>
          </div>

          <input
            className="score-search"
            type="search"
            placeholder="Buscar empleado…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Buscar empleado para calificar"
          />

          {loading ? (
            <LoadingState label="Cargando empleados…" compact />
          ) : employees.length === 0 ? (
            <EmptyState
              compact
              icon="users"
              title="Sin resultados"
              description="No encontramos empleados con ese filtro."
            />
          ) : (
            <div className="score-employee-list">
              {employees.map((employee) => (
                <button
                  key={employee.id}
                  type="button"
                  className={`score-employee-row ${employee.id === selectedId ? "active" : ""}`}
                  onClick={() => setSelectedId(employee.id)}
                >
                  <span className="employee-avatar" aria-hidden="true">
                    {(employee.first_name?.[0] || employee.email?.[0] || "?").toUpperCase()}
                  </span>
                  <span>
                    <strong>{employeeName(employee)}</strong>
                    <small>{employee.job_title || employee.department || employee.email}</small>
                  </span>
                  <b className={employee.score_total < 0 ? "score-negative" : "score-positive"}>
                    {employee.score_total > 0 ? "+" : ""}{employee.score_total}
                  </b>
                </button>
              ))}
            </div>
          )}
        </aside>

        <section className="score-detail-column">
          {!selectedEmployee ? (
            <section className="panel">
              <EmptyState
                icon="employee"
                title="Selecciona un empleado"
                description="Elige un perfil para consultar su historial y registrar una calificación."
              />
            </section>
          ) : (
            <>
              <section className="panel score-summary-panel">
                <div>
                  <span className="eyebrow">Puntuación actual</span>
                  <h2>{employeeName(selectedEmployee)}</h2>
                  <p>{selectedEmployee.job_title || "Sin cargo"} · {selectedEmployee.department || "Sin área"}</p>
                </div>
                <strong
                  key={`${selectedId}-${detail?.employee?.score_total ?? selectedEmployee.score_total ?? 0}`}
                  className={`direction-score-total ${(detail?.employee?.score_total ?? selectedEmployee.score_total) < 0 ? "score-negative" : "score-positive"}`}
                >
                  {(detail?.employee?.score_total ?? selectedEmployee.score_total) > 0 ? "+" : ""}
                  {detail?.employee?.score_total ?? selectedEmployee.score_total ?? 0}
                  <small> pts</small>
                </strong>
              </section>

              <section className="panel score-entry-panel">
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">Nuevo movimiento</span>
                    <h2>Agregar calificación</h2>
                  </div>
                </div>

                <form onSubmit={createEvent}>
                  <div className="score-entry-grid">
                    <div className="form-group">
                      <label htmlFor="score-points">Puntos</label>
                      <input
                        id="score-points"
                        type="number"
                        step="1"
                        value={points}
                        onChange={(event) => setPoints(event.target.value)}
                        placeholder="+30 o -5"
                        required
                      />
                      <small>Usa un valor positivo para reconocer y negativo para descontar.</small>
                    </div>
                    <div className="form-group">
                      <label htmlFor="score-description">Descripción</label>
                      <textarea
                        id="score-description"
                        rows="4"
                        value={description}
                        onChange={(event) => setDescription(event.target.value)}
                        placeholder="Ej. Completó exitosamente el proyecto de integración."
                        required
                      />
                    </div>
                  </div>
                  <div className="form-actions">
                    <button className="btn btn-primary" type="submit" disabled={saving || !selectedId}>
                      {saving ? "Guardando…" : "Guardar calificación"}
                    </button>
                  </div>
                </form>
              </section>

              <section className="panel score-history-panel">
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">Trazabilidad</span>
                    <h2>Historial de calificaciones</h2>
                  </div>
                </div>

                {detailLoading ? (
                  <LoadingState label="Cargando historial…" compact />
                ) : !detail?.history?.length ? (
                  <EmptyState
                    compact
                    icon="star"
                    title="Aún no hay movimientos"
                    description="La primera calificación aparecerá aquí."
                  />
                ) : (
                  <div className="score-history-list">
                    {detail.history.map((scoreEvent, index) => (
                      <article
                        key={scoreEvent.id}
                        className={`score-history-row ${scoreEvent.status === "VOIDED" ? "is-voided" : ""}`}
                        style={{ "--score-delay": `${Math.min(index, 8) * 45}ms` }}
                      >
                        <div className={`score-history-points ${scoreEvent.points < 0 ? "score-negative" : "score-positive"}`}>
                          {scoreEvent.points > 0 ? "+" : ""}{scoreEvent.points}
                        </div>
                        <div className="score-history-copy">
                          <strong>{scoreEvent.description}</strong>
                          <small>
                            {scoreEvent.event_date ? new Date(scoreEvent.event_date).toLocaleString("es-CO") : "Sin fecha"}
                            {scoreEvent.status === "VOIDED" ? " · ANULADO" : ""}
                          </small>
                          {scoreEvent.void_reason && <p>Motivo de anulación: {scoreEvent.void_reason}</p>}
                        </div>
                        {scoreEvent.status === "ACTIVE" && (
                          <button className="btn btn-ghost" type="button" onClick={() => requestVoidEvent(scoreEvent)}>
                            Anular
                          </button>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </section>
      </div>

      {voidTarget && (
        <div className="modal-overlay" role="presentation" onMouseDown={closeVoidDialog}>
          <section
            className="modal score-void-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="score-void-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">Trazabilidad</span>
                <h2 id="score-void-title">Anular movimiento</h2>
                <p>El movimiento seguirá visible en el historial y quedará marcado como anulado.</p>
              </div>
              <button className="btn btn-close" type="button" onClick={closeVoidDialog} disabled={voiding} aria-label="Cerrar">×</button>
            </div>

            <form onSubmit={submitVoidEvent}>
              <div className="form-group">
                <label htmlFor="score-void-reason">Motivo de la anulación</label>
                <textarea
                  id="score-void-reason"
                  rows="4"
                  value={voidReason}
                  onChange={(event) => setVoidReason(event.target.value)}
                  placeholder="Explica por qué este movimiento debe quedar anulado."
                  required
                  autoFocus
                />
              </div>
              <div className="form-actions">
                <button className="btn btn-secondary" type="button" onClick={closeVoidDialog} disabled={voiding}>Cancelar</button>
                <button className="btn btn-danger" type="submit" disabled={voiding || !voidReason.trim()}>
                  {voiding ? "Anulando…" : "Anular movimiento"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

export default EmployeeScores;
