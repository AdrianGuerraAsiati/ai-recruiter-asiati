import { useCallback, useEffect, useState } from "react";
import api from "../../api/client";
import { getApiErrorMessage } from "../../utils/errors";

export default function NameNormalizationModal({ onClose, onApplied }) {
  const [audit, setAudit] = useState(null);
  const [suggestions, setSuggestions] = useState({});
  const [approved, setApproved] = useState({});
  const [rejected, setRejected] = useState({});
  const [manualNames, setManualNames] = useState({});
  const [manualReasons, setManualReasons] = useState({});
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
    const chosen = (audit?.items || []).filter((item) => approved[item.candidate_id]).map((item) => {
      const manual = String(manualNames[item.candidate_id] || "").trim().replace(/\s+/g, " ");
      const suggestion = suggestions[item.candidate_id];
      return { candidate_id: item.candidate_id, current_name: item.current_name,
        suggested_name: manual || suggestion?.suggested_name,
        source: manual ? "manual" : "bedrock", review_reason: manual ? String(manualReasons[item.candidate_id] || "").trim() : "" };
    });
    if (!chosen.length || !window.confirm("¿Confirmas que verificaste visualmente estos " + chosen.length + " nombres?")) return;
    setWorking(true);
    setError("");
    try {
      const payload = chosen.map((item) => ({
        candidate_id: item.candidate_id,
        expected_current_name: item.current_name,
        proposed_name: item.suggested_name,
        source: item.source,
        review_reason: item.review_reason,
      }));
      const result = await api.post("/candidates/name-normalization/apply", { approvals: payload });
      setMessage("Nombres actualizados: " + result.data.applied + ". Lote: " + result.data.batch_id);
      setApproved({});
      setRejected({});
      setManualNames({});
      setManualReasons({});
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
      setRejected({});
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
  const rejectedCount = Object.values(rejected).filter(Boolean).length;
  const readyCount = Object.values(suggestions).filter((item) => item.status === "REVIEW_REQUIRED").length;
  const approveAll = () => {
    const next = {};
    for (const suggestion of Object.values(suggestions)) {
      if (suggestion.status === "REVIEW_REQUIRED" && !rejected[suggestion.candidate_id] && !String(manualNames[suggestion.candidate_id] || "").trim()) next[suggestion.candidate_id] = true;
    }
    setApproved(next);
  };
  return (
    <div className="modal-overlay" onClick={() => { if (!working) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="normalize-title"
        style={{ width: "min(96vw, 1100px)", maxWidth: "none", maxHeight: "94vh", overflowY: "auto", boxSizing: "border-box" }}
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
          <p role="status"><strong>{count}</strong> aprobados · <strong>{rejectedCount}</strong> rechazados · <strong>{Math.max(items.length - count - rejectedCount, 0)}</strong> pendientes.</p>
          {audit.has_more && <p role="alert">Hay más casos fuera del límite de 2000. No se analizarán en esta ejecución.</p>}
          <p className="muted">Se revisan todos los nombres, pero Bedrock solo analiza los sospechosos y guarda las propuestas para evitar repetir cobros. Nada se modifica sin aprobación.</p>
          <div className="ui-actions" style={{ marginBottom: 16 }}>
            <button type="button" className="btn btn-secondary" disabled={!items.length || working} onClick={analyze}>
              {working ? "Procesando…" : "Analizar nombres sospechosos con IA"}
            </button>
            {working && <span role="status">Analizados {processed}/{items.length}</span>}
          </div>
          <div className="ui-actions" style={{ marginBottom: 12, flexWrap: "wrap" }}>
            <button type="button" className="btn btn-secondary" disabled={working || readyCount === 0} onClick={approveAll}>Aprobar todas las propuestas disponibles</button>
            <button type="button" className="btn btn-secondary" disabled={working || count === 0} onClick={() => setApproved({})}>Desmarcar aprobaciones</button>
            <span className="muted">Aprobar solo marca para aplicar; no cambia la base de datos todavía.</span>
          </div>
          <div style={{ display: "grid", gap: 12, marginBottom: 18 }}>
            {items.map((item) => {
              const suggestion = suggestions[item.candidate_id];
              const manual = String(manualNames[item.candidate_id] || "").trim();
              const manualReason = String(manualReasons[item.candidate_id] || "").trim();
              const eligible = (manual ? /^[\p{L}][\p{L} '-]*(?:\s+[\p{L}][\p{L} '-]*)+$/u.test(manual) && manualReason.length >= 10 : suggestion?.status === "REVIEW_REQUIRED");
              const isApproved = Boolean(approved[item.candidate_id]);
              const isRejected = Boolean(rejected[item.candidate_id]);
              return (
                <article key={item.candidate_id} style={{
                  background: "rgba(255,255,255,0.035)", border: "1px solid rgba(180,220,230,0.18)",
                  borderRadius: 12, padding: 16, minWidth: 0
                }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 225px), 1fr))", gap: 18 }}>
                    <div style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                      <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Nombre actual</div>
                      <strong>{item.current_name}</strong>
                      <div style={{ marginTop: 12 }}>
                        <button type="button" className="btn btn-secondary" onClick={() => void openCv(item.candidate_id)}>Ver CV original</button>
                      </div>
                    </div>
                    <div style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                      <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Nombre propuesto</div>
                      <strong>{suggestion?.suggested_name || "Sin propuesta de IA"}</strong>
                      <label style={{ display: "block", fontSize: 12, marginTop: 12 }} htmlFor={"manual-name-" + item.candidate_id}>Nombre propuesto por administrador</label>
                      <input id={"manual-name-" + item.candidate_id} type="text" className="select" maxLength={90} value={manualNames[item.candidate_id] || ""}
                        placeholder="Nombre y apellidos" disabled={working}
                        onChange={(event) => { const value = event.target.value; setManualNames((previous) => ({ ...previous, [item.candidate_id]: value })); setApproved((previous) => ({ ...previous, [item.candidate_id]: false })); }} />
                      {manual && <><label style={{ display: "block", fontSize: 12, marginTop: 10 }} htmlFor={"manual-reason-" + item.candidate_id}>Fundamento de la corrección (mínimo 10 caracteres)</label>
                        <textarea id={"manual-reason-" + item.candidate_id} rows={2} maxLength={500} value={manualReasons[item.candidate_id] || ""}
                          placeholder="Ej.: nombre identificado visualmente en la primera página del CV" disabled={working}
                          onChange={(event) => { setManualReasons((previous) => ({ ...previous, [item.candidate_id]: event.target.value })); setApproved((previous) => ({ ...previous, [item.candidate_id]: false })); }} /></> }
                      <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>Evidencia</div>
                      <p style={{ margin: "4px 0 0", overflowWrap: "anywhere" }}>
                        {suggestion?.evidence || suggestion?.status || item.reason}
                      </p>
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>Decisión</div>
                      {eligible ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                          <button type="button" className={isApproved ? "btn btn-primary" : "btn btn-secondary"}
                            aria-pressed={isApproved} disabled={working}
                            onClick={() => {
                              setApproved((previous) => ({ ...previous, [item.candidate_id]: !isApproved }));
                              setRejected((previous) => ({ ...previous, [item.candidate_id]: false }));
                            }}>
                            {isApproved ? "✓ Aprobado" : "Aprobar nombre"}
                          </button>
                          <button type="button" className="btn btn-secondary" aria-pressed={isRejected}
                            disabled={working}
                            onClick={() => {
                              setRejected((previous) => ({ ...previous, [item.candidate_id]: !isRejected }));
                              setApproved((previous) => ({ ...previous, [item.candidate_id]: false }));
                            }}>
                            {isRejected ? "Rechazado · Deshacer" : "Rechazar"}
                          </button>
                        </div>
                      ) : <span className="muted">{manual ? "Ingresa nombre completo y justificación para aprobar." : "Analiza con IA o propone manualmente un nombre."}</span>}
                    </div>
                  </div>
                </article>
              );
            })}
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
