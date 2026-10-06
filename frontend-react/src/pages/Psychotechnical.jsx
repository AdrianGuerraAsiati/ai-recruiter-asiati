// eslint-disable-next-line no-unused-vars
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import PageHeader from "../components/ui/PageHeader";
import { EmptyState, FeedbackMessage, LoadingState } from "../components/ui/StatePanel";
import "./Psychotechnical.css";

const STATUS_LABELS = {
  PENDING: "Pendiente",
  IN_PROGRESS: "En curso",
  COMPLETED: "Completada",
  EXPIRED: "Expirada",
  CANCELED: "Cancelada",
};

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function durationLabel(seconds) {
  if (!Number.isFinite(Number(seconds))) return "—";
  const minutes = Math.floor(Number(seconds) / 60);
  const rest = Number(seconds) % 60;
  return `${minutes} min ${rest} s`;
}

function statusClass(status) {
  if (status === "COMPLETED") return "is-completed";
  if (status === "IN_PROGRESS") return "is-progress";
  if (status === "PENDING") return "is-pending";
  return "is-muted";
}

export default function Psychotechnical() {
  const [searchParams] = useSearchParams();
  const candidateIdFilter = searchParams.get("candidate_id") || "";
  const [items, setItems] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  const [assignOpen, setAssignOpen] = useState(false);
  const [candidateQuery, setCandidateQuery] = useState("");
  const [candidateOptions, setCandidateOptions] = useState([]);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [form, setForm] = useState({
    candidate_id: "",
    job_id: "",
    expires_days: 7,
  });
  const [saving, setSaving] = useState(false);
  const [createdLink, setCreatedLink] = useState("");
  const [copyNotice, setCopyNotice] = useState("");

  const loadAssignments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/psychotechnical/assignments", {
        params: {
          ...(status ? { status } : {}),
          ...(query.trim() ? { q: query.trim() } : {}),
          ...(candidateIdFilter ? { candidate_id: candidateIdFilter } : {}),
        },
      });
      setItems(data?.items || []);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, {
        action: "cargar las pruebas psicotécnicas",
        resource: "pruebas psicotécnicas",
        fallback: "No fue posible cargar las pruebas.",
      }));
    } finally {
      setLoading(false);
    }
  }, [candidateIdFilter, query, status]);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void loadAssignments();
    }, query.trim() ? 250 : 0);
    return () => window.clearTimeout(id);
  }, [loadAssignments, query]);

  useEffect(() => {
    api.get("/jobs")
      .then(({ data }) => setJobs((data || []).filter((job) => job.status !== "PAUSED")))
      .catch(() => setJobs([]));
  }, []);

  useEffect(() => {
    if (!assignOpen) return undefined;
    const normalized = candidateQuery.trim();
    if (normalized.length < 2) return undefined;

    const id = window.setTimeout(async () => {
      setCandidateLoading(true);
      try {
        const { data } = await api.get(
          `/candidates?page=1&page_size=20&q=${encodeURIComponent(normalized)}`,
        );
        setCandidateOptions((data?.items || []).filter((candidate) => !candidate.is_banned));
      } catch {
        setCandidateOptions([]);
      } finally {
        setCandidateLoading(false);
      }
    }, 250);

    return () => window.clearTimeout(id);
  }, [assignOpen, candidateQuery]);

  const metrics = useMemo(() => ({
    pending: items.filter((item) => item.status === "PENDING").length,
    inProgress: items.filter((item) => item.status === "IN_PROGRESS").length,
    completed: items.filter((item) => item.status === "COMPLETED").length,
  }), [items]);

  function openAssignment() {
    setForm({ candidate_id: "", job_id: "", expires_days: 7 });
    setCandidateQuery("");
    setCandidateOptions([]);
    setCreatedLink("");
    setCopyNotice("");
    setError("");
    setAssignOpen(true);
  }

  async function createAssignment(event) {
    event.preventDefault();
    if (!form.candidate_id || saving) return;
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post("/psychotechnical/assignments", {
        candidate_id: form.candidate_id,
        job_id: form.job_id || null,
        expires_days: Number(form.expires_days),
      });
      const link = `${window.location.origin}/psychotechnical/take/${data.token}`;
      setCreatedLink(link);
      await loadAssignments();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, {
        action: "asignar la prueba psicotécnica",
        resource: "prueba psicotécnica",
        fallback: "No fue posible asignar la prueba.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function copyLink() {
    if (!createdLink) return;
    try {
      await navigator.clipboard.writeText(createdLink);
      setCopyNotice("Enlace copiado.");
    } catch {
      setCopyNotice("Copia el enlace manualmente.");
    }
  }

  async function regenerateLink(assignment) {
    setError("");
    try {
      const { data } = await api.post(
        `/psychotechnical/assignments/${assignment.id}/link`,
        { expires_days: 7 },
      );
      setCreatedLink(`${window.location.origin}/psychotechnical/take/${data.token}`);
      setCopyNotice("");
      setAssignOpen(true);
      await loadAssignments();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, {
        action: "generar un nuevo enlace",
        resource: "prueba psicotécnica",
        fallback: "No fue posible generar un nuevo enlace.",
      }));
    }
  }

  async function cancelAssignment(assignment) {
    if (!window.confirm(`¿Cancelar la prueba de ${assignment.candidate_name || "este candidato"}?`)) return;
    try {
      await api.post(`/psychotechnical/assignments/${assignment.id}/cancel`);
      await loadAssignments();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, {
        action: "cancelar la prueba",
        resource: "prueba psicotécnica",
      }));
    }
  }

  return (
    <div className="page psychotechnical-page">
      <PageHeader
        eyebrow="Evaluación complementaria"
        title="Pruebas psicotécnicas"
        description="Asigna pruebas laborales objetivas de razonamiento y atención. Los resultados complementan el proceso y no toman decisiones de contratación automáticamente."
        actions={(
          <button className="btn btn-primary" type="button" onClick={openAssignment}>
            Asignar prueba
          </button>
        )}
      />

      <div className="psychotechnical-safety-note">
        <strong>Uso laboral, no clínico.</strong>
        <span>
          Esta prueba no diagnostica salud mental ni personalidad y no debe utilizarse como criterio único de selección.
        </span>
      </div>

      {error && <FeedbackMessage title="No pudimos completar la operación">{error}</FeedbackMessage>}

      <section className="psychotechnical-metrics" aria-label="Resumen de pruebas">
        <article className="panel psychotechnical-metric">
          <span>Pendientes</span>
          <strong>{metrics.pending}</strong>
          <small>Enlace generado, sin iniciar</small>
        </article>
        <article className="panel psychotechnical-metric">
          <span>En curso</span>
          <strong>{metrics.inProgress}</strong>
          <small>El candidato ya comenzó</small>
        </article>
        <article className="panel psychotechnical-metric">
          <span>Completadas</span>
          <strong>{metrics.completed}</strong>
          <small>Resultados disponibles</small>
        </article>
      </section>

      {candidateIdFilter && (
        <div className="psychotechnical-filter-note">
          Mostrando únicamente las pruebas del candidato seleccionado desde su perfil.
        </div>
      )}

      <section className="panel psychotechnical-directory">
        <div className="psychotechnical-toolbar">
          <div>
            <span className="eyebrow">Seguimiento</span>
            <h2>Asignaciones</h2>
          </div>
          <div className="psychotechnical-filters">
            <input
              type="search"
              value={query}
              placeholder="Buscar candidato o correo…"
              aria-label="Buscar pruebas por candidato"
              onChange={(event) => setQuery(event.target.value)}
            />
            <select
              value={status}
              aria-label="Filtrar por estado"
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">Todos los estados</option>
              <option value="PENDING">Pendientes</option>
              <option value="IN_PROGRESS">En curso</option>
              <option value="COMPLETED">Completadas</option>
              <option value="EXPIRED">Expiradas</option>
              <option value="CANCELED">Canceladas</option>
            </select>
          </div>
        </div>

        {loading ? (
          <LoadingState label="Cargando pruebas…" />
        ) : items.length === 0 ? (
          <EmptyState
            icon="check"
            title="No hay pruebas con este filtro"
            description="Asigna una prueba a un candidato para comenzar el seguimiento."
            action={<button className="btn btn-primary" type="button" onClick={openAssignment}>Asignar prueba</button>}
          />
        ) : (
          <div className="psychotechnical-list">
            {items.map((item) => (
              <article className="psychotechnical-assignment" key={item.id}>
                <div className="psychotechnical-assignment-main">
                  <div>
                    <span className={`psychotechnical-status ${statusClass(item.status)}`}>
                      {STATUS_LABELS[item.status] || item.status}
                    </span>
                    <h3>{item.candidate_name || "Candidato"}</h3>
                    <p>{item.candidate_email || "Sin correo registrado"}</p>
                    <small>{item.job_title ? `Vacante: ${item.job_title}` : "Sin vacante asociada"}</small>
                  </div>
                  <div className="psychotechnical-assignment-meta">
                    <span>Vence</span>
                    <strong>{formatDate(item.expires_at)}</strong>
                    {item.completed_at && <small>Completada {formatDate(item.completed_at)}</small>}
                  </div>
                </div>

                {item.status === "COMPLETED" && (
                  <div className="psychotechnical-result">
                    <div className="psychotechnical-score">
                      <span>Resultado objetivo</span>
                      <strong>{item.score_total}%</strong>
                      <small>{durationLabel(item.duration_seconds)}</small>
                    </div>
                    <div className="psychotechnical-dimensions">
                      {Object.entries(item.dimension_scores || {}).map(([key, dimension]) => (
                        <div key={key}>
                          <span>{dimension.label}</span>
                          <strong>{dimension.score}%</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {["PENDING", "IN_PROGRESS"].includes(item.status) && (
                  <div className="psychotechnical-assignment-actions">
                    <button
                      className="btn btn-secondary"
                      type="button"
                      onClick={() => regenerateLink(item)}
                    >
                      Nuevo enlace
                    </button>
                    <button
                      className="btn btn-secondary"
                      type="button"
                      onClick={() => cancelAssignment(item)}
                    >
                      Cancelar prueba
                    </button>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      {assignOpen && (
        <div className="modal-overlay" role="presentation" onMouseDown={() => !saving && setAssignOpen(false)}>
          <section
            className="modal psychotechnical-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="psychotechnical-assign-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">Nueva asignación</span>
                <h2 id="psychotechnical-assign-title">Asignar prueba psicotécnica</h2>
                <p>Razonamiento lógico, numérico, atención al detalle y comprensión verbal · 20 min.</p>
              </div>
              <button className="btn-close" type="button" aria-label="Cerrar" onClick={() => setAssignOpen(false)} disabled={saving}>×</button>
            </div>

            {createdLink ? (
              <div className="psychotechnical-link-ready">
                <span className="psychotechnical-link-icon">✓</span>
                <h3>Prueba asignada</h3>
                <p>Comparte este enlace únicamente con el candidato. Expira según el plazo configurado.</p>
                <div className="psychotechnical-link-box">
                  <input value={createdLink} readOnly aria-label="Enlace de la prueba" />
                  <button className="btn btn-primary" type="button" onClick={copyLink}>Copiar</button>
                </div>
                {copyNotice && <small>{copyNotice}</small>}
                <div className="form-actions">
                  <button className="btn btn-secondary" type="button" onClick={() => setAssignOpen(false)}>Cerrar</button>
                </div>
              </div>
            ) : (
              <form onSubmit={createAssignment}>
                <div className="form-group">
                  <label htmlFor="psychotechnical-candidate-search">Candidato</label>
                  <input
                    id="psychotechnical-candidate-search"
                    type="search"
                    placeholder="Escribe nombre o correo…"
                    value={candidateQuery}
                    onChange={(event) => {
                      setCandidateQuery(event.target.value);
                      setCandidateOptions([]);
                      setForm((current) => ({ ...current, candidate_id: "" }));
                    }}
                  />
                  {candidateLoading && <small>Buscando candidatos…</small>}
                  {candidateOptions.length > 0 && (
                    <div className="psychotechnical-candidate-options">
                      {candidateOptions.map((candidate) => (
                        <button
                          key={candidate.candidate_id}
                          type="button"
                          className={form.candidate_id === candidate.candidate_id ? "is-selected" : ""}
                          onClick={() => {
                            setForm((current) => ({ ...current, candidate_id: candidate.candidate_id }));
                            setCandidateQuery(candidate.name || candidate.email || "");
                            setCandidateOptions([]);
                          }}
                        >
                          <strong>{candidate.name || "Sin nombre"}</strong>
                          <span>{candidate.email || "Sin correo"}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {form.candidate_id && <small className="psychotechnical-selected">✓ Candidato seleccionado</small>}
                </div>

                <div className="form-group">
                  <label htmlFor="psychotechnical-job">Vacante asociada</label>
                  <select
                    id="psychotechnical-job"
                    value={form.job_id}
                    onChange={(event) => setForm((current) => ({ ...current, job_id: event.target.value }))}
                  >
                    <option value="">Sin vacante específica</option>
                    {jobs.map((job) => (
                      <option key={job.job_id} value={job.job_id}>{job.title}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="psychotechnical-expiry">Vigencia del enlace</label>
                  <select
                    id="psychotechnical-expiry"
                    value={form.expires_days}
                    onChange={(event) => setForm((current) => ({ ...current, expires_days: Number(event.target.value) }))}
                  >
                    <option value={3}>3 días</option>
                    <option value={7}>7 días</option>
                    <option value={14}>14 días</option>
                    <option value={30}>30 días</option>
                  </select>
                </div>

                <div className="psychotechnical-test-preview">
                  <strong>Razonamiento y atención</strong>
                  <span>12 preguntas · 20 minutos</span>
                  <small>Resultado separado del Ranking IA; no descarta candidatos automáticamente.</small>
                </div>

                <div className="form-actions">
                  <button className="btn btn-secondary" type="button" onClick={() => setAssignOpen(false)} disabled={saving}>Cancelar</button>
                  <button className="btn btn-primary" type="submit" disabled={saving || !form.candidate_id}>
                    {saving ? "Asignando…" : "Generar enlace"}
                  </button>
                </div>
              </form>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
