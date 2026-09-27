// eslint-disable-next-line no-unused-vars
import React from "react";
import Icon from "./Icon";

export function LoadingState({ label = "Cargando…", compact = false, className = "" }) {
  return (
    <div className={`page-loading ui-loading-state ${compact ? "compact-loading" : ""} ${className}`.trim()} role="status" aria-live="polite">
      <span aria-hidden="true" />
      <span className="ui-loading-label">{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon = "info",
  compact = false,
  className = "",
}) {
  return (
    <div className={`empty-state ui-empty-state ${compact ? "compact" : ""} ${className}`.trim()}>
      <span className="ui-empty-icon" aria-hidden="true"><Icon name={icon} size={20} /></span>
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action}
    </div>
  );
}

export function FeedbackMessage({ tone = "error", title, children, className = "" }) {
  const icon = tone === "success" ? "check" : tone === "warning" ? "warning" : tone === "info" ? "info" : "error";
  const role = tone === "error" ? "alert" : "status";

  return (
    <div className={`ui-feedback ui-feedback--${tone} ${className}`.trim()} role={role}>
      <span className="ui-feedback-icon" aria-hidden="true"><Icon name={icon} size={18} /></span>
      <div>
        {title ? <strong>{title}</strong> : null}
        <div className="ui-feedback-copy">{children}</div>
      </div>
    </div>
  );
}

export function ProgressBar({ value = 0, label, showValue = false, className = "" }) {
  const normalized = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className={`ui-progress ${className}`.trim()}>
      {(label || showValue) && (
        <div className="ui-progress-copy">
          <span>{label}</span>
          {showValue ? <strong>{normalized}%</strong> : null}
        </div>
      )}
      <div className="ui-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={normalized} aria-label={label || "Progreso"}>
        <i style={{ width: `${normalized}%` }} />
      </div>
    </div>
  );
}

export function MetricCard({ icon, label, value, detail, tone = "neutral", live = false }) {
  return (
    <article className={`metric-card metric-${tone} ui-metric-card`}>
      <div className="metric-top">
        {icon ? <span className="metric-icon" aria-hidden="true"><Icon name={icon} size={19} /></span> : <span />}
        {live ? <span className="metric-trend"><i /> En vivo</span> : null}
      </div>
      <strong className="metric-value">{value}</strong>
      <span className="metric-label">{label}</span>
      {detail ? <small>{detail}</small> : null}
    </article>
  );
}
