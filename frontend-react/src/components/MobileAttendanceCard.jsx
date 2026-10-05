// eslint-disable-next-line no-unused-vars
import React from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import {
  clearMobileDeviceCredential,
  createMobileDeviceKey,
  loadMobileDeviceCredential,
  mobileDeviceCryptoSupported,
  saveMobileDeviceCredential,
  signMobileDeviceChallenge,
} from "../utils/mobileDeviceCrypto";
import { FeedbackMessage, LoadingState } from "./ui/StatePanel";
import "../mobile-attendance.css";

function defaultDeviceLabel() {
  const platform = String(navigator.userAgentData?.platform || navigator.platform || "").trim();
  return platform ? `Mi celular · ${platform}` : "Mi celular";
}

function secondsRemaining(expiresAt, nowMs) {
  if (!expiresAt) return 0;
  const expiresMs = new Date(expiresAt).getTime();
  if (Number.isNaN(expiresMs)) return 0;
  return Math.max(0, Math.ceil((expiresMs - nowMs) / 1000));
}

function MobileAttendanceCard() {
  const [loading, setLoading] = useState(true);
  const [linking, setLinking] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [devices, setDevices] = useState([]);
  const [localCredential, setLocalCredential] = useState(null);
  const [qr, setQr] = useState(null);
  const [nowMs, setNowMs] = useState(Date.now());
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const refreshTimerRef = useRef(null);

  const activeDevice = useMemo(
    () => devices.find((item) => item.active && item.id === localCredential?.deviceId) || null,
    [devices, localCredential?.deviceId],
  );
  const remaining = secondsRemaining(qr?.expires_at, nowMs);
  const supported = mobileDeviceCryptoSupported();

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [deviceResponse, local] = await Promise.all([
        api.get("/talent-id/mobile-devices"),
        loadMobileDeviceCredential(),
      ]);
      setDevices(deviceResponse.data?.items || []);
      setLocalCredential(local || null);

      if (
        local?.deviceId
        && !(deviceResponse.data?.items || []).some(
          (item) => item.id === local.deviceId && item.active,
        )
      ) {
        await clearMobileDeviceCredential();
        setLocalCredential(null);
      }
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar el dispositivo móvil",
        resource: "Talent ID",
        fallback: "No pudimos cargar la vinculación de este celular.",
      }));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => () => {
    if (refreshTimerRef.current) {
      window.clearTimeout(refreshTimerRef.current);
    }
  }, []);

  async function linkThisDevice() {
    if (!supported) {
      setError("Este navegador no soporta la vinculación criptográfica requerida por Talent ID.");
      return;
    }

    setLinking(true);
    setError("");
    setFeedback("");
    setQr(null);
    try {
      const { publicKeyJwk, privateKey } = await createMobileDeviceKey();
      const label = defaultDeviceLabel();
      const { data } = await api.post("/talent-id/mobile-devices", {
        label,
        public_key_jwk: publicKeyJwk,
      });
      await saveMobileDeviceCredential({
        deviceId: data.id,
        label: data.label,
        privateKey,
      });
      setLocalCredential({
        deviceId: data.id,
        label: data.label,
        privateKey,
      });
      setDevices([data]);
      setFeedback("Este celular quedó vinculado. La llave privada permanece local y no es exportable.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "vincular este celular",
        resource: "Talent ID",
        fallback: "No fue posible vincular este dispositivo.",
      }));
    } finally {
      setLinking(false);
    }
  }

  async function generateQr({ silent = false } = {}) {
    if (!activeDevice || !localCredential?.privateKey) return;

    setGenerating(true);
    if (!silent) {
      setError("");
      setFeedback("");
    }
    try {
      const challengeResponse = await api.post(
        `/talent-id/mobile-devices/${activeDevice.id}/challenge`,
      );
      const challenge = challengeResponse.data;
      const signature = await signMobileDeviceChallenge(
        localCredential.privateKey,
        challenge.message,
      );
      const { data } = await api.post("/talent-id/mobile-qr", {
        device_id: activeDevice.id,
        challenge_id: challenge.challenge_id,
        nonce: challenge.nonce,
        signature,
      });
      setQr(data);
      setNowMs(Date.now());

      if (refreshTimerRef.current) {
        window.clearTimeout(refreshTimerRef.current);
      }
      const refreshInMs = Math.max(8000, (Number(data.ttl_seconds || 30) - 8) * 1000);
      refreshTimerRef.current = window.setTimeout(() => {
        void generateQr({ silent: true });
      }, refreshInMs);
    } catch (err) {
      setQr(null);
      setError(getApiErrorMessage(err, {
        action: "generar el QR dinámico",
        resource: "Talent ID",
        fallback: "No pudimos generar el código. Verifica que este celular siga vinculado.",
      }));
    } finally {
      setGenerating(false);
    }
  }

  async function revokeDevice() {
    if (!activeDevice) return;
    setError("");
    setFeedback("");
    try {
      await api.delete(`/talent-id/mobile-devices/${activeDevice.id}`);
      await clearMobileDeviceCredential();
      if (refreshTimerRef.current) {
        window.clearTimeout(refreshTimerRef.current);
      }
      setQr(null);
      setLocalCredential(null);
      setDevices((current) => current.map((item) => (
        item.id === activeDevice.id ? { ...item, active: false } : item
      )));
      setFeedback("El vínculo de este celular fue revocado.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "revocar el dispositivo",
        resource: "Talent ID",
        fallback: "No fue posible revocar este celular.",
      }));
    }
  }

  if (loading) {
    return (
      <section className="panel mobile-attendance-card">
        <LoadingState label="Cargando alternativa de marcación…" compact />
      </section>
    );
  }

  return (
    <section className="panel mobile-attendance-card">
      <div className="mobile-attendance-heading">
        <div>
          <span className="eyebrow">Talent ID · Alternativa no biométrica</span>
          <h2>QR dinámico desde tu celular</h2>
          <p>
            Vincula un único celular y genera códigos de corta duración para marcar entrada o salida sin reconocimiento facial.
          </p>
        </div>
        <span className={`mobile-device-status ${activeDevice ? "is-linked" : ""}`}>
          {activeDevice ? "Celular vinculado" : "Sin vincular"}
        </span>
      </div>

      {error && <FeedbackMessage title="No se pudo completar la operación">{error}</FeedbackMessage>}
      {feedback && <div className="talent-id-success" role="status">{feedback}</div>}

      {!supported ? (
        <div className="mobile-attendance-warning">
          Tu navegador no ofrece WebCrypto + almacenamiento seguro compatible. Usa Chrome, Edge o Safari actualizado desde tu celular.
        </div>
      ) : !activeDevice ? (
        <div className="mobile-attendance-link">
          <div>
            <strong>Vincular este celular</strong>
            <p>
              Talent crea una llave ECDSA P-256 local. La llave privada se guarda como no exportable en el navegador y no se envía al servidor.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={linking}
            onClick={linkThisDevice}
          >
            {linking ? "Vinculando…" : "Vincular este celular"}
          </button>
        </div>
      ) : (
        <>
          <div className="mobile-attendance-device">
            <div>
              <span>Dispositivo activo</span>
              <strong>{activeDevice.label}</strong>
              <small>
                {activeDevice.last_used_at
                  ? `Último uso · ${new Date(activeDevice.last_used_at).toLocaleString("es-CO")}`
                  : "Aún no se ha usado para marcar"}
              </small>
            </div>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={revokeDevice}
            >
              Revocar vínculo
            </button>
          </div>

          {!qr ? (
            <div className="mobile-attendance-generate">
              <div>
                <strong>Genera el código cuando estés frente al kiosco</strong>
                <p>
                  El QR dura unos segundos, cambia automáticamente y solo puede consumirse una vez.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                disabled={generating}
                onClick={() => generateQr()}
              >
                {generating ? "Generando…" : "Mostrar QR para marcar"}
              </button>
            </div>
          ) : (
            <div className="mobile-attendance-qr">
              <div className="mobile-attendance-qr-frame">
                <img src={qr.qr_image} alt="Código QR dinámico de Talent ID" />
              </div>
              <div className="mobile-attendance-qr-copy">
                <span className={`mobile-attendance-countdown ${remaining <= 8 ? "is-expiring" : ""}`}>
                  {remaining > 0 ? `${remaining} s` : "Renovando…"}
                </span>
                <strong>Muestra este QR al kiosco</strong>
                <p>
                  En la tablet selecciona <b>QR móvil</b>, luego Entrada o Salida, y acerca la pantalla del celular a la cámara.
                </p>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={generating}
                  onClick={() => generateQr()}
                >
                  {generating ? "Renovando…" : "Renovar ahora"}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      <div className="mobile-attendance-security">
        <strong>Por qué es más seguro que un PIN</strong>
        <p>
          La marcación exige este dispositivo vinculado, una firma criptográfica local y un QR de un solo uso con expiración corta. Compartir usuario y contraseña no basta para generar el código.
        </p>
      </div>
    </section>
  );
}

export default MobileAttendanceCard;
