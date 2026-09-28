function JobDeleteModal({
  job,
  deleting,
  error,
  onClose,
  onConfirm,
}) {
  if (!job) return null;

  const candidateCount = job.candidate_count || 0;
  const plural = candidateCount === 1 ? "" : "s";

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal job-delete-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-job-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow job-danger-eyebrow">Eliminar vacante</span>
            <h2 id="delete-job-title">¿qué deseas eliminar?</h2>
          </div>
          <button
            className="btn btn-close"
            onClick={onClose}
            disabled={deleting}
            aria-label="Cerrar modal de eliminación"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>

        <p className="job-delete-job-title">{job.title}</p>
        <p className="muted job-delete-copy">
          Esta vacante tiene {candidateCount} candidato{plural} asignado{plural}.
        </p>

        {error && (
          <div className="job-delete-error" role="alert">
            {error}
          </div>
        )}

        <div className="job-delete-options">
          <button
            type="button"
            className="job-delete-option job-delete-option-danger-outline"
            disabled={deleting}
            onClick={() => onConfirm(false)}
          >
            <strong>Borrar solo la vacante</strong>
            <span>Conserva los candidatos en tu cuenta.</span>
          </button>

          <button
            type="button"
            className="job-delete-option job-delete-option-danger-solid"
            disabled={deleting || !candidateCount}
            onClick={() => onConfirm(true)}
          >
            <strong>Borrar vacante y candidatos</strong>
            <span>
              Elimina también los {candidateCount} candidatos.
              {candidateCount > 0 && " Puede afectar otras vacantes donde estén."}
            </span>
          </button>

          <button
            type="button"
            className="job-delete-option job-delete-option-cancel"
            disabled={deleting}
            onClick={onClose}
          >
            Cancelar
          </button>
        </div>

        {deleting && <p className="job-delete-loading">Eliminando…</p>}
      </div>
    </div>
  );
}

export default JobDeleteModal;
