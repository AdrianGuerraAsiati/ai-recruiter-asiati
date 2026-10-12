import { useEffect, useMemo, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";

/** Only Talent HR reviewers can see this list; backend enforces read_all. */
export default function DocumentReviewQueue({ onSelect, revision = 0 }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("PENDING");

  useEffect(() => {
    let active = true;
    // Updating one document refreshes this queue without a full page reload.
    const fetchQueue = async () => {
      try {
        const { data } = await api.get("/employee-documents/review-queue");
        if (active) {
          setItems(Array.isArray(data?.items) ? data.items : []);
          setError("");
        }
      } catch (err) {
        if (active) setError(getApiErrorMessage(err, {
          action: "consultar expedientes pendientes",
          fallback: "No se pudo cargar la bandeja de revisión.",
        }));
      } finally {
        if (active) setLoading(false);
      }
    };
    void fetchQueue();
    return () => { active = false; };
  }, [revision]);

  const visible = useMemo(() => items.filter((item) => {
    if (filter === "PENDING") return item.pending_review > 0;
    if (filter === "CHANGES") return item.changes_requested > 0;
    return true;
  }), [filter, items]);

  return (
    <section className="panel" aria-label="Bandeja de revisión documental">
      <div className="employee-toolbar">
        <div>
          <span className="eyebrow">Talento Humano</span>
          <h2>Bandeja de revisión documental</h2>
          <p>Expedientes con documentos recibidos o correcciones solicitadas.</p>
        </div>
        <select
          aria-label="Filtrar bandeja documental"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        >
          <option value="PENDING">Por revisar</option>
          <option value="CHANGES">Por corregir</option>
          <option value="ALL">Todos los pendientes</option>
        </select>
      </div>
      {error && <p role="alert">{error}</p>}
      {loading ? <p>Cargando documentos pendientes…</p> : visible.length ? (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr><th>Postulante o empleado</th><th>Por revisar</th><th>Por corregir</th><th>Acción</th></tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.profile_id}>
                  <td><strong>{item.name}</strong><small>{item.email}</small></td>
                  <td>{item.pending_review}</td>
                  <td>{item.changes_requested}</td>
                  <td>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => onSelect(item.profile_id)}>
                      Abrir expediente
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p>No hay expedientes para este filtro.</p>}
      {items.length >= 100 && <p className="muted">Se muestran los 100 expedientes más recientes. Revisa los demás desde Postulaciones.</p>}
    </section>
  );
}
