import { useCallback, useEffect, useState } from "react";

export const SIDEBAR_WIDTH_STORAGE_KEY = "sap-brim-sidebar-width";
export const SIDEBAR_MIN_WIDTH = 200;
export const SIDEBAR_MAX_WIDTH = 420;
export const SIDEBAR_DEFAULT_WIDTH = 260;

export function getSidebarMaxWidth() {
  if (typeof window === "undefined") return SIDEBAR_MAX_WIDTH;
  // Reserve enough room for a usable chat pane and the resize handle.
  return Math.max(SIDEBAR_MIN_WIDTH, Math.min(SIDEBAR_MAX_WIDTH, window.innerWidth - 326));
}

function clampWidth(width: number) {
  return Math.min(getSidebarMaxWidth(), Math.max(SIDEBAR_MIN_WIDTH, width));
}

function readSavedWidth() {
  try {
    const saved = Number(localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));
    return Number.isFinite(saved) && saved > 0 ? clampWidth(saved) : SIDEBAR_DEFAULT_WIDTH;
  } catch {
    return SIDEBAR_DEFAULT_WIDTH;
  }
}

export function useResizableSidebar() {
  const [width, setWidth] = useState(readSavedWidth);

  const resizeTo = useCallback((nextWidth: number) => {
    setWidth(clampWidth(nextWidth));
  }, []);

  const resetWidth = useCallback(() => {
    setWidth(clampWidth(SIDEBAR_DEFAULT_WIDTH));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(width));
    } catch {
      // The sidebar remains resizable when storage is unavailable.
    }
  }, [width]);

  useEffect(() => {
    const handleWindowResize = () => setWidth((current) => clampWidth(current));
    window.addEventListener("resize", handleWindowResize);
    return () => window.removeEventListener("resize", handleWindowResize);
  }, []);

  return { width, resizeTo, resetWidth, maxWidth: getSidebarMaxWidth() };
}
