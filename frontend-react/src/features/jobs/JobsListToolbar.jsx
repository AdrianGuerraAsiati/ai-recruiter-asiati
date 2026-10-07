function JobsListToolbar({
  searchValue,
  hasActiveQuery,
  sort,
  pageSize,
  pageSizeOptions,
  country,
  countryOptions,
  onSearchValueChange,
  onSearchSubmit,
  onClearSearch,
  onSortChange,
  onPageSizeChange,
  onCountryChange,
}) {
  return (
    <div className="jobs-list-toolbar">
      <form className="jobs-search" onSubmit={onSearchSubmit}>
        <label className="jobs-filter jobs-search-filter">
          <span>Buscar vacante</span>
          <input
            aria-label="Buscar vacante"
            type="search"
            placeholder="Título de la vacante"
            value={searchValue}
            onChange={(event) => onSearchValueChange(event.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-secondary">Buscar</button>
        {hasActiveQuery && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onClearSearch}
          >
            Limpiar
          </button>
        )}
      </form>

      <div className="jobs-list-filters">
        <label className="jobs-filter">
          <span>País</span>
          <select
            aria-label="Filtrar vacantes por país"
            value={country}
            onChange={(event) => onCountryChange(event.target.value)}
          >
            <option value="">Todos los países</option>
            {countryOptions.map((item) => (
              <option key={item.code} value={item.code}>{item.name}</option>
            ))}
          </select>
        </label>
        <label className="jobs-filter">
          <span>Ordenar por</span>
          <select
            aria-label="Ordenar por"
            value={sort}
            onChange={(event) => onSortChange(event.target.value)}
          >
            <option value="created_desc">Más recientes</option>
            <option value="created_asc">Más antiguas</option>
            <option value="candidates_desc">Más candidatos</option>
            <option value="candidates_asc">Menos candidatos</option>
            <option value="title_asc">Nombre A–Z</option>
            <option value="title_desc">Nombre Z–A</option>
          </select>
        </label>

        <label className="jobs-filter">
          <span>Vacantes por página</span>
          <select
            aria-label="Vacantes por página"
            value={String(pageSize)}
            onChange={(event) => onPageSizeChange(event.target.value)}
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}

export default JobsListToolbar;
