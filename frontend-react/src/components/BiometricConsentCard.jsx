// eslint-disable-next-line no-unused-vars
import React from "react";
import { useEffect, useMemo, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import { FeedbackMessage, LoadingState } from "./ui/StatePanel";
import "../biometric-consent.css";

const STATUS_COPY = {
  PENDING: { label: "Pendiente", tone: "pending" },
  AUTHORIZED: { label: "Autorizado", tone: "authorized" },
  DENIED: { label: "No autorizado", tone: "denied" },
  REVOKED: { label: "Revocado", tone: "revoked" },
};

function formatDateTime(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function BiometricConsentCard() {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [requesting, setRequesting] = useState(false);
  const [signing, setSigning] = useState(false);
  const [pendingDecision, setPendingDecision] = useState("");
  const [otp, setOtp] = useState("");
  const [otpInfo, setOtpInfo] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/talent-id/consent");
      setState(data);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar la autorización biométrica",
        resource: "Talent ID",
        fallback: "No fue posible cargar tu decisión de tratamiento biométrico.",
      }));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const status = state?.status || "PENDING";
  const statusCopy = STATUS_COPY[status] || STATUS_COPY.PENDING;
  const canAuthorize = status !== "AUTHORIZED";
  const canDeny = status !== "AUTHORIZED" && status !== "DENIED";
  const canRevoke = status === "AUTHORIZED";

  const decisionLabel = useMemo(() => ({
    AUTHORIZED: "Autorizar reconocimiento facial",
    DENIED: "No autorizar biometría",
    REVOKED: "Revocar autorización",
  }[pendingDecision] || ""), [pendingDecision]);

  async function startDecision(decision) {
    setRequesting(true);
    setError("");
    setSuccess("");
    setOtp("");
    try {
      const { data } = await api.post("/talent-id/consent/otp");
      setOtpInfo(data);
      setPendingDecision(decision);
      setSuccess(`Enviamos un código de 6 dígitos a ${data.destination}.`);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "enviar el código de firma",
        resource: "Talent ID",
        fallback: "No fue posible enviar el código de firma electrónica.",
      }));
    } finally {
      setRequesting(false);
    }
  }

  async function confirmDecision(event) {
    event.preventDefault();
    if (!/^\d{6}$/.test(otp)) {
      setError("Ingresa el código de 6 dígitos enviado a tu correo.");
      return;
    }

    const decision = pendingDecision;
    setSigning(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/talent-id/consent/sign", {
        decision,
        otp,
        document_version: state?.document?.version || state?.document_version,
      });
      setPendingDecision("");
      setOtp("");
      setOtpInfo(null);
      setSuccess(
        decision === "AUTHORIZED"
          ? "Autorización firmada. Talento Humano ya puede habilitar tu enrolamiento facial."
          : decision === "REVOKED"
            ? "Revocación firmada. El reconocimiento facial quedó deshabilitado."
            : "Decisión firmada. Seguirás teniendo disponible un mecanismo no biométrico de asistencia.",
      );
      await load();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "firmar tu decisión",
        resource: "Talent ID",
        fallback: "No fue posible validar el código o registrar la firma.",
      }));
    } finally {
      setSigning(false);
    }
  }

  async function downloadReceipt() {
    setError("");
    try {
      const response = await api.get("/talent-id/consent/document", {
        responseType: "blob",
      });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "ASIATI_Autorizacion_Biometrica_Talent_ID.pdf";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "descargar el documento firmado",
        resource: "Talent ID",
        fallback: "No fue posible descargar el documento firmado.",
      }));
    }
  }

  if (loading) {
    return (
      <section className="panel biometric-consent-card">
        <LoadingState label="Cargando autorización biométrica…" compact />
      </section>
    );
  }

  return (
    <section className="panel biometric-consent-card">
      <div className="biometric-consent-heading">
        <div>
          <span className="eyebrow">Talent ID · Privacidad</span>
          <h2>Reconocimiento facial</h2>
          <p>Tu decisión es independiente del uso corporativo de fotografías o videos.</p>
        </div>
        <span className={`biometric-consent-status is-${statusCopy.tone}`}>
          {statusCopy.label}
        </span>
      </div>

      {error && <FeedbackMessage title="No se pudo completar la operación">{error}</FeedbackMessage>}
      {success && <div className="talent-id-success" role="status">{success}</div>}

      <div className="biometric-consent-document" tabIndex="0">
        <div className="biometric-consent-document-meta">
          <strong>{state?.document?.title}</strong>
          <span>Versión {state?.document?.version || state?.document_version}</span>
        </div>
        {String(state?.document?.text || "").split("\n\n").map((paragraph) => (
          <p key={paragraph.slice(0, 40)}>{paragraph}</p>
        ))}
      </div>

      <div className="biometric-consent-note">
        Si no autorizas o revocas la biometría, ASIATI debe mantener disponible una alternativa de marcación no biométrica.
      </div>

      {state?.signed_at && (
        <div className="biometric-consent-evidence">
          <div>
            <span>Última decisión firmada</span>
            <strong>{formatDateTime(state.signed_at)}</strong>
          </div>
          <div>
            <span>Versión</span>
            <strong>{state.document_version}</strong>
          </div>
          <div>
            <span>Integridad</span>
            <strong>{String(state.pdf_sha256 || "").slice(0, 12)}…</strong>
          </div>
        </div>
      )}

      {!pendingDecision ? (
        <div className="biometric-consent-actions">
          {canAuthorize && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={requesting}
              onClick={() => startDecision("AUTHORIZED")}
            >
              {requesting ? "Enviando código…" : "Autorizar biometría"}
            </button>
          )}
          {canDeny && (
            <button
              type="button"
              className="btn btn-secondary"
              disabled={requesting}
              onClick={() => startDecision("DENIED")}
            >
              No autorizar
            </button>
          )}
          {canRevoke && (
            <button
              type="button"
              className="btn btn-secondary"
              disabled={requesting}
              onClick={() => startDecision("REVOKED")}
            >
              Revocar autorización
            </button>
          )}
          {state?.has_signed_document && (
            <button type="button" className="btn btn-ghost" onClick={downloadReceipt}>
              Descargar documento firmado
            </button>
          )}
        </div>
      ) : (
        <form className="biometric-consent-otp" onSubmit={confirmDecision}>
          <div>
            <span className="eyebrow">Firma electrónica</span>
            <h3>{decisionLabel}</h3>
            <p>
              Código enviado a {otpInfo?.destination}. Confirma tu decisión con el OTP de un solo uso.
            </p>
          </div>
          <label htmlFor="talent-id-consent-otp">Código de 6 dígitos</label>
          <input
            id="talent-id-consent-otp"
            value={otp}
            onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))}
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="\d{6}"
            placeholder="000000"
            required
          />
          <div className="biometric-consent-actions">
            <button className="btn btn-primary" type="submit" disabled={signing}>
              {signing ? "Firmando…" : "Confirmar y firmar"}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={signing}
              onClick={() => {
                setPendingDecision("");
                setOtp("");
                setOtpInfo(null);
                setError("");
              }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export default BiometricConsentCard;
