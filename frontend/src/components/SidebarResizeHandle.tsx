import { useRef, type KeyboardEvent, type PointerEvent } from "react";
import { getSidebarMaxWidth, SIDEBAR_MIN_WIDTH } from "../hooks/useResizableSidebar";

type SidebarResizeHandleProps = {
  width: number;
  onResize: (width: number) => void;
  onReset: () => void;
  onResizeStart: () => void;
  onResizeEnd: () => void;
};

export function SidebarResizeHandle({ width, onResize, onReset, onResizeStart, onResizeEnd }: SidebarResizeHandleProps) {
  const dragRef = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null);

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (window.matchMedia("(max-width: 650px)").matches) return;

    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { pointerId: event.pointerId, startX: event.clientX, startWidth: width };
    onResizeStart();
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    onResize(drag.startWidth + event.clientX - drag.startX);
  }

  function finishPointer(event: PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    onResizeEnd();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 25 : 10;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      onResize(width - step);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      onResize(width + step);
    } else if (event.key === "Home") {
      event.preventDefault();
      onResize(SIDEBAR_MIN_WIDTH);
    } else if (event.key === "End") {
      event.preventDefault();
      onResize(getSidebarMaxWidth());
    }
  }

  return (
    <div
      className="sidebar-resize-handle"
      role="separator"
      aria-label="Resize sidebar"
      aria-orientation="vertical"
      aria-valuemin={SIDEBAR_MIN_WIDTH}
      aria-valuemax={getSidebarMaxWidth()}
      aria-valuenow={width}
      aria-valuetext={`${width} pixels`}
      tabIndex={0}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishPointer}
      onPointerCancel={finishPointer}
      onLostPointerCapture={onResizeEnd}
      onDoubleClick={onReset}
      onKeyDown={handleKeyDown}
    />
  );
}
