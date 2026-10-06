import { useCallback, useEffect, useState } from "react";

import api from "../api/client";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../utils/errors";
import { FeedbackMessage, LoadingState } from "./ui/StatePanel";

const EMPTY_PROFILE = {
  first_name: "",
  last_name: "",
  personal_email: "",
  phone: "",
  address: "",
  city: "",
  emergency_contact_name: "",
  emergency_contact_phone: "",
};

function fileSize(value) {
  const bytes = Number(value || 0);
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function EmployeeSelfServiceCard() {
  const { refreshSession } = useSession();
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [documents, setDocuments] = useState([]);
  const [files, setFiles] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploadingId, setUploadingId] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [profileResponse, documentResponse] = await Promise.all([
        api.get("/employee-self/profile"),
        api.get("/employee-self/documents"),
      ]);
      setProfile({
        ...EMPTY_PROFILE,
        ...(profileResponse.data || {}),
      });
      setDocuments(documentResponse.data?.items || []);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar tus datos y documentos",
        resource: "perfil",
        fallback: "No fue posible cargar tu información de autoservicio.",
      }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [load]);

  async function saveProfile(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const { data } = await api.put("/employee-self/profile", {
        first_name: profile.first_name || null,
        last_name: profile.last_name || null,
        personal_email: profile.personal_email || null,
        phone: profile.phone || null,
        address: profile.address || null,
        city: profile.city || null,
        emergency_contact_name: profile.emergency_contact_name || null,
        emergency_contact_phone: profile.emergency_contact_phone || null,
      });
      setProfile({ ...EMPTY_PROFILE, ...(data || {}) });
      await refreshSession();
      setSuccess("Tus datos personales se actualizaron correctamente.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "guardar tus datos",
        resource: "perfil",
        fallback: "No fue posible guardar tus datos.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function uploadDocument(request) {
    const selected = files[request.id];
    if (!selected) {
      setError(`Selecciona un archivo para ${request.label}.`);
      return;
    }
    setUploadingId(request.id);
    setError("");
    setSuccess("");
    try {
      const body = new FormData();
      body.append("file", selected);
      await api.post(
        `/employee-self/documents/${request.id}/upload`,
        body,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      setFiles((current) => ({ ...current, [request.id]: null }));
      setSuccess(`${request.label}: documento cargado correctamente.`);
      await load();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "subir el documento",
        resource: request.label,
        fallback: "No fue posible cargar el archivo. Usa PDF, JPG, PNG o DOCX de máximo 10 MB.",
      }));
    } finally {
      setUploadingId("");
    }
  }

  async function downloadDocument(request) {
    setError("");
    try {
      const response = await api.get(
        `/employee-self/documents/${request.id}/download`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = request.original_filename || "documento";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "descargar el documento",
        resource: request.label,
        fallback: "No fue posible descargar el archivo.",
      }));
    }
  }

  if (loading) {
    return (
      <section className="panel employee-self-card">
        <LoadingState label="Cargando tus datos y documentos…" compact />
      </section>
    );
  }

  return (
    <div className="employee-self-stack">
      {error && <FeedbackMessage title="No pudimos completar la acción">{error}</FeedbackMessage>}
      {success && <FeedbackMessage tone="success" title="Cambios guardados">{success}</FeedbackMessage>}

      <section className="panel employee-self-card">
        <div className="employee-self-heading">
          <div>
            <span className="eyebrow">Autoservicio</span>
            <h2>Mis datos personales</h2>
            <p>
              Puedes mantener actualizados tus datos de contacto. Cargo, área, correo laboral y fecha de ingreso siguen siendo administrados por Talento Humano.
            </p>
          </div>
        </div>

        <form className="employee-self-form" onSubmit={saveProfile}>
          <div className="employee-self-grid">
            <div className="form-group">
              <label htmlFor="self-first-name">Nombre</label>
              <input
                id="self-first-name"
                value={profile.first_name || ""}
                onChange={(event) => setProfile({ ...profile, first_name: event.target.value })}
              />
            </div>
            <div className="form-group">
              <label htmlFor="self-last-name">Apellido</label>
              <input
                id="self-last-name"
                value={profile.last_name || ""}
                onChange={(event) => setProfile({ ...profile, last_name: event.target.value })}
              />
            </div>
            <div className="form-group">
              <label htmlFor="self-personal-email">Correo personal</label>
              <input
                id="self-personal-email"
                type="email"
                value={profile.personal_email || ""}
                onChange={(event) => setProfile({ ...profile, personal_email: event.target.value })}
                placeholder="correo@personal.com"
              />
            </div>
            <div className="form-group">
              <label htmlFor="self-phone">Teléfono</label>
              <input
                id="self-phone"
                value={profile.phone || ""}
                onChange={(event) => setProfile({ ...profile, phone: event.target.value })}
                placeholder="+57 300 000 0000"
              />
            </div>
            <div className="form-group">
              <label htmlFor="self-city">Ciudad</label>
              <input
                id="self-city"
                value={profile.city || ""}
                onChange={(event) => setProfile({ ...profile, city: event.target.value })}
              />
            </div>
            <div className="form-group">
              <label htmlFor="self-address">Dirección</label>
              <input
                id="self-address"
                value={profile.address || ""}
                onChange={(event) => setProfile({ ...profile, address: event.target.value })}
              />
            </div>
            <div className="form-group">
              <label htmlFor="self-emergency-name">Contacto de emergencia</label>
              <input
                id="self-emergency-name"
                value={profile.emergency_contact_name || ""}
                onChange={(event) => setProfile({ ...profile, emergency_contact_name: event.target.value })}
              />
            </div>
            <div className="form-group">
              <label htmlFor="self-emergency-phone">Teléfono de emergencia</label>
              <input
                id="self-emergency-phone"
                value={profile.emergency_contact_phone || ""}
                onChange={(event) => setProfile({ ...profile, emergency_contact_phone: event.target.value })}
              />
            </div>
          </div>

          <div className="employee-self-work-summary">
            <div><span>Correo laboral</span><strong>{profile.work_email || "Sin registrar"}</strong></div>
            <div><span>Cargo</span><strong>{profile.job_title || "Por completar"}</strong></div>
            <div><span>Área</span><strong>{profile.department || "Por completar"}</strong></div>
          </div>

          <div className="form-actions">
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? "Guardando…" : "Guardar mis datos"}
            </button>
          </div>
        </form>
      </section>

      <section className="panel employee-documents-card">
        <div className="employee-self-heading">
          <div>
            <span className="eyebrow">Documentación</span>
            <h2>Documentos solicitados</h2>
            <p>
              Sube únicamente los documentos que Talento Humano te solicite. Los archivos quedan privados y solo los administradores autorizados pueden consultarlos.
            </p>
          </div>
          <span className="employee-documents-count">
            {documents.filter((item) => item.status === "UPLOADED").length}/{documents.length} cargados
          </span>
        </div>

        {documents.length === 0 ? (
          <div className="employee-documents-empty">
            No tienes documentos pendientes en este momento.
          </div>
        ) : (
          <div className="employee-document-list">
            {documents.map((request) => (
              <article className="employee-document-item" key={request.id}>
                <div className="employee-document-copy">
                  <div className="employee-document-title">
                    <strong>{request.label}</strong>
                    <span className={`status-pill ${request.status === "UPLOADED" ? "" : "status-disabled"}`}>
                      <i /> {request.status === "UPLOADED" ? "Cargado" : "Pendiente"}
                    </span>
                  </div>
                  <small>
                    {request.required ? "Requerido" : "Opcional"}
                    {request.original_filename ? ` · ${request.original_filename}` : ""}
                    {request.size_bytes ? ` · ${fileSize(request.size_bytes)}` : ""}
                  </small>
                </div>

                <div className="employee-document-actions">
                  {request.has_file && (
                    <button
                      className="btn btn-secondary btn-sm"
                      type="button"
                      onClick={() => downloadDocument(request)}
                    >
                      Descargar
                    </button>
                  )}
                  <label className="btn btn-ghost btn-sm employee-document-file-button">
                    {request.has_file ? "Reemplazar" : "Seleccionar archivo"}
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,.docx"
                      onChange={(event) => setFiles({
                        ...files,
                        [request.id]: event.target.files?.[0] || null,
                      })}
                    />
                  </label>
                  {files[request.id] && (
                    <button
                      className="btn btn-primary btn-sm"
                      type="button"
                      disabled={uploadingId === request.id}
                      onClick={() => uploadDocument(request)}
                    >
                      {uploadingId === request.id ? "Subiendo…" : "Subir"}
                    </button>
                  )}
                </div>
                {files[request.id] && (
                  <small className="employee-document-selected">
                    Seleccionado: {files[request.id].name}
                  </small>
                )}
              </article>
            ))}
          </div>
        )}

        <p className="employee-document-help">
          Formatos admitidos: PDF, JPG, PNG y DOCX · máximo 10 MB por archivo.
        </p>
      </section>
    </div>
  );
}
