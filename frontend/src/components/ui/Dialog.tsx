import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Simple centered modal (no external deps). Used for export confirmations,
// AI summary regeneration confirmation, etc.
//
// Accessibility: traps focus inside the dialog while open (Tab/Shift+Tab
// wrap around instead of escaping to the page behind the backdrop), closes
// on Escape, and restores focus to whatever triggered it on close — without
// these, a keyboard/screen-reader user opening a dialog would lose their
// place in the page entirely.
export default function Dialog({
  open,
  onClose,
  title,
  children,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  size?: "md" | "xl";
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const dialogEl = dialogRef.current;
    const focusable = dialogEl?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    const initialFocus = dialogEl?.querySelector<HTMLElement>("[data-dialog-initial-focus]");
    (initialFocus ?? focusable?.[0] ?? dialogEl)?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !dialogEl) return;

      const nodes = dialogEl.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-on-surface/40" onClick={onClose} aria-hidden="true" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`relative w-full ${size === "xl" ? "max-w-6xl" : "max-w-md"} bg-surface-container-lowest border border-border rounded-lg shadow-[0_4px_24px_rgba(0,0,0,0.15)] overflow-hidden`}
      >
        <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-surface-container-lowest">
          <h3 id={titleId} className="text-headline-sm font-semibold text-on-surface">
            {title}
          </h3>
          <button
            onClick={onClose}
            className="p-1 rounded-full text-on-surface-variant hover:text-primary hover:bg-surface-container-low"
            aria-label="Chiudi"
          >
            <Icon name="close" size={18} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
