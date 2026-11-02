import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

async function renderApp() {
  document.body.innerHTML = '<div id="root"></div>';
  vi.resetModules();
  await import("../main");
}

function submit(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
}

describe("authentication flow", () => {
  beforeEach(() => {
    localStorage.clear();
    Element.prototype.scrollTo = vi.fn();
    window.matchMedia = window.matchMedia || ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false }) as MediaQueryList);
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("shows the sign-in screen when there is no token", async () => {
    await renderApp();
    expect(await screen.findByLabelText("Email")).toBeTruthy();
  });

  it("requires email and password before calling the API", async () => {
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    await renderApp();
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Email and password are required.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts credentials to same-origin /api/auth/login and surfaces the server error", async () => {
    const fetchMock = vi.fn((_url: string) => jsonResponse(401, { detail: "Invalid email or password" })); vi.stubGlobal("fetch", fetchMock);
    await renderApp();
    await screen.findByLabelText("Email"); submit("a@b.co", "wrong-password");
    expect(await screen.findByText("Invalid email or password")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/login");
    expect(localStorage.getItem("token")).toBeNull();
  });

  it("reports an unreachable backend without crashing", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    await renderApp();
    await screen.findByLabelText("Email"); submit("a@b.co", "password-1");
    expect(await screen.findByText("Failed to fetch")).toBeTruthy();
  });

  it("stores the token on successful login", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/auth/login") ? jsonResponse(200, { access_token: "tok", token_type: "bearer" }) : jsonResponse(200, [])));
    await renderApp();
    await screen.findByLabelText("Email"); submit("a@b.co", "password-1");
    await waitFor(() => expect(localStorage.getItem("token")).toBe("tok"));
  });
});
