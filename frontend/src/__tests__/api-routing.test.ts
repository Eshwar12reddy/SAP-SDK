import { describe, expect, it } from "vitest";
import { API_URL } from "../services/api";
import en from "../locales/en.json";
import ar from "../locales/ar.json";

describe("API routing", () => {
  it("defaults to same-origin /api so it works behind the HTTPS reverse proxy", () => {
    expect(API_URL).toBe("/api");
    expect(API_URL).not.toMatch(/localhost|:8000|^https?:/);
  });
});

describe("locales", () => {
  it("English and Arabic define the same keys", () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort());
  });
});
