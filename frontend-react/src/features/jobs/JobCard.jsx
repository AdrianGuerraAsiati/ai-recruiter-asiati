import { Link } from "react-router-dom";

import Icon from "../../components/ui/Icon";
import { countryFlag, countryName } from "../../data/countries";
import { titleCase } from "../../utils/text";

function JobCard({ job, onView, onEdit, onDelete, onToggleStatus, statusBusy = false }) {
  const candidateCount = job.candidate_count || 0;
  const location = [job.company_name, job.city, countryName(job.country_code)].filter(Boolean).join(" · ");
  const paused = job.status === "PAUSED";
  const country = countryName(job.country_code) || "País sin definir";
  const flag = countryFlag(job.country_code);

  return (
    <article className="job-card">
      <div className="job-card-top">
        <span className="job-card-icon" aria-hidden="true">
          <Icon name="briefcase" size={18} />
        </span>
        <div className="job-card-badges">
          <span
            className="job-country-flag"
            role="img"
            aria-label={`País: ${country}`}
            title={country}
          >
            {flag}
          </span>
          <span className={`status-pill ${paused ? "is-paused" : ""}`}>
            <i /> {paused ? "Pausada" : "Activa"}
          </span>
        </div>
      </div>

      <h3>{titleCase(job.title)}</h3>
      <p>{job.description}</p>

      <p className="job-description-source-meta">
        Descripción activa:{" "}
        <strong>{job.active_description_source === "ai" ? "IA" : "Indeed"}</strong>
      </p>

      {location && <p className="muted">{location}</p>}

      <p className="muted">
        {candidateCount} candidato{candidateCount === 1 ? "" : "s"} asignado{candidateCount === 1 ? "" : "s"}
      </p>

      <div className="job-card-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => onView(job)}
        >
          Ver
        </button>
        <button
          type="button"
          className={paused ? "btn btn-primary" : "btn btn-secondary"}
          onClick={() => onToggleStatus(job)}
          disabled={statusBusy}
          aria-label={paused ? `Activar ${job.title}` : `Desactivar ${job.title}`}
        >
          {statusBusy ? "Actualizando…" : paused ? "Activar" : "Desactivar"}
        </button>
        <Link
          className="btn btn-primary"
          to={`/candidates?job_id=${job.job_id}`}
        >
          Agregar candidatos
        </Link>
        <Link
          className="btn btn-secondary"
          to={`/ranking?job_id=${encodeURIComponent(job.job_id)}`}
          aria-label={`Ver ranking de ${job.title}`}
        >
          Ver ranking
        </Link>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => onEdit(job)}
        >
          Editar
        </button>
        <button
          type="button"
          className="btn btn-danger"
          onClick={() => onDelete(job)}
        >
          Eliminar
        </button>
      </div>
    </article>
  );
}

export default JobCard;
