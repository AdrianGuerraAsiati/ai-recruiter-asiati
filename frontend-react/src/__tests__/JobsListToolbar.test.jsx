// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import JobsListToolbar from "../features/jobs/JobsListToolbar";

function renderToolbar(overrides = {}) {
  const props = {
    searchValue: "backend",
    hasActiveQuery: true,
    sort: "created_desc",
    pageSize: 12,
    pageSizeOptions: [12, 24, 48],
    onSearchValueChange: vi.fn(),
    onSearchSubmit: vi.fn((event) => event.preventDefault()),
    onClearSearch: vi.fn(),
    onSortChange: vi.fn(),
    onPageSizeChange: vi.fn(),
    ...overrides,
  };

  render(<JobsListToolbar {...props} />);
  return props;
}

describe("JobsListToolbar", () => {
  it("renders controlled search, sort and page-size values", () => {
    renderToolbar();

    expect(screen.getByLabelText("Buscar vacante")).toHaveValue("backend");
    expect(screen.getByLabelText("Ordenar por")).toHaveValue("created_desc");
    expect(screen.getByLabelText("Vacantes por página")).toHaveValue("12");
    expect(screen.getByRole("button", { name: "Limpiar" })).toBeInTheDocument();
  });

  it("delegates search input, submit and clear actions", () => {
    const props = renderToolbar();

    fireEvent.change(screen.getByLabelText("Buscar vacante"), {
      target: { value: "frontend" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Buscar" }).closest("form"));
    fireEvent.click(screen.getByRole("button", { name: "Limpiar" }));

    expect(props.onSearchValueChange).toHaveBeenCalledWith("frontend");
    expect(props.onSearchSubmit).toHaveBeenCalledTimes(1);
    expect(props.onClearSearch).toHaveBeenCalledTimes(1);
  });

  it("delegates sort and page-size changes", () => {
    const props = renderToolbar();

    fireEvent.change(screen.getByLabelText("Ordenar por"), {
      target: { value: "candidates_desc" },
    });
    fireEvent.change(screen.getByLabelText("Vacantes por página"), {
      target: { value: "24" },
    });

    expect(props.onSortChange).toHaveBeenCalledWith("candidates_desc");
    expect(props.onPageSizeChange).toHaveBeenCalledWith("24");
  });

  it("hides clear when there is no active query", () => {
    renderToolbar({ hasActiveQuery: false, searchValue: "" });

    expect(screen.queryByRole("button", { name: "Limpiar" }))
      .not.toBeInTheDocument();
  });
});
