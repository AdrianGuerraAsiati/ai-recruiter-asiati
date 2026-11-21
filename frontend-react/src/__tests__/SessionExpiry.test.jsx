// eslint-disable-next-line no-unused-vars
import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AUTH_EXPIRED_EVENT, emitAuthExpired } from "../api/authEvents";
import { resolvePostLoginPath } from "../auth/redirect";

const clientState = vi.hoisted(() => ({
  token: null,
  get: vi.fn(),
  post: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("../api/client", () => ({
  default: {
    get: clientState.get,
    post: clientState.post,
  },
  getAccessToken: () => clientState.token,
  setAccessToken: (token) => {
    clientState.token = token;
  },
  clearAccessToken: () => {
    clientState.token = null;
  },
  refreshAccessToken: clientState.refresh,
}));

import App from "../App";

const principal = {
  email: "admin@asiati.com.co",
  roles: ["ADMIN"],
  permissions: ["profile.read_own"],
  profile: { id: "admin-1", first_name: "Katherine", last_name: "Admin", email: "admin@asiati.com.co" },
};

async function login() {
  fireEvent.change(await screen.findByLabelText("Usuario"), { target: { value: "admin@asiati.com.co" } });
  fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "secret-password" } });
  fireEvent.click(screen.getByRole("button", { name: /Iniciar sesión/i }));
}

describe("resolvePostLoginPath", () => {
  it.each([
    [{ pathname: "/profile", search: "?tab=1", hash: "#datos" }, "/profile?tab=1#datos"],
    ["/candidates/abc?job_id=1", "/candidates/abc?job_id=1"],
    ["//evil.example/phish", "/dashboard"],
    ["/\\evil.example", "/dashboard"],
    ["https://evil.example", "/dashboard"],
    ["/login", "/dashboard"],
    ["/", "/dashboard"],
    [undefined, "/dashboard"],
    [null, "/dashboard"],
  ])("maps %j to %s", (from, expected) => {
    expect(resolvePostLoginPath(from)).toBe(expected);
  });
});

describe("session expiry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clientState.token = null;
    clientState.post.mockImplementation((url) => {
      if (url === "/auth/login") return Promise.resolve({ data: { access_token: "access-token" } });
      return Promise.resolve({ data: {} });
    });
    clientState.get.mockImplementation((url) => {
      if (url === "/auth/me") return Promise.resolve({ data: principal });
      return Promise.resolve({ data: {} });
    });
    window.scrollTo = vi.fn();
  });

  it("returns to the originally requested page after logging in", async () => {
    clientState.refresh.mockRejectedValue(new Error("anonymous"));
    window.history.pushState({}, "", "/profile");

    render(<App />);
    await login();

    expect(await screen.findByRole("heading", { name: "Mi perfil" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/profile");
  });

  it("sends the user to login when the API reports an expired session", async () => {
    clientState.token = "access-token";
    window.history.pushState({}, "", "/profile");

    render(<App />);
    expect(await screen.findByRole("heading", { name: "Mi perfil" })).toBeInTheDocument();

    clientState.refresh.mockRejectedValue(new Error("expired"));
    await act(async () => {
      emitAuthExpired({ url: "/profile/me" });
    });

    expect(await screen.findByLabelText("Usuario")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");

    await login();
    expect(await screen.findByRole("heading", { name: "Mi perfil" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/profile");
  });

  it("uses a stable event name", () => {
    expect(AUTH_EXPIRED_EVENT).toBe("auth:expired");
  });
});
