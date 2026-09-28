import React from "react";

import { compactPageNumbers } from "./jobUtils";

function JobsPagination({ currentPage, totalPages, onPageChange }) {
  if (totalPages <= 1) return null;

  const visiblePages = compactPageNumbers(totalPages, currentPage);

  return (
    <nav className="jobs-pagination" aria-label="Paginación de vacantes">
      <button
        type="button"
        className="jobs-page-button jobs-page-edge"
        disabled={currentPage <= 1}
        onClick={() => onPageChange(currentPage - 1)}
      >
        ‹ Anterior
      </button>

      <div className="jobs-page-numbers">
        {visiblePages.map((pageNumber, index) => {
          const previous = visiblePages[index - 1];
          return (
            <React.Fragment key={pageNumber}>
              {previous && pageNumber - previous > 1 && (
                <span className="jobs-page-ellipsis" aria-hidden="true">…</span>
              )}
              <button
                type="button"
                className={`jobs-page-button ${pageNumber === currentPage ? "is-active" : ""}`}
                aria-current={pageNumber === currentPage ? "page" : undefined}
                aria-label={`Página ${pageNumber}`}
                onClick={() => onPageChange(pageNumber)}
              >
                {pageNumber}
              </button>
            </React.Fragment>
          );
        })}
      </div>

      <button
        type="button"
        className="jobs-page-button jobs-page-edge"
        disabled={currentPage >= totalPages}
        onClick={() => onPageChange(currentPage + 1)}
      >
        Siguiente ›
      </button>
    </nav>
  );
}

export default JobsPagination;
