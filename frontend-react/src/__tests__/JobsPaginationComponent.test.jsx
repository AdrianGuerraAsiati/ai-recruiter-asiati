// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import JobsPagination from "../features/jobs/JobsPagination";

describe("JobsPagination component", () => {
  it("renders nothing for a single page", () => {
    const { container } = render(
      <JobsPagination currentPage={1} totalPages={1} onPageChange={vi.fn()} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders compact page buttons with current-page semantics", () => {
    render(
      <JobsPagination currentPage={6} totalPages={12} onPageChange={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: "Página 6" }))
      .toHaveAttribute("aria-current", "page");
    expect(screen.getAllByText("…")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Página 4" }))
      .not.toBeInTheDocument();
  });

  it("delegates edge and direct page changes", () => {
    const onPageChange = vi.fn();
    render(
      <JobsPagination currentPage={2} totalPages={4} onPageChange={onPageChange} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /anterior/i }));
    fireEvent.click(screen.getByRole("button", { name: "Página 4" }));
    fireEvent.click(screen.getByRole("button", { name: /siguiente/i }));

    expect(onPageChange).toHaveBeenNthCalledWith(1, 1);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 4);
    expect(onPageChange).toHaveBeenNthCalledWith(3, 3);
  });

  it("disables previous on first page and next on last page", () => {
    const { rerender } = render(
      <JobsPagination currentPage={1} totalPages={3} onPageChange={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: /anterior/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /siguiente/i })).toBeEnabled();

    rerender(
      <JobsPagination currentPage={3} totalPages={3} onPageChange={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: /anterior/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /siguiente/i })).toBeDisabled();
  });
});
