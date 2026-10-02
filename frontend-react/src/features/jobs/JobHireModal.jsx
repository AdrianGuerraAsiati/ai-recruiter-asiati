function JobHireModal({
  candidate,
  jobTitle,
  form,
  hiring,
  error,
  onClose,
  onFormChange,
  onSubmit,
}) {
  if (!candidate) return null;

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <section
        className="modal job-hire-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="job-hire-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">Contratación</span>
            <h2 id="job-hire-title">Contratar y crear empleado</h2>
            <p>
              Define el acceso y los datos iniciales del contrato. Se generará una
              contraseña temporal, no se enviarán correos y el onboarding ASIATI se
              asignará automáticamente.
            </p>
          </div>
          <button
            className="btn-close"
            type="button"
            aria-label="Cerrar"
            disabled={hiring}
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <form className="job-hire-form" onSubmit={onSubmit}>
          <div className="job-hire-candidate">
            <strong>{candidate.name || "Candidato"}</strong>
            <span>{jobTitle}</span>
          </div>

          {error && <div className="alert" role="alert">{error}</div>}

          <div className="job-hire-grid">
            <div className="form-group">
              <label htmlFor="hire-first-name">Nombre</label>
              <input
                id="hire-first-name"
                value={form.first_name}
                onChange={(event) => onFormChange("first_name", event.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label htmlFor="hire-last-name">Apellido</label>
              <input
                id="hire-last-name"
                value={form.last_name}
                onChange={(event) => onFormChange("last_name", event.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="hire-username">Usuario de Talent</label>
            <input
              id="hire-username"
              value={form.username}
              onChange={(event) => onFormChange("username", event.target.value.toLowerCase())}
              placeholder="Ej. jperez"
              autoComplete="off"
              required
            />
            <small>Lo define el administrador. No se usa correo para iniciar sesión.</small>
          </div>

          <div className="form-group">
            <label htmlFor="hire-email">Correo de contacto</label>
            <input
              id="hire-email"
              type="email"
              value={form.email}
              onChange={(event) => onFormChange("email", event.target.value)}
              required
            />
            <small>No se enviará ninguna invitación automática por correo.</small>
          </div>

          <div className="job-hire-grid">
            <div className="form-group">
              <label htmlFor="hire-job-title">Cargo</label>
              <input
                id="hire-job-title"
                value={form.job_title}
                onChange={(event) => onFormChange("job_title", event.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="hire-department">Área</label>
              <input
                id="hire-department"
                value={form.department}
                onChange={(event) => onFormChange("department", event.target.value)}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="hire-date">Fecha de ingreso</label>
            <input
              id="hire-date"
              type="date"
              value={form.hire_date}
              onChange={(event) => onFormChange("hire_date", event.target.value)}
              required
            />
          </div>

          <div className="job-hire-contract-section">
            <div>
              <span className="eyebrow">Contrato</span>
              <h3>Datos contractuales</h3>
              <p>
                Talent preparará el contrato y, cuando Odoo esté disponible, lo
                creará o actualizará sobre el empleado sincronizado.
              </p>
            </div>

            <div className="job-hire-grid">
              <div className="form-group">
                <label htmlFor="hire-contract-type">Tipo de contrato</label>
                <input
                  id="hire-contract-type"
                  list="hire-contract-types"
                  value={form.contract_type}
                  onChange={(event) => onFormChange("contract_type", event.target.value)}
                  placeholder="Ej. Indefinido"
                  required
                />
                <datalist id="hire-contract-types">
                  <option value="Indefinido" />
                  <option value="Término fijo" />
                  <option value="Obra o labor" />
                  <option value="Aprendizaje" />
                  <option value="Prestación de servicios" />
                </datalist>
              </div>
              <div className="form-group">
                <label htmlFor="hire-monthly-wage">Salario mensual</label>
                <input
                  id="hire-monthly-wage"
                  type="number"
                  min="1"
                  step="1000"
                  inputMode="numeric"
                  value={form.monthly_wage}
                  onChange={(event) => onFormChange("monthly_wage", event.target.value)}
                  placeholder="Ej. 3500000"
                  required
                />
              </div>
            </div>

            <div className="job-hire-grid">
              <div className="form-group">
                <label htmlFor="hire-contract-start-date">Inicio del contrato</label>
                <input
                  id="hire-contract-start-date"
                  type="date"
                  value={form.contract_start_date}
                  onChange={(event) => onFormChange("contract_start_date", event.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="hire-contract-end-date">Finalización</label>
                <input
                  id="hire-contract-end-date"
                  type="date"
                  value={form.contract_end_date}
                  min={form.contract_start_date || undefined}
                  onChange={(event) => onFormChange("contract_end_date", event.target.value)}
                />
                <small>Déjala vacía cuando el contrato no tenga fecha de finalización.</small>
              </div>
            </div>
          </div>

          <div className="form-actions">
            <button
              className="btn btn-secondary"
              type="button"
              disabled={hiring}
              onClick={onClose}
            >
              Cancelar
            </button>
            <button className="btn btn-primary" type="submit" disabled={hiring}>
              {hiring ? "Contratando…" : "Confirmar contratación"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default JobHireModal;
