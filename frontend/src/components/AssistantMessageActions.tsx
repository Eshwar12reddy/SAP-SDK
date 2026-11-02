import { useEffect, useState } from "react";

type IconName = "copy" | "like" | "dislike" | "speak" | "share" | "regenerate" | "more";

function Icon({ name }: { name: IconName }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (name) {
    case "copy": return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="7" width="12" height="14" rx="2" {...common}/><path d="M16 7V5a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2" {...common}/></svg>;
    case "like": return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v10H4a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2h3Zm0 0 5-7a3 3 0 0 1 2 3v4h4a2 2 0 0 1 2 2l-1 6a2 2 0 0 1-2 2H7" {...common}/></svg>;
    case "dislike": return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 14V4H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h3Zm0 0 5 7a3 3 0 0 0 2-3v-4h4a2 2 0 0 0 2-2l-1-6a2 2 0 0 0-2-2H7" {...common}/></svg>;
    case "speak": return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5Z" {...common}/><path d="M15 9a5 5 0 0 1 0 6m3-9a9 9 0 0 1 0 12" {...common}/></svg>;
    case "share": return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V3m-4 4 4-4 4 4M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" {...common}/></svg>;
    case "regenerate": return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5" {...common}/><path d="M5.5 9A7 7 0 0 1 18 6l2 6M4 12l2 6a7 7 0 0 0 12.5-3" {...common}/></svg>;
    case "more": return <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="19" cy="12" r="1" fill="currentColor"/></svg>;
  }
}

type AssistantMessageActionsProps = {
  content: string;
  messageKey: string;
  canRegenerate: boolean;
  onRegenerate: () => void;
};

function makeFeedbackKey(messageKey: string, content: string) {
  let hash = 2166136261;
  for (let index = 0; index < content.length; index += 1) {
    hash = Math.imul(hash ^ content.charCodeAt(index), 16777619);
  }
  return `sap-brim-feedback:${messageKey}:${(hash >>> 0).toString(16)}`;
}

function readFeedback(key: string): "like" | "dislike" | null {
  try {
    const value = localStorage.getItem(key);
    return value === "like" || value === "dislike" ? value : null;
  } catch {
    return null;
  }
}

async function copyText(text: string) {
  await navigator.clipboard.writeText(text);
}

export function AssistantMessageActions({ content, messageKey, canRegenerate, onRegenerate }: AssistantMessageActionsProps) {
  const [responseComplete, setResponseComplete] = useState(() => document.body.dataset.assistantResponseComplete !== "false");
  const feedbackKey = makeFeedbackKey(messageKey, content);
  const [feedback, setFeedback] = useState<"like" | "dislike" | null>(() => readFeedback(feedbackKey));
  const [notice, setNotice] = useState("");
  const [moreOpen, setMoreOpen] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => setFeedback(readFeedback(feedbackKey)), [feedbackKey]);
  useEffect(() => {
    const observer = new MutationObserver(() => setResponseComplete(document.body.dataset.assistantResponseComplete !== "false"));
    observer.observe(document.body, { attributes: true, attributeFilter: ["data-assistant-response-complete"] });
    return () => observer.disconnect();
  }, []);

  if (!responseComplete || !content.trim()) return null;

  function rateResponse(value: "like" | "dislike") {
    const next = feedback === value ? null : value;
    setFeedback(next);
    setNotice(next === "like" ? "Marked helpful" : next === "dislike" ? "Marked not helpful" : "Rating removed");
    try {
      if (next) localStorage.setItem(feedbackKey, next);
      else localStorage.removeItem(feedbackKey);
    } catch {
      // The selected rating still works for this page when storage is unavailable.
    }
    globalThis.setTimeout(() => setNotice(""), 1800);
  }

  async function copyResponse() {
    try {
      await copyText(content);
      setNotice("Copied");
    } catch {
      setNotice("Copy unavailable");
    }
    window.setTimeout(() => setNotice(""), 1800);
  }

  async function shareResponse() {
    try {
      const share = (navigator as Navigator & { share?: (data: ShareData) => Promise<void> }).share;
      if (typeof share === "function") await share.call(navigator, { title: "SAP BRIM AI response", text: content });
      else await copyText(content);
      setNotice(typeof share === "function" ? "Shared" : "Copied to share");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      setNotice("Share unavailable");
    }
    globalThis.setTimeout(() => setNotice(""), 1800);
  }

  function toggleSpeech() {
    const speech = (window as Window & { speechSynthesis?: SpeechSynthesis }).speechSynthesis;
    if (!speech || typeof SpeechSynthesisUtterance === "undefined") {
      setNotice("Audio unavailable");
      globalThis.setTimeout(() => setNotice(""), 1800);
      return;
    }
    if (speaking) {
      speech.cancel();
      setSpeaking(false);
      return;
    }
    speech.cancel();
    const utterance = new SpeechSynthesisUtterance(content);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    speech.speak(utterance);
    setSpeaking(true);
  }

  return (
    <div className="assistant-action-area">
      <div className="assistant-message-actions" role="group" aria-label="Assistant response actions">
        <button type="button" aria-label="Copy response" title={notice || "Copy response"} onClick={() => void copyResponse()}><Icon name="copy"/></button>
        <button type="button" className={feedback === "like" ? "is-rated" : ""} aria-label={feedback === "like" ? "Remove helpful rating" : "Mark helpful"} title={feedback === "like" ? "Helpful" : "Mark helpful"} aria-pressed={feedback === "like"} onClick={() => rateResponse("like")}><Icon name="like"/></button>
        <button type="button" className={feedback === "dislike" ? "is-rated" : ""} aria-label={feedback === "dislike" ? "Remove not helpful rating" : "Mark not helpful"} title={feedback === "dislike" ? "Not helpful" : "Mark not helpful"} aria-pressed={feedback === "dislike"} onClick={() => rateResponse("dislike")}><Icon name="dislike"/></button>
        <button type="button" aria-label={speaking ? "Stop reading aloud" : "Read response aloud"} title={speaking ? "Stop reading aloud" : "Read aloud"} aria-pressed={speaking} onClick={toggleSpeech}><Icon name="speak"/></button>
        <button type="button" aria-label="Share response" title="Share response" onClick={() => void shareResponse()}><Icon name="share"/></button>
        {canRegenerate && <button type="button" aria-label="Regenerate response" title="Regenerate response" onClick={onRegenerate}><Icon name="regenerate"/></button>}
        <button type="button" aria-label="More response actions" title="More" aria-expanded={moreOpen} onClick={() => setMoreOpen(!moreOpen)}><Icon name="more"/></button>
      </div>
      {notice && <span className="assistant-action-notice" role="status">{notice}</span>}
      {moreOpen && <div className="assistant-action-menu">
        <button type="button" onClick={() => { setMoreOpen(false); void copyResponse(); }}>Copy response</button>
        <button type="button" onClick={() => { setMoreOpen(false); void shareResponse(); }}>Share response</button>
        {canRegenerate && <button type="button" onClick={() => { setMoreOpen(false); onRegenerate(); }}>Regenerate response</button>}
      </div>}
    </div>
  );
}
