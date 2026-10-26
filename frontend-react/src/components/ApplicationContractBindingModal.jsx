import { useEffect, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";

function bindingEndpoint(application) {
  return "/jobs/" + encodeURIComponent(application.job.job_id)
    + "/candidates/" + encodeURIComponent(application.candidate.candidate_id)
    + "/contract/binding";
}

function bindEndpoint(application) {
  return "/jobs/" + encodeURIComponent(application.job.job_id)
    + "/candidates/" + encodeURIComponent(application.candidate.candidate_id)
    + "/contract/bind";
}

export default function ApplicationContractBindingModal({ application, onClose, onContinue }) {
  const [bindingStatus, setBindingStatus] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [companyId, setCompanyId] = useState("");
  const [loading, setLoading] = useState(true);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [companiesError, setCompaniesError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!application) return undefined;
    let active = true;
    api.get(bindingEndpoint(application))
      .then(({ data }) => {
        if (active) setBindingStatus(data);
      })
      .catch((err) => {
        if (active) {
          setError(getApiErrorMessage(err, {
            action: "consultar la vinculación contractual",
            resource: "postulación",
            fallback: "No se pudo verificar el estado del contrato. Actualiza la página antes de continuar.",
          }));
        }
      })
      .finally(() => { if (active) setLoading(false); });

    api.get("/odoo/companies")
      .then(({ data }) => {
        if (!active) return;
        setCompanies((Array.isArray(data?.items) ? data.items : [])
          .filter((item) => Number.isInteger(item?.id) && Boolean(item?.name)));
        setCompaniesError(false);
      })
      .catch(() => { if (active) setCompaniesError(true); })
      .finally(() => { if (active) setCompaniesLoading(false); });

    return () => { active = false; };
  }, [application]);

  useEffect(() => {
    if (!bindingStatus || companiesLoading) return;
    if (bindingStatus.odoo_company_id) {
      setCompanyId(String(bindingStatus.odoo_company_id));
      return;
    }
    if (!companyId) {
      const match = companies.find((item) => item.name === application?.job?.company_name);
      if (match) setCompanyId(String(match.id));
    }
  }, [application, bindingStatus, companies, companiesLoading, companyId]);

  if (!application) return null;

  const profileId = application.access?.profile_id || bindingStatus?.profile_id || "";
  const isBound = Boolean(bindingStatus?.bound && bindingStatus?.valid);
  const bindingInvalid = Boolean(bindingStatus?.bound && !bindingStatus?.valid);
  const canSubmit = Boolean(
    bindingStatus?.enabled
    && bindingStatus?.can_bind
    && companyId
    && !busy
    && !loading
    && !companiesLoading
    && !companiesError
  );

  async function submit(event) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const { data } = await api.post(bindEndpoint(application), {
        odoo_company_id: Number(companyId),
      });
      const nextCompanyId = Number(data?.odoo_company_id || companyId);
      setBindingStatus((current) => ({
        ...current,
        enabled: true,
        bound: true,
        valid: true,
        can_bind: false,
        document_approved: true,
        profile_id: profileId,
        odoo_company_id: nextCompanyId,
        status: "APPLICATION_CONTRACT_BOUND",
        message: "La vinculación quedó registrada para esta postulación y empresa Odoo.",
      }));
      setSuccess(data?.already_bound
        ? "La vinculación existente fue verificada."
        : "La vinculación quedó registrada para esta postulación y empresa Odoo.");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "vincular el contrato",
        resource: "postulación",
        fallback: "No se pudo vincular el contrato. Revisa el estado del documento y la empresa seleccionada.",
      }));
    } finally {
      setBusy(false);
    }
  }

  function continueToDocuments() {
    if (!isBound || !profileId) return;
    onContinue?.(profileId);
  }

  return (
    <div className="modal-overlay" role="presentation" onMouseDown={() => !busy && onClose?.()}>
      <section
        className="modal employee-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="application-contract-binding-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">Firma antes de contratación</span>
            <h2 id="application-contract-binding-title">Vincular contrato a la postulación</h2>
            <p>{application.candidate?.name || "Candidato"} · {application.job?.title || "Vacante"}</p>
          </div>
          <button className="btn-close" type="button" aria-label="Cerrar" disabled={busy} onClick={onClose}>×</button>
        </div>

        <p>Asocia el PDF aprobado a esta vacante y a una empresa Odoo antes de preparar la firma. El vínculo no se puede reasignar después.</p>

        {loading && <p role="status">Consultando vínculo contractual…</p>}
        {!loading && bindingStatus?.message && (
          <div className={bindingInvalid ? "alert" : "employee-credentials-warning"} role="status">
            <strong>{isBound ? "Contrato vinculado" : bindingInvalid ? "Vínculo inconsistente" : "Estado del contrato"}</strong>
            <span>{bindingStatus.message}</span>
          </div>
        )}
        {!loading && !bindingStatus?.enabled && (
          <div className="alert" role="alert">La vinculación contractual no está habilitada en este entorno.</div>
        )}
        {error && <div className="alert" role="alert">{error}</div>}
        {success && <div className="employee-credentials-warning" role="status">{success}</div>}
        {companiesError && <div className="alert" role="alert">No se pudo cargar el catálogo de empresas Odoo. No escribimos ninguna vinculación.</div>}

        <form className="employee-form" onSubmit={submit}>
          <div className="form-group">
            <label htmlFor="application-contract-odoo-company">Empresa Odoo</label>
            <select
              id="application-contract-odoo-company"
              value={companyId}
              onChange={(event) => setCompanyId(event.target.value)}
              disabled={loading || companiesLoading || Boolean(bindingStatus?.bound) || !bindingStatus?.enabled || busy}
              required
            >
              <option value="">{companiesLoading ? "Cargando empresas…" : "Selecciona una empresa"}</option>
              {companies.map((company) => (
                <option key={company.id} value={String(company.id)}>
                  {company.name}{company.country ? " · " + company.country : ""}
                </option>
              ))}
            </select>
            {companies.length === 0 && !companiesLoading && !companiesError && (
              <small>No hay empresas Odoo disponibles para seleccionar.</small>
            )}
          </div>

          {bindingStatus?.status === "CONTRACT_NOT_APPROVED" && (
            <p>Abre Documentos, carga el contrato PDF y espera a que Talento Humano lo apruebe antes de vincularlo.</p>
          )}
          {bindingStatus?.status === "CONTRACT_ALREADY_PREPARED" && (
            <p>Este documento ya entró en el flujo de firma y no se puede vincular retrospectivamente.</p>
          )}

          <div className="form-actions">
            <button className="btn btn-secondary" type="button" disabled={busy} onClick={onClose}>Cerrar</button>
            {!isBound && (
              <button className="btn btn-primary" type="submit" disabled={!canSubmit}>
                {busy ? "Vinculando…" : "Vincular contrato"}
              </button>
            )}
            {isBound && profileId && (
              <button className="btn btn-primary" type="button" onClick={continueToDocuments}>
                Continuar a Documentos
              </button>
            )}
          </div>
        </form>
      </section>
    </div>
  );
}
