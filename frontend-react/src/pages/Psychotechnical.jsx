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

function resultEntries(item) {
  return Object.entries(item.dimension_scores || {})
    .filter(([key, value]) => key !== "PROFILE" && value && typeof value === "object");
}

function ResultSummary({ item }) {
  const entries = resultEntries(item);
  const isValanti = item.test_key === "VALANTI_ASIATI";
  const profile = item.dimension_scores?.PROFILE;
  const scoredEntries = entries.filter(([, value]) => Number.isFinite(Number(value.score)));

  return (
    <div className="psychotechnical-result">
      <div className="psychotechnical-score">
        <span>{item.score_total == null ? "Lectura descriptiva" : "Resultado"}</span>
        {item.score_total == null ? (
          <strong className="psychotechnical-score-label">
            {profile?.profiles?.join(" / ") || profile?.highest || "Perfil disponible"}
          </strong>
        ) : (
          <strong>{item.score_total}%</strong>
        )}
        <small>{durationLabel(item.duration_seconds)}</small>
        {profile?.note && <small>{profile.note}</small>}
      </div>

      <div className="psychotechnical-dimensions">
        {scoredEntries.map(([key, dimension]) => (
          <div key={key}>
            <span>{dimension.label || key}</span>
            <strong>
              {Number(dimension.score).toFixed(Number(dimension.score) % 1 ? 1 : 0)}
              {isValanti ? "" : "%"}
            </strong>
            {dimension.band && <small>{dimension.band}</small>}
            {isValanti && Number.isFinite(Number(dimension.reference)) && (
              <small>Referencia ASIATI: {dimension.reference} · Δ {dimension.difference}</small>
            )}
            {Number.isFinite(Number(dimension.count)) && (
              <small>{dimension.count} de {dimension.total}</small>
            )}
            {Number.isFinite(Number(dimension.direct)) && (
              <small>Puntaje directo: {dimension.direct}</small>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Psychotechnical() {
  const [searchParams] = useSearchParams();
  const candidateIdFilter = searchParams.get("candidate_id") || "";
  const [catalog, setCatalog] = useState([]);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [testFilter, setTestFilter] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  const [copyNotice, setCopyNotice] = useState("");

  const loadAssignments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/psychotechnical/assignments", {
        params: {
          ...(status ? { status } : {}),
          ...(testFilter ? { test_key: testFilter } : {}),
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
  }, [candidateIdFilter, query, status, testFilter]);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void loadAssignments();
    }, query.trim() ? 250 : 0);
    return () => window.clearTimeout(id);
  }, [loadAssignments, query]);

  useEffect(() => {
    api.get("/psychotechnical/catalog")
      .then(({ data }) => setCatalog(data?.items || []))
      .catch(() => setCatalog([]));
  }, []);

  const metrics = useMemo(() => ({
    pending: items.filter((item) => item.status === "PENDING").length,
    inProgress: items.filter((item) => item.status === "IN_PROGRESS").length,
    completed: items.filter((item) => item.status === "COMPLETED").length,
  }), [items]);

  async function regenerateLink(assignment) {
    setError("");
    try {
      const { data } = await api.post(
        `/psychotechnical/assignments/${assignment.id}/link`,
        { expires_days: 7 },
      );
      const link = `${window.location.origin}/psychotechnical/take/${data.token}`;
      await navigator.clipboard.writeText(link);
      setCopyNotice("Nuevo enlace copiado para compartir de forma segura.");
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
    if (!window.confirm(`¿Cancelar ${assignment.test_name} para ${assignment.candidate_name || "este candidato"}?`)) return;
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
        eyebrow="Gestión de talento humano"
        title="Pruebas psicotécnicas"
        description="Digitaliza los formatos internos de ASIATI: Sentido Común, Temperamento, VALANTI y Atención al Detalle. Cada resultado se conserva separado del Ranking IA."

      />

      <div className="psychotechnical-safety-note">
        <strong>Evaluación complementaria.</strong>
        <span>
          Los resultados son descriptivos y de apoyo para Talento Humano. No descartan, seleccionan ni recomiendan candidatos automáticamente.
        </span>
      </div>

      {catalog.length > 0 && (
        <section className="psychotechnical-catalog" aria-label="Catálogo de pruebas ASIATI">
          {catalog.map((test) => (
            <article className="panel psychotechnical-catalog-card" key={test.key}>
              <div className="psychotechnical-catalog-top">
                <span className="psychotechnical-code">{test.code} · v{test.source_version}</span>
                <span>{test.duration_minutes} min</span>
              </div>
              <h2>{test.name}</h2>
              <p>{test.description}</p>
              <div className="psychotechnical-catalog-footer">
                <small>{test.question_count} ítems</small>
                <span className="psychotechnical-automatic-label">Automática</span>
              </div>
            </article>
          ))}
        </section>
      )}

      {error && <FeedbackMessage title="No pudimos completar la operación">{error}</FeedbackMessage>}
      {copyNotice && <FeedbackMessage title="Enlace actualizado" tone="success">{copyNotice}</FeedbackMessage>}

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
              value={testFilter}
              aria-label="Filtrar por prueba"
              onChange={(event) => setTestFilter(event.target.value)}
            >
              <option value="">Todas las pruebas</option>
              {catalog.map((test) => (
                <option key={test.key} value={test.key}>{test.name}</option>
              ))}
            </select>
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
            description="Las cuatro pruebas se asignan automáticamente cuando se inicia una postulación. Sus resultados aparecerán aquí."
          />
        ) : (
          <div className="psychotechnical-list">
            {items.map((item) => (
              <article className="psychotechnical-assignment" key={item.id}>
                <div className="psychotechnical-assignment-main">
                  <div>
                    <div className="psychotechnical-assignment-badges">
                      <span className={`psychotechnical-status ${statusClass(item.status)}`}>
                        {STATUS_LABELS[item.status] || item.status}
                      </span>
                      <span className="psychotechnical-test-badge">{item.test_code}</span>
                    </div>
                    <h3>{item.candidate_name || "Candidato"}</h3>
                    <p>{item.test_name}</p>
                    <small>{item.candidate_email || "Sin correo registrado"}</small>
                    <small>{item.job_title ? ` · Vacante: ${item.job_title}` : " · Sin vacante asociada"}</small>
                  </div>
                  <div className="psychotechnical-assignment-meta">
                    <span>Vence</span>
                    <strong>{formatDate(item.expires_at)}</strong>
                    {item.completed_at && <small>Completada {formatDate(item.completed_at)}</small>}
                  </div>
                </div>

                {item.status === "COMPLETED" && <ResultSummary item={item} />}

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


    </div>
  );
}
