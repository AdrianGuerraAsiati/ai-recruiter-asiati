import { useEffect, useState } from "react";
import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import { useSession } from "../context/SessionContext";
import { FeedbackMessage } from "./ui/StatePanel";

export default function GoogleCalendarConnection() {
  const { hasPermission } = useSession();
  const canManage = hasPermission("integrations.manage");
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.get("/recruitment-calendar/google/status")
      .then(({ data }) => { if (active) setStatus(data); })
      .catch(() => { if (active) setStatus(null); });
    return () => { active = false; };
  }, []);

  async function connect() {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/recruitment-calendar/google/oauth/start");
      if (!data?.authorization_url) throw new Error("AUTH_URL_MISSING");
      window.location.assign(data.authorization_url);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "conectar Google Calendar",
        fallback: "No se pudo solicitar acceso a Google Calendar.",
      }));
      setLoading(false);
    }
  }

  async function synchronize() {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.post("/recruitment-calendar/google/sync");
      setMessage(`Citas sincronizadas: ${data.synced}. Fallidas: ${data.failed}.`);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "sincronizar las entrevistas",
        fallback: "No se pudieron sincronizar las entrevistas.",
      }));
    } finally {
      setLoading(false);
    }
  }

  async function disconnect() {
    setLoading(true);
    setError("");
    try {
      await api.delete("/recruitment-calendar/google");
      setStatus((current) => ({ ...current, connected: false }));
      setMessage("Conexión desactivada. Las citas de Google no se han eliminado.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "desconectar Google Calendar",
        fallback: "No se pudo desconectar Google Calendar.",
      }));
    } finally {
      setLoading(false);
    }
  }

  const outcome = new URLSearchParams(window.location.search).get("google");

  return (
    <section className="panel" aria-label="Google Calendar de Talento Humano">
      <div className="employee-toolbar">
        <div>
          <span className="eyebrow">Integración de agenda</span>
          <h2>Google Calendar</h2>
          <p>Cuenta: <strong>talentohumano@asiati.com.co</strong></p>
          <p>{status?.connected ? "Conectado · Talent → Google Calendar" : "Pendiente de autorización de Talento Humano"}</p>
        </div>
        {canManage && (
          <div className="ui-actions">
            {!status?.connected && (
              <button type="button" className="btn btn-primary" onClick={() => void connect()} disabled={loading || !status?.oauth_configured}>
                Conectar cuenta
              </button>
            )}
            {status?.connected && (
              <>
                <button type="button" className="btn btn-primary" onClick={() => void synchronize()} disabled={loading}>
                  {loading ? "Sincronizando…" : "Sincronizar citas"}
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => void disconnect()} disabled={loading}>
                  Desconectar
                </button>
              </>
            )}
          </div>
        )}
      </div>
      {status && !status.oauth_configured && (
        <p className="muted">Es necesario configurar OAuth en Google Cloud y registrar el callback de Talent.</p>
      )}
      {outcome === "connected" && <FeedbackMessage tone="success" title="Autorización completada">Ya puedes sincronizar las citas.</FeedbackMessage>}
      {outcome === "wrong_account" && <FeedbackMessage title="Cuenta no autorizada">Debes usar talentohumano@asiati.com.co.</FeedbackMessage>}
      {outcome === "error" && <FeedbackMessage title="Conexión incompleta">No se pudo validar la autorización de Google.</FeedbackMessage>}
      {message && <FeedbackMessage tone="success" title="Google Calendar">{message}</FeedbackMessage>}
      {error && <FeedbackMessage title="Error de sincronización">{error}</FeedbackMessage>}
    </section>
  );
}
