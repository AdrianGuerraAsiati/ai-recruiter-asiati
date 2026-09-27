// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import api from "../api/client";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  ["APPLIED", "Aplicó"],
  ["SCREENING", "En filtro"],
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
      setError(err.response?.data?.detail || "No fue posible cargar las postulaciones.");
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
      setError(err.response?.data?.detail || "No fue posible actualizar la postulación.");
    } finally {
      setSavingId("");
    }
  }

  return (
    <div className="page applications-page">
      <header className="page-header split-header">
        <div>
          <span className="eyebrow">Pipeline de selección</span>
          <h1>Postulaciones</h1>
          <p>Consulta cada candidato por vacante y actualiza su etapa sin perder el historial.</p>
        </div>
      </header>

      {error && <div className="alert" role="alert">{error}</div>}

      <section className="metrics-grid" aria-label="Resumen de postulaciones">
        <article className="metric-card metric-blue">
          <span className="metric-label">Total</span>
          <strong className="metric-value">{total}</strong>
          <small>Postulaciones registradas</small>
        </article>
        <article className="metric-card metric-cyan">
          <span className="metric-label">Activas en esta página</span>
          <strong className="metric-value">{stageCounts.active}</strong>
          <small>En proceso de selección</small>
        </article>
        <article className="metric-card metric-violet">
          <span className="metric-label">Contratados en esta página</span>
          <strong className="metric-value">{stageCounts.hired}</strong>
          <small>Etapa finalizada</small>
        </article>
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
          <div className="page-loading"><span /> Cargando postulaciones…</div>
        ) : items.length === 0 ? (
          <div className="empty-state compact">
            <strong>No hay postulaciones para mostrar</strong>
            <p>Prueba con otros filtros o asigna candidatos a una vacante.</p>
          </div>
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
                        disabled={savingId === application.id}
                        onChange={(event) => void updateStatus(application, event.target.value)}
                      >
                        {STATUS_OPTIONS.map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
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
