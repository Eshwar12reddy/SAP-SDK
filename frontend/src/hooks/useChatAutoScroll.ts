import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

const BOTTOM_THRESHOLD_PX = 100;

type ScrollBehavior = "auto" | "smooth" | "instant";

export function useChatAutoScroll(messages: { role: string; content: string }[], conversationId: number | null) {
  const scrollRef = useRef<HTMLElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const pinnedToBottomRef = useRef(true);
  const lastConversationRef = useRef<number | null>(conversationId);
  const previousMessageCountRef = useRef(messages.length);
  const [isAtBottom, setIsAtBottom] = useState(true);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const element = scrollRef.current;
    if (!element) return;
    pinnedToBottomRef.current = true;
    setIsAtBottom(true);
    requestAnimationFrame(() => {
      const current = scrollRef.current;
      if (!current) return;
      if (behavior === "instant") current.scrollTop = current.scrollHeight;
      else current.scrollTo({ top: current.scrollHeight, behavior });
    });
  }, []);

  const handleScroll = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    const atBottom = element.scrollHeight - element.clientHeight - element.scrollTop <= BOTTOM_THRESHOLD_PX;
    pinnedToBottomRef.current = atBottom;
    setIsAtBottom(atBottom);
  }, []);

  useLayoutEffect(() => {
    const conversationChanged = lastConversationRef.current !== conversationId;
    const newUserMessage = messages.length > previousMessageCountRef.current && messages[messages.length - 1]?.role === "user";
    lastConversationRef.current = conversationId;
    previousMessageCountRef.current = messages.length;

    if (conversationChanged) scrollToBottom("instant");
    else if (newUserMessage) scrollToBottom("smooth");
    else if (pinnedToBottomRef.current) scrollToBottom("auto");
  }, [messages, conversationId, scrollToBottom]);

  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (pinnedToBottomRef.current) scrollToBottom("auto");
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [scrollToBottom]);

  return { scrollRef, contentRef, isAtBottom, handleScroll, scrollToBottom };
}
