// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import PageHeader from "../components/ui/PageHeader";
import {
  EmptyState,
  FeedbackMessage,
  LoadingState,
  MetricCard,
} from "../components/ui/StatePanel";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  ["APPLIED", "Aplicó"],
  ["SCREENING", "En filtro"],
  ["SELECTED", "Seleccionado"],
  ["INTERVIEW", "Entrevista"],
  ["OFFER", "Oferta"],
  ["HIRED", "Contratado"],
  ["ON_HOLD", "En espera"],
  ["REJECTED", "Rechazado"],
  ["WITHDRAWN", "Retirado"],
];


function Applications() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState("");
  const [error, setError] = useState("");

  const loadApplications = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/candidates/applications", {
        params: {
          page,
          page_size: PAGE_SIZE,
          status: status || undefined,
          q: query.trim() || undefined,
        },
      });
      setItems(Array.isArray(data?.items) ? data.items : []);
      setTotal(Number(data?.total || 0));
      setPages(Number(data?.pages || 0));
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar las postulaciones",
        resource: "postulaciones",
        fallback: "La lista de postulaciones no se actualizó. Conservamos los filtros actuales para que puedas reintentar.",
      }));
    } finally {
      setLoading(false);
    }
  }, [page, query, status]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadApplications();
    }, 200);
    return () => window.clearTimeout(timeoutId);
  }, [loadApplications]);

  const stageCounts = useMemo(() => {
    const counts = { active: 0, hired: 0 };
    items.forEach((item) => {
      if (item.application_status === "HIRED") counts.hired += 1;
      else if (!["REJECTED", "WITHDRAWN"].includes(item.application_status)) counts.active += 1;
    });
    return counts;
  }, [items]);

  async function updateStatus(application, nextStatus) {
    setSavingId(application.id);
    setError("");
    try {
      await api.put(
        `/jobs/${application.job.job_id}/candidates/${application.candidate.candidate_id}/status`,
        { status: nextStatus },
      );
      await loadApplications();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cambiar el estado de la postulación",
        resource: "postulaciones",
        fallback: "El estado de la postulación no cambió. Recarga la lista antes de volver a intentarlo.",
      }));
    } finally {
      setSavingId("");
    }
  }

  return (
    <div className="page applications-page">
      <PageHeader
        eyebrow="Pipeline de selección"
        title="Postulaciones"
        description="Consulta cada candidato por vacante y actualiza su etapa sin perder el historial."
        className="split-header"
      />

      {error && <FeedbackMessage title="Las postulaciones no están actualizadas">{error}</FeedbackMessage>}

      <section className="metrics-grid" aria-label="Resumen de postulaciones">
        <MetricCard icon="applications" label="Total" value={total} detail="Postulaciones registradas" tone="blue" />
        <MetricCard icon="progress" label="Activas en esta página" value={stageCounts.active} detail="En proceso de selección" tone="cyan" />
        <MetricCard icon="check" label="Contratados en esta página" value={stageCounts.hired} detail="Etapa finalizada" tone="violet" />
      </section>

      <section className="panel employee-list-panel">
        <div className="employee-toolbar">
          <div>
            <span className="eyebrow">Seguimiento</span>
            <h2>Candidatos por vacante</h2>
          </div>
          <div className="employee-filters">
            <input
              type="search"
              value={query}
              placeholder="Buscar candidato, correo o vacante…"
              aria-label="Buscar postulaciones"
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
            />
            <select
              value={status}
              aria-label="Filtrar postulaciones por estado"
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            >
              <option value="">Todos los estados</option>
              {STATUS_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <LoadingState label="Cargando postulaciones…" compact />
        ) : items.length === 0 ? (
          <EmptyState
            compact
            icon="applications"
            title="No hay postulaciones para mostrar"
            description="Prueba con otros filtros o asigna candidatos a una vacante."
          />
        ) : (
          <div className="employee-table-wrap">
            <table className="employee-table">
              <thead>
                <tr>
                  <th>Candidato</th>
                  <th>Vacante</th>
                  <th>Estado</th>
                  <th>Último cambio</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {items.map((application) => (
                  <tr key={application.id}>
                    <td>
                      <strong>{application.candidate.name}</strong>
                      <small>{application.candidate.email || "Sin correo"}</small>
                    </td>
                    <td>{application.job.title}</td>
                    <td>
                      <select
                        aria-label={`Estado de ${application.candidate.name}`}
                        value={application.application_status}
                        disabled={
                          savingId === application.id
                          || application.application_status === "HIRED"
                        }
                        onChange={(event) => void updateStatus(application, event.target.value)}
                      >
                        {STATUS_OPTIONS
                          .filter(([value]) => (
                            value !== "HIRED"
                            || application.application_status === "HIRED"
                          ))
                          .map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                          ))}
                      </select>
                      {application.application_status !== "HIRED" && (
                        <small>Para contratar, usa “Contratar candidato” desde Vacantes.</small>
                      )}
                    </td>
                    <td>
                      {application.status_changed_at
                        ? new Date(application.status_changed_at).toLocaleDateString("es-CO")
                        : "—"}
                    </td>
                    <td>
                      <Link
                        className="btn btn-secondary"
                        to={`/candidates/${application.candidate.candidate_id}`}
                      >
                        Ver candidato
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {pages > 1 && (
          <div className="form-actions">
            <button className="btn btn-secondary" type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>
              Anterior
            </button>
            <span>Página {page} de {pages}</span>
            <button className="btn btn-secondary" type="button" disabled={page >= pages || loading} onClick={() => setPage((value) => Math.min(pages, value + 1))}>
              Siguiente
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

export default Applications;
