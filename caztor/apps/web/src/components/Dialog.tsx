import { useEffect, useId, useRef, type FocusEvent, type KeyboardEvent, type ReactNode } from "react";
import "./Dialog.css";

interface DialogProps {
  title: string;
  children: ReactNode;
  /** The buttons, right-aligned. The first focusable one receives focus when the dialog opens. */
  actions: ReactNode;
  /** Called when the user presses Escape. A dialog without it can only be closed by one of its actions. */
  onDismiss?: () => void;
}

const FOCUSABLE_ACTION = "button:not(:disabled)";
const FOCUSABLE = 'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';

/** Marks every region outside `backdrop` inert and returns the function that undoes only what it changed. */
function makeBackgroundInert(backdrop: HTMLElement): () => void {
  const changed: HTMLElement[] = [];
  for (let node: HTMLElement = backdrop; node.parentElement !== null; node = node.parentElement) {
    for (const sibling of node.parentElement.children) {
      if (sibling === node || !(sibling instanceof HTMLElement) || sibling.hasAttribute("inert")) continue;
      sibling.setAttribute("inert", "");
      changed.push(sibling);
    }
  }
  return () => {
    for (const element of changed) element.removeAttribute("inert");
  };
}

/** Where focus goes when the element that opened a dialog is gone: the pane it lived in, else any pane. */
function focusHome(origin: HTMLElement | null, home: HTMLElement | null): void {
  if (origin?.isConnected) {
    origin.focus();
    return;
  }
  const target = home?.isConnected ? home : document.querySelector<HTMLElement>("[data-focus-home]");
  target?.focus();
}

const FOCUS_WATCH_MS = 2000;

/**
 * After a dialog closes, the element that opened it may still be removed by a re-render that waits for the server
 * (a confirmed delete). Watches the page for a short time and moves focus to the pane when the browser drops it
 * on the body; stops at the first sign that the user moved focus or at the time limit.
 */
function keepFocusAlive(origin: HTMLElement | null, home: HTMLElement | null): void {
  const lost = () => document.activeElement === null || document.activeElement === document.body;
  const observer = new MutationObserver(() => {
    if (lost()) focusHome(origin, home);
  });
  const stop = () => {
    observer.disconnect();
    clearTimeout(timer);
    document.removeEventListener("focusin", stop);
    document.removeEventListener("pointerdown", stop, true);
    document.removeEventListener("keydown", stop, true);
  };
  const timer = setTimeout(stop, FOCUS_WATCH_MS);
  observer.observe(document.body, { childList: true, subtree: true });
  document.addEventListener("focusin", stop);
  document.addEventListener("pointerdown", stop, true);
  document.addEventListener("keydown", stop, true);
}

/**
 * A modal dialog: labelled, focus moves in on open, Tab stays inside, the rest of the page is inert, and focus
 * returns to where it was (or to the pane it was in when that element has been removed).
 */
export function Dialog({ title, children, actions, onDismiss }: DialogProps) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const backdrop = useRef<HTMLDivElement>(null);
  const pendingCheck = useRef(0);

  /** Puts focus back on an enabled control inside the dialog (or the dialog itself) when it has left. */
  function keepFocusInside(): void {
    const current = panel.current;
    if (current === null || current.contains(document.activeElement)) return;
    const target = current.querySelector<HTMLElement>(`.dialog__actions ${FOCUSABLE_ACTION}`) ?? current;
    target.focus();
  }

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const home = previous?.closest<HTMLElement>("[data-focus-home]") ?? null;
    const current = panel.current;
    const outside = backdrop.current;
    if (current === null || outside === null) return;
    const restoreBackground = makeBackgroundInert(outside);
    current.querySelector<HTMLElement>(`.dialog__actions ${FOCUSABLE_ACTION}`)?.focus();
    // A control that becomes disabled loses focus without any event in some browsers, so watch for the attribute too.
    const observer = new MutationObserver(keepFocusInside);
    observer.observe(current, { attributes: true, attributeFilter: ["disabled"], subtree: true, childList: true });
    document.addEventListener("focusin", keepFocusInside);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(pendingCheck.current);
      document.removeEventListener("focusin", keepFocusInside);
      restoreBackground();
      focusHome(previous, home);
      keepFocusAlive(previous, home);
    };
  }, []);

  function onBlur(event: FocusEvent<HTMLDivElement>): void {
    const next = event.relatedTarget;
    if (next instanceof Node && panel.current?.contains(next)) return;
    // Check on the next frame, not in a microtask: during a native Tab the body is focused between the blur and the
    // focus of the next control, and a microtask would run in that gap and pull focus back to the first button.
    cancelAnimationFrame(pendingCheck.current);
    pendingCheck.current = requestAnimationFrame(keepFocusInside);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Escape" && onDismiss !== undefined) {
      event.stopPropagation();
      onDismiss();
    }
    if (event.key !== "Tab" || panel.current === null) return;
    const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const first = items[0];
    const last = items[items.length - 1];
    if (first === undefined || last === undefined) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div ref={backdrop} className="dialog__backdrop" onKeyDown={onKeyDown} onBlur={onBlur}>
      <div ref={panel} className="dialog" role="dialog" tabIndex={-1} aria-modal="true" aria-labelledby={titleId}>
        <h2 id={titleId} className="dialog__title">
          {title}
        </h2>
        <div className="dialog__body">{children}</div>
        <div className="dialog__actions">{actions}</div>
      </div>
    </div>
  );
}
