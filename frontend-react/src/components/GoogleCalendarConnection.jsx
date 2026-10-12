import { useEffect, useState } from "react";
import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import { useSession } from "../context/SessionContext";
import { FeedbackMessage } from "./ui/StatePanel";

export default function GoogleCalendarConnection() {
  const { hasPermission } = useSession();
  const canManage = hasPermission("integrations.manage");
  const [status, setStatus] = useState(null);
  const [accountEmail, setAccountEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.get("/recruitment-calendar/google/status")
      .then(({ data }) => {
        if (active) {
          setStatus(data);
          setAccountEmail(data?.target_email || "");
        }
      })
      .catch(() => { if (active) setStatus(null); });
    return () => { active = false; };
  }, []);

  async function saveAccount(event) {
    event.preventDefault();
    const next = accountEmail.trim().toLowerCase();
    if (!next || next === status?.target_email) return;
    if (status?.connected && !window.confirm(
      "¿Cambiar la cuenta de Google? Se desconectará el calendario actual y tendrás que autorizar la cuenta nueva. Las citas ya creadas en Google permanecerán allí."
    )) return;
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const { data } = await api.put("/recruitment-calendar/google/account", { email: next });
      setStatus(data);
      setAccountEmail(data.target_email);
      setMessage("Cuenta de gestión actualizada. Autoriza la nueva cuenta de Google para continuar.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cambiar la cuenta de calendario",
        fallback: "No se pudo guardar la cuenta corporativa.",
      }));
    } finally {
      setLoading(false);
    }
  }

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
      setStatus((current) => ({ ...current, connected: false, connected_email: null }));
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
    <section className="panel" aria-label="Cuenta de Google Calendar para selección">
      <div className="employee-toolbar">
        <div>
          <span className="eyebrow">Integración de agenda</span>
          <h2>Cuenta Google (Gmail) para gestión de entrevistas</h2>
          <p>Cuenta configurada: <strong>{status?.target_email || "Consultando…"}</strong></p>
          <p>{status?.connected
            ? `Conectada: ${status.connected_email}. Sincronización Talent → Google Calendar.`
            : "Sin conectar. Las citas siguen guardadas en Talent."}</p>
          <p className="muted">La autorización solo permite gestionar el calendario. No permite leer el correo Gmail.</p>
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
      {canManage && status && (
        <form onSubmit={(event) => void saveAccount(event)} className="ui-actions" style={{ marginTop: "1rem", flexWrap: "wrap" }}>
          <label htmlFor="talent-calendar-email">Cambiar la cuenta responsable</label>
          <input
            id="talent-calendar-email"
            className="form-control"
            type="email"
            maxLength={254}
            required
            value={accountEmail}
            onChange={(event) => setAccountEmail(event.target.value)}
            disabled={loading}
            placeholder="cuenta@asiati.com.co"
            autoComplete="email"
          />
          <button
            type="submit"
            className="btn btn-secondary"
            disabled={loading || !accountEmail.trim() || accountEmail.trim().toLowerCase() === status.target_email}
          >
            Guardar cuenta
          </button>
          <p className="muted">La nueva cuenta deberá autorizar Google. Cambiarla desconecta la anterior sin borrar sus eventos; por seguridad se admiten dominios corporativos autorizados.</p>
        </form>
      )}
      {status && !status.oauth_configured && (
        <p className="muted">Es necesario configurar OAuth en Google Cloud y registrar el callback de Talent.</p>
      )}
      {outcome === "connected" && <FeedbackMessage tone="success" title="Autorización completada">Ya puedes sincronizar las citas.</FeedbackMessage>}
      {outcome === "wrong_account" && <FeedbackMessage title="Cuenta no autorizada">Debes autorizar exactamente la cuenta configurada arriba.</FeedbackMessage>}
      {outcome === "error" && <FeedbackMessage title="Conexión incompleta">No se pudo validar la autorización de Google.</FeedbackMessage>}
      {message && <FeedbackMessage tone="success" title="Google Calendar">{message}</FeedbackMessage>}
      {error && <FeedbackMessage title="Error de sincronización">{error}</FeedbackMessage>}
    </section>
  );
}
