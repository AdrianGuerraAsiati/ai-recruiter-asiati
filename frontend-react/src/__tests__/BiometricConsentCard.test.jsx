// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BiometricConsentCard from "../components/BiometricConsentCard";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from "../api/client";


function consentPayload(status = "PENDING") {
  return {
    employee_id: "employee-1",
    status,
    signed_at: status === "AUTHORIZED" ? "2026-10-06T14:30:00+00:00" : null,
    document_version: "1.2",
    accepted_document_version: status === "AUTHORIZED" ? "1.2" : null,
    document_sha256: "d".repeat(64),
    pdf_sha256: status === "AUTHORIZED" ? "p".repeat(64) : null,
    verified_email: "an***@asiati.com.co",
    has_signed_document: status === "AUTHORIZED",
    last_decision: status === "PENDING" ? null : status,
    document: {
      title: "Autorización para el tratamiento de datos biométricos - Talent ID",
      version: "1.2",
      text: "Declaro que ASIATI me informó sobre el tratamiento biométrico.\n\nLa autorización es voluntaria.",
    },
  };
}


describe("BiometricConsentCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("requires the checkbox and records authorization without OTP", async () => {
    let status = "PENDING";
    api.get.mockImplementation((url) => {
      if (url !== "/talent-id/consent") {
        return Promise.reject(new Error(`Unexpected GET ${url}`));
      }
      return Promise.resolve({ data: consentPayload(status) });
    });
    api.post.mockImplementation((url, body) => {
      if (url === "/talent-id/consent/accept") {
        expect(body).toEqual({
          document_version: "1.2",
          confirmed: true,
        });
        status = "AUTHORIZED";
        return Promise.resolve({ data: consentPayload(status) });
      }
      return Promise.reject(new Error(`Unexpected POST ${url}`));
    });

    render(<BiometricConsentCard />);

    expect(await screen.findByText("Pendiente")).toBeInTheDocument();
    const acceptButton = screen.getByRole("button", { name: "Aceptar y continuar" });
    expect(acceptButton).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox"));
    expect(acceptButton).toBeEnabled();
    fireEvent.click(acceptButton);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/consent/accept",
        {
          document_version: "1.2",
          confirmed: true,
        },
      );
    });

    expect(await screen.findByText("Autorizado")).toBeInTheDocument();
    expect(screen.getByText("Autorización biométrica registrada")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("opens the authorization text and revokes with explicit confirmation", async () => {
    let status = "AUTHORIZED";
    api.get.mockImplementation((url) => {
      if (url !== "/talent-id/consent") {
        return Promise.reject(new Error(`Unexpected GET ${url}`));
      }
      return Promise.resolve({ data: consentPayload(status) });
    });
    api.post.mockImplementation((url, body) => {
      if (url === "/talent-id/consent/revoke") {
        expect(body).toEqual({
          document_version: "1.2",
          confirmed: true,
        });
        status = "REVOKED";
        return Promise.resolve({ data: consentPayload(status) });
      }
      return Promise.reject(new Error(`Unexpected POST ${url}`));
    });

    render(<BiometricConsentCard />);

    expect(await screen.findByText("Autorizado")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ver autorización" }));
    expect(await screen.findByText(/declaro que ASIATI me informó/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Revocar autorización" }));
    expect(screen.getByText(/Talent ID dejará de usar reconocimiento facial/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Confirmar revocación" }));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/consent/revoke",
        {
          document_version: "1.2",
          confirmed: true,
        },
      );
    });

    expect(await screen.findByText("Revocado")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
  });
});
