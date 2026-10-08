import { useEffect, useState } from "react";
import api from "../../api/client";
import { getApiErrorMessage } from "../../utils/errors";
import "../../pages/Jobs.css";

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

export default function RecruitmentFlow({ jobId, candidateId, onContractSigned, activated = 0, onProcessChange }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!jobId || !candidateId) return;
    let cancelled = false;
    api.get(`/jobs/${jobId}/candidates/${candidateId}/process`)
      .then(({ data }) => {
        if (cancelled) return;
        const next = data.has_process
          ? (LEGACY_STAGE[data.status] || data.status || "APPLIED")
          : null;
        setStatus(next);
        onProcessChange?.(Boolean(data.has_process));
      })
      .catch((err) => {
        if (!cancelled) {
          setError(getApiErrorMessage(err, { fallback: "No fue posible consultar el proceso de selección." }));
          setStatus(null);
          onProcessChange?.(false);
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [jobId, candidateId, activated]);

  if (!jobId) return null;
  const currentIndex = Math.max(0, STAGES.findIndex((stage) => stage.status === status));

  async function moveTo(stage) {
    if (saving || !status || stage.status === status) return;
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
    if (saving || !status) return;
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
        {status && status !== "REJECTED" && (
          <button type="button" className="btn btn-secondary btn-sm" disabled={saving} onClick={reject}>
            Descartar
          </button>
        )}
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {loading ? <p className="muted">Consultando el proceso de selección…</p> : !status ? (
        <p className="muted" role="status">Este candidato aún no ha sido agregado al proceso de esta vacante. Puedes evaluar su perfil libremente e iniciar la contratación desde el encabezado.</p>
      ) : status === "REJECTED" ? (
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
      {status && <p className="muted recruitment-flow__hint">
        Al llegar a “Contrato firmado”, completa la contratación para crear el empleado, enviarlo a Odoo y asignar su onboarding.
      </p>}
    </section>
  );
}
