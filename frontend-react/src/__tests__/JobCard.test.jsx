// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import JobCard from "../features/jobs/JobCard";

const JOB = {
  job_id: "job-1",
  title: "Backend Developer",
  description: "Python APIs REST",
  active_description_source: "ai",
  city: "Bogotá",
  country_code: "CO",
  candidate_count: 1,
  status: "ACTIVE",
};

function renderCard(overrides = {}, callbacks = {}) {
  const job = { ...JOB, ...overrides };
  const onView = callbacks.onView || vi.fn();
  const onEdit = callbacks.onEdit || vi.fn();
  const onDelete = callbacks.onDelete || vi.fn();

  render(
    <MemoryRouter>
      <JobCard
        job={job}
        onView={onView}
        onEdit={onEdit}
        onDelete={onDelete}
      />
    </MemoryRouter>,
  );

  return { job, onView, onEdit, onDelete };
}

describe("JobCard", () => {
  it("renders source, location, candidate count and candidates link", () => {
    renderCard();

    expect(screen.getByText("Backend Developer")).toBeInTheDocument();
    expect(screen.getByText("IA")).toBeInTheDocument();
    expect(screen.getByText("Bogotá · Colombia")).toBeInTheDocument();
    expect(screen.getByText("1 candidato asignado")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Agregar candidatos" }))
      .toHaveAttribute("href", "/candidates?job_id=job-1");
  });

  it("falls back to Indeed and pluralizes candidate count", () => {
    renderCard({
      active_description_source: "indeed",
      candidate_count: 2,
      city: "",
      country_code: "",
    });

    expect(screen.getByText("Indeed")).toBeInTheDocument();
    expect(screen.getByText("2 candidatos asignados")).toBeInTheDocument();
    expect(screen.queryByText("Bogotá · CO")).not.toBeInTheDocument();
  });

  it("renders paused vacancies explicitly", () => {
    renderCard({ status: "PAUSED" });

    expect(screen.getByText("Pausada")).toBeInTheDocument();
    expect(screen.queryByText("Activa")).not.toBeInTheDocument();
  });

  it("delegates view, edit and delete actions with the job", () => {
    const handlers = {
      onView: vi.fn(),
      onEdit: vi.fn(),
      onDelete: vi.fn(),
    };
    const { job } = renderCard({}, handlers);

    fireEvent.click(screen.getByRole("button", { name: "Ver" }));
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    expect(handlers.onView).toHaveBeenCalledWith(job);
    expect(handlers.onEdit).toHaveBeenCalledWith(job);
    expect(handlers.onDelete).toHaveBeenCalledWith(job);
  });
});
