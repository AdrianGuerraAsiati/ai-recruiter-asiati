// eslint-disable-next-line no-unused-vars
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MobileAttendanceCard from "../components/MobileAttendanceCard";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("../utils/mobileDeviceCrypto", () => ({
  mobileDeviceCryptoSupported: vi.fn(() => true),
  createMobileDeviceKey: vi.fn(async () => ({
    publicKeyJwk: {
      kty: "EC",
      crv: "P-256",
      x: "x-value",
      y: "y-value",
      ext: true,
    },
    privateKey: { fake: "private-key" },
  })),
  saveMobileDeviceCredential: vi.fn(async () => {}),
  loadMobileDeviceCredential: vi.fn(async () => null),
  clearMobileDeviceCredential: vi.fn(async () => {}),
  signMobileDeviceChallenge: vi.fn(async () => "signed-proof"),
}));

import api from "../api/client";
import {
  loadMobileDeviceCredential,
  signMobileDeviceChallenge,
} from "../utils/mobileDeviceCrypto";


describe("MobileAttendanceCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { items: [], total: 0 } });
    loadMobileDeviceCredential.mockResolvedValue(null);
  });

  it("requires email OTP before linking the current phone", async () => {
    api.post
      .mockResolvedValueOnce({
        data: {
          challenge_id: "link-challenge-1",
          delivery: "EMAIL",
          destination: "em***@asiati.com.co",
          expires_in_seconds: 600,
        },
      })
      .mockResolvedValueOnce({
        data: {
          id: "mobile-1",
          employee_id: "employee-1",
          label: "Mi celular",
          active: true,
          created_at: "2026-10-05T20:00:00Z",
          last_used_at: null,
        },
      });

    render(<MobileAttendanceCard />);

    fireEvent.click(await screen.findByRole("button", { name: "Verificar y vincular" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/talent-id/mobile-devices/link-otp");
    });

    fireEvent.change(screen.getByLabelText("Código de 6 dígitos"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar y vincular" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/mobile-devices",
        expect.objectContaining({
          public_key_jwk: expect.objectContaining({
            kty: "EC",
            crv: "P-256",
          }),
          link_challenge_id: "link-challenge-1",
          link_otp: "123456",
        }),
      );
    });
    expect(await screen.findByText("Celular vinculado")).toBeInTheDocument();
  });

  it("signs a challenge before requesting the dynamic QR", async () => {
    const privateKey = { fake: "private-key" };
    const device = {
      id: "mobile-1",
      employee_id: "employee-1",
      label: "Mi celular",
      active: true,
      created_at: "2026-10-05T20:00:00Z",
      last_used_at: null,
    };
    api.get.mockResolvedValue({ data: { items: [device], total: 1 } });
    loadMobileDeviceCredential.mockResolvedValue({
      deviceId: "mobile-1",
      label: "Mi celular",
      privateKey,
    });
    api.post
      .mockResolvedValueOnce({
        data: {
          challenge_id: "challenge-1",
          nonce: "nonce-value-123456789",
          message: "talent-id-qr:v1:employee-1:mobile-1:challenge-1:nonce-value-123456789",
          expires_at: "2026-10-05T20:01:00Z",
        },
      })
      .mockResolvedValueOnce({
        data: {
          qr_image: "data:image/svg+xml;base64,PHN2Zz4=",
          expires_at: new Date(Date.now() + 30000).toISOString(),
          ttl_seconds: 30,
          device,
        },
      });

    render(<MobileAttendanceCard />);

    fireEvent.click(await screen.findByRole("button", { name: "Mostrar QR para marcar" }));

    await waitFor(() => {
      expect(signMobileDeviceChallenge).toHaveBeenCalledWith(
        privateKey,
        expect.stringContaining("challenge-1"),
      );
      expect(api.post).toHaveBeenCalledWith(
        "/talent-id/mobile-qr",
        {
          device_id: "mobile-1",
          challenge_id: "challenge-1",
          nonce: "nonce-value-123456789",
          signature: "signed-proof",
        },
      );
    });
    expect(await screen.findByAltText("Código QR dinámico de Talent ID")).toBeInTheDocument();
  });
});
