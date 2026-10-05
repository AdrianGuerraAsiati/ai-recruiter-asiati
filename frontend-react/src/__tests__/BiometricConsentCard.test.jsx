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
    signed_at: status === "PENDING" ? null : "2026-10-05T19:10:00+00:00",
    document_version: "1.0",
    document_sha256: "d".repeat(64),
    pdf_sha256: status === "PENDING" ? null : "p".repeat(64),
    verified_email: "an***@asiati.com.co",
    has_signed_document: status !== "PENDING",
    document: {
      title: "Autorización para el tratamiento de datos biométricos - Talent ID",
      version: "1.0",
      text: "Declaro que ASIATI me informó sobre el tratamiento biométrico.\n\nLa autorización es voluntaria.",
    },
  };
}


describe("BiometricConsentCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("signs an authorization with an OTP and refreshes the status", async () => {
    let status = "PENDING";
    api.get.mockImplementation((url) => {
      if (url !== "/talent-id/consent") {
        return Promise.reject(new Error(`Unexpected GET ${url}`));
      }
      return Promise.resolve({ data: consentPayload(status) });
    });
    api.post.mockImplementation((url, body) => {
      if (url === "/talent-id/consent/otp") {
        return Promise.resolve({
          data: {
            challenge_id: "challenge-1",
            delivery: "EMAIL",
            destination: "an***@asiati.com.co",
            expires_in_seconds: 600,
          },
        });
      }
      if (url === "/talent-id/consent/sign") {
        expect(body).toEqual({
          decision: "AUTHORIZED",
          otp: "123456",
          document_version: "1.0",
        });
        status = "AUTHORIZED";
        return Promise.resolve({ data: consentPayload(status) });
      }
      return Promise.reject(new Error(`Unexpected POST ${url}`));
    });

    render(<BiometricConsentCard />);

    expect(await screen.findByText("Pendiente")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Autorizar biometría" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/consent/otp",
        {
          decision: "AUTHORIZED",
          document_version: "1.0",
        },
      );
    });
    expect(await screen.findByText(/enviamos un código de 6 dígitos/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Código de 6 dígitos"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar y firmar" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/consent/sign",
        {
          decision: "AUTHORIZED",
          otp: "123456",
          document_version: "1.0",
        },
      );
    });
    expect(await screen.findByText("Autorizado")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revocar autorización" })).toBeInTheDocument();
  });

  it("keeps the biometric decision independent and offers non-authorization", async () => {
    api.get.mockResolvedValue({ data: consentPayload("PENDING") });
    api.post.mockResolvedValue({
      data: {
        challenge_id: "challenge-2",
        delivery: "EMAIL",
        destination: "an***@asiati.com.co",
        expires_in_seconds: 600,
      },
    });

    render(<BiometricConsentCard />);

    expect(await screen.findByText(/tu decisión es independiente del uso corporativo/i)).toBeInTheDocument();
    expect(screen.getByText(/alternativa de marcación no biométrica/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "No autorizar" }));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/consent/otp",
        {
          decision: "DENIED",
          document_version: "1.0",
        },
      );
    });
    expect(await screen.findByRole("heading", { name: "No autorizar biometría" })).toBeInTheDocument();
  });
});
