import { useState } from "react";

type Props = { content: string; onEdit: () => void };

export function UserMessageActions({ content, onEdit }: Props) {
  const [notice, setNotice] = useState("");

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(content);
      setNotice("Prompt copied");
    } catch {
      setNotice("Copy unavailable");
    }
    globalThis.setTimeout(() => setNotice(""), 1800);
  }

  async function sharePrompt() {
    try {
      const share = (navigator as Navigator & { share?: (data: ShareData) => Promise<void> }).share;
      if (typeof share === "function") {
        await share.call(navigator, { title: "SAP BRIM AI prompt", text: content });
        setNotice("Prompt shared");
      } else {
        await navigator.clipboard.writeText(content);
        setNotice("Prompt copied to share");
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      setNotice("Share unavailable");
    }
    globalThis.setTimeout(() => setNotice(""), 1800);
  }

  return (
    <div className="user-message-actions" role="group" aria-label="Prompt actions">
      <button type="button" aria-label="Copy prompt" title={notice || "Copy prompt"} onClick={() => void copyPrompt()}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="7" width="12" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2"/></svg>
      </button>
      <button type="button" aria-label="Share prompt" title="Share prompt" onClick={() => void sharePrompt()}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V3m-4 4 4-4 4 4M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/></svg>
      </button>
      <button type="button" aria-label="Edit prompt" title="Edit prompt" onClick={onEdit}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5 4 4M4 20l4-.8L19 8a2.8 2.8 0 0 0-4-4L4 15l-.8 5Z"/></svg>
      </button>
      {notice && <span className="user-action-notice" role="status">{notice}</span>}
    </div>
  );
}
