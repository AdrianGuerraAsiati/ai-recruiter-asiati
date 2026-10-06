import { useEffect, useMemo, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import EmployeeCredentialsModal from "./EmployeeCredentialsModal";
import { FeedbackMessage, LoadingState } from "./ui/StatePanel";

function todayInputValue() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function splitName(value = "") {
  const parts = String(value).trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return { first_name: "", last_name: "" };
  if (parts.length === 1) return { first_name: parts[0], last_name: "" };
  return {
    first_name: parts.slice(0, Math.max(1, parts.length - 1)).join(" "),
    last_name: parts[parts.length - 1],
  };
}

function slug(value = "") {
  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function suggestedUsername(candidate) {
  const { first_name, last_name } = splitName(candidate?.name);
  const first = slug(first_name).slice(0, 1);
  const last = slug(last_name);
  const fallback = slug(candidate?.email?.split("@")[0] || "");
  return (first + last || fallback).slice(0, 40);
}

function buildForm(candidate, jobTitle = "") {
  const names = splitName(candidate?.name);
  return {
    username: suggestedUsername(candidate),
    first_name: names.first_name,
    last_name: names.last_name,
    email: candidate?.email || "",
    job_title: jobTitle || "",
    department: "",
    hire_date: todayInputValue(),
    role: "EMPLOYEE",
  };
}

export default function CandidateCreateUserModal({
  open,
  candidateId,
  candidate: initialCandidate = null,
  jobTitle = "",
  onClose,
  onCreated,
}) {
  const [candidate, setCandidate] = useState(initialCandidate);
  const [form, setForm] = useState(() => buildForm(initialCandidate, jobTitle));
  const [loadingCandidate, setLoadingCandidate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [credentialResult, setCredentialResult] = useState(null);

  const titleName = useMemo(
    () => candidate?.name || [form.first_name, form.last_name].filter(Boolean).join(" ") || "Candidato",
    [candidate?.name, form.first_name, form.last_name],
  );

  useEffect(() => {
    if (!open) return undefined;

    let cancelled = false;
    setError("");
    setCredentialResult(null);

    async function loadCandidate() {
      const seed = initialCandidate?.candidate_id || initialCandidate?.id
        ? initialCandidate
        : null;

      if (seed?.email && seed?.name) {
        setCandidate(seed);
        setForm(buildForm(seed, jobTitle));
        return;
      }

      if (!candidateId) {
        setCandidate(seed);
        setForm(buildForm(seed, jobTitle));
        return;
      }

      setLoadingCandidate(true);
      try {
        const { data } = await api.get(`/candidates/${candidateId}`);
        if (cancelled) return;
        setCandidate(data || seed);
        setForm(buildForm(data || seed, jobTitle));
      } catch (err) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, {
            action: "cargar los datos del candidato",
            resource: "candidato",
            fallback: "No se pudieron cargar los datos necesarios para crear el usuario.",
          }));
        }
      } finally {
        if (!cancelled) setLoadingCandidate(false);
      }
    }

    void loadCandidate();
    return () => {
      cancelled = true;
    };
  }, [candidateId, initialCandidate, jobTitle, open]);

  if (!open) return null;

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post("/employees", form);
      setCredentialResult({
        employeeName: [data?.employee?.first_name, data?.employee?.last_name]
          .filter(Boolean)
          .join(" ") || titleName,
        credentials: data?.credentials || null,
      });
      await onCreated?.(data);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "crear el usuario del candidato",
        resource: "usuarios",
        fallback: "No se pudo crear el usuario. Revisa correo, username y permisos antes de reintentar.",
      }));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="modal-overlay" role="presentation" onMouseDown={onClose}>
        <section
          className="modal employee-modal candidate-user-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="candidate-user-modal-title"
          onMouseDown={(event) => event.stopPropagation()}
        >
          <div className="modal-header">
            <div>
              <span className="eyebrow">Acceso a Talent</span>
              <h2 id="candidate-user-modal-title">Crear usuario</h2>
              <p>
                Crea el acceso de {titleName}. Talent generará una contraseña temporal y asignará el onboarding corporativo.
              </p>
            </div>
            <button className="btn-close" type="button" aria-label="Cerrar" onClick={onClose}>×</button>
          </div>

          {loadingCandidate ? (
            <LoadingState label="Cargando candidato…" compact />
          ) : (
            <>
              {error && <FeedbackMessage title="No se pudo crear el usuario">{error}</FeedbackMessage>}

              <form className="employee-form" onSubmit={submit}>
                <div className="form-group">
                  <label htmlFor="candidate-user-username">Usuario de Talent</label>
                  <input
                    id="candidate-user-username"
                    value={form.username}
                    onChange={(event) => setForm({ ...form, username: event.target.value.toLowerCase() })}
                    minLength={3}
                    maxLength={40}
                    autoComplete="off"
                    placeholder="Ej. jperez"
                    required
                  />
                  <small>Puedes ajustar el usuario sugerido antes de crear la cuenta.</small>
                </div>

                <div className="employee-form-grid">
                  <div className="form-group">
                    <label htmlFor="candidate-user-first-name">Nombre</label>
                    <input
                      id="candidate-user-first-name"
                      value={form.first_name}
                      onChange={(event) => setForm({ ...form, first_name: event.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="candidate-user-last-name">Apellido</label>
                    <input
                      id="candidate-user-last-name"
                      value={form.last_name}
                      onChange={(event) => setForm({ ...form, last_name: event.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="candidate-user-email">Correo</label>
                  <input
                    id="candidate-user-email"
                    type="email"
                    value={form.email}
                    onChange={(event) => setForm({ ...form, email: event.target.value })}
                    placeholder="nombre@correo.com"
                    required
                  />
                </div>

                <div className="employee-form-grid">
                  <div className="form-group">
                    <label htmlFor="candidate-user-job-title">Cargo</label>
                    <input
                      id="candidate-user-job-title"
                      value={form.job_title}
                      onChange={(event) => setForm({ ...form, job_title: event.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="candidate-user-department">Área</label>
                    <input
                      id="candidate-user-department"
                      value={form.department}
                      onChange={(event) => setForm({ ...form, department: event.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="candidate-user-hire-date">Fecha de ingreso</label>
                  <input
                    id="candidate-user-hire-date"
                    type="date"
                    value={form.hire_date}
                    onChange={(event) => setForm({ ...form, hire_date: event.target.value })}
                  />
                </div>

                <div className="employee-fixed-onboarding employee-create-onboarding">
                  <strong>Onboarding ASIATI</strong>
                  <small>Se asignará automáticamente la ruta corporativa común.</small>
                </div>

                <div className="form-actions">
                  <button className="btn btn-secondary" type="button" onClick={onClose}>Cancelar</button>
                  <button className="btn btn-primary" type="submit" disabled={saving || !form.email}>
                    {saving ? "Creando…" : "Crear usuario"}
                  </button>
                </div>
              </form>
            </>
          )}
        </section>
      </div>

      <EmployeeCredentialsModal
        open={Boolean(credentialResult?.credentials)}
        employeeName={credentialResult?.employeeName}
        credentials={credentialResult?.credentials}
        onClose={() => {
          setCredentialResult(null);
          onClose?.();
        }}
      />
    </>
  );
}
