import { useEffect, useState } from "react";
import api from "../../api/client";
import { getApiErrorMessage } from "../../utils/errors";

const STAGES = [
  { status: "APPLIED", label: "Nuevo", odoo: "New" },
  { status: "INITIAL_QUALIFICATION", label: "Calificación inicial", odoo: "Initial Qualification" },
  { status: "FIRST_INTERVIEW", label: "Primera entrevista", odoo: "First Interview" },
  { status: "SECOND_INTERVIEW", label: "Segunda entrevista", odoo: "Second Interview" },
  { status: "CONTRACT_PROPOSAL", label: "Propuesta contractual", odoo: "Contract Proposal" },
  { status: "CONTRACT_SIGNED", label: "Contrato firmado", odoo: "Contract Signed" },
];

const LEGACY_STAGE = {
  SCREENING: "INITIAL_QUALIFICATION",
  INTERVIEW: "FIRST_INTERVIEW",
  SELECTED: "CONTRACT_PROPOSAL",
  OFFER: "CONTRACT_PROPOSAL",
  HIRED: "CONTRACT_SIGNED",
};

export default function RecruitmentFlow({ jobId, candidateId, onContractSigned }) {
  const [status, setStatus] = useState("APPLIED");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!jobId || !candidateId) return;
    api.get(`/jobs/${jobId}/candidates?page=1&page_size=100`)
      .then(({ data }) => {
        const row = (Array.isArray(data) ? data : data?.items || []).find(
          (item) => item.candidate_id === candidateId || item.id === candidateId
        );
        if (row?.application_status) setStatus(LEGACY_STAGE[row.application_status] || row.application_status);
      })
      .catch(() => {});
  }, [jobId, candidateId]);

  if (!jobId) return null;
  const currentIndex = Math.max(0, STAGES.findIndex((stage) => stage.status === status));

  async function moveTo(stage) {
    if (saving || stage.status === status) return;
    setSaving(true);
    setError("");
    try {
      await api.put(`/jobs/${jobId}/candidates/${candidateId}/status`, { status: stage.status });
      setStatus(stage.status);
      if (stage.status === "CONTRACT_SIGNED" && onContractSigned) onContractSigned();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "actualizar la etapa de selección",
        resource: "candidato",
        fallback: "No fue posible cambiar la etapa. Intenta nuevamente.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function reject() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await api.put(`/jobs/${jobId}/candidates/${candidateId}/status`, { status: "REJECTED" });
      setStatus("REJECTED");
    } catch (err) {
      setError(getApiErrorMessage(err, { fallback: "No fue posible descartar al candidato." }));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel recruitment-flow">
      <div className="recruitment-flow__header">
        <div>
          <span className="eyebrow">Proceso de selección</span>
          <h2>Pipeline sincronizado con Odoo</h2>
          <p className="muted">Las etapas corresponden directamente a hr.applicant de Odoo.</p>
        </div>
        {status !== "REJECTED" && (
          <button type="button" className="btn btn-secondary btn-sm" disabled={saving} onClick={reject}>
            Descartar
          </button>
        )}
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {status === "REJECTED" ? (
        <div className="candidate-ban-alert candidate-ban-alert--detail"><strong>Candidato descartado</strong><span>El historial se conserva.</span></div>
      ) : (
        <div className="recruitment-flow__stages">
          {STAGES.map((stage, index) => (
            <button
              key={stage.status}
              type="button"
              className={`recruitment-stage ${index < currentIndex ? "is-done" : ""} ${index === currentIndex ? "is-current" : ""}`}
              disabled={saving}
              onClick={() => moveTo(stage)}
              title={`Odoo: ${stage.odoo}`}
            >
              <span className="recruitment-stage__index">{index < currentIndex ? "✓" : index + 1}</span>
              <span><strong>{stage.label}</strong><small>{stage.odoo}</small></span>
            </button>
          ))}
        </div>
      )}
      <p className="muted recruitment-flow__hint">
        Al llegar a “Contrato firmado”, completa la contratación para crear el empleado, enviarlo a Odoo y asignar su onboarding.
      </p>
    </section>
  );
}
