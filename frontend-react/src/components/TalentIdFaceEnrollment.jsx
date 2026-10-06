// eslint-disable-next-line no-unused-vars
import React from "react";
import { useEffect, useMemo, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import { FeedbackMessage, LoadingState } from "./ui/StatePanel";
import TalentIdAttendanceFields from "./TalentIdAttendanceFields";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_BATCH_FILES = 5;
const ALLOWED_IMAGE_TYPES = new Set(["image/jpeg", "image/png"]);

function employeeName(employee) {
  return [employee?.first_name, employee?.last_name].filter(Boolean).join(" ")
    || "Sin nombre";
}

function employeeOptionLabel(employee) {
  const name = employeeName(employee);
  const identity = employee?.email || employee?.username || "";
  const role = employee?.job_title || "";
  return [name, identity, role].filter(Boolean).join(" · ");
}

function employeeInitials(employee) {
  const first = employee?.first_name?.trim()?.[0] || "";
  const last = employee?.last_name?.trim()?.[0] || "";
  return `${first}${last}`.toUpperCase() || employee?.email?.[0]?.toUpperCase() || "?";
}

function TalentIdFaceEnrollment({
  employees = [],
  sites = [],
  schedules = [],
  onEmployeeUpdated,
}) {
  const [employeeId, setEmployeeId] = useState("");
  const [attendance, setAttendance] = useState(null);
  const [biometric, setBiometric] = useState(null);
  const [files, setFiles] = useState([]);
  const [consent, setConsent] = useState({
    status: "PENDING",
    signed_at: null,
    document_version: null,
    has_signed_document: false,
  });
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [savingAttendance, setSavingAttendance] = useState(false);
  const [purgingBiometric, setPurgingBiometric] = useState(false);
  const [nameForm, setNameForm] = useState({ first_name: "", last_name: "" });

  const activeEmployees = useMemo(
    () => employees
      .filter((employee) => employee.status !== "DISABLED")
      .slice()
      .sort((a, b) => employeeOptionLabel(a).localeCompare(employeeOptionLabel(b), "es", { sensitivity: "base" })),
    [employees],
  );

  const selectedEmployee = useMemo(
    () => activeEmployees.find((employee) => employee.id === employeeId) || null,
    [activeEmployees, employeeId],
  );

  useEffect(() => {
    if (!employeeId) return undefined;

    let cancelled = false;

    Promise.all([
      api.get(`/talent-id/employees/${employeeId}/attendance`),
      api.get(`/talent-id/employees/${employeeId}/biometrics`),
      api.get(`/talent-id/employees/${employeeId}/consent`)
        .catch(() => ({ data: { status: "PENDING" } })),
    ])
      .then(([attendanceResponse, biometricResponse, consentResponse]) => {
        if (cancelled) return;
        const currentAttendance = attendanceResponse.data || {};
        const activeSites = sites.filter((item) => item.active !== false);
        const activeSchedules = schedules.filter((item) => item.active !== false);
        setAttendance({
          configured: Boolean(currentAttendance.configured),
          site_id: currentAttendance.site_id
            || (activeSites.length === 1 ? activeSites[0].id : ""),
          schedule_id: currentAttendance.schedule_id
            || (activeSchedules.length === 1 ? activeSchedules[0].id : ""),
          attendance_eligible: Boolean(currentAttendance.attendance_eligible),
        });
        setBiometric(biometricResponse.data || {});
        setConsent({
          status: consentResponse.data?.status || "PENDING",
          signed_at: consentResponse.data?.signed_at || null,
          document_version: consentResponse.data?.document_version || null,
          has_signed_document: Boolean(consentResponse.data?.has_signed_document),
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setError(getApiErrorMessage(err, {
          action: "cargar el estado biométrico del empleado",
          resource: "Talent ID",
          fallback: "No se pudo consultar la configuración de asistencia y reconocimiento.",
        }));
      })
      .finally(() => {
        if (!cancelled) setLoadingStatus(false);
      });

    return () => {
      cancelled = true;
    };
  }, [employeeId, schedules, sites]);

  function changeEmployee(event) {
    const nextEmployeeId = event.target.value;
    const nextEmployee = activeEmployees.find((employee) => employee.id === nextEmployeeId);
    setEmployeeId(nextEmployeeId);
    setNameForm({
      first_name: nextEmployee?.first_name || "",
      last_name: nextEmployee?.last_name || "",
    });
    setAttendance(null);
    setBiometric(null);
    setFiles([]);
    setError("");
    setSuccess("");
    setLoadingStatus(Boolean(nextEmployeeId));
  }

  async function saveEmployeeName(event) {
    event.preventDefault();
    if (!employeeId) return;

    const firstName = nameForm.first_name.trim();
    const lastName = nameForm.last_name.trim();
    if (!firstName || !lastName) {
      setError("Ingresa nombre y apellido para identificar al empleado.");
      return;
    }

    setSavingName(true);
    setError("");
    setSuccess("");
    try {
      await api.put(`/employees/${employeeId}`, {
        first_name: firstName,
        last_name: lastName,
      });
      await onEmployeeUpdated?.();
      setSuccess("Nombre del empleado actualizado.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "actualizar el nombre del empleado",
        resource: "empleados",
        fallback: "No se pudo guardar el nombre del empleado.",
      }));
    } finally {
      setSavingName(false);
    }
  }

  async function saveAttendance() {
    if (!employeeId || !attendance) return;
    if (!attendance.site_id || !attendance.schedule_id) {
      setError("Selecciona una sede y un horario antes de guardar la asistencia.");
      return;
    }

    setSavingAttendance(true);
    setError("");
    setSuccess("");
    try {
      const { data } = await api.put(
        `/talent-id/employees/${employeeId}/attendance`,
        {
          site_id: attendance.site_id,
          schedule_id: attendance.schedule_id,
          attendance_eligible: Boolean(attendance.attendance_eligible),
        },
      );
      setAttendance({
        configured: true,
        site_id: data?.site_id || attendance.site_id,
        schedule_id: data?.schedule_id || attendance.schedule_id,
        attendance_eligible: Boolean(data?.attendance_eligible),
      });
      setSuccess(
        data?.attendance_eligible
          ? (consent.status === "AUTHORIZED"
            ? "Asistencia habilitada. Ya puedes registrar las fotos del empleado."
            : "Asistencia habilitada. El enrolamiento seguirá bloqueado hasta que el empleado autorice la biometría.")
          : "Asistencia guardada como deshabilitada.",
      );
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "guardar la configuración de asistencia",
        resource: "Talent ID",
        fallback: "No se pudo guardar la sede, el horario o el estado de asistencia.",
      }));
    } finally {
      setSavingAttendance(false);
    }
  }

  function selectFiles(event) {
    const selectedFiles = Array.from(event.target.files || []);
    setError("");
    setSuccess("");

    if (selectedFiles.length > MAX_BATCH_FILES) {
      setFiles([]);
      event.target.value = "";
      setError(`Selecciona máximo ${MAX_BATCH_FILES} fotos por carga.`);
      return;
    }

    const invalidType = selectedFiles.find((file) => !ALLOWED_IMAGE_TYPES.has(file.type));
    if (invalidType) {
      setFiles([]);
      event.target.value = "";
      setError("Todas las fotografías deben ser JPEG o PNG.");
      return;
    }

    const oversized = selectedFiles.find((file) => file.size > MAX_IMAGE_BYTES);
    if (oversized) {
      setFiles([]);
      event.target.value = "";
      setError(`La fotografía ${oversized.name} supera el límite de 5 MB.`);
      return;
    }

    setFiles(selectedFiles);
  }

  async function refreshBiometricStatus() {
    if (!employeeId) return;
    const { data } = await api.get(`/talent-id/employees/${employeeId}/biometrics`);
    setBiometric(data || {});
  }


  async function downloadConsentDocument() {
    if (!employeeId) return;
    setError("");
    try {
      const response = await api.get(
        `/talent-id/employees/${employeeId}/consent/document`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `Talent_ID_${employeeId}_consentimiento.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "descargar la autorización biométrica",
        resource: "Talent ID",
        fallback: "No fue posible descargar el comprobante de autorización.",
      }));
    }
  }


  async function retryBiometricPurge() {
    if (!employeeId) return;
    setPurgingBiometric(true);
    setError("");
    setSuccess("");
    try {
      const { data } = await api.post(
        `/talent-id/employees/${employeeId}/biometrics/purge-provider`,
      );
      setBiometric((current) => ({
        ...(current || {}),
        provider_cleanup_pending: Boolean(data?.provider_cleanup_pending),
        provider_cleanup_last_error: data?.provider_cleanup_last_error || null,
        provider_cleanup_attempted_at: data?.provider_cleanup_attempted_at || null,
      }));
      setSuccess("La eliminación de los datos biométricos en el proveedor fue confirmada.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "reintentar la eliminación biométrica",
        resource: "Talent ID",
        fallback: "La eliminación en el proveedor sigue pendiente.",
      }));
    } finally {
      setPurgingBiometric(false);
    }
  }

  async function uploadPhotos(event) {
    event.preventDefault();

    if (!attendance?.configured || !attendance?.attendance_eligible) {
      setError("Este empleado debe tener asistencia habilitada antes de registrar sus fotos.");
      return;
    }
    if (files.length === 0) {
      setError("Selecciona al menos una fotografía del empleado.");
      return;
    }
    if (consent.status !== "AUTHORIZED") {
      setError("El empleado debe aceptar la autorización biométrica desde Mi perfil antes de registrar fotos.");
      return;
    }

    setUploading(true);
    setError("");
    setSuccess("");

    let uploadedCount = 0;
    try {
      for (let index = 0; index < files.length; index += 1) {
        setUploadProgress(`Procesando foto ${index + 1} de ${files.length}…`);
        const formData = new FormData();
        formData.append("image", files[index]);
        const { data } = await api.post(
          `/talent-id/employees/${employeeId}/biometrics/enroll`,
          formData,
        );
        uploadedCount += 1;
        setBiometric(data || {});
      }

      setFiles([]);
      setSuccess(
        uploadedCount === 1
          ? "Foto registrada para reconocimiento facial."
          : `${uploadedCount} fotos registradas para reconocimiento facial.`,
      );
      await refreshBiometricStatus();
    } catch (err) {
      const providerMessage = getApiErrorMessage(err, {
        action: "registrar las fotos para reconocimiento facial",
        resource: "Talent ID",
        fallback: "No se pudieron registrar todas las fotos. Usa imágenes claras, frontales y con una sola persona.",
      });
      const remainingFiles = files.slice(uploadedCount);
      setFiles(remainingFiles);
      setError(
        uploadedCount > 0
          ? `Se registraron ${uploadedCount} de ${files.length} fotos. ${providerMessage} Las fotos pendientes quedaron seleccionadas para reintentar.`
          : providerMessage,
      );
      try {
        await refreshBiometricStatus();
      } catch {
        // Keep the upload error as the primary feedback.
      }
    } finally {
      setUploading(false);
      setUploadProgress("");
    }
  }

  const attendanceReady = Boolean(attendance?.configured && attendance?.attendance_eligible);
  const biometricAuthorized = consent.status === "AUTHORIZED";
  const biometricReady = attendanceReady && biometricAuthorized;
  const faceCount = Number(biometric?.face_count || 0);

  return (
    <section className="panel talent-id-admin-card talent-id-biometric-card">
      <div className="talent-id-biometric-heading">
        <div>
          <span className="eyebrow">3 · Biometría</span>
          <h2>Fotos para reconocimiento facial</h2>
          <p className="muted">
            Selecciona un empleado y registra varias referencias faciales para mejorar el reconocimiento en los kioscos.
          </p>
        </div>
        <span className="talent-id-device-count">
          {selectedEmployee ? `${faceCount} rostros` : `${activeEmployees.length} empleados`}
        </span>
      </div>

      <div className="talent-id-biometric-body">
        <div className="form-group talent-id-employee-select">
          <label htmlFor="talent-id-biometric-employee">Empleado</label>
          <select
            id="talent-id-biometric-employee"
            value={employeeId}
            onChange={changeEmployee}
            disabled={activeEmployees.length === 0}
          >
            <option value="">Selecciona un empleado</option>
            {activeEmployees.map((employee) => (
              <option key={employee.id} value={employee.id}>
                {employeeOptionLabel(employee)}
              </option>
            ))}
          </select>
          <small>Solo se muestran empleados activos. Recomendamos 2–3 fotos claras por persona.</small>
        </div>

        {error && <FeedbackMessage title="No se pudo completar el enrolamiento">{error}</FeedbackMessage>}
        {success && <div className="talent-id-success" role="status">{success}</div>}

        {!selectedEmployee ? (
          <div className="talent-id-biometric-empty">
            <strong>Selecciona un empleado para comenzar</strong>
            <span>Verás su estado de asistencia y las referencias faciales ya registradas.</span>
          </div>
        ) : loadingStatus ? (
          <LoadingState label="Consultando biometría…" compact />
        ) : (
          <div className="talent-id-biometric-workspace">
            {(!selectedEmployee.first_name?.trim() || !selectedEmployee.last_name?.trim()) && (
              <form className="talent-id-name-completion" onSubmit={saveEmployeeName}>
                <div>
                  <span className="eyebrow">Identificación</span>
                  <h3>Completar nombre del empleado</h3>
                  <p>Este perfil fue creado sin nombre. Agrégalo aquí para que Talent ID deje de mostrar solo el correo.</p>
                </div>
                <div className="talent-id-name-grid">
                  <div className="form-group">
                    <label htmlFor="talent-id-employee-first-name">Nombre</label>
                    <input
                      id="talent-id-employee-first-name"
                      value={nameForm.first_name}
                      onChange={(event) => setNameForm({ ...nameForm, first_name: event.target.value })}
                      placeholder="Ej. Natalí"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="talent-id-employee-last-name">Apellido</label>
                    <input
                      id="talent-id-employee-last-name"
                      value={nameForm.last_name}
                      onChange={(event) => setNameForm({ ...nameForm, last_name: event.target.value })}
                      placeholder="Ej. Garzón"
                      required
                    />
                  </div>
                </div>
                <button className="btn btn-secondary" type="submit" disabled={savingName}>
                  {savingName ? "Guardando…" : "Guardar nombre"}
                </button>
              </form>
            )}

            <div className="talent-id-selected-employee">
              <span className="talent-id-employee-avatar" aria-hidden="true">
                {employeeInitials(selectedEmployee)}
              </span>
              <div>
                <strong>{employeeName(selectedEmployee)}</strong>
                <small>
                  {selectedEmployee.job_title || "Sin cargo"}
                  {selectedEmployee.department ? ` · ${selectedEmployee.department}` : ""}
                </small>
              </div>
              <div className="talent-id-biometric-statuses">
                <span className={`status-pill ${attendanceReady ? "" : "status-disabled"}`}>
                  <i /> {attendanceReady ? "Asistencia habilitada" : "Asistencia pendiente"}
                </span>
                <span className={`status-pill ${faceCount > 0 ? "" : "status-disabled"}`}>
                  <i /> {faceCount > 0 ? `${faceCount} rostro${faceCount === 1 ? "" : "s"}` : "Sin fotos"}
                </span>
              </div>
            </div>

            <TalentIdAttendanceFields
              attendance={attendance || {
                configured: false,
                site_id: "",
                schedule_id: "",
                attendance_eligible: false,
              }}
              sites={sites}
              schedules={schedules}
              onChange={setAttendance}
              disabled={savingAttendance}
            />
            <div className="talent-id-attendance-save-row">
              <span>
                {attendanceReady
                  ? (biometricAuthorized
                    ? "Asistencia habilitada y autorización biométrica vigente."
                    : "Asistencia habilitada. Falta la autorización biométrica del empleado para enrolar el rostro.")
                  : "Configura sede, horario y habilita la asistencia para continuar."}
              </span>
              <button
                className="btn btn-secondary"
                type="button"
                onClick={saveAttendance}
                disabled={savingAttendance || !attendance?.site_id || !attendance?.schedule_id}
              >
                {savingAttendance ? "Guardando…" : "Guardar asistencia"}
              </button>
            </div>

            <form className="talent-id-photo-form" onSubmit={uploadPhotos}>
              <div className={`talent-id-photo-dropzone ${attendanceReady ? "" : "is-disabled"}`}>
                <div>
                  <strong>Agregar fotografías</strong>
                  <span>JPEG o PNG · máximo 5 MB por imagen · hasta 5 fotos por carga.</span>
                </div>
                <label className="btn btn-secondary" htmlFor="talent-id-employee-photos">
                  Seleccionar fotos
                </label>
                <input
                  id="talent-id-employee-photos"
                  className="talent-id-photo-input"
                  type="file"
                  accept="image/jpeg,image/png"
                  multiple
                  onChange={selectFiles}
                  disabled={!biometricReady || uploading}
                  aria-label="Fotos del empleado"
                />
              </div>

              {files.length > 0 && (
                <div className="talent-id-photo-selection" aria-label="Fotos seleccionadas">
                  {files.map((file) => (
                    <div key={`${file.name}-${file.size}-${file.lastModified}`}>
                      <span aria-hidden="true">IMG</span>
                      <div>
                        <strong>{file.name}</strong>
                        <small>{Math.max(1, Math.round(file.size / 1024))} KB · lista para registrar</small>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="talent-id-biometric-consent talent-id-biometric-consent-status">
                <div>
                  <strong>
                    Autorización biométrica: {
                      consent.status === "AUTHORIZED"
                        ? "Autorizada"
                        : consent.status === "DENIED"
                          ? "No autorizada"
                          : consent.status === "REVOKED"
                            ? "Revocada"
                            : "Pendiente"
                    }
                  </strong>
                  <span>
                    La decisión debe aceptarla expresamente el empleado desde Mi perfil. Talento Humano no puede autorizar en su nombre.
                    {consent.signed_at
                      ? ` Última decisión: ${new Date(consent.signed_at).toLocaleString("es-CO")}.`
                      : ""}
                  </span>
                </div>
                {consent.has_signed_document && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={downloadConsentDocument}
                  >
                    Descargar autorización
                  </button>
                )}
              </div>

              {!biometricAuthorized && (
                <div className="talent-id-biometric-blocker">
                  El enrolamiento facial está bloqueado hasta que el empleado acepte una autorización biométrica vigente.
                </div>
              )}

              {biometric?.provider_cleanup_pending && (
                <div className="talent-id-biometric-blocker">
                  <strong>Eliminación biométrica pendiente en el proveedor</strong>
                  <span>
                    Talent ya bloqueó el reconocimiento. Reintenta la eliminación externa para cerrar la revocación técnica.
                  </span>
                  {biometric.provider_cleanup_last_error && (
                    <small>{biometric.provider_cleanup_last_error}</small>
                  )}
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={purgingBiometric}
                    onClick={retryBiometricPurge}
                  >
                    {purgingBiometric ? "Reintentando…" : "Reintentar eliminación"}
                  </button>
                </div>
              )}

              <div className="talent-id-biometric-actions">
                <div>
                  <strong>{faceCount >= 2 ? "Referencias suficientes para el piloto" : "Agrega 2–3 referencias para el piloto"}</strong>
                  <small>Las fotos originales no quedan disponibles en Talent después del enrolamiento.</small>
                </div>
                <button
                  className="btn btn-primary"
                  type="submit"
                  disabled={!biometricReady || uploading || files.length === 0}
                >
                  {uploading ? (uploadProgress || "Procesando…") : "Agregar fotos"}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </section>
  );
}

export default TalentIdFaceEnrollment;
