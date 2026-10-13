import { useCallback, useEffect, useState } from "react";
import api from "../../api/client";
import { getApiErrorMessage } from "../../utils/errors";

export default function NameNormalizationModal({ onClose, onApplied }) {
  const [audit, setAudit] = useState(null);
  const [suggestions, setSuggestions] = useState({});
  const [approved, setApproved] = useState({});
  const [working, setWorking] = useState(false);
  const [scanning, setScanning] = useState(true);
  const [processed, setProcessed] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState([]);
  const load = useCallback(async () => {
    setScanning(true);
    try {
      const [response, auditHistory] = await Promise.all([
        api.get("/candidates/name-normalization/preview?limit=2000"),
        api.get("/candidates/name-normalization/history"),
      ]);
      setAudit(response.data);
      setHistory(auditHistory.data?.items || []);
    } catch (err) {
      setError(getApiErrorMessage(err, { fallback: "No se pudo revisar la base de candidatos." }));
    } finally {
      setScanning(false);
    }
  }, []);
  useEffect(() => {
    // Initial fetch synchronizes this modal with the secured API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function analyze() {
    if (!window.confirm("¿Analizar los nombres sospechosos con Bedrock? Puede generar consumo AWS. Las propuestas creadas previamente desde este botón se reutilizan.")) return;
    setWorking(true);
    setError("");
    setProcessed(0);
    const all = audit?.items || [];
    const next = { ...suggestions };
    try {
      for (let i = 0; i < all.length; i += 5) {
        const ids = all.slice(i, i + 5).map((item) => item.candidate_id);
        const { data } = await api.post("/candidates/name-normalization/suggest", { candidate_ids: ids });
        for (const item of data.items || []) next[item.candidate_id] = item;
        setSuggestions({ ...next });
        setProcessed(Math.min(i + 5, all.length));
      }
    } catch (err) {
      setError(getApiErrorMessage(err, { fallback: "La ejecución se interrumpió. Los análisis anteriores siguen en caché." }));
    } finally {
      setWorking(false);
    }
  }

  async function openCv(candidateId) {
    const tab = window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    try {
      const response = await api.get("/candidates/" + candidateId + "/download");
      const url = response.data?.download_url;
      if (!url) throw new Error("CV unavailable");
      if (tab) tab.location.replace(url);
      else window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      if (tab) tab.close();
      setError(getApiErrorMessage(err, { fallback: "No se pudo abrir el CV original." }));
    }
  }

  async function apply() {
    const chosen = Object.values(suggestions).filter((item) => approved[item.candidate_id] && item.status === "REVIEW_REQUIRED");
    if (!chosen.length || !window.confirm("¿Confirmas que verificaste visualmente estos " + chosen.length + " nombres?")) return;
    setWorking(true);
    setError("");
    try {
      const payload = chosen.map((item) => ({
        candidate_id: item.candidate_id,
        expected_current_name: item.current_name,
        proposed_name: item.suggested_name,
      }));
      const result = await api.post("/candidates/name-normalization/apply", { approvals: payload });
      setMessage("Nombres actualizados: " + result.data.applied + ". Lote: " + result.data.batch_id);
      setApproved({});
      setSuggestions({});
      await load();
      onApplied?.();
    } catch (err) {
      setError(getApiErrorMessage(err, { fallback: "No fue posible aplicar las correcciones." }));
    } finally {
      setWorking(false);
    }
  }

  async function undoBatch(batchId) {
    if (!window.confirm("¿Revertir este lote completo? Solo se restaurarán nombres que no hayan cambiado desde su aprobación.")) return;
    setWorking(true);
    setError("");
    try {
      const response = await api.post("/candidates/name-normalization/revert-batch", { batch_id: batchId });
      setMessage("Nombres revertidos: " + response.data.reverted);
      setSuggestions({});
      setApproved({});
      await load();
      onApplied?.();
    } catch (err) {
      setError(getApiErrorMessage(err, { fallback: "No fue posible revertir el lote." }));
    } finally {
      setWorking(false);
    }
  }

  const items = audit?.items || [];
  const count = Object.values(approved).filter(Boolean).length;
  return (
    <div className="modal-overlay" onClick={() => { if (!working) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="normalize-title"
        style={{ width: "min(95vw, 1080px)", maxHeight: "90vh", overflowY: "auto" }}
        onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div><h2 id="normalize-title">Normalizar todos los nombres</h2>
            <p className="muted">Auditoría, propuestas IA y aprobación antes de guardar.</p></div>
          <button type="button" className="btn btn-close" onClick={onClose} disabled={working}>✕</button>
        </div>
        {scanning && <p role="status">Revisando los candidatos…</p>}
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        {audit && <>
          <p><strong>{audit.total_scanned}</strong> candidatos auditados · <strong>{audit.suspected_count}</strong> sospechosos · {items.length} en revisión.</p>
          {audit.has_more && <p role="alert">Hay más casos fuera del límite de 2000. No se analizarán en esta ejecución.</p>}
          <p className="muted">Se revisan todos los nombres, pero Bedrock solo analiza los sospechosos y guarda las propuestas para evitar repetir cobros. Nada se modifica sin aprobación.</p>
          <div className="ui-actions" style={{ marginBottom: 16 }}>
            <button type="button" className="btn btn-secondary" disabled={!items.length || working} onClick={analyze}>
              {working ? "Procesando…" : "Analizar nombres sospechosos con IA"}
            </button>
            {working && <span role="status">Analizados {processed}/{items.length}</span>}
          </div>
          <div style={{ maxHeight: "48vh", overflow: "auto" }}>
            <table className="table" style={{ width: "100%" }}>
              <thead><tr><th>Aprobar</th><th>Nombre actual</th><th>Propuesta</th><th>Evidencia / Estado</th></tr></thead>
              <tbody>{items.map((item) => {
                const suggestion = suggestions[item.candidate_id];
                const eligible = suggestion?.status === "REVIEW_REQUIRED";
                return <tr key={item.candidate_id}>
                  <td><input type="checkbox" checked={Boolean(approved[item.candidate_id])}
                    aria-label={"Aprobar nombre propuesto para " + item.current_name}
                    disabled={!eligible || working}
                    onChange={(event) => setApproved((previous) => ({ ...previous, [item.candidate_id]: event.target.checked }))} /></td>
                  <td>{item.current_name}<div><button type="button" className="btn btn-secondary" onClick={() => void openCv(item.candidate_id)}>Ver CV</button></div></td><td>{suggestion?.suggested_name || "—"}</td>
                  <td>{suggestion?.evidence || suggestion?.status || item.reason}</td>
                </tr>;
              })}</tbody>
            </table>
          </div>
          {history.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <h3>Historial de normalizaciones</h3>
              {history.map((batch) => (
                <div key={batch.batch_id} className="ui-actions" style={{ marginBottom: 8 }}>
                  <span>{batch.count} candidatos · {new Date(batch.approved_at).toLocaleString("es-CO")}</span>
                  <button type="button" className="btn btn-secondary" disabled={working}
                    onClick={() => void undoBatch(batch.batch_id)}>Revertir lote</button>
                </div>
              ))}
            </div>
          )}
          <div className="form-actions" style={{ marginTop: 18 }}>
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={working}>Cerrar</button>
            <button type="button" className="btn btn-primary" onClick={apply} disabled={!count || working}>
              {"Aplicar " + count + " nombres aprobados"}
            </button>
          </div>
        </>}
      </section>
    </div>
  );
}
