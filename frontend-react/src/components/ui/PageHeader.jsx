export default function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className = "",
  children,
}) {
  return (
    <header className={`page-header ui-page-header ${actions ? "ui-page-header--with-actions" : ""} ${className}`.trim()}>
      <div className="ui-page-header-copy">
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
        {children}
      </div>
      {actions ? <div className="ui-page-header-actions">{actions}</div> : null}
    </header>
  );
}
