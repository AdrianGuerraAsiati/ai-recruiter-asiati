// eslint-disable-next-line no-unused-vars
import React, { useCallback, useEffect, useMemo, useState } from "react";

import api from "../api/client";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../utils/errors";
import PageHeader from "../components/ui/PageHeader";
import {
  FeedbackMessage,
  LoadingState,
  ProgressBar,
} from "../components/ui/StatePanel";

const MAX_BYTES = 15 * 1024 * 1024;
const ALLOWED_TYPES = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

const STATUS_META = {
  MISSING: { label: "Pendiente de envío", className: "missing" },
  PENDING_REVIEW: { label: "En revisión", className: "pending" },
  APPROVED: { label: "Aprobado", className: "approved" },
  CHANGES_REQUESTED: { label: "Requiere cambios", className: "changes" },
};

function statusMeta(value) {
  return STATUS_META[value] || STATUS_META.MISSING;
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function employeeLabel(employee) {
  return [employee?.first_name, employee?.last_name].filter(Boolean).join(" ")
    || employee?.email
    || employee?.id
    || "Empleado";
}

function Documents() {
  const { principal, hasPermission } = useSession();
  const ownEmployeeId = principal?.profile?.id || "";
  const canReadAll = hasPermission("employee_documents.read_all");
  const canReview = hasPermission("employee_documents.review");
  const canUploadOwn = hasPermission("employee_documents.upload_own");

  const [employees, setEmployees] = useState([]);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState(ownEmployeeId);
  const [portfolio, setPortfolio] = useState(null);
  const [filesByType, setFilesByType] = useState({});
  const [valuesByType, setValuesByType] = useState({});
  const [reviewNotes, setReviewNotes] = useState({});
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const viewingOwn = selectedEmployeeId === ownEmployeeId;
  const selectedEmployee = useMemo(
    () => employees.find((item) => item.id === selectedEmployeeId) || null,
    [employees, selectedEmployeeId],
  );

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

  const loadPortfolio = useCallback(async () => {
    if (!selectedEmployeeId) return;
    setLoading(true);
    setError("");
    try {
      const endpoint = viewingOwn
        ? "/employee-documents/me"
        : `/employee-documents/employees/${selectedEmployeeId}`;
      const { data } = await api.get(endpoint);
      const items = Array.isArray(data?.items) ? data.items : [];
      setPortfolio({ ...data, items });
      setValuesByType(Object.fromEntries(
        items
          .filter((item) => item.kind === "TEXT")
          .map((item) => [item.document_type, item.value_text || ""]),
      ));
      setReviewNotes(Object.fromEntries(
        items
          .filter((item) => item.id)
          .map((item) => [item.id, item.review_comment || ""]),
      ));
    } catch (err) {
      setPortfolio(null);
      setError(getApiErrorMessage(err, {
        action: "cargar el expediente de ingreso",
        resource: "documentos",
        fallback: "No se pudo actualizar el expediente del empleado.",
      }));
    } finally {
      setLoading(false);
    }
  }, [selectedEmployeeId, viewingOwn]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadPortfolio();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadPortfolio]);

  function selectEmployee(employeeId) {
    setSelectedEmployeeId(employeeId);
    setFilesByType({});
    setValuesByType({});
    setReviewNotes({});
    setSuccess("");
    setError("");
  }

  function onFileChange(documentType, event) {
    const nextFile = event.target.files?.[0] || null;
    setSuccess("");
    setError("");
    if (!nextFile) {
      setFilesByType((current) => ({ ...current, [documentType]: null }));
      return;
    }
    if (!ALLOWED_TYPES.has(nextFile.type)) {
      setFilesByType((current) => ({ ...current, [documentType]: null }));
      setError("Formato no soportado. Usa PDF, JPG, PNG, DOC o DOCX.");
      event.target.value = "";
      return;
    }
    if (nextFile.size <= 0 || nextFile.size > MAX_BYTES) {
      setFilesByType((current) => ({ ...current, [documentType]: null }));
      setError("El documento debe pesar máximo 15 MB.");
      event.target.value = "";
      return;
    }
    setFilesByType((current) => ({ ...current, [documentType]: nextFile }));
  }

  async function uploadRequirement(item) {
    const file = filesByType[item.document_type];
    if (!file || !viewingOwn) return;

    setBusyKey(item.document_type);
    setError("");
    setSuccess("");
    try {
      const manifest = {
        document_type: item.document_type,
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
      setFilesByType((current) => ({ ...current, [item.document_type]: null }));
      setSuccess(`${item.label} quedó enviado a revisión.`);
      await loadPortfolio();
    } catch (err) {
      setError(
        err.response?.data?.detail
        || getApiErrorMessage(err, {
          action: "subir el documento",
          resource: "documentos",
          fallback: "El documento no quedó guardado. Vuelve a seleccionarlo e inténtalo nuevamente.",
        }),
      );
    } finally {
      setBusyKey("");
    }
  }

  async function saveValue(item) {
    if (!viewingOwn) return;
    const value = String(valuesByType[item.document_type] || "").trim();
    if (!value) {
      setError(`Completa “${item.label}” antes de enviarlo.`);
      return;
    }

    setBusyKey(item.document_type);
    setError("");
    setSuccess("");
    try {
      await api.put("/employee-documents/me/value", {
        document_type: item.document_type,
        value,
      });
      setSuccess(`${item.label} quedó enviado a revisión.`);
      await loadPortfolio();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "guardar la información",
        resource: "documentos",
        fallback: "La información no quedó guardada.",
      }));
    } finally {
      setBusyKey("");
    }
  }

  async function downloadDocument(item) {
    if (!item.id) return;
    setError("");
    try {
      const { data } = await api.get(`/employee-documents/${item.id}/download`);
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "descargar el documento",
        resource: "documentos",
        fallback: "No fue posible generar el enlace privado de descarga.",
      }));
    }
  }

  async function reviewRequirement(item, status) {
    if (!item.id || !canReview || viewingOwn) return;
    const comment = String(reviewNotes[item.id] || "").trim();
    if (status === "CHANGES_REQUESTED" && !comment) {
      setError("Escribe un comentario para indicar qué debe corregir el empleado.");
      return;
    }

    setBusyKey(`review-${item.id}`);
    setError("");
    setSuccess("");
    try {
      const { data } = await api.post(`/employee-documents/${item.id}/review`, {
        status,
        comment: comment || null,
      });
      const items = Array.isArray(data?.items) ? data.items : [];
      setPortfolio({ ...data, items });
      setReviewNotes(Object.fromEntries(
        items
          .filter((row) => row.id)
          .map((row) => [row.id, row.review_comment || ""]),
      ));
      setSuccess(
        status === "APPROVED"
          ? `${item.label} aprobado.`
          : `Se solicitaron cambios en ${item.label}.`,
      );
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "revisar el requisito",
        resource: "documentos",
        fallback: "La revisión no quedó guardada.",
      }));
    } finally {
      setBusyKey("");
    }
  }

  const items = portfolio?.items || [];
  const fileItems = items.filter((item) => item.kind === "FILE");
  const textItems = items.filter((item) => item.kind === "TEXT");
  const summary = portfolio?.summary || {
    total: 13,
    submitted: 0,
    approved: 0,
    pending_review: 0,
    changes_requested: 0,
    missing: 13,
    approval_percent: 0,
  };

  function renderRequirement(item) {
    const meta = statusMeta(item.review_status);
    const isBusy = busyKey === item.document_type || busyKey === `review-${item.id}`;
    const inputKey = `${item.document_type}-${item.uploaded_at || "missing"}`;

    return (
      <article
        className={`document-requirement-card document-status-${meta.className}`}
        key={item.document_type}
      >
        <div className="document-requirement-header">
          <div>
            <span className="document-requirement-kind">
              {item.kind === "FILE" ? "Documento" : "Información"}
            </span>
            <h3>{item.label}</h3>
            <p>{item.description}</p>
          </div>
          <span className={`document-review-status status-${meta.className}`}>
            <i aria-hidden="true" />
            {meta.label}
          </span>
        </div>

        {item.kind === "FILE" ? (
          <div className="document-requirement-body">
            {item.id && (
              <div className="document-current-file">
                <div>
                  <strong>{item.original_filename}</strong>
                  <small>
                    {[formatBytes(item.size_bytes), formatDate(item.uploaded_at)]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </div>
                <button
                  className="btn btn-secondary btn-sm"
                  type="button"
                  onClick={() => downloadDocument(item)}
                >
                  Ver archivo
                </button>
              </div>
            )}

            {viewingOwn && canUploadOwn && (
              <div className="document-upload-row">
                <label className="document-file-picker">
                  <span>{item.id ? "Reemplazar archivo" : "Seleccionar archivo"}</span>
                  <input
                    key={inputKey}
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,application/pdf,image/jpeg,image/png,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={(event) => onFileChange(item.document_type, event)}
                    disabled={isBusy}
                  />
                </label>
                {filesByType[item.document_type] && (
                  <small className="document-file-selection">
                    {filesByType[item.document_type].name} · {formatBytes(filesByType[item.document_type].size)}
                  </small>
                )}
                <button
                  className="btn btn-primary btn-sm"
                  type="button"
                  disabled={!filesByType[item.document_type] || isBusy}
                  onClick={() => uploadRequirement(item)}
                >
                  {isBusy ? "Enviando…" : item.id ? "Enviar nueva versión" : "Enviar a revisión"}
                </button>
              </div>
            )}
          </div>
        ) : viewingOwn && canUploadOwn ? (
          <div className="document-value-editor">
            <textarea
              aria-label={item.label}
              rows={item.document_type === "EMERGENCY_CONTACT" ? 3 : 2}
              value={valuesByType[item.document_type] || ""}
              onChange={(event) => setValuesByType((current) => ({
                ...current,
                [item.document_type]: event.target.value,
              }))}
              placeholder={item.description}
              disabled={isBusy}
            />
            <button
              className="btn btn-primary btn-sm"
              type="button"
              onClick={() => saveValue(item)}
              disabled={isBusy || !String(valuesByType[item.document_type] || "").trim()}
            >
              {isBusy ? "Guardando…" : item.id ? "Actualizar y enviar" : "Enviar a revisión"}
            </button>
          </div>
        ) : (
          <div className="document-readonly-value">
            <span>Información reportada</span>
            <strong>{item.value_text || "Sin información enviada"}</strong>
          </div>
        )}

        {item.review_comment && (
          <div className="document-review-comment">
            <strong>Comentario de revisión</strong>
            <p>{item.review_comment}</p>
          </div>
        )}

        {canReview && !viewingOwn && item.id && (
          <div className="document-admin-review">
            <label htmlFor={`review-note-${item.id}`}>Comentario del administrador</label>
            <textarea
              id={`review-note-${item.id}`}
              rows="2"
              value={reviewNotes[item.id] || ""}
              onChange={(event) => setReviewNotes((current) => ({
                ...current,
                [item.id]: event.target.value,
              }))}
              placeholder="Opcional al aprobar; obligatorio si solicitas cambios."
              disabled={isBusy}
            />
            <div className="ui-actions">
              <button
                className="btn btn-secondary btn-sm document-approve-button"
                type="button"
                onClick={() => reviewRequirement(item, "APPROVED")}
                disabled={isBusy}
              >
                ✓ Dar visto bueno
              </button>
              <button
                className="btn btn-ghost btn-sm"
                type="button"
                onClick={() => reviewRequirement(item, "CHANGES_REQUESTED")}
                disabled={isBusy}
              >
                Solicitar corrección
              </button>
            </div>
          </div>
        )}
      </article>
    );
  }

  return (
    <div className="page employee-documents-page">
      <PageHeader
        eyebrow="Ingreso y vinculación"
        title="Documentos"
        description="Cada requisito debe ser enviado por el nuevo empleado y revisado individualmente por un administrador antes de quedar aprobado."
        className="split-header"
      />

      {error && <FeedbackMessage title="No se pudo completar la operación">{error}</FeedbackMessage>}
      {success && <FeedbackMessage title="Expediente actualizado" tone="success">{success}</FeedbackMessage>}

      {canReadAll && (
        <section className="panel document-employee-selector">
          <div>
            <span className="eyebrow">Revisión administrativa</span>
            <h2>Selecciona un empleado</h2>
            <p>Abre su expediente, revisa cada soporte y deja observaciones cuando requiera correcciones.</p>
          </div>
          <div className="form-group">
            <label htmlFor="employee-documents-employee">Empleado a consultar</label>
            <select
              id="employee-documents-employee"
              aria-label="Empleado a consultar"
              value={selectedEmployeeId}
              onChange={(event) => selectEmployee(event.target.value)}
            >
              <option value={ownEmployeeId}>Mis documentos</option>
              {employees
                .filter((employee) => employee.id !== ownEmployeeId)
                .map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employeeLabel(employee)}
                  </option>
                ))}
            </select>
          </div>
        </section>
      )}

      {loading ? (
        <LoadingState label="Cargando expediente…" />
      ) : portfolio ? (
        <>
          <section className="panel document-summary-panel">
            <div className="document-summary-copy">
              <span className="eyebrow">
                {viewingOwn ? "Tu expediente" : "Expediente seleccionado"}
              </span>
              <h2>
                {viewingOwn
                  ? "Estado de documentación"
                  : employeeLabel(portfolio.employee || selectedEmployee)}
              </h2>
              <p>
                El expediente queda completo únicamente cuando los {summary.total} requisitos
                tengan visto bueno.
              </p>
              <ProgressBar
                value={summary.approval_percent}
                label="Requisitos aprobados"
                showValue
              />
            </div>
            <div className="document-summary-metrics">
              <div><strong>{summary.approved}</strong><span>Aprobados</span></div>
              <div><strong>{summary.pending_review}</strong><span>En revisión</span></div>
              <div><strong>{summary.changes_requested}</strong><span>Por corregir</span></div>
              <div><strong>{summary.missing}</strong><span>Pendientes</span></div>
            </div>
          </section>

          <section className="document-requirement-section">
            <div className="section-heading">
              <div>
                <span className="eyebrow">Archivos</span>
                <h2>Documentos requeridos</h2>
                <p>PDF, JPG, PNG, DOC o DOCX · máximo 15 MB por archivo.</p>
              </div>
              <span className="document-section-count">{fileItems.length} requisitos</span>
            </div>
            <div className="document-requirement-grid">
              {fileItems.map(renderRequirement)}
            </div>
          </section>

          <section className="document-requirement-section">
            <div className="section-heading">
              <div>
                <span className="eyebrow">Datos de ingreso</span>
                <h2>Información complementaria</h2>
                <p>Estos datos también deben recibir visto bueno de Talento Humano.</p>
              </div>
              <span className="document-section-count">{textItems.length} requisitos</span>
            </div>
            <div className="document-requirement-grid">
              {textItems.map(renderRequirement)}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}

export default Documents;
