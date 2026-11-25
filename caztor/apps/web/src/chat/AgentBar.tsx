import { useEffect, useRef, useState } from "react";
import type { ChatAgent } from "./papersmith-agents.ts";
import "./AgentBar.css";

interface AgentBarProps {
  /** The chat agents this workspace has, in the order they are offered. */
  agents: readonly ChatAgent[];
  active: string | null;
  onChange: (name: string | null) => void;
}

/**
 * Switches that make the next messages go to one of the workspace's PaperSmith agents, until switched off. Switching
 * one on sends nothing: the agent waits for the user's question.
 */
export function AgentBar({ agents, active, onChange }: AgentBarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (!menu.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);
  if (agents.length === 0) return null;
  const primary = agents.filter((agent) => agent.primary);
  const more = agents.filter((agent) => !agent.primary);
  const current = agents.find((agent) => agent.name === active) ?? null;
  const toggle = (name: string) => onChange(active === name ? null : name);
  return (
    <div className="agent-bar">
      <div className="agent-bar__row" role="group" aria-label="PaperSmith agents">
        {primary.map((agent) => (
          <button key={agent.name} type="button" className="agent-bar__agent" aria-pressed={active === agent.name} onClick={() => toggle(agent.name)}>
            {agent.label}
          </button>
        ))}
        {more.length === 0 ? null : (
          <div className="agent-bar__more" ref={menu}>
            <button type="button" className="agent-bar__agent" aria-haspopup="menu" aria-expanded={menuOpen} aria-pressed={more.some((agent) => agent.name === active)} onClick={() => setMenuOpen(!menuOpen)}>
              {more.find((agent) => agent.name === active)?.label ?? "More"} ▾
            </button>
            {menuOpen ? (
              <ul role="menu" className="agent-bar__menu">
                {more.map((agent) => (
                  <li key={agent.name} role="none">
                    <button
                      type="button"
                      role="menuitemcheckbox"
                      aria-checked={active === agent.name}
                      onClick={() => {
                        toggle(agent.name);
                        setMenuOpen(false);
                      }}
                    >
                      {agent.label}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </div>
      {current === null ? null : (
        <div className="agent-bar__status" role="status">
          <span>
            The <strong>{current.label}</strong> answers your next messages
          </span>
          <button type="button" className="agent-bar__link" onClick={() => onChange(null)}>
            Stop
          </button>
        </div>
      )}
    </div>
  );
}
