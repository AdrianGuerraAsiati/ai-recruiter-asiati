// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useState } from "react";

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
  const [saving, setSaving] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [showDocument, setShowDocument] = useState(false);
  const [confirmRevocation, setConfirmRevocation] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/talent-id/consent");
      setState(data);
      setAccepted(false);
      setConfirmRevocation(false);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar la autorización biométrica",
        resource: "Talent ID",
        fallback: "No fue posible cargar tu decisión de tratamiento biométrico.",
      }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [load]);

  const status = state?.status || "PENDING";
  const statusCopy = STATUS_COPY[status] || STATUS_COPY.PENDING;
  const documentVersion = state?.document?.version || state?.document_version;
  const authorized = status === "AUTHORIZED";

  async function acceptBiometrics() {
    if (!accepted) {
      setError("Marca la casilla de autorización para continuar.");
      return;
    }

    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/talent-id/consent/accept", {
        document_version: documentVersion,
        confirmed: true,
      });
      setSuccess("Autorización biométrica registrada.");
      await load();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "registrar tu autorización biométrica",
        resource: "Talent ID",
        fallback: "No fue posible registrar la autorización.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function revokeBiometrics() {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/talent-id/consent/revoke", {
        document_version: documentVersion,
        confirmed: true,
      });
      setSuccess("Autorización revocada. El reconocimiento facial quedó deshabilitado.");
      setShowDocument(false);
      await load();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "revocar tu autorización biométrica",
        resource: "Talent ID",
        fallback: "No fue posible revocar la autorización.",
      }));
    } finally {
      setSaving(false);
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
        action: "descargar el comprobante de autorización",
        resource: "Talent ID",
        fallback: "No fue posible descargar el comprobante.",
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
          <p>
            La biometría es voluntaria. Si no la autorizas, puedes utilizar QR móvil para registrar asistencia.
          </p>
        </div>
        <span className={`biometric-consent-status is-${statusCopy.tone}`}>
          {statusCopy.label}
        </span>
      </div>

      {error && <FeedbackMessage title="No se pudo completar la operación">{error}</FeedbackMessage>}
      {success && <div className="talent-id-success" role="status">{success}</div>}

      {!authorized ? (
        <div className="biometric-consent-checkbox-flow">
          <label className="biometric-consent-check">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(event) => {
                setAccepted(event.target.checked);
                setError("");
              }}
            />
            <span>
              <strong>
                Autorizo el tratamiento de mis datos biométricos para reconocimiento facial y registro de asistencia.
              </strong>
              <small>
                Al marcar esta casilla y seleccionar <b>Aceptar y continuar</b>, declaro que leí y acepto la autorización
                para el tratamiento de datos biométricos. Esta autorización es voluntaria y puedo usar QR móvil como alternativa.
              </small>
            </span>
          </label>

          <button
            className="biometric-consent-document-link"
            type="button"
            onClick={() => setShowDocument((current) => !current)}
          >
            {showDocument ? "Ocultar autorización completa" : "Ver autorización completa"}
          </button>

          {showDocument && (
            <div className="biometric-consent-document" tabIndex="0">
              <div className="biometric-consent-document-meta">
                <strong>{state?.document?.title}</strong>
                <span>Versión {documentVersion}</span>
              </div>
              {String(state?.document?.text || "").split("\n\n").map((paragraph) => (
                <p key={paragraph.slice(0, 40)}>{paragraph}</p>
              ))}
            </div>
          )}

          <button
            type="button"
            className="btn btn-primary biometric-consent-accept"
            disabled={!accepted || saving}
            onClick={acceptBiometrics}
          >
            {saving ? "Registrando…" : "Aceptar y continuar"}
          </button>
        </div>
      ) : (
        <div className="biometric-consent-accepted">
          <div className="biometric-consent-accepted-summary">
            <span className="biometric-consent-accepted-icon" aria-hidden="true">✓</span>
            <div>
              <strong>Autorización biométrica registrada</strong>
              <small>
                {formatDateTime(state?.signed_at)}
                {state?.document_version ? ` · Versión ${state.document_version}` : ""}
              </small>
            </div>
          </div>

          <div className="biometric-consent-actions">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setShowDocument((current) => !current)}
            >
              {showDocument ? "Ocultar autorización" : "Ver autorización"}
            </button>
            {state?.has_signed_document && (
              <button type="button" className="btn btn-ghost" onClick={downloadReceipt}>
                Descargar comprobante
              </button>
            )}
            {!confirmRevocation ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setConfirmRevocation(true)}
              >
                Revocar autorización
              </button>
            ) : null}
          </div>

          {showDocument && (
            <div className="biometric-consent-document" tabIndex="0">
              <div className="biometric-consent-document-meta">
                <strong>{state?.document?.title}</strong>
                <span>Versión {documentVersion}</span>
              </div>
              {String(state?.document?.text || "").split("\n\n").map((paragraph) => (
                <p key={paragraph.slice(0, 40)}>{paragraph}</p>
              ))}
            </div>
          )}

          {confirmRevocation && (
            <div className="biometric-consent-revoke-confirm">
              <p>
                Al confirmar, Talent ID dejará de usar reconocimiento facial y conservará el registro de esta revocación.
                Podrás seguir marcando mediante QR móvil.
              </p>
              <div className="biometric-consent-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={saving}
                  onClick={revokeBiometrics}
                >
                  {saving ? "Revocando…" : "Confirmar revocación"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={saving}
                  onClick={() => setConfirmRevocation(false)}
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default BiometricConsentCard;
