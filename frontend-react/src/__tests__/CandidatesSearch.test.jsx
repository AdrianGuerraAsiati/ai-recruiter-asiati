// eslint-disable-next-line no-unused-vars
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Candidates from "../pages/Candidates";

vi.mock("../context/SessionContext", () => ({
  useSession: () => ({ hasPermission: () => false }),
}));

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("../features/candidate-import/CandidateImportModal.jsx", () => ({
  default: () => null,
}));

import api from "../api/client";

function page(items) {
  return { data: { items, total: items.length, page: 1, page_size: 20, pages: 1 } };
}

function renderCandidates() {
  return render(
    <MemoryRouter>
      <Candidates />
    </MemoryRouter>,
  );
}

function candidateCalls() {
  return api.get.mock.calls.map(([url]) => url).filter((url) => url.startsWith("/candidates"));
}

describe("Candidates search", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("debounces typing into a single request and loads /jobs only once", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/jobs") return Promise.resolve({ data: [{ job_id: "job-1", title: "Backend" }] });
      if (url.includes("q=ana")) return Promise.resolve(page([{ candidate_id: "c-ana", name: "Ana Filtrada" }]));
      return Promise.resolve(page([{ candidate_id: "c-1", name: "Primer Perfil" }]));
    });

    renderCandidates();
    await screen.findByText("Primer Perfil");
    expect(candidateCalls()).toEqual(["/candidates?page=1&page_size=20"]);

    vi.useFakeTimers();
    const input = screen.getByLabelText("Buscar candidatos");
    fireEvent.change(input, { target: { value: "a" } });
    fireEvent.change(input, { target: { value: "an" } });
    fireEvent.change(input, { target: { value: "ana" } });

    await act(async () => {
      vi.advanceTimersByTime(249);
    });
    expect(candidateCalls()).toHaveLength(1);

    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    vi.useRealTimers();

    expect(await screen.findByText("Ana Filtrada")).toBeInTheDocument();
    expect(candidateCalls()).toEqual([
      "/candidates?page=1&page_size=20",
      "/candidates?page=1&page_size=20&q=ana",
    ]);
    expect(api.get.mock.calls.filter(([url]) => url === "/jobs")).toHaveLength(1);
  });

  it("ignores a slower response from an older search", async () => {
    const pending = {};
    api.get.mockImplementation((url) => {
      if (url === "/jobs") return Promise.resolve({ data: [] });
      if (url.includes("q=")) {
        return new Promise((resolve) => { pending[new URL(url, "http://x").searchParams.get("q")] = resolve; });
      }
      return Promise.resolve(page([{ candidate_id: "c-1", name: "Primer Perfil" }]));
    });

    renderCandidates();
    await screen.findByText("Primer Perfil");
    const input = screen.getByLabelText("Buscar candidatos");

    fireEvent.change(input, { target: { value: "lu" } });
    await waitFor(() => expect(pending.lu).toBeTypeOf("function"));
    fireEvent.change(input, { target: { value: "luis" } });
    await waitFor(() => expect(pending.luis).toBeTypeOf("function"));

    await act(async () => {
      pending.luis(page([{ candidate_id: "c-luis", name: "Luis Reciente" }]));
    });
    expect(await screen.findByText("Luis Reciente")).toBeInTheDocument();

    await act(async () => {
      pending.lu(page([{ candidate_id: "c-lu", name: "Lucía Antigua" }]));
    });

    expect(screen.queryByText("Lucía Antigua")).not.toBeInTheDocument();
    expect(screen.getByText("Luis Reciente")).toBeInTheDocument();
  });
});
