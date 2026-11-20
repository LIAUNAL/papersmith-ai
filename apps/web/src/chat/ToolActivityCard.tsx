import { useId, useState } from "react";
import type { ChatItem } from "@caztor/core";
import { Icon } from "../components/Icon.tsx";
import "./ToolActivityCard.css";

type Tool = Extract<ChatItem, { kind: "tool" }>;

const STATUS_LABEL: Record<Tool["status"], string> = { running: "Running", done: "Done", failed: "Failed", interrupted: "Interrupted" };

/** One tool the agent used, as a compact card: what it is, the file it touched and how it went. Details open on request. */
export function ToolActivityCard({ tool }: { tool: Tool }) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const hasDetails = tool.title !== undefined || tool.summary !== undefined;
  const row = (
    <>
      <span className="tool-card__name">{tool.name}</span>
      {tool.path === undefined ? null : <span className="tool-card__path">{tool.path}</span>}
      <span className={`tool-card__status tool-card__status--${tool.status}`}>{STATUS_LABEL[tool.status]}</span>
    </>
  );
  return (
    <div className={`tool-card tool-card--${tool.status}`}>
      {hasDetails ? (
        <button type="button" className="tool-card__row tool-card__row--button" aria-expanded={open} aria-controls={detailsId} onClick={() => setOpen(!open)}>
          {row}
          <Icon name="chevron" className={`tool-card__chevron${open ? " tool-card__chevron--open" : ""}`} />
        </button>
      ) : (
        <div className="tool-card__row">{row}</div>
      )}
      {hasDetails && open ? (
        <div id={detailsId} className="tool-card__details">
          {tool.title === undefined ? null : <p>{tool.title}</p>}
          {tool.summary === undefined ? null : <p>{tool.summary}</p>}
        </div>
      ) : null}
    </div>
  );
}
