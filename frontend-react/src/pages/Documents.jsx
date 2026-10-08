// eslint-disable-next-line no-unused-vars
import React, { useCallback, useEffect, useMemo, useState } from "react";

import api from "../api/client";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../utils/errors";
import PageHeader from "../components/ui/PageHeader";
import { EmptyState, FeedbackMessage, LoadingState } from "../components/ui/StatePanel";

const DOCUMENT_TYPES = [
  { value: "IDENTITY", label: "Documento de identidad" },
  { value: "RESUME", label: "Hoja de vida" },
  { value: "BANK_CERTIFICATE", label: "Certificación bancaria" },
  { value: "EDUCATION_CERTIFICATES", label: "Certificados académicos" },
  { value: "EMPLOYMENT_CERTIFICATES", label: "Certificados laborales" },
  { value: "SOCIAL_SECURITY", label: "Seguridad social" },
  { value: "OTHER", label: "Otro documento" },
];

const MAX_BYTES = 15 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["application/pdf", "image/jpeg", "image/png"]);

function documentTypeLabel(value) {
  return DOCUMENT_TYPES.find((item) => item.value === value)?.label || value;
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  if (!value) return "Sin fecha";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Sin fecha";
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function Documents() {
  const { principal, hasPermission } = useSession();
  const ownEmployeeId = principal?.profile?.id || "";
  const canReadAll = hasPermission("employee_documents.read_all");
  const canUploadOwn = hasPermission("employee_documents.upload_own");

  const [employees, setEmployees] = useState([]);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState(ownEmployeeId);
  const [documents, setDocuments] = useState([]);
  const [documentType, setDocumentType] = useState("IDENTITY");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!canReadAll) return undefined;
    let active = true;
    api.get("/employees")
      .then(({ data }) => {
        if (active) setEmployees(Array.isArray(data?.items) ? data.items : []);
      })
      .catch(() => {
        if (active) setEmployees([]);
      });
    return () => {
      active = false;
    };
  }, [canReadAll]);

  const selectedEmployee = useMemo(
    () => employees.find((item) => item.id === selectedEmployeeId) || null,
    [employees, selectedEmployeeId],
  );
  const viewingOwn = selectedEmployeeId === ownEmployeeId;

  const loadDocuments = useCallback(async () => {
    if (!selectedEmployeeId) return;
    setLoading(true);
    setError("");
    try {
      const endpoint = viewingOwn
        ? "/employee-documents/me"
        : `/employee-documents/employees/${selectedEmployeeId}`;
      const { data } = await api.get(endpoint);
      setDocuments(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar los documentos",
        resource: "documentos",
        fallback: "No se pudo actualizar el listado de documentos.",
      }));
    } finally {
      setLoading(false);
    }
  }, [selectedEmployeeId, viewingOwn]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadDocuments();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadDocuments]);

  function onFileChange(event) {
    const nextFile = event.target.files?.[0] || null;
    setSuccess("");
    setError("");
    if (!nextFile) {
      setFile(null);
      return;
    }
    if (!ALLOWED_TYPES.has(nextFile.type)) {
      setFile(null);
      setError("Formato no soportado. Usa PDF, JPG o PNG.");
      event.target.value = "";
      return;
    }
    if (nextFile.size <= 0 || nextFile.size > MAX_BYTES) {
      setFile(null);
      setError("El documento debe pesar máximo 15 MB.");
      event.target.value = "";
      return;
    }
    setFile(nextFile);
  }

  async function uploadDocument(event) {
    event.preventDefault();
    if (!file || !viewingOwn) return;
    setUploading(true);
    setError("");
    setSuccess("");
    try {
      const manifest = {
        document_type: documentType,
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
      };
      const { data } = await api.post("/employee-documents/me/upload", manifest);
      const formData = new FormData();
      Object.entries(data.upload?.fields || {}).forEach(([key, value]) => {
        formData.append(key, value);
      });
      formData.append("file", file);

      const uploadResponse = await fetch(data.upload.url, {
        method: "POST",
        body: formData,
      });
      if (!uploadResponse.ok) throw new Error("S3 upload failed");

      await api.post("/employee-documents/me/complete", {
        ...manifest,
        key: data.key,
      });
      setFile(null);
      const input = document.getElementById("employee-document-file");
      if (input) input.value = "";
      setSuccess("Documento cargado correctamente.");
      await loadDocuments();
    } catch (err) {
      setError(
        err.response?.data?.detail
        || getApiErrorMessage(err, {
          action: "subir el documento",
          resource: "documentos",
          fallback: "El documento no quedó guardado. Vuelve a seleccionar el archivo e inténtalo nuevamente.",
        }),
      );
    } finally {
      setUploading(false);
    }
  }

  async function downloadDocument(document) {
    setError("");
    try {
      const { data } = await api.get(`/employee-documents/${document.id}/download`);
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "descargar el documento",
        resource: "documentos",
        fallback: "No fue posible generar el enlace privado de descarga.",
      }));
    }
  }

  const titleDetail = viewingOwn
    ? "Tus archivos privados"
    : [selectedEmployee?.first_name, selectedEmployee?.last_name].filter(Boolean).join(" ")
      || selectedEmployee?.email
      || "Empleado";

  return (
    <div className="page employee-documents-page">
      <PageHeader
        eyebrow="Ingreso y vinculación"
        title="Documentos"
        description="Carga y consulta la documentación de ingreso en un espacio privado. Los enlaces de descarga son temporales."
        className="split-header"
      />

      {error && <FeedbackMessage title="No se pudo completar la operación">{error}</FeedbackMessage>}
      {success && <FeedbackMessage title="Carga completada">{success}</FeedbackMessage>}

      {canReadAll && (
        <section className="panel">
          <div className="form-group">
            <label htmlFor="employee-documents-employee">Empleado a consultar</label>
            <select
              id="employee-documents-employee"
              aria-label="Empleado a consultar"
              value={selectedEmployeeId}
              onChange={(event) => {
                setSelectedEmployeeId(event.target.value);
                setSuccess("");
              }}
            >
              <option value={ownEmployeeId}>Mis documentos</option>
              {employees
                .filter((employee) => employee.id !== ownEmployeeId)
                .map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {[employee.first_name, employee.last_name].filter(Boolean).join(" ")
                      || employee.email
                      || employee.id}
                  </option>
                ))}
            </select>
          </div>
        </section>
      )}

      {viewingOwn && canUploadOwn && (
        <section className="panel">
          <div className="employee-toolbar">
            <div>
              <span className="eyebrow">Carga segura</span>
              <h2>Subir o reemplazar documento</h2>
              <p>PDF, JPG o PNG · máximo 15 MB. Si cargas el mismo tipo otra vez, reemplaza la versión anterior.</p>
            </div>
          </div>
          <form onSubmit={uploadDocument}>
            <div className="employee-form-grid">
              <div className="form-group">
                <label htmlFor="employee-document-type">Tipo de documento</label>
                <select
                  id="employee-document-type"
                  value={documentType}
                  onChange={(event) => setDocumentType(event.target.value)}
                >
                  {DOCUMENT_TYPES.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="employee-document-file">Archivo</label>
                <input
                  id="employee-document-file"
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                  onChange={onFileChange}
                  required
                />
                {file && <small>{file.name} · {formatBytes(file.size)}</small>}
              </div>
            </div>
            <div className="form-actions">
              <button className="btn btn-primary" type="submit" disabled={!file || uploading}>
                {uploading ? "Subiendo…" : "Subir documento"}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="panel">
        <div className="employee-toolbar">
          <div>
            <span className="eyebrow">Expediente</span>
            <h2>{titleDetail}</h2>
          </div>
          <span>{documents.length} documento{documents.length === 1 ? "" : "s"}</span>
        </div>

        {loading ? (
          <LoadingState label="Cargando documentos…" compact />
        ) : documents.length === 0 ? (
          <EmptyState
            compact
            icon="applications"
            title="Aún no hay documentos cargados"
            description={viewingOwn
              ? "Carga el primer archivo solicitado por Talento Humano."
              : "Este empleado todavía no ha cargado documentación."}
          />
        ) : (
          <div className="employee-table-wrap">
            <table className="employee-table">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Archivo</th>
                  <th>Fecha</th>
                  <th aria-label="Acciones" />
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => (
                  <tr key={document.id}>
                    <td><strong>{documentTypeLabel(document.document_type)}</strong></td>
                    <td>
                      <strong className="employee-secondary">{document.original_filename}</strong>
                      <small>{formatBytes(document.size_bytes)} · {document.content_type}</small>
                    </td>
                    <td><small>{formatDate(document.uploaded_at)}</small></td>
                    <td>
                      <button
                        className="btn btn-ghost"
                        type="button"
                        onClick={() => downloadDocument(document)}
                      >
                        Descargar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default Documents;
