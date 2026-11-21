// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ErrorBoundary from "../components/ErrorBoundary";
import Layout from "../components/Layout";

vi.mock("../components/Navbar", () => ({
  default: () => <nav>Navegación</nav>,
}));

vi.mock("../components/Footer", () => ({
  default: () => <footer>Pie</footer>,
}));

function Boom() {
  throw new Error("fallo de render");
}

describe("ErrorBoundary", () => {
  let consoleError;

  beforeEach(() => {
    consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it("shows a Spanish fallback with a reload button instead of a blank screen", () => {
    const reload = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, reload },
    });

    try {
      render(
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>,
      );

      expect(screen.getByRole("alert")).toHaveTextContent("Algo salió mal al mostrar esta sección");
      fireEvent.click(screen.getByRole("button", { name: "Recargar" }));
      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
    }
  });

  it("keeps the layout navigation visible when a page crashes", () => {
    window.scrollTo = vi.fn();

    render(
      <MemoryRouter initialEntries={["/broken"]}>
        <Layout><Boom /></Layout>
      </MemoryRouter>,
    );

    expect(screen.getByText("Navegación")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Algo salió mal");
  });

  it("clears the error when resetKey changes", () => {
    let shouldThrow = true;
    function MaybeBoom() {
      if (shouldThrow) throw new Error("fallo");
      return <p>Contenido recuperado</p>;
    }

    const { rerender } = render(
      <ErrorBoundary resetKey="/a"><MaybeBoom /></ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();

    shouldThrow = false;
    rerender(<ErrorBoundary resetKey="/b"><MaybeBoom /></ErrorBoundary>);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Contenido recuperado")).toBeInTheDocument();
  });
});
