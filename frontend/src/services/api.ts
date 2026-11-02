// Same-origin by default: Caddy (staging) and the Vite dev proxy both forward /api to the backend.
// Set VITE_API_URL only when the API lives on a different origin.
export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, "") || "/api";
