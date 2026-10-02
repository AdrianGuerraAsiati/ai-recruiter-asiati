import { useState } from "react";

function credentialText(credentials, accessUrl) {
  return [
    "Talent Intelligence",
    `Usuario: ${credentials.username}`,
    `Contraseña temporal: ${credentials.temporary_password}`,
    `Acceso: ${accessUrl}`,
  ].join("\n");
}

export default function EmployeeCredentialsModal({
  open,
  employeeName,
  credentials,
  onClose,
}) {
  const [copied, setCopied] = useState("");
  if (!open || !credentials) return null;

  const accessUrl = "https://talent.asiaticorp.com/";

  async function copy(value, kind) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
      window.setTimeout(() => setCopied(""), 1600);
    } catch {
      setCopied("");
    }
  }

  return (
    <div className="modal-overlay" role="presentation">
      <section
        className="modal employee-credentials-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="employee-credentials-title"
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">Acceso creado</span>
            <h2 id="employee-credentials-title">Credenciales temporales</h2>
            <p>{employeeName || "Empleado"}</p>
          </div>
        </div>

        <div className="employee-credentials-warning" role="note">
          <strong>Guarda estas credenciales ahora.</strong>
          <span>
            La contraseña temporal se muestra una sola vez. El empleado deberá
            cambiarla en su primer acceso.
          </span>
        </div>

        <div className="employee-credentials-grid">
          <div className="employee-credential-field">
            <span>Usuario</span>
            <strong>{credentials.username}</strong>
            <button
              className="btn btn-ghost btn-sm"
              type="button"
              onClick={() => copy(credentials.username, "username")}
            >
              {copied === "username" ? "Copiado" : "Copiar"}
            </button>
          </div>
          <div className="employee-credential-field">
            <span>Contraseña temporal</span>
            <strong>{credentials.temporary_password}</strong>
            <button
              className="btn btn-ghost btn-sm"
              type="button"
              onClick={() => copy(credentials.temporary_password, "password")}
            >
              {copied === "password" ? "Copiada" : "Copiar"}
            </button>
          </div>
        </div>

        <div className="employee-credentials-access">
          <span>Acceso</span>
          <a href={accessUrl} target="_blank" rel="noreferrer">{accessUrl}</a>
        </div>

        <div className="form-actions">
          <button
            className="btn btn-secondary"
            type="button"
            onClick={() => copy(credentialText(credentials, accessUrl), "all")}
          >
            {copied === "all" ? "Credenciales copiadas" : "Copiar credenciales"}
          </button>
          <button className="btn btn-primary" type="button" onClick={onClose}>
            Finalizar
          </button>
        </div>
      </section>
    </div>
  );
}
