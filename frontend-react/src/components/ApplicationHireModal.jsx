import { useEffect, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import EmployeeCredentialsModal from "./EmployeeCredentialsModal";

function splitName(name = "") {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return {
    first_name: parts.slice(0, -1).join(" ") || parts[0] || "",
    last_name: parts.length > 1 ? parts[parts.length - 1] : "",
  };
}

function initialForm(application) {
  const candidate = application?.candidate || {};
  const names = splitName(candidate.name || "");
  return {
    username: application?.access?.username || "",
    email: application?.access?.email || candidate.email || "",
    first_name: names.first_name,
    last_name: names.last_name,
    job_title: application?.job?.title || "",
    department: "",
    country_code: candidate.country_code || "",
    company_name: "",
    hire_date: (() => {
      const now = new Date();
      const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
      return local.toISOString().slice(0, 10);
    })(),
  };
}

export default function ApplicationHireModal({ application, onClose, onHired }) {
  const [form, setForm] = useState(() => initialForm(application));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [credentials, setCredentials] = useState(null);

  useEffect(() => {
    if (application) {
      setForm(initialForm(application));
      setError("");
      setCredentials(null);
    }
  }, [application]);

  if (!application) return null;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(
        `/jobs/${application.job.job_id}/candidates/${application.candidate.candidate_id}/hire`,
        { ...form, country_code: form.country_code || null, company_name: form.company_name || null },
      );
      await onHired?.(data);
      if (data?.credentials) setCredentials(data.credentials);
      else onClose?.();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "contratar al postulante",
        resource: "postulaciones",
        fallback: "No se pudo completar la contratación.",
      }));
    } finally {
      setBusy(false);
    }
  }

  if (credentials) {
    return (
      <EmployeeCredentialsModal
        open
        credentials={credentials}
        employeeName={application.candidate.name}
        onClose={onClose}
      />
    );
  }

  return (
    <div className="modal-overlay" role="presentation" onMouseDown={() => !busy && onClose?.()}>
      <section className="modal employee-modal" role="dialog" aria-modal="true" aria-labelledby="application-hire-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="eyebrow">Contratación formal</span>
            <h2 id="application-hire-title">Crear empleado</h2>
            <p>{application.candidate.name} · {application.job.title}</p>
          </div>
          <button className="btn-close" type="button" aria-label="Cerrar" disabled={busy} onClick={onClose}>×</button>
        </div>
        <p>Esta acción finaliza la postulación como Contratado, activa la ruta de onboarding y ejecuta la integración configurada con Odoo. El usuario y los documentos existentes se conservarán.</p>
        {error && <div className="alert" role="alert">{error}</div>}
        <form className="employee-form" onSubmit={submit}>
          <div className="form-group">
            <label htmlFor="application-hire-username">Usuario de Talent</label>
            <input id="application-hire-username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })} minLength={3} maxLength={40} required />
          </div>
          <div className="employee-form-grid">
            <div className="form-group">
              <label htmlFor="application-hire-first-name">Nombre</label>
              <input id="application-hire-first-name" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} required />
            </div>
            <div className="form-group">
              <label htmlFor="application-hire-last-name">Apellido</label>
              <input id="application-hire-last-name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} required />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="application-hire-email">Correo electrónico</label>
            <input id="application-hire-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </div>
          <div className="employee-form-grid">
            <div className="form-group">
              <label htmlFor="application-hire-job">Cargo</label>
              <input id="application-hire-job" value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} required />
            </div>
            <div className="form-group">
              <label htmlFor="application-hire-department">Área</label>
              <input id="application-hire-department" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
            </div>
          </div>
          <div className="employee-form-grid">
            <div className="form-group">
              <label htmlFor="application-hire-country">Código de país</label>
              <input id="application-hire-country" value={form.country_code} onChange={(e) => setForm({ ...form, country_code: e.target.value.toUpperCase() })} maxLength={2} placeholder="CO" />
            </div>
            <div className="form-group">
              <label htmlFor="application-hire-company">Empresa</label>
              <input id="application-hire-company" value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} placeholder="ASIATI" />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="application-hire-date">Fecha de ingreso</label>
            <input id="application-hire-date" type="date" value={form.hire_date} onChange={(e) => setForm({ ...form, hire_date: e.target.value })} required />
          </div>
          <div className="form-actions">
            <button className="btn btn-secondary" type="button" disabled={busy} onClick={onClose}>Cancelar</button>
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Contratando…" : "Confirmar contratación"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
