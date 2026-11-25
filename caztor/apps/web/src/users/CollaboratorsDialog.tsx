import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { ApiClient, Collaborator, CollaboratorInvite, CollaboratorKey } from "../api/types.ts";
import { Dialog } from "../components/Dialog.tsx";
import "./CollaboratorsDialog.css";

interface CollaboratorsDialogProps {
  api: ApiClient;
  onClose: () => void;
  /** Puts text on the clipboard. Tests replace it; the default is the browser's clipboard. */
  copy?: (text: string) => Promise<void>;
  /** The clock expiries are shown against. Tests replace it. */
  now?: () => number;
}

const MINUTE_MS = 60_000;
const DAY_MINUTES = 24 * 60;
/** The server's bounds for a key's lifetime. */
const MIN_MINUTES = 10;
const MAX_MINUTES = 365 * DAY_MINUTES;
const LIFETIME_REFUSED = "Choose how long the key lasts: from 10 minutes to 365 days.";
const CUSTOM = "custom";
const LIFETIMES = [
  { minutes: 60, label: "1 hour" },
  { minutes: DAY_MINUTES, label: "1 day" },
  { minutes: 7 * DAY_MINUTES, label: "7 days" },
  { minutes: 30 * DAY_MINUTES, label: "30 days" },
] as const;
const DEFAULT_LIFETIME = String(7 * DAY_MINUTES);

const browserCopy = (text: string) => navigator.clipboard.writeText(text);
const messageOf = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback);
const plural = (count: number, unit: string) => `${count} ${unit}${count === 1 ? "" : "s"}`;

/**
 * How long is left, rounded to the nearest whole unit: `in 6 days`, `in 3 hours`, `in 25 minutes`. A key made for one
 * day reads "in 1 day" right after, not "in 23 hours".
 */
export function timeLeft(ms: number): string {
  const minutes = Math.max(1, Math.round(ms / MINUTE_MS));
  if (minutes < 60) return `in ${plural(minutes, "minute")}`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `in ${plural(hours, "hour")}`;
  return `in ${plural(Math.round(minutes / DAY_MINUTES), "day")}`;
}

function statusOf(person: Collaborator): string {
  return person.sessions > 0 ? `Signed in on ${plural(person.sessions, "browser")}` : "Not signed in";
}

function keyState(key: CollaboratorKey, index: number, now: number): string {
  const label = `Key ${index + 1}`;
  if (key.status === "old") return `${label}: old invite, create a new one`;
  if (key.status === "locked") return `${label}: locked after 10 wrong keys`;
  if (key.status === "expired" || key.expiresAt <= now) return `${label}: expired`;
  const used = key.sessions > 0 ? `on ${plural(key.sessions, "browser")}` : "not used yet";
  return `${label}: expires ${timeLeft(key.expiresAt - now)}, ${used}`;
}

