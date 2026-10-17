// eslint-disable-next-line no-unused-vars
import React, { useCallback, useEffect, useMemo, useState } from "react";

import api from "../api/client";
import DocumentReviewQueue from "../components/DocumentReviewQueue";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../utils/errors";
import PageHeader from "../components/ui/PageHeader";
import "../talent-workspaces.css";
import "./ContractSignature.css";
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
  const requestedProfileId = canReadAll
    ? new URLSearchParams(window.location.search).get("employee_id")
    : null;
  const [selectedEmployeeId, setSelectedEmployeeId] = useState(requestedProfileId || ownEmployeeId);
  const [portfolio, setPortfolio] = useState(null);
  const [filesByType, setFilesByType] = useState({});
  const [valuesByType, setValuesByType] = useState({});
  const [reviewNotes, setReviewNotes] = useState({});
  const [queueRevision, setQueueRevision] = useState(0);
  const [welcomeStatus, setWelcomeStatus] = useState(null);
  const [welcomeBusy, setWelcomeBusy] = useState(false);
  const [signReadiness, setSignReadiness] = useState(null);
  const [signBusy, setSignBusy] = useState(false);
  const [signRequest, setSignRequest] = useState(null);
  const [signRequestBusy, setSignRequestBusy] = useState(false);
  const [signSendStatus, setSignSendStatus] = useState(null);
  const [signSendPreview, setSignSendPreview] = useState(false);
  const [signSendConfirmed, setSignSendConfirmed] = useState(false);
  const [signSendBusy, setSignSendBusy] = useState(false);
  const [signedArtifact, setSignedArtifact] = useState(null);
  const [signedBusy, setSignedBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [idCopyStatus, setIdCopyStatus] = useState("");

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

  useEffect(() => {
    if (!canReadAll || viewingOwn || !selectedEmployeeId) {
      return undefined;
    }
    let active = true;
    api.get(`/employee-documents/employees/${selectedEmployeeId}/welcome`)
      .then(({ data }) => { if (active) setWelcomeStatus(data); })
      .catch(() => { if (active) setWelcomeStatus(null); });
    return () => { active = false; };
  }, [canReadAll, selectedEmployeeId, viewingOwn]);

  async function retryWelcome() {
    if (!selectedEmployeeId || !canReview) return;
    setWelcomeBusy(true);
    setError("");
    try {
      const { data } = await api.post(
        `/employee-documents/employees/${selectedEmployeeId}/welcome/retry`,
      );
      setWelcomeStatus(data);
      setSuccess(data.status === "SENT"
        ? "Correo de bienvenida y documentos enviado al empleado."
        : "La solicitud de envío quedó registrada; revisa la configuración de SES.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "reenviar el correo de bienvenida",
        fallback: "No fue posible reenviar la solicitud de documentos.",
      }));
    } finally {
      setWelcomeBusy(false);
    }
  }

  function selectEmployee(employeeId) {
    setSignReadiness(null);
    setSignRequest(null);
    setSignSendStatus(null);
    setSignSendPreview(false);
    setSignSendConfirmed(false);
    setSignedArtifact(null);
    setSelectedEmployeeId(employeeId);
    setIdCopyStatus("");
    setFilesByType({});
    setValuesByType({});
    setReviewNotes({});
    setSuccess("");
    setError("");
  }

  async function copySelectedProfileId() {
    const profileId = portfolio?.employee?.id;
    if (!canReadAll || viewingOwn || !profileId || profileId !== selectedEmployeeId) return;
    try {
      if (!window.navigator.clipboard?.writeText) {
        throw new Error("clipboard-unavailable");
      }
      await window.navigator.clipboard.writeText(profileId);
      setIdCopyStatus("ID copiado");
    } catch {
      setIdCopyStatus("No se pudo copiar automáticamente. Selecciona el UUID para copiarlo.");
    }
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
    const adminContract = item.admin_only && canReview && canReadAll && !viewingOwn;
    if (!file || (!viewingOwn && !adminContract)) return;
    if (item.admin_only && !adminContract) return;

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
      const uploadBase = adminContract
        ? `/employee-documents/employees/${selectedEmployeeId}/contract`
        : "/employee-documents/me";
      const { data } = await api.post(`${uploadBase}/upload`, manifest);
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

      await api.post(`${uploadBase}/complete`, {
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
      setQueueRevision((current) => current + 1);
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


  useEffect(() => {
    if (!canReadAll || viewingOwn || !selectedEmployeeId) {
      return undefined;
    }
    let active = true;
    api.get(`/employee-documents/employees/${encodeURIComponent(selectedEmployeeId)}/contract/sign`)
      .then(({ data }) => { if (active) setSignReadiness(data); })
      .catch(() => {
        if (active) setSignReadiness({
          ready: false,
          message: "No se pudo consultar Odoo Sign staging.",
        });
      });
    return () => { active = false; };
  }, [canReadAll, selectedEmployeeId, viewingOwn, queueRevision]);

  useEffect(() => {
    if (!canReadAll || viewingOwn || !selectedEmployeeId) return undefined;
    let active = true;
    api.get(`/employee-documents/employees/${encodeURIComponent(selectedEmployeeId)}/contract/sign/request`)
      .then(({ data }) => {
        if (active) {
          setSignRequest(data);
        }
      })
      .catch(() => { if (active) setSignRequest(null); });
    return () => { active = false; };
  }, [canReadAll, selectedEmployeeId, viewingOwn]);


  useEffect(() => {
    if (!selectedEmployeeId) return undefined;
    let active = true;
    const path = (viewingOwn
      ? "/employee-documents/me/contract/signed"
      : `/employee-documents/employees/${encodeURIComponent(selectedEmployeeId)}/contract/signed`);
    api.get(path).then(({ data }) => {
      if (active) setSignedArtifact(data);
    }).catch(() => {
      if (active) setSignedArtifact({ archived: false });
    });
    return () => { active = false; };
  }, [selectedEmployeeId, viewingOwn]);

  useEffect(() => {
    if (!canReadAll || viewingOwn || !selectedEmployeeId) return undefined;
    let active = true;
    api.get(`/employee-documents/employees/${encodeURIComponent(selectedEmployeeId)}/contract/sign/request/send-status`)
      .then(({ data }) => { if (active) setSignSendStatus(data); })
      .catch(() => { if (active) setSignSendStatus(null); });
    return () => { active = false; };
  }, [canReadAll, selectedEmployeeId, viewingOwn]);

  async function runStagingSignSend(action) {
    if (!canReview || viewingOwn || signSendBusy || !selectedEmployeeId) return;
    if (action === "send" && (!signSendConfirmed || !signSendPreview)) return;
    const prefix = `/employee-documents/employees/${encodeURIComponent(selectedEmployeeId)}/contract/sign/request`;
    setSignSendBusy(true);
    setError("");
    setSuccess("");
    try {
      if (action === "preview") {
        const { data } = await api.post(`${prefix}/automatic-preview`);
        setSignSendPreview(Boolean(data?.validated));
        setSuccess("Plantilla, firmantes y contactos ficticios verificados. Aún no se ha enviado.");
      } else {
        const { data } = await api.post(
          action === "send" ? `${prefix}/automatic-send` : `${prefix}/reconcile`,
          action === "send" ? { confirm: true } : undefined,
        );
        setSignSendPreview(false);
        setSignSendConfirmed(false);
        setSignSendStatus({
          enabled: true, status: data.status, request_id: data.request_id,
        });
        if (data.request_id) {
          const { data: current } = await api.get(prefix);
          setSignRequest(current);
          setSuccess("Solicitud de firma creada en Odoo staging; firma y correos permanecen bajo control de Odoo.");
        } else {
          setSuccess("Sin solicitud confirmada. No reintentes el envío: concilia primero con Odoo.");
        }
      }
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: action === "preview" ? "validar la solicitud" :
          action === "send" ? "enviar la solicitud" : "reconciliar la solicitud",
        resource: "Odoo Sign staging",
        fallback: "No se confirmó el resultado. No repitas el envío; consulta su estado y reconcilia.",
      }));
      if (action === "send") {
        setSignSendPreview(false);
        setSignSendConfirmed(false);
      }
      if (action !== "preview") {
        api.get(`${prefix}/send-status`)
          .then(({ data }) => setSignSendStatus(data))
          .catch(() => {});
      }
    } finally {
      setSignSendBusy(false);
    }
  }

  async function archiveCompletedSignature() {
    if (signedBusy || !canReview || viewingOwn || signRequest?.status !== "SIGNED") return;
    setSignedBusy(true);
    setError("");
    try {
      const { data } = await api.post(
        `/employee-documents/employees/${encodeURIComponent(selectedEmployeeId)}/contract/signed/archive`,
      );
      setSignedArtifact(data);
      setSuccess("PDF firmado archivado en el expediente. Confirma los datos contractuales antes de contratar.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "archivar el PDF firmado",
        resource: "Odoo Sign",
        fallback: "El PDF final aún no está disponible para archivar; verifica la configuración de staging.",
      }));
    } finally {
      setSignedBusy(false);
    }
  }

  async function downloadSignedContract() {
    setError("");
    const path = viewingOwn
      ? "/employee-documents/me/contract/signed/download"
      : `/employee-documents/employees/${encodeURIComponent(selectedEmployeeId)}/contract/signed/download`;
    try {
      const { data } = await api.get(path);
      if (!data?.url) throw new Error("missing-download");
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "descargar el contrato firmado",
        resource: "expediente laboral",
        fallback: "No fue posible generar el enlace privado del contrato firmado.",
      }));
    }
  }

  async function refreshSignRequest() {
    if (!canReview || viewingOwn || signRequestBusy || !signRequest?.linked) return;
    const path = `/employee-documents/employees/${encodeURIComponent(selectedEmployeeId)}/contract/sign/request`;
    setSignRequestBusy(true);
    setError("");
    setSuccess("");
    try {
      const { data } = await api.post(`${path}/refresh`);
      setSignRequest(data);
      setSuccess("Estado de los dos firmantes actualizado desde Odoo Sign.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "consultar firmas",
        resource: "Odoo Sign",
        fallback: "No se pudo actualizar el estado de firmas.",
      }));
    } finally {
      setSignRequestBusy(false);
    }
  }

  async function prepareContractSignature() {
    if (!canReview || viewingOwn || !signReadiness?.ready || signBusy) return;
    setSignBusy(true);
    setError("");
    setSuccess("");
    try {
      const { data } = await api.post(
        `/employee-documents/employees/${encodeURIComponent(selectedEmployeeId)}/contract/sign/prepare`,
        { confirm: true },
      );
      setSignReadiness(data);
      setSuccess("Contrato preparado en Odoo Sign staging. Debes configurar firmantes y enviar desde Odoo.");
      await loadPortfolio();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "preparar contrato en Odoo Sign",
        resource: "contrato laboral",
        fallback: "No fue posible preparar el contrato; no se enviaron solicitudes de firma.",
      }));
    } finally {
      setSignBusy(false);
    }
  }

  const items = portfolio?.items || [];
  const fileItems = items.filter((item) => item.kind === "FILE");
  const textItems = items.filter((item) => item.kind === "TEXT");
  const summary = portfolio?.summary || {
    total: 14,
    submitted: 0,
    approved: 0,
    pending_review: 0,
    changes_requested: 0,
    missing: 14,
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
              {item.admin_only ? "Documento obligatorio de Talento Humano" : item.kind === "FILE" ? "Documento" : "Información"}
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

            {((viewingOwn && canUploadOwn && !item.admin_only) ||
              (item.admin_only && canReadAll && canReview && !viewingOwn && !["PREPARING", "PREPARED"].includes(item.odoo_sign_status))) && (
              <div className="document-upload-row">
                <label
                  className={`document-dropzone ${filesByType[item.document_type] ? "has-file" : ""} ${isBusy ? "is-busy" : ""}`}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    event.preventDefault();
                    if (isBusy) return;
                    const file = event.dataTransfer?.files?.[0] || null;
                    if (file) onFileChange(item.document_type, { target: { files: [file], value: "" } });
                  }}
                >
                  <input
                    key={inputKey}
                    className="document-dropzone-input"
                    type="file"
                    aria-label={`Seleccionar archivo para ${item.label}`}
                    accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,application/pdf,image/jpeg,image/png,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={(event) => onFileChange(item.document_type, event)}
                    disabled={isBusy}
                  />
                  <span className="document-dropzone-icon" aria-hidden="true">↑</span>
                  {filesByType[item.document_type] ? (
                    <>
                      <strong className="document-dropzone-filename">{filesByType[item.document_type].name}</strong>
                      <small>{formatBytes(filesByType[item.document_type].size)} · Listo para enviar</small>
                      <span className="document-dropzone-action">Cambiar archivo</span>
                    </>
                  ) : (
                    <>
                      <strong>{item.id ? "Seleccionar nueva versión" : "Adjuntar documento"}</strong>
                      <span className="document-dropzone-helper">Haz clic aquí o arrastra tu archivo</span>
                      <small>PDF, JPG, PNG, DOC o DOCX · Máx. 15 MB</small>
                    </>
                  )}
                </label>
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


        {item.document_type === "EMPLOYMENT_CONTRACT" && canReview && !viewingOwn && (
          <div className="contract-sign-workspace" aria-label="Odoo Sign para contrato laboral">
            <div>
              <strong>Firma del contrato · Odoo Sign</strong>
              <p>{signReadiness?.message || "Consultando disponibilidad en Odoo staging…"}</p>
              <small>Preparar una plantilla no envía correos ni acredita una firma. Los destinatarios y el envío se administran desde ADN360 cuando estén configurados.</small>
            </div>
            {signReadiness?.template_url ? (
              <a className="btn btn-secondary btn-sm" href={signReadiness.template_url} target="_blank" rel="noopener noreferrer">
                Abrir plantilla en Odoo staging ↗
              </a>
            ) : (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={!signReadiness?.ready || item.review_status !== "APPROVED" || signBusy}
                onClick={() => void prepareContractSignature()}
              >
                {signBusy ? "Preparando…" : "Preparar en Odoo Sign"}
              </button>
            )}
            {item.id && signReadiness?.template_url && (
              <div className="contract-sign-request-panel" aria-label="Seguimiento de firmas en staging">
                <strong>Seguimiento de solicitud de prueba</strong>
                <p>
                  {signRequest?.linked
                    ? `${({
                        PENDING_SIGNATURE: "Esperando ambas firmas",
                        PARTIALLY_SIGNED: "Firma parcial",
                        SIGNED: "Firmada por ambas partes",
                        CANCELLED: "Cancelada",
                        EXPIRED: "Vencida",
                      })[signRequest.status] || signRequest.status}`
                    : "Todavía no se ha enviado para firma. ADN360 creará y vinculará la solicitud automáticamente."}
                </p>
                {canReview && signSendStatus?.enabled &&
                  signSendStatus?.status === "NOT_SENT" && !signRequest?.linked && (
                    <div className="contract-sign-request-controls">
                      <strong>Firmantes de prueba configurados</strong>
                      <p>Empleado y representante legal: ADN360 verificará sus contactos directamente en Odoo staging.</p>
                      <button type="button" className="btn btn-secondary btn-sm" disabled={signSendBusy}
                        onClick={() => void runStagingSignSend("preview")}>
                        {signSendBusy ? "Validando…" : "Validar solicitud antes de enviar"}
                      </button>
                      {signSendPreview && (
                        <>
                          <label>
                            <input type="checkbox" checked={signSendConfirmed}
                              onChange={(event) => setSignSendConfirmed(event.target.checked)} />
                            Confirmo el envío único a contactos ficticios de Odoo staging
                          </label>
                          <button type="button" className="btn btn-primary btn-sm"
                            disabled={!signSendConfirmed || signSendBusy}
                            onClick={() => void runStagingSignSend("send")}>
                            {signSendBusy ? "Enviando…" : "Enviar a Odoo Sign (prueba)"}
                          </button>
                        </>
                      )}
                    </div>
                  )}
                {canReview && ["UNKNOWN", "DISPATCHING"].includes(signSendStatus?.status) && (
                  <div className="contract-sign-request-controls">
                    <p>Resultado de envío incierto: no vuelvas a enviarlo.</p>
                    <button type="button" className="btn btn-secondary btn-sm"
                      disabled={signSendBusy} onClick={() => void runStagingSignSend("reconcile")}>
                      {signSendBusy ? "Verificando…" : "Reconciliar solicitud con Odoo"}
                    </button>
                  </div>
                )}
                {signRequest?.linked && (
                  <div className="contract-sign-participants">
                    <span>Empleado: {signRequest.employee || "Pendiente"}</span>
                    <span>Representante legal: {signRequest.representative || "Pendiente"}</span>
                  </div>
                )}
                {signRequest?.linked && (
                  <button type="button" className="btn btn-secondary btn-sm" disabled={signRequestBusy}
                    onClick={() => void refreshSignRequest()}>
                    {signRequestBusy ? "Consultando…" : "Actualizar estado de firmas"}
                  </button>
                )}
                {canReview && signSendStatus && !signSendStatus.enabled && !signRequest?.linked && (
                  <p>El envío de solicitudes todavía no está habilitado en ADN360. No se necesita ningún ID de Odoo.</p>
                )}
                {signRequest?.status === "SIGNED" && !signedArtifact?.archived && (
                  <button type="button" className="btn btn-primary btn-sm"
                    disabled={signedBusy} onClick={() => void archiveCompletedSignature()}>
                    {signedBusy ? "Archivando…" : "Archivar PDF firmado de Odoo"}
                  </button>
                )}
                {signedArtifact?.archived && (
                  <button type="button" className="btn btn-secondary btn-sm"
                    onClick={() => void downloadSignedContract()}>
                    Descargar contrato firmado
                  </button>
                )}
                <small>Odoo gestiona las firmas. ADN360 asocia internamente la solicitud; no necesitas copiar identificadores.</small>
              </div>
            )}
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
        description="Cada postulante envía sus soportes con su cuenta de Talent. Talento Humano revisa individualmente cada requisito antes de la contratación."
        className="split-header"
      />

      {error && <FeedbackMessage title="No se pudo completar la operación">{error}</FeedbackMessage>}
      {success && <FeedbackMessage title="Expediente actualizado" tone="success">{success}</FeedbackMessage>}

      {canReadAll && (
        <DocumentReviewQueue onSelect={selectEmployee} revision={queueRevision} />
      )}

      {canReadAll && !viewingOwn && welcomeStatus && welcomeStatus.status !== "NOT_REQUESTED" && (
        <section className="panel" aria-label="Notificación de bienvenida">
          <h2>Bienvenida y solicitud de documentos</h2>
          <p>
            {welcomeStatus.status === "SENT"
              ? "Correo enviado al empleado."
              : welcomeStatus.status === "SENDING"
                ? "Envío en proceso."
                : "Correo pendiente o con error de entrega."}
          </p>
          {canReview && ["PENDING", "FAILED"].includes(welcomeStatus.status) && (
            <button className="btn btn-secondary" disabled={welcomeBusy} type="button" onClick={() => void retryWelcome()}>
              {welcomeBusy ? "Enviando…" : "Reintentar correo de bienvenida"}
            </button>
          )}
        </section>
      )}

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
              {selectedEmployeeId !== ownEmployeeId && !employees.some((item) => item.id === selectedEmployeeId) && (
                <option value={selectedEmployeeId}>Postulante seleccionado</option>
              )}
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
              {canReadAll && !viewingOwn && portfolio.employee?.id === selectedEmployeeId && (
                <div className="document-profile-id">
                  <span className="document-profile-id-label">UUID del perfil en ADN360</span>
                  <div className="document-profile-id-actions">
                    <code data-testid="selected-profile-uuid">{portfolio.employee.id}</code>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void copySelectedProfileId()}
                      aria-label="Copiar UUID del perfil"
                    >
                      Copiar ID
                    </button>
                  </div>
                  {idCopyStatus && <span role="status" className="document-profile-id-feedback">{idCopyStatus}</span>}
                </div>
              )}
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
