// eslint-disable-next-line no-unused-vars
import React, { useMemo, useState } from "react";

import PageHeader from "../components/ui/PageHeader";
import { useSession } from "../context/SessionContext";

const DOCUMENTS = [
  { id: "identity", label: "Documento de identidad", help: "Cédula o documento de identificación vigente.", required: true },
  { id: "bank", label: "Certificación bancaria", help: "Certificado de la cuenta donde se realizarán los pagos.", required: true },
  { id: "rut", label: "RUT", help: "Registro Único Tributario actualizado, cuando aplique.", required: true },
  { id: "social_security", label: "Seguridad social", help: "Soporte de EPS y fondo de pensión, cuando aplique.", required: true },
  { id: "other", label: "Otros soportes", help: "Documentos adicionales solicitados por Talento Humano.", required: false },
];

function EmployeeDocuments() {
  const { principal } = useSession();
  const profile = principal?.profile || {};
  const [files, setFiles] = useState({});
  const [accepted, setAccepted] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const required = DOCUMENTS.filter((item) => item.required);
  const ready = useMemo(
    () => required.every((item) => Boolean(files[item.id])) && accepted,
    [files, accepted, required],
  );
  const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(" ") || "Nuevo empleado";

  function selectFile(id, file) {
    if (!file) return;
    setFiles((current) => ({ ...current, [id]: file }));
    setSubmitted(false);
  }

  return (
    <div className="page employee-documents-page">
      <PageHeader
        eyebrow="Vinculación"
        title="Mis documentos"
        description="Completa tu expediente de ingreso. Talento Humano revisará la información antes de generar el contrato."
      />

      <div className="employee-documents-layout">
        <section className="panel employee-documents-main">
          <div className="employee-documents-intro">
            <div>
              <span className="eyebrow">Expediente de contratación</span>
              <h2>{fullName}</h2>
              <p>{principal?.email}</p>
            </div>
            <span className={`document-status ${ready ? "is-ready" : ""}`}>
              {ready ? "Listo para revisión" : `${Object.keys(files).length}/${required.length} obligatorios`}
            </span>
          </div>

          <div className="employee-document-list">
            {DOCUMENTS.map((document) => (
              <label className="employee-document-row" key={document.id}>
                <div className="employee-document-copy">
                  <div className="employee-document-title">
                    <strong>{document.label}</strong>
                    {document.required && <span>Obligatorio</span>}
                  </div>
                  <p>{document.help}</p>
                  {files[document.id] && <small>Seleccionado: {files[document.id].name}</small>}
                </div>
                <span className="btn btn-secondary btn-sm">
                  {files[document.id] ? "Cambiar" : "Adjuntar"}
                  <input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png"
                    hidden
                    onChange={(event) => selectFile(document.id, event.target.files?.[0])}
                  />
                </span>
              </label>
            ))}
          </div>

          <label className="employee-document-consent">
            <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
            <span>Confirmo que los documentos corresponden a mi información y autorizo su uso para el proceso de vinculación.</span>
          </label>

          <div className="employee-documents-actions">
            <button className="btn btn-primary" type="button" disabled={!ready} onClick={() => setSubmitted(true)}>
              Enviar a Talento Humano
            </button>
            {submitted && <span className="document-submitted">Expediente preparado para revisión.</span>}
          </div>
        </section>

        <aside className="panel contract-readiness-card">
          <span className="eyebrow">Contrato</span>
          <h2>Preparación para Odoo</h2>
          <p>El contrato se genera después de validar los documentos y los datos laborales del empleado.</p>
          <div className="contract-data-list">
            <div><span>Cargo</span><strong>{profile.job_title || "Pendiente"}</strong></div>
            <div><span>Área</span><strong>{profile.department || "Pendiente"}</strong></div>
            <div><span>Fecha de ingreso</span><strong>{profile.hire_date || "Pendiente"}</strong></div>
          </div>
          <div className="contract-flow">
            <span className="is-done">1. Documentos</span>
            <span>2. Revisión TH</span>
            <span>3. Generación en Odoo</span>
            <span>4. Firma</span>
          </div>
          <p className="muted">La firma del contrato será la confirmación final del proceso de contratación.</p>
        </aside>
      </div>
    </div>
  );
}

export default EmployeeDocuments;
