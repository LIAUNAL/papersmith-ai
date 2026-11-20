import { useState } from "react";
import { Dialog } from "../components/Dialog.tsx";
import "./NoticeBanner.css";

interface NoticeBannerProps {
  level: "info" | "warning";
  message: string;
  /** What the chat can offer next to the notice. */
  action?: "replace_definition";
  onReplace?: () => void;
}

/** A short note in the conversation. The one action it can carry asks for confirmation before it overwrites anything. */
export function NoticeBanner({ level, message, action, onReplace }: NoticeBannerProps) {
  const [confirming, setConfirming] = useState(false);
  return (
    <div className={`notice notice--${level}`}>
      <p className="notice__message">{message}</p>
      {action === "replace_definition" && onReplace !== undefined ? (
        <button type="button" className="button notice__action" onClick={() => setConfirming(true)}>
          Replace definition
        </button>
      ) : null}
      {confirming ? (
        <Dialog
          title="Replace the agent definition?"
          onDismiss={() => setConfirming(false)}
          actions={
            <>
              <button type="button" className="button" onClick={() => setConfirming(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="button button--primary"
                onClick={() => {
                  setConfirming(false);
                  onReplace?.();
                }}
              >
                Replace
              </button>
            </>
          }
        >
          <p>You changed the assistant's definition file in this project. Replacing it writes Caztor's version over your changes. Your own edits to it are lost.</p>
        </Dialog>
      ) : null}
    </div>
  );
}
