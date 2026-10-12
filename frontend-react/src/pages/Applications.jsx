// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import api from "../api/client";
import { useSession } from "../context/SessionContext";
import CandidateCreateUserModal from "../components/CandidateCreateUserModal.jsx";
import ApplicationHireModal from "../components/ApplicationHireModal.jsx";
import ApplicationAccessModal from "../components/ApplicationAccessModal.jsx";
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
  const { hasPermission } = useSession();
  const canCreateEmployees = hasPermission("employees.create");
  const canManageAccess = hasPermission("employees.credentials.manage");
  const canReviewDocuments = hasPermission("employee_documents.read_all");
  const [items, setItems] = useState([]);
  const [provisionTarget, setProvisionTarget] = useState(null);
  const [accessTarget, setAccessTarget] = useState(null);
  const [hireTarget, setHireTarget] = useState(null);
  const [success, setSuccess] = useState("");
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
    if (nextStatus === "HIRED") {
      setError("La contratación formal se realiza con el botón Crear empleado.");
      return;
    }
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
        description="Cada postulante dispone de un acceso para enviar documentos. La creación del empleado ocurre únicamente al confirmar la contratación aquí."
        className="split-header"
      />

      {error && <FeedbackMessage title="No se completó la operación">{error}</FeedbackMessage>}
      {success && <FeedbackMessage tone="success" title="Operación completada">{success}</FeedbackMessage>}

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
                        disabled={savingId === application.id}
                        onChange={(event) => void updateStatus(application, event.target.value)}
                      >
                        {STATUS_OPTIONS.map(([value, label]) => (
                          <option key={value} value={value} disabled={value === "HIRED" && application.application_status !== "HIRED"}>{label}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      {application.status_changed_at
                        ? new Date(application.status_changed_at).toLocaleDateString("es-CO")
                        : "—"}
                    </td>
                    <td>
                      <div className="ui-actions" style={{ flexWrap: "wrap", gap: 8 }}>
                        <Link className="btn btn-ghost" to={`/candidates/${application.candidate.candidate_id}?job_id=${application.job.job_id}`}>
                          Ver candidato
                        </Link>
                        {canReviewDocuments && application.access?.profile_id && (
                          <Link
                            className="btn btn-secondary"
                            to={`/documents?employee_id=${encodeURIComponent(application.access.profile_id)}`}
                          >
                            Revisar documentos
                          </Link>
                        )}
                        {canCreateEmployees && application.application_status !== "HIRED" && !application.access?.provisioned && (
                          <button className="btn btn-primary" type="button" onClick={() => setProvisionTarget(application)}>
                            Crear acceso
                          </button>
                        )}
                        {canManageAccess && application.access?.profile_id && (
                          <button className="btn btn-secondary" type="button" onClick={() => setAccessTarget(application)}>
                            {application.access.username || "Usuario"} · Credenciales
                          </button>
                        )}
                        {canCreateEmployees && application.application_status !== "HIRED" && application.access?.provisioned && (
                          <button className="btn btn-primary" type="button" onClick={() => setHireTarget(application)}>
                            Crear empleado
                          </button>
                        )}
                      </div>
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
      <CandidateCreateUserModal
        open={Boolean(provisionTarget)}
        candidateId={provisionTarget?.candidate?.candidate_id}
        candidate={provisionTarget?.candidate}
        jobId={provisionTarget?.job?.job_id || ""}
        jobTitle={provisionTarget?.job?.title || ""}
        onClose={() => setProvisionTarget(null)}
        onCreated={async () => {
          setSuccess("Acceso del postulante creado. Ya puede iniciar sesión y cargar sus documentos.");
          await loadApplications();
        }}
      />
      {accessTarget && (
        <ApplicationAccessModal
          key={accessTarget.id}
          application={accessTarget}
          onClose={() => setAccessTarget(null)}
          onUpdated={loadApplications}
        />
      )}
      {hireTarget && (
        <ApplicationHireModal
          key={hireTarget.id}
          application={hireTarget}
          onClose={() => setHireTarget(null)}
          onHired={async () => {
            setSuccess("Postulación cerrada como Contratado. El usuario ahora es empleado y recibirá onboarding.");
            await loadApplications();
          }}
        />
      )}
    </div>
  );
}

export default Applications;
