import { useRef, useState } from "react";

function credentialText(credentials, accessUrl) {
  return [
    "ADN360",
    `Usuario: ${credentials.username || ""}`,
    `Contraseña temporal: ${credentials.temporary_password || ""}`,
    `Acceso: ${accessUrl}`,
  ].join("\n");
}

// navigator.clipboard falla en contextos no seguros, iframes o por permisos del
// navegador. En ese caso se usa el método clásico con un textarea temporal.
function legacyCopy(value) {
  if (typeof document === "undefined" || typeof document.execCommand !== "function") return false;
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  let ok;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(textarea);
  return ok;
}

async function copyText(value) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Continúa con el método clásico.
  }
  return legacyCopy(value);
}

export default function EmployeeCredentialsModal({
  open,
  employeeName,
  credentials,
  onClose,
}) {
  const [copied, setCopied] = useState("");
  const [copyFailed, setCopyFailed] = useState(false);
  const usernameRef = useRef(null);
  const passwordRef = useRef(null);
  if (!open || !credentials) return null;

  const accessUrl = `${window.location.origin}/`;
  const password = credentials.temporary_password || "";

  async function copy(value, kind, inputRef) {
    const ok = await copyText(value);
    if (ok) {
      setCopyFailed(false);
      setCopied(kind);
      window.setTimeout(() => setCopied(""), 1600);
      return;
    }
    setCopied("");
    setCopyFailed(true);
    // Deja el texto seleccionado para copiarlo con Ctrl+C.
    inputRef?.current?.focus();
    inputRef?.current?.select();
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
            La contraseña temporal se muestra una sola vez. La persona deberá
            cambiarla en su primer acceso.
          </span>
        </div>

        {!password && (
          <div className="employee-credentials-warning" role="alert">
            <strong>No se recibió la contraseña temporal.</strong>
            <span>Cierra esta ventana y vuelve a generar una nueva contraseña.</span>
          </div>
        )}

        <div className="employee-credentials-grid">
          <div className="employee-credential-field">
            <label htmlFor="employee-credential-username">Usuario</label>
            <input
              id="employee-credential-username"
              ref={usernameRef}
              type="text"
              readOnly
              value={credentials.username || ""}
              onFocus={(event) => event.currentTarget.select()}
            />
            <button
              className="btn btn-ghost btn-sm"
              type="button"
              onClick={() => copy(credentials.username || "", "username", usernameRef)}
            >
              {copied === "username" ? "Copiado" : "Copiar"}
            </button>
          </div>
          <div className="employee-credential-field">
            <label htmlFor="employee-credential-password">Contraseña temporal</label>
            <input
              id="employee-credential-password"
              ref={passwordRef}
              type="text"
              readOnly
              value={password}
              autoComplete="off"
              spellCheck={false}
              onFocus={(event) => event.currentTarget.select()}
            />
            <button
              className="btn btn-ghost btn-sm"
              type="button"
              disabled={!password}
              onClick={() => copy(password, "password", passwordRef)}
            >
              {copied === "password" ? "Copiada" : "Copiar"}
            </button>
          </div>
        </div>

        {copyFailed && (
          <p className="employee-credentials-copy-error" role="alert">
            El navegador bloqueó el portapapeles. El texto quedó seleccionado: cópialo con Ctrl+C.
          </p>
        )}

        <div className="employee-credentials-access">
          <span>Acceso</span>
          <a href={accessUrl} target="_blank" rel="noreferrer">{accessUrl}</a>
        </div>

        <div className="form-actions">
          <button
            className="btn btn-secondary"
            type="button"
            onClick={() => copy(credentialText(credentials, accessUrl), "all", passwordRef)}
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
