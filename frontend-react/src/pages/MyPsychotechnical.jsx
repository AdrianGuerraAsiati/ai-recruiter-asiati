import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import { getApiErrorMessage } from "../utils/errors";

const LABEL = {
  PENDING: "Pendiente",
  IN_PROGRESS: "En curso",
  COMPLETED: "Completada",
  EXPIRED: "Vencida",
  CANCELED: "Cancelada",
};

export default function MyPsychotechnical() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [launching, setLaunching] = useState("");
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/psychotechnical/me");
      setItems(data.items || []);
    } catch (err) {
      setError(getApiErrorMessage(err, { fallback: "No se pudieron consultar tus pruebas." }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial data load is an external API synchronization.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  async function openTest(assignmentId) {
    setLaunching(assignmentId);
    setError("");
    try {
      const { data } = await api.post("/psychotechnical/me/" + assignmentId + "/launch");
      navigate("/psychotechnical/take/" + encodeURIComponent(data.token));
    } catch (err) {
      setError(getApiErrorMessage(err, { fallback: "No se pudo abrir la prueba." }));
    } finally {
      setLaunching("");
    }
  }

  return (
    <div className="page">
      <PageHeader eyebrow="Tu proceso de selección" title="Ficha psicotécnica"
        description="Consulta las pruebas que te asignó Talento Humano y complétalas desde tu cuenta." />
      {error && <p role="alert">{error}</p>}
      {loading && <p role="status">Consultando tus pruebas…</p>}
      {!loading && !error && items.length === 0 && (
        <section className="card" style={{ padding: 24 }}>
          <h2>No tienes pruebas asignadas</h2>
          <p className="muted">Cuando Talento Humano te asigne una prueba psicotécnica, aparecerá aquí.</p>
        </section>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 290px), 1fr))", gap: 16 }}>
        {items.map((item) => {
          const available = ["PENDING", "IN_PROGRESS"].includes(item.status);
          return (
            <section className="card" key={item.id} style={{ padding: 22, minWidth: 0 }}>
              <span className="muted">{LABEL[item.status] || item.status}</span>
              <h2 style={{ marginTop: 8 }}>{item.test_name}</h2>
              <p>{item.test_description}</p>
              {item.job_title && <p className="muted">Proceso: {item.job_title}</p>}
              {item.duration_minutes && <p className="muted">Duración estimada: {item.duration_minutes} minutos</p>}
              {item.expires_at && item.status !== "COMPLETED" && <p className="muted">Vence: {new Date(item.expires_at).toLocaleDateString("es-CO")}</p>}
              {item.completed_at && <p className="muted">Realizada: {new Date(item.completed_at).toLocaleDateString("es-CO")}</p>}
              {available && (
                <button type="button" className="btn btn-primary" disabled={Boolean(launching)}
                  onClick={() => void openTest(item.id)}>
                  {launching === item.id ? "Abriendo…" : item.status === "IN_PROGRESS" ? "Continuar prueba" : "Iniciar prueba"}
                </button>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