/** Host only: who is invited, an invite link plus access key per person, the expiry of every key, and revoking. */
export function CollaboratorsDialog({ api, onClose, copy = browserCopy, now = Date.now }: CollaboratorsDialogProps) {
  const [people, setPeople] = useState<Collaborator[] | null>(null);
  const [name, setName] = useState("");
  const [lifetime, setLifetime] = useState<string>(DEFAULT_LIFETIME);
  const [until, setUntil] = useState("");
  const [invite, setInvite] = useState<CollaboratorInvite | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPeople(await api.listCollaborators());
    } catch (error) {
      setProblem(messageOf(error, "The collaborators could not be listed."));
    }
  }, [api]);

  useEffect(() => void refresh(), [refresh]);

  /** The minutes asked for, or null when the custom date is missing or out of bounds. */
  function minutesWanted(): number | null {
    if (lifetime !== CUSTOM) return Number(lifetime);
    const at = new Date(until).getTime();
    if (Number.isNaN(at)) return null;
    const minutes = Math.ceil((at - now()) / MINUTE_MS);
    return minutes >= MIN_MINUTES && minutes <= MAX_MINUTES ? minutes : null;
  }

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setProblem(null);
    setCopied(null);
    const minutes = minutesWanted();
    if (minutes === null) {
      setProblem(LIFETIME_REFUSED);
      return;
    }
    try {
      setInvite(await api.inviteCollaborator(name.trim(), minutes));
      setName("");
      await refresh();
    } catch (error) {
      setProblem(messageOf(error, "The invite could not be created."));
    }
  }

  async function copyText(text: string, what: "link" | "key"): Promise<void> {
    try {
      await copy(text);
      setCopied(what === "link" ? "Link copied." : "Key copied.");
    } catch {
      setCopied(`Select the ${what} and copy it.`);
    }
  }

  async function revoke(person: Collaborator): Promise<void> {
    setProblem(null);
    try {
      await api.revokeCollaborator(person.id);
      if (invite?.user.id === person.id) setInvite(null);
      await refresh();
    } catch (error) {
      setProblem(messageOf(error, `${person.name} could not be revoked.`));
    }
  }

  async function revokeKey(person: Collaborator, key: CollaboratorKey, index: number): Promise<void> {
    setProblem(null);
    try {
      await api.revokeCollaboratorKey(key.id);
      if (invite?.inviteId === key.id) setInvite(null);
      await refresh();
    } catch (error) {
      setProblem(messageOf(error, `Key ${index + 1} of ${person.name} could not be revoked.`));
    }
  }

  const at = now();

  return (
    <Dialog
      title="Collaborators"
      onDismiss={onClose}
      actions={
        <button type="button" className="button" onClick={onClose}>
          Close
        </button>
      }
    >
      <p>Each invite is a link and an access key. The link opens a page that asks for the key; the key signs in any number of browsers until it expires. Send them only to the person they name.</p>
      <form className="collaborators__invite" onSubmit={(event) => void submit(event)}>
        <input className="text-input" aria-label="Name" placeholder="Name" value={name} onChange={(event) => setName(event.target.value)} />
        <select className="collaborators__lifetime" aria-label="Key lasts" value={lifetime} onChange={(event) => setLifetime(event.target.value)}>
          {LIFETIMES.map((option) => (
            <option key={option.minutes} value={String(option.minutes)}>
              {option.label}
            </option>
          ))}
          <option value={CUSTOM}>Until a date and time</option>
        </select>
        {lifetime === CUSTOM ? (
          <input className="text-input collaborators__until" type="datetime-local" aria-label="Key ends at" value={until} onChange={(event) => setUntil(event.target.value)} />
        ) : null}
        <button type="submit" className="button button--primary" disabled={name.trim() === ""}>
          Invite
        </button>
      </form>
      {invite === null ? null : (
        <div className="collaborators__made">
          <div className="collaborators__link">
            <input className="text-input" readOnly aria-label={`Invite link for ${invite.user.name}`} value={invite.link} onFocus={(event) => event.target.select()} />
            <button type="button" className="button" onClick={() => void copyText(invite.link, "link")}>
              Copy link
            </button>
          </div>
          <div className="collaborators__link">
            <input className="text-input collaborators__key" readOnly aria-label={`Access key for ${invite.user.name}`} value={invite.key} onFocus={(event) => event.target.select()} />
            <button type="button" className="button" onClick={() => void copyText(invite.key, "key")}>
              Copy key
            </button>
          </div>
          <p className="collaborators__note">{`Expires ${new Date(invite.expiresAt).toLocaleString()} (${timeLeft(invite.expiresAt - at)}).`}</p>
          <p className="collaborators__note collaborators__warning">The key is shown only now: copy it before you close this. Send the link and the key apart if you can.</p>
          {copied === null ? null : <span role="status">{copied}</span>}
        </div>
      )}
      {problem === null ? null : <p role="alert">{problem}</p>}
      {people === null ? null : people.length === 0 ? (
        <p className="collaborators__empty">Nobody is invited yet.</p>
      ) : (
        <ul className="collaborators__list" aria-label="Collaborators">
          {people.map((person) => (
            <li key={person.id} className="collaborators__entry">
              <div className="collaborators__person">
                <span className="collaborators__name">{person.name}</span>
                <span className="collaborators__status">{statusOf(person)}</span>
                <button type="button" className="button button--danger" aria-label={`Revoke ${person.name}`} onClick={() => void revoke(person)}>
                  Revoke
                </button>
              </div>
              {person.invites.length === 0 ? null : (
                <ul className="collaborators__keys" aria-label={`Keys of ${person.name}`}>
                  {person.invites.map((key, index) => (
                    <li key={key.id} className="collaborators__key-row">
                      <span className="collaborators__key-state">{keyState(key, index, at)}</span>
                      <button type="button" className="button" aria-label={`Revoke key ${index + 1} of ${person.name}`} onClick={() => void revokeKey(person, key, index)}>
                        Revoke key
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}
