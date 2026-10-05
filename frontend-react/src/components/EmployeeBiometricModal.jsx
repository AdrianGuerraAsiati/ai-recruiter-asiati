// eslint-disable-next-line no-unused-vars
import React from "react";
import { useEffect, useMemo, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import { FeedbackMessage, LoadingState } from "./ui/StatePanel";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(["image/jpeg", "image/png"]);

function employeeName(employee) {
  return [employee?.first_name, employee?.last_name].filter(Boolean).join(" ")
    || employee?.email
    || "Empleado";
}

function formatEnrollmentDate(value) {
  if (!value) return "Sin enrolamiento";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Enrolado";
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function EmployeeBiometricModal({ employee, open, onClose }) {
  const [loading, setLoading] = useState(true);
  const [savingAttendance, setSavingAttendance] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [sites, setSites] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [attendance, setAttendance] = useState({
    configured: false,
    site_id: "",
    schedule_id: "",
    attendance_eligible: false,
  });
  const [biometric, setBiometric] = useState({
    enrolled: false,
    face_count: 0,
    active: false,
    enrolled_at: null,
    provider_cleanup_pending: false,
    provider_cleanup_last_error: null,
    provider_cleanup_attempted_at: null,
  });
  const [purgingBiometric, setPurgingBiometric] = useState(false);
  const [image, setImage] = useState(null);
  const [consent, setConsent] = useState({
    status: "PENDING",
    signed_at: null,
    document_version: null,
    has_signed_document: false,
  });
  const [mobileDevices, setMobileDevices] = useState([]);
  const [revokingMobile, setRevokingMobile] = useState("");

  const activeSites = useMemo(
    () => sites.filter((item) => item.active !== false),
    [sites],
  );
  const activeSchedules = useMemo(
    () => schedules.filter((item) => item.active !== false),
    [schedules],
  );

  useEffect(() => {
    if (!open || !employee?.id) return undefined;

    let cancelled = false;

    Promise.all([
      api.get("/talent-id/sites"),
      api.get("/talent-id/schedules"),
      api.get(`/talent-id/employees/${employee.id}/attendance`),
      api.get(`/talent-id/employees/${employee.id}/biometrics`),
      api.get(`/talent-id/employees/${employee.id}/consent`),
      api.get(`/talent-id/employees/${employee.id}/mobile-devices`),
    ])
      .then(([sitesResponse, schedulesResponse, attendanceResponse, biometricResponse, consentResponse, mobileDevicesResponse]) => {
        if (cancelled) return;

        const nextSites = sitesResponse.data?.items || [];
        const nextSchedules = schedulesResponse.data?.items || [];
        const nextAttendance = attendanceResponse.data || {};

        setSites(nextSites);
        setSchedules(nextSchedules);
        setAttendance({
          configured: Boolean(nextAttendance.configured),
          site_id:
            nextAttendance.site_id
            || (nextSites.filter((item) => item.active !== false).length === 1
              ? nextSites.find((item) => item.active !== false)?.id
              : "")
            || "",
          schedule_id:
            nextAttendance.schedule_id
            || (nextSchedules.filter((item) => item.active !== false).length === 1
              ? nextSchedules.find((item) => item.active !== false)?.id
              : "")
            || "",
          attendance_eligible: Boolean(nextAttendance.attendance_eligible),
        });
        setBiometric({
          enrolled: Boolean(biometricResponse.data?.enrolled),
          face_count: Number(biometricResponse.data?.face_count || 0),
          active: Boolean(biometricResponse.data?.active),
          enrolled_at: biometricResponse.data?.enrolled_at || null,
          provider_cleanup_pending: Boolean(biometricResponse.data?.provider_cleanup_pending),
          provider_cleanup_last_error: biometricResponse.data?.provider_cleanup_last_error || null,
          provider_cleanup_attempted_at: biometricResponse.data?.provider_cleanup_attempted_at || null,
        });
        setConsent({
          status: consentResponse.data?.status || "PENDING",
          signed_at: consentResponse.data?.signed_at || null,
          document_version: consentResponse.data?.document_version || null,
          has_signed_document: Boolean(consentResponse.data?.has_signed_document),
        });
        setMobileDevices(mobileDevicesResponse.data?.items || []);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(getApiErrorMessage(err, {
          action: "cargar la configuración biométrica",
          resource: "Talent ID",
          fallback: "No pudimos cargar sedes, horario o estado biométrico. Cierra el panel y vuelve a intentarlo.",
        }));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [employee?.id, open]);

  if (!open || !employee) return null;

  async function saveAttendance(event) {
    event.preventDefault();
    if (!attendance.site_id || !attendance.schedule_id) {
      setError("Selecciona una sede y un horario antes de habilitar la asistencia.");
      return;
    }

    setSavingAttendance(true);
    setError("");
    setSuccess("");
    try {
      const { data } = await api.put(
        `/talent-id/employees/${employee.id}/attendance`,
        {
          site_id: attendance.site_id,
          schedule_id: attendance.schedule_id,
          attendance_eligible: attendance.attendance_eligible,
        },
      );
      setAttendance((current) => ({
        ...current,
        configured: true,
        attendance_eligible: Boolean(data?.attendance_eligible),
      }));
      setSuccess("Configuración de asistencia guardada.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "guardar la configuración de asistencia",
        resource: "Talent ID",
        fallback: "No se pudo guardar la sede y el horario del empleado.",
      }));
    } finally {
      setSavingAttendance(false);
    }
  }



  async function downloadConsentDocument() {
    setError("");
    setSuccess("");
    try {
      const response = await api.get(
        `/talent-id/employees/${employee.id}/consent/document`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `Talent_ID_${employee.id}_consentimiento.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "descargar la autorización biométrica",
        resource: "Talent ID",
        fallback: "No se pudo descargar el documento firmado del empleado.",
      }));
    }
  }


  async function retryBiometricPurge() {
    setPurgingBiometric(true);
    setError("");
    setSuccess("");
    try {
      const { data } = await api.post(
        `/talent-id/employees/${employee.id}/biometrics/purge-provider`,
      );
      setBiometric((current) => ({
        ...current,
        provider_cleanup_pending: Boolean(data?.provider_cleanup_pending),
        provider_cleanup_last_error: data?.provider_cleanup_last_error || null,
        provider_cleanup_attempted_at: data?.provider_cleanup_attempted_at || null,
      }));
      setSuccess("La eliminación de los datos biométricos en el proveedor fue confirmada.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "eliminar los datos biométricos del proveedor",
        resource: "Talent ID",
        fallback: "La eliminación sigue pendiente. Intenta nuevamente más tarde.",
      }));
    } finally {
      setPurgingBiometric(false);
    }
  }

  async function revokeMobileDevice(deviceId) {
    setRevokingMobile(deviceId);
    setError("");
    setSuccess("");
    try {
      await api.delete(
        `/talent-id/employees/${employee.id}/mobile-devices/${deviceId}`,
      );
      setMobileDevices((current) => current.map((item) => (
        item.id === deviceId ? { ...item, active: false } : item
      )));
      setSuccess("Celular revocado. El empleado deberá verificar un nuevo dispositivo con OTP para volver a usar QR.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "revocar el celular vinculado",
        resource: "Talent ID",
        fallback: "No se pudo revocar el dispositivo móvil.",
      }));
    } finally {
      setRevokingMobile("");
    }
  }

  function selectImage(event) {
    const file = event.target.files?.[0] || null;
    setError("");
    setSuccess("");

    if (!file) {
      setImage(null);
      return;
    }
    if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
      setImage(null);
      setError("La fotografía debe ser JPEG o PNG.");
      event.target.value = "";
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setImage(null);
      setError("La fotografía supera el límite de 5 MB.");
      event.target.value = "";
      return;
    }
    setImage(file);
  }

  async function enrollBiometric(event) {
    event.preventDefault();

    if (!attendance.configured || !attendance.attendance_eligible) {
      setError("Primero guarda la asistencia del empleado como habilitada.");
      return;
    }
    if (!image) {
      setError("Selecciona o captura una fotografía del empleado.");
      return;
    }
    if (consent.status !== "AUTHORIZED") {
      setError("El empleado debe firmar la autorización biométrica desde su perfil antes del enrolamiento.");
      return;
    }

    setUploading(true);
    setError("");
    setSuccess("");

    const formData = new FormData();
    formData.append("image", image);

    try {
      const { data } = await api.post(
        `/talent-id/employees/${employee.id}/biometrics/enroll`,
        formData,
      );
      setBiometric({
        enrolled: true,
        face_count: Number(data?.face_count || 0),
        active: Boolean(data?.active),
        enrolled_at: data?.enrolled_at || new Date().toISOString(),
        provider_cleanup_pending: false,
        provider_cleanup_last_error: null,
        provider_cleanup_attempted_at: null,
      });
      setImage(null);
      setSuccess(
        Number(data?.face_count || 0) >= 2
          ? "Rostro agregado. Ya hay múltiples referencias para iniciar la prueba en kiosco."
          : "Primer rostro enrolado. Agrega 1–2 fotografías adicionales antes de la prueba.",
      );
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "enrolar la biometría facial",
        resource: "Talent ID",
        fallback: "No se pudo enrolar el rostro. Usa una foto frontal, bien iluminada y con una sola persona visible.",
      }));
    } finally {
      setUploading(false);
    }
  }

  const biometricReady =
    consent.status === "AUTHORIZED"
    && biometric.active
    && biometric.face_count >= 2;
  const qrReady = mobileDevices.some((item) => item.active);
  const readyForKiosk =
    attendance.configured
    && attendance.attendance_eligible
    && (biometricReady || qrReady);

  return (
    <div className="modal-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="modal employee-biometric-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="employee-biometric-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">Talent ID · Piloto</span>
            <h2 id="employee-biometric-title">Biometría y asistencia</h2>
            <p>{employeeName(employee)}</p>
          </div>
          <button className="btn-close" type="button" aria-label="Cerrar Talent ID" onClick={onClose}>×</button>
        </div>

        {loading ? (
          <LoadingState label="Cargando Talent ID…" compact />
        ) : (
          <>
            {error && <FeedbackMessage title="No se pudo completar la operación">{error}</FeedbackMessage>}
            {success && <div className="talent-id-success" role="status">{success}</div>}

            <div className="talent-id-readiness">
              <div>
                <span>Estado para prueba</span>
                <strong>{readyForKiosk ? "Listo para kiosco" : "Configuración pendiente"}</strong>
              </div>
              <div>
                <span>Rostros enrolados</span>
                <strong>{biometric.face_count}</strong>
              </div>
              <div>
                <span>Biometría</span>
                <strong>{biometricReady ? "Lista" : "No disponible"}</strong>
              </div>
              <div>
                <span>QR móvil</span>
                <strong>{qrReady ? "Listo" : "No vinculado"}</strong>
              </div>
            </div>

            <form className="talent-id-section" onSubmit={saveAttendance}>
              <div className="talent-id-section-heading">
                <div>
                  <span className="eyebrow">Paso 1</span>
                  <h3>Configurar asistencia</h3>
                </div>
                <span className={`status-pill ${attendance.configured ? "" : "status-disabled"}`}>
                  <i /> {attendance.configured ? "Configurada" : "Pendiente"}
                </span>
              </div>

              {activeSites.length === 0 || activeSchedules.length === 0 ? (
                <div className="talent-id-blocker">
                  Para continuar debe existir al menos una sede y un horario activos en Talent ID.
                </div>
              ) : (
                <>
                  <div className="employee-form-grid">
                    <div className="form-group">
                      <label htmlFor="talent-id-site">Sede</label>
                      <select
                        id="talent-id-site"
                        value={attendance.site_id}
                        onChange={(event) => setAttendance({ ...attendance, site_id: event.target.value })}
                        required
                      >
                        <option value="">Selecciona sede</option>
                        {activeSites.map((site) => (
                          <option key={site.id} value={site.id}>
                            {site.name}{site.code ? ` · ${site.code}` : ""}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="form-group">
                      <label htmlFor="talent-id-schedule">Horario</label>
                      <select
                        id="talent-id-schedule"
                        value={attendance.schedule_id}
                        onChange={(event) => setAttendance({ ...attendance, schedule_id: event.target.value })}
                        required
                      >
                        <option value="">Selecciona horario</option>
                        {activeSchedules.map((schedule) => (
                          <option key={schedule.id} value={schedule.id}>
                            {schedule.name} · {String(schedule.start_time || "").slice(0, 5)}–{String(schedule.end_time || "").slice(0, 5)}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <label className="talent-id-toggle">
                    <input
                      type="checkbox"
                      checked={attendance.attendance_eligible}
                      onChange={(event) => setAttendance({
                        ...attendance,
                        attendance_eligible: event.target.checked,
                      })}
                    />
                    <span>
                      <strong>Habilitar marcación de asistencia</strong>
                      <small>Solo empleados activos y habilitados pueden ser reconocidos por el kiosco.</small>
                    </span>
                  </label>
                  <button className="btn btn-secondary" type="submit" disabled={savingAttendance}>
                    {savingAttendance ? "Guardando…" : "Guardar asistencia"}
                  </button>
                </>
              )}
            </form>

            <form className="talent-id-section" onSubmit={enrollBiometric}>
              <div className="talent-id-section-heading">
                <div>
                  <span className="eyebrow">Paso 2</span>
                  <h3>Enrolar rostro</h3>
                </div>
                <span className={`status-pill ${biometric.active ? "" : "status-disabled"}`}>
                  <i /> {biometric.active ? `${biometric.face_count} rostro(s)` : "Sin enrolar"}
                </span>
              </div>

              <p className="talent-id-help">
                Recomendación para el piloto: 2–3 fotos frontales, sin otras personas, con iluminación normal y ligeras variaciones de ángulo.
              </p>

              <div className="form-group">
                <label htmlFor="talent-id-image">Fotografía del empleado</label>
                <input
                  id="talent-id-image"
                  type="file"
                  accept="image/jpeg,image/png"
                  capture="user"
                  onChange={selectImage}
                />
                <small>{image ? `${image.name} · ${Math.max(1, Math.round(image.size / 1024))} KB` : "JPEG o PNG · máximo 5 MB"}</small>
              </div>

              <div className="talent-id-consent">
                <span>
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
                  <small>
                    La decisión solo puede firmarla el empleado desde Mi perfil mediante OTP. Un administrador no puede autorizarla en su nombre.
                    {consent.signed_at
                      ? ` Última decisión: ${new Date(consent.signed_at).toLocaleString("es-CO")}.`
                      : ""}
                  </small>
                </span>
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

              {consent.status !== "AUTHORIZED" && (
                <div className="talent-id-biometric-blocker">
                  No es posible enrolar el rostro hasta que exista una autorización biométrica vigente.
                </div>
              )}

              <div className="talent-id-consent">
                <span>
                  <strong>
                    Alternativa no biométrica: {
                      mobileDevices.some((item) => item.active)
                        ? "Celular vinculado"
                        : "Sin celular vinculado"
                    }
                  </strong>
                  <small>
                    El empleado vincula su propio celular desde Mi perfil con OTP. El QR dinámico funciona aunque no autorice reconocimiento facial.
                  </small>
                  {mobileDevices.filter((item) => item.active).map((device) => (
                    <small key={device.id}>
                      {device.label || "Celular vinculado"}
                      {device.last_used_at
                        ? ` · último uso ${new Date(device.last_used_at).toLocaleString("es-CO")}`
                        : " · aún sin marcaciones"}
                    </small>
                  ))}
                </span>
                {mobileDevices.filter((item) => item.active).map((device) => (
                  <button
                    key={device.id}
                    type="button"
                    className="btn btn-secondary"
                    disabled={revokingMobile === device.id}
                    onClick={() => revokeMobileDevice(device.id)}
                  >
                    {revokingMobile === device.id ? "Revocando…" : "Revocar celular"}
                  </button>
                ))}
              </div>

              <div className="talent-id-privacy-note">
                Talent procesa esta imagen para el enrolamiento y no la guarda como archivo original. El estado biométrico conserva identificadores del proveedor y cantidad de rostros.
              </div>

              {biometric.provider_cleanup_pending && (
                <div className="talent-id-biometric-blocker">
                  <strong>Eliminación del proveedor pendiente</strong>
                  <span>
                    El reconocimiento ya está deshabilitado en Talent, pero aún falta confirmar la eliminación de los datos biométricos en el proveedor.
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

              <button
                className="btn btn-primary"
                type="submit"
                disabled={
                  uploading
                  || !attendance.configured
                  || !attendance.attendance_eligible
                  || !image
                  || consent.status !== "AUTHORIZED"
                }
              >
                {uploading ? "Enrolando…" : biometric.enrolled ? "Agregar otra fotografía" : "Enrolar rostro"}
              </button>

              {biometric.enrolled_at && (
                <small className="talent-id-enrolled-at">
                  Último estado de enrolamiento: {formatEnrollmentDate(biometric.enrolled_at)}
                </small>
              )}
            </form>
          </>
        )}
      </section>
    </div>
  );
}

export default EmployeeBiometricModal;
