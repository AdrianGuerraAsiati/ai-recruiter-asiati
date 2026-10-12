import { useEffect, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import EmployeeCredentialsModal from "./EmployeeCredentialsModal";

export default function ApplicationAccessModal({ application, onClose, onUpdated }) {
  const [username, setUsername] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [credentials, setCredentials] = useState(null);

  useEffect(() => {
    setUsername(application?.access?.username || "");
    setCredentials(null);
    setError("");
  }, [application]);

  if (!application?.access?.profile_id) return null;
  const profileId = application.access.profile_id;

  async function saveUsername(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.put(`/employees/${profileId}/credentials/username`, { username });
      await onUpdated?.();
      onClose?.();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "actualizar el usuario del postulante",
        resource: "credenciales",
        fallback: "No se pudo guardar el usuario.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function resetPassword() {
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post(`/employees/${profileId}/credentials/reset-password`);
      setCredentials(data?.credentials || null);
      await onUpdated?.();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "generar contraseña provisional",
        resource: "credenciales",
        fallback: "No se pudo restablecer la contraseña.",
      }));
    } finally {
      setSaving(false);
    }
  }

  if (credentials) {
    return <EmployeeCredentialsModal open credentials={credentials} employeeName={application.candidate.name} onClose={onClose} />;
  }

  return (
    <div className="modal-overlay" role="presentation" onMouseDown={() => !saving && onClose?.()}>
      <section className="modal employee-modal" role="dialog" aria-modal="true" aria-labelledby="applicant-access-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="eyebrow">Acceso para cargar documentos</span>
            <h2 id="applicant-access-title">Credenciales del postulante</h2>
            <p>{application.candidate.name} · {application.job.title}</p>
          </div>
          <button className="btn-close" type="button" aria-label="Cerrar" disabled={saving} onClick={onClose}>×</button>
        </div>
        {error && <div className="alert" role="alert">{error}</div>}
        <form className="employee-form" onSubmit={saveUsername}>
          <div className="form-group">
            <label htmlFor="applicant-access-username">Usuario de Talent</label>
            <input id="applicant-access-username" value={username} onChange={(event) => setUsername(event.target.value.toLowerCase())} required minLength={3} maxLength={40} autoComplete="off" />
          </div>
          <div className="form-actions">
            <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? "Guardando…" : "Guardar usuario"}</button>
          </div>
        </form>
        <div className="employee-fixed-onboarding employee-create-onboarding">
          <strong>Contraseña</strong>
          <p>Por seguridad no es posible ver la contraseña actual. Puedes generar una nueva contraseña provisional de un solo uso para el primer ingreso.</p>
          <button className="btn btn-secondary" type="button" onClick={() => void resetPassword()} disabled={saving || !application.access.provisioned}>
            Generar nueva contraseña provisional
          </button>
        </div>
      </section>
    </div>
  );
}
