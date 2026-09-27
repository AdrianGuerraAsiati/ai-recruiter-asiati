// eslint-disable-next-line no-unused-vars
import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import { useSession } from "../context/SessionContext";
import { useNotice } from "../context/noticeStore";
import PageHeader from "../components/ui/PageHeader";
import Icon from "../components/ui/Icon";
import { EmptyState, FeedbackMessage, ProgressBar } from "../components/ui/StatePanel";
import CandidateImportModal from "../features/candidate-import/CandidateImportModal.jsx";

const PAGE_SIZE = 20;

function Candidates() {
  const { hasPermission } = useSession();
  const { notify } = useNotice();
  const canRestrictCandidates = hasPermission("candidates.restrict");
  const [candidates, setCandidates] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState({});
  const [loading, setLoading] = useState(false);
  const [selectedEvaluation, setSelectedEvaluation] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [searchParams] = useSearchParams();
  const [restrictionTarget, setRestrictionTarget] = useState(null);
  const [restrictionMode, setRestrictionMode] = useState("ban");
  const [restrictionReason, setRestrictionReason] = useState("");
  const [restrictionSaving, setRestrictionSaving] = useState(false);

  const requestedJobId = searchParams.get("job_id") || "";

  const loadData = useCallback(async (targetPage = page) => {
    setLoadError("");
    try {
      const [candidatesResponse, jobsResponse] = await Promise.all([
        api.get(`/candidates?page=${targetPage}&page_size=${PAGE_SIZE}`),
        api.get("/jobs"),
      ]);

      const candidatesData = candidatesResponse.data || {};
      const jobsData = jobsResponse.data;
      const items = Array.isArray(candidatesData.items)
        ? candidatesData.items
        : [];
      const responseTotal = Number(candidatesData.total || 0);
      const responsePages = Number(candidatesData.pages || 0);

      setCandidates(items);
      setTotal(responseTotal);
      setPages(responsePages);
      setJobs(Array.isArray(jobsData) ? jobsData : jobsData.jobs || []);
    } catch (error) {
      setLoadError(getApiErrorMessage(error, {
        action: "cargar candidatos y vacantes",
        resource: "reclutamiento",
        fallback: "No se pudo completar el directorio porque candidatos o vacantes no respondieron. Recarga la página antes de asignar perfiles.",
      }));
    }
  }, [page]);

  useEffect(() => {
    // The initial request synchronizes this view with the API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData(page);
  }, [loadData, page]);

  useEffect(() => {
    if (!requestedJobId) return;
    // A job deep link intentionally opens the durable import surface.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setShowCreateModal(true);
  }, [requestedJobId]);

  function openCreateCandidateModal() {
    setShowCreateModal(true);
  }

  function closeCreateCandidateModal() {
    setShowCreateModal(false);
    if (page !== 1) {
      setPage(1);
      return;
    }
    void loadData(1);
  }

  async function evaluate(candidateId) {
    const jobId = selectedJob[candidateId];

    if (!jobId) {
      notify({
        tone: "warning",
        title: "Selecciona una vacante",
        message: "La evaluación necesita una vacante para comparar el perfil contra sus requisitos.",
      });
      return;
    }

    try {
      setLoading(true);
      const response = await api.post(
        `/candidates/${candidateId}/evaluate-job`,
        { job_id: jobId },
      );

      setSelectedEvaluation({
        candidateId,
        evaluation: response.data,
      });
    } catch (error) {
      notify({
        tone: "error",
        title: "La evaluación no se completó",
        message: getApiErrorMessage(error, {
          action: "evaluar el candidato",
          resource: "evaluación",
          fallback: "La evaluación no se guardó. El candidato conserva su resultado anterior; vuelve a evaluarlo cuando el servicio esté disponible.",
        }),
      });
    } finally {
      setLoading(false);
    }
  }

  async function assignCandidate(candidateId) {
    const jobId = selectedJob[candidateId];
    if (!jobId) {
      notify({
        tone: "warning",
        title: "Selecciona una vacante",
        message: "La asignación necesita una vacante para crear la postulación del candidato.",
      });
      return;
    }

    try {
      setLoading(true);
      await api.post(`/jobs/${jobId}/candidates`, {
        candidate_ids: [candidateId],
      });
      notify({
        tone: "success",
        title: "Candidato asignado",
        message: "La postulación quedó vinculada a la vacante seleccionada.",
      });
      await loadData(page);
    } catch (error) {
      notify({
        tone: "error",
        title: "No se creó la postulación",
        message: getApiErrorMessage(error, {
          action: "asignar el candidato a la vacante",
          resource: "postulación",
          fallback: "El candidato no quedó asignado a la vacante. Actualiza el listado y confirma que la vacante siga activa.",
        }),
      });
    } finally {
      setLoading(false);
    }
  }

  async function viewCV(candidate) {
    const viewer = window.open("about:blank", "_blank");
    if (!viewer) {
      notify({
        tone: "warning",
        title: "El navegador bloqueó el CV",
        message: "Permite ventanas emergentes para este sitio y vuelve a seleccionar «Ver CV».",
      });
      return;
    }
    viewer.opener = null;

    try {
      const response = await api.get(
        `/candidates/${candidate.candidate_id}/download`,
      );
      const viewUrl = response.data.download_url;
      if (!viewUrl) throw new Error("No se recibió URL del CV");
      viewer.location.replace(viewUrl);
    } catch (error) {
      viewer.close();
      notify({
        tone: "error",
        title: "El CV no se abrió",
        message: getApiErrorMessage(error, {
          action: "abrir el CV",
          resource: "archivo del candidato",
          fallback: "El CV no devolvió un enlace de visualización válido. Vuelve a abrirlo desde el perfil del candidato.",
        }),
      });
    }
  }

  function openRestriction(candidate, mode) {
    setRestrictionTarget(candidate);
    setRestrictionMode(mode);
    setRestrictionReason("");
  }

  function closeRestriction() {
    if (restrictionSaving) return;
    setRestrictionTarget(null);
    setRestrictionReason("");
  }

  async function submitRestriction(event) {
    event.preventDefault();
    if (!restrictionTarget || restrictionReason.trim().length < 3) return;

    setRestrictionSaving(true);
    try {
      await api.post(
        `/candidates/${restrictionTarget.candidate_id}/${restrictionMode === "ban" ? "ban" : "unban"}`,
        { reason: restrictionReason.trim() },
      );
      setRestrictionTarget(null);
      setRestrictionReason("");
      await loadData(page);
    } catch (error) {
      notify({
        tone: "error",
        title: "La restricción no cambió",
        message: getApiErrorMessage(error, {
          action: "actualizar el veto del candidato",
          resource: "restricciones",
          fallback: "La restricción del candidato no cambió. Recarga su perfil antes de repetir la acción.",
        }),
      });
    } finally {
      setRestrictionSaving(false);
    }
  }

  function getDisplayFilename(candidate) {
    if (candidate.filename) return candidate.filename;
    if (candidate.name) {
      const cleanName = candidate.name
        .trim()
        .replace(/\s+/g, "_")
        .replace(/[^\wáéíóúÁÉÍÓÚñÑ-]/g, "");
      return `${cleanName}_CV.pdf`;
    }
    return "CV.pdf";
  }

  function closeEvaluationModal() {
    setSelectedEvaluation(null);
  }

  function getRecommendationLabel(recommendation) {
    if (recommendation === "STRONG_MATCH") return "Excelente coincidencia";
    if (recommendation === "GOOD_MATCH") return "Buena coincidencia";
    if (recommendation === "PARTIAL_MATCH") return "Coincidencia parcial";
    if (recommendation === "LOW_MATCH") return "Baja coincidencia";
    if (recommendation === "EVALUATION_FAILED") return "Evaluación fallida";
    if (recommendation === "PENDING") return "Pendiente";
    return "Sin clasificación";
  }

  function badgeClass(recommendation) {
    if (recommendation === "STRONG_MATCH") return "candidate-evaluation-badge--strong";
    if (recommendation === "GOOD_MATCH") return "candidate-evaluation-badge--good";
    if (recommendation === "PARTIAL_MATCH") return "candidate-evaluation-badge--partial";
    if (recommendation === "EVALUATION_FAILED") return "candidate-evaluation-badge--failed";
    return "candidate-evaluation-badge--low";
  }

  const selectedEvaluationFailed =
    selectedEvaluation?.evaluation?.status === "FAILED" ||
    selectedEvaluation?.evaluation?.recommendation === "EVALUATION_FAILED";

  const initialImportJobId =
    requestedJobId || (jobs.length === 1 ? jobs[0].job_id : "");

  const visibleStart = total > 0 ? (page - 1) * PAGE_SIZE + 1 : 0;
  const visibleEnd = total > 0 ? Math.min(page * PAGE_SIZE, total) : 0;

  return (
    <div className="page candidate-page">
      <PageHeader
        eyebrow="Base de talento"
        title="Candidatos"
        description="Centraliza CVs, asigna perfiles a vacantes y ejecuta evaluaciones asistidas por IA."
        actions={(
          <button
            type="button"
            className="btn btn-primary candidate-add-button"
            onClick={openCreateCandidateModal}
          >
            <Icon name="plus" size={17} />
            Agregar candidato
          </button>
        )}
      />

      {loadError && (
        <FeedbackMessage title="La base de candidatos no está actualizada">
          <p>{loadError}</p>
          <button type="button" className="btn btn-secondary" onClick={() => void loadData(page)}>
            Reintentar carga
          </button>
        </FeedbackMessage>
      )}

      <div className="section-heading candidate-section-heading">
        <div>
          <h2>Candidatos registrados</h2>
          <p>
            {total}{" "}
            {total === 1
              ? "perfil disponible"
              : "perfiles disponibles"}
          </p>
        </div>
      </div>

      {candidates.length === 0 ? (
        <EmptyState
          icon="users"
          title="Aún no hay candidatos registrados"
          description="Agrega CVs manualmente o mediante una ingesta para empezar a construir la base de talento. Usa «Agregar candidato» para iniciar la importación."
        />
      ) : (
        candidates.map((candidate) => (
          <article className="card candidate-card candidate-card--directory" key={candidate.candidate_id}>
            <div className="candidate-header candidate-directory-header">
              <div>
                <h2>{candidate.name}</h2>
                <p className="muted candidate-directory-subtitle">Candidato registrado</p>
                {candidate.is_banned && (
                  <div className="candidate-ban-alert" role="alert">
                    <strong>⚠ Candidato vetado</strong>
                    <span>{candidate.banned_reason || "Este perfil fue vetado por un administrador."}</span>
                  </div>
                )}
              </div>

              <div className="candidate-actions ui-actions">
                <button
                  className="btn btn-secondary"
                  type="button"
                  onClick={() => viewCV(candidate)}
                >
                  <Icon name="applications" size={16} />
                  Ver CV
                </button>
                {canRestrictCandidates && (
                  <button
                    className={`btn ${candidate.is_banned ? "btn-secondary" : "btn-danger"}`}
                    onClick={() => openRestriction(candidate, candidate.is_banned ? "unban" : "ban")}
                  >
                    {candidate.is_banned ? "Quitar veto" : "Vetar"}
                  </button>
                )}
              </div>
            </div>

            <div className="candidate-file candidate-directory-file">
              <span className="candidate-file-label">
                Archivo
              </span>
              <strong>{getDisplayFilename(candidate)}</strong>
            </div>

            <div className="controls candidate-directory-controls">
              <select
                className="select"
                value={selectedJob[candidate.candidate_id] || ""}
                onChange={(event) =>
                  setSelectedJob((current) => ({
                    ...current,
                    [candidate.candidate_id]: event.target.value,
                  }))
                }
              >
                <option value="">Seleccione vacante</option>
                {jobs.map((job) => (
                  <option key={job.job_id} value={job.job_id}>
                    {job.title}
                  </option>
                ))}
              </select>

              <button
                className="btn btn-primary"
                onClick={() => assignCandidate(candidate.candidate_id)}
                disabled={loading || candidate.is_banned}
                title={candidate.is_banned ? "Un candidato vetado no puede recibir nuevas asignaciones." : undefined}
              >
                {loading ? "Asignando..." : "Asignar a vacante"}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => evaluate(candidate.candidate_id)}
                disabled={loading || candidate.is_banned}
                title={candidate.is_banned ? "Quita el veto antes de evaluar nuevamente." : undefined}
              >
                Evaluar candidato
              </button>
            </div>
          </article>
        ))
      )}

      {total > 0 && (
        <div className="candidate-pagination">
          <span className="muted">Mostrando {visibleStart}–{visibleEnd}</span>
          <div className="candidate-pagination-controls">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1}
            >
              Anterior
            </button>
            <strong>Página {page} de {Math.max(pages, 1)}</strong>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setPage((current) => Math.min(Math.max(pages, 1), current + 1))}
              disabled={page >= Math.max(pages, 1)}
            >
              Siguiente
            </button>
          </div>
        </div>
      )}

      {showCreateModal && (
        <CandidateImportModal
          open
          jobs={jobs}
          initialJobId={initialImportJobId}
          onClose={closeCreateCandidateModal}
        />
      )}

      {restrictionTarget && (
        <div className="modal-overlay" onMouseDown={closeRestriction}>
          <section
            className="modal candidate-restriction-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="candidate-restriction-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">Control administrativo</span>
                <h2 id="candidate-restriction-title">
                  {restrictionMode === "ban" ? "Vetar candidato" : "Quitar veto"}
                </h2>
                <p className="muted">
                  {restrictionTarget.name}
                </p>
              </div>
              <button
                type="button"
                className="btn btn-close"
                onClick={closeRestriction}
                disabled={restrictionSaving}
              >
                ✕
              </button>
            </div>

            {restrictionMode === "ban" && (
              <div className="candidate-ban-warning">
                <strong>Este candidato no será eliminado.</strong>
                <span>
                  El veto conservará su CV, evaluaciones y postulaciones históricas,
                  pero lo excluirá de nuevas asignaciones y recomendaciones.
                </span>
              </div>
            )}

            <form onSubmit={submitRestriction}>
              <div className="form-group">
                <label htmlFor="candidate-restriction-reason">
                  {restrictionMode === "ban" ? "Motivo del veto" : "Motivo para quitar el veto"}
                </label>
                <textarea
                  id="candidate-restriction-reason"
                  rows="4"
                  value={restrictionReason}
                  onChange={(event) => setRestrictionReason(event.target.value)}
                  placeholder="Describe el motivo para dejar trazabilidad."
                  required
                />
              </div>
              <div className="form-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={closeRestriction}
                  disabled={restrictionSaving}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className={`btn ${restrictionMode === "ban" ? "btn-danger" : "btn-primary"}`}
                  disabled={restrictionSaving || restrictionReason.trim().length < 3}
                >
                  {restrictionSaving
                    ? "Guardando…"
                    : restrictionMode === "ban"
                      ? "Confirmar veto"
                      : "Quitar veto"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {selectedEvaluation && (
        <div className="modal-overlay" onClick={closeEvaluationModal}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h2>Resultado de evaluación IA</h2>
                <p className="muted candidate-evaluation-subtitle">
                  Evaluación del candidato
                </p>
              </div>
              <button className="btn btn-close" onClick={closeEvaluationModal}>
                ✕
              </button>
            </div>

            {selectedEvaluationFailed ? (
              <div className="candidate-evaluation-summary candidate-evaluation-summary--failed">
                <div className="badge candidate-evaluation-badge candidate-evaluation-badge--failed">
                  Evaluación fallida
                </div>
              </div>
            ) : (
              <div className="candidate-evaluation-summary">
                <div className="score">
                  {selectedEvaluation.evaluation.match_score}%
                </div>
                <ProgressBar
                  value={selectedEvaluation.evaluation.match_score}
                  label="Afinidad con la vacante"
                />
                <div className={`badge candidate-evaluation-badge ${badgeClass(selectedEvaluation.evaluation.recommendation)}`}>
                  {getRecommendationLabel(
                    selectedEvaluation.evaluation.recommendation,
                  )}
                </div>
              </div>
            )}

            <div className="result">
              <h3>Resumen</h3>
              <p className="candidate-evaluation-copy">
                {selectedEvaluation.evaluation.summary}
              </p>
            </div>

            <div className="columns">
              <div>
                <h3 className="section-title candidate-section-title candidate-section-title--positive"><Icon name="check" size={16} /> Fortalezas</h3>
                {selectedEvaluation.evaluation.strengths?.length ? (
                  <ul className="list">
                    {selectedEvaluation.evaluation.strengths.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Sin datos</p>
                )}
              </div>

              <div>
                <h3 className="section-title candidate-section-title candidate-section-title--negative"><Icon name="warning" size={16} /> Brechas</h3>
                {selectedEvaluation.evaluation.gaps?.length ? (
                  <ul className="list">
                    {selectedEvaluation.evaluation.gaps.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Sin datos</p>
                )}
              </div>
            </div>

            <div className="form-actions">
              <button className="btn btn-close" onClick={closeEvaluationModal}>
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Candidates;
