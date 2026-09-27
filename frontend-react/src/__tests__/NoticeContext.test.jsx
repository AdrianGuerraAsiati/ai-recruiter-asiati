// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NoticeProvider, useNotice } from "../context/NoticeContext";

function Trigger() {
  const { notify } = useNotice();
  return (
    <button
      type="button"
      onClick={() => notify({
        tone: "success",
        title: "Guardado",
        message: "Los cambios quedaron confirmados.",
        timeout: 0,
      })}
    >
      Notificar
    </button>
  );
}

describe("NoticeProvider", () => {
  it("shows and dismisses non-blocking feedback", () => {
    render(
      <NoticeProvider>
        <Trigger />
      </NoticeProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Notificar" }));

    expect(screen.getByText("Guardado")).toBeInTheDocument();
    expect(screen.getByText("Los cambios quedaron confirmados.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cerrar notificación" }));
    expect(screen.queryByText("Guardado")).not.toBeInTheDocument();
  });
});
