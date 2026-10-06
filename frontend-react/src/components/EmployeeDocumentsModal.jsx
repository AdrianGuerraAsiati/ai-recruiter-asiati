import { useCallback, useEffect, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import { FeedbackMessage, LoadingState } from "./ui/StatePanel";

const PRESETS = [
  "Documento de identidad",
  "Certificación bancaria",
  "Certificación EPS",
  "Certificación de pensión",
  "Certificado de estudios",
  "Otro documento",
];

export default function EmployeeDocumentsModal({ open, employee, onClose }) {
  const [items, setItems] = useState([]);
  const [label, setLabel] = useState(PRESETS[0]);
  const [customLabel, setCustomLabel] = useState("");
  const [required, setRequired] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!open || !employee?.id) return;
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get(`/employees/${employee.id}/documents`);
      setItems(data?.items || []);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar los documentos del empleado",
        resource: "documentos",
        fallback: "No fue posible cargar las solicitudes de documentos.",
      }));
    } finally {
      setLoading(false);
    }
  }, [employee?.id, open]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [load]);

  if (!open || !employee) return null;

  async function createRequest(event) {
    event.preventDefault();
    const finalLabel = label === "Otro documento" ? customLabel.trim() : label;
    if (!finalLabel) {
      setError("Escribe el nombre del documento que deseas solicitar.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.post(`/employees/${employee.id}/documents/requests`, {
        label: finalLabel,
        document_type: label === "Otro documento" ? "OTHER" : label,
        required,
      });
      setCustomLabel("");
      await load();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "solicitar el documento",
        resource: "documentos",
        fallback: "No fue posible crear la solicitud.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function download(item) {
    setError("");
    try {
      const response = await api.get(
        `/employees/${employee.id}/documents/${item.id}/download`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = item.original_filename || "documento";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "descargar el documento",
        resource: item.label,
        fallback: "No fue posible descargar el archivo.",
      }));
    }
  }

  const fullName = [employee.first_name, employee.last_name].filter(Boolean).join(" ")
    || employee.email
    || "Empleado";

  return (
    <div className="modal-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="modal employee-documents-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="employee-documents-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">Expediente del empleado</span>
            <h2 id="employee-documents-modal-title">Documentos</h2>
            <p>{fullName}</p>
          </div>
          <button className="btn-close" type="button" aria-label="Cerrar documentos" onClick={onClose}>×</button>
        </div>

        {error && <FeedbackMessage title="No pudimos completar la acción">{error}</FeedbackMessage>}

        <form className="employee-document-request-form" onSubmit={createRequest}>
          <div>
            <span className="eyebrow">Nueva solicitud</span>
            <h3>Solicitar un documento</h3>
          </div>
          <div className="employee-document-request-grid">
            <div className="form-group">
              <label htmlFor="admin-document-type">Documento</label>
              <select id="admin-document-type" value={label} onChange={(event) => setLabel(event.target.value)}>
                {PRESETS.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            {label === "Otro documento" && (
              <div className="form-group">
                <label htmlFor="admin-document-custom">Nombre del documento</label>
                <input
                  id="admin-document-custom"
                  value={customLabel}
                  onChange={(event) => setCustomLabel(event.target.value)}
                  placeholder="Ej. Certificado específico"
                  required
                />
              </div>
            )}
            <label className="employee-document-required">
              <input
                type="checkbox"
                checked={required}
                onChange={(event) => setRequired(event.target.checked)}
              />
              Documento requerido
            </label>
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? "Solicitando…" : "Solicitar documento"}
            </button>
          </div>
        </form>

        <div className="employee-document-admin-list">
          <div className="employee-documents-modal-heading">
            <h3>Solicitudes</h3>
            <span>{items.length}</span>
          </div>

          {loading ? (
            <LoadingState label="Cargando documentos…" compact />
          ) : items.length === 0 ? (
            <div className="employee-documents-empty">
              Todavía no se han solicitado documentos a este empleado.
            </div>
          ) : (
            items.map((item) => (
              <article className="employee-document-admin-item" key={item.id}>
                <div>
                  <strong>{item.label}</strong>
                  <small>
                    {item.required ? "Requerido" : "Opcional"}
                    {item.original_filename ? ` · ${item.original_filename}` : ""}
                  </small>
                </div>
                <div className="ui-actions">
                  <span className={`status-pill ${item.status === "UPLOADED" ? "" : "status-disabled"}`}>
                    <i /> {item.status === "UPLOADED" ? "Recibido" : "Pendiente"}
                  </span>
                  {item.has_file && (
                    <button className="btn btn-secondary btn-sm" type="button" onClick={() => download(item)}>
                      Descargar
                    </button>
                  )}
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
