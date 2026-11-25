import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import type { LoginKey, LoginMethod, LoginView, ProviderId } from "../api/types.ts";
import { Dialog } from "../components/Dialog.tsx";
import type { LoginApi } from "./controller.ts";
import { PROVIDER_META } from "./providers.ts";
import "./LoginDialog.css";

interface LoginDialogProps {
  provider: ProviderId;
  api: LoginApi;
  /** How often the CLI's text is read again while the sign-in runs. */
  pollMs: number;
  /** The sign-in ended: the providers are read again so its state shows. */
  onEnded: () => void;
  onClose: () => void;
}

const LINK = /(https?:\/\/[^\s<>"'`]+)/;
const KEYS: Array<{ key: LoginKey; label: string }> = [
  { key: "up", label: "Up" },
  { key: "down", label: "Down" },
  { key: "enter", label: "Enter" },
  { key: "escape", label: "Esc" },
];
const messageOf = (error: unknown, fallback: string) => (error instanceof Error && error.message !== "" ? error.message : fallback);

/** The CLI's text, with every web address a link that opens in a new tab and leaves this page alone. */
function RelayedText({ text }: { text: string }) {
  return (
    <pre className="login-dialog__text" aria-label="Sign-in output" aria-live="polite">
      {text.split(LINK).map((part, index) =>
        index % 2 === 1 ? (
          <a key={index} href={part} target="_blank" rel="noopener noreferrer">
            {part}
          </a>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </pre>
  );
}

/**
 * Signs the person in to the provider's CLI on the host: the CLI's text relayed from the server, the device code ready
 * to copy, a box for the code a web page gives back, and the menu keys when the CLI runs in a terminal.
 */
export function LoginDialog({ provider, api, pollMs, onEnded, onClose }: LoginDialogProps) {
  const name = PROVIDER_META[provider].name;
  const [methods, setMethods] = useState<LoginMethod[] | null>(null);
  const [login, setLogin] = useState<LoginView | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [line, setLine] = useState("");
  const [copied, setCopied] = useState(false);
  const endedOnce = useRef(false);
  const running = login?.state === "running";

  async function start(method?: string) {
    setProblem(null);
    try {
      const started = await api.startLogin(provider, method);
      setLogin(started.login);
    } catch (error) {
      setProblem(messageOf(error, "The sign-in could not be started."));
    }
  }

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const listed = await api.followLogin(provider);
        if (!alive) return;
        setMethods(listed.methods);
        if (listed.methods.length <= 1) await start(listed.methods[0]?.id);
      } catch (error) {
        if (alive) setProblem(messageOf(error, "The sign-in could not be started."));
      }
    })();
    return () => void (alive = false);
    // The dialog starts once per opening.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => {
      void api.followLogin(provider).then(
        (listed) => {
          if (listed.login !== null) setLogin(listed.login);
        },
        () => {},
      );
    }, pollMs);
    return () => clearInterval(timer);
  }, [api, provider, pollMs, running]);

  useEffect(() => {
    if (login === null || login.state === "running" || endedOnce.current) return;
    endedOnce.current = true;
    onEnded();
  }, [login, onEnded]);

  async function send(input: { line: string } | { key: LoginKey }) {
    setProblem(null);
    try {
      setLogin(await api.sendLogin(provider, input));
    } catch (error) {
      setProblem(messageOf(error, "That could not be sent."));
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (line.trim() === "") return;
    const sent = line;
    setLine("");
    void send({ line: sent });
  }

  async function close() {
    if (running) await api.cancelLogin(provider).catch(() => {});
    onClose();
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const choosing = login === null && methods !== null && methods.length > 1;
  return (
    <Dialog
      title={`Sign in to ${name}`}
      onDismiss={() => void close()}
      actions={
        <button type="button" className="button" onClick={() => void close()}>
          {running || login === null ? "Cancel" : "Close"}
        </button>
      }
    >
      {choosing ? (
        <div className="login-dialog__methods" role="group" aria-label="How to sign in">
          {methods.map((method) => (
            <button key={method.id} type="button" className="button" onClick={() => void start(method.id)}>
              {method.label}
            </button>
          ))}
        </div>
      ) : null}
      {login === null ? null : (
        <>
          <p className="login-dialog__lead">
            {login.terminal ? "This runs the CLI's own sign-in on the host. Use the keys below for its menu." : "Open the link, sign in, then paste the code the page gives you."}
          </p>
          <RelayedText text={login.text} />
          {login.code === undefined ? null : (
            <p className="login-dialog__code">
              Code: <code>{login.code}</code>{" "}
              <button type="button" className="button" aria-label={`Copy code ${login.code}`} onClick={() => void copy(login.code!)}>
                {copied ? "Copied" : "Copy"}
              </button>
            </p>
          )}
          {running ? (
            <>
              <form className="login-dialog__input" onSubmit={submit}>
                <input
                  type="text"
                  className="input"
                  aria-label="Code or answer"
                  placeholder="Paste the code here"
                  autoComplete="off"
                  spellCheck={false}
                  maxLength={2048}
                  value={line}
                  onChange={(event) => setLine(event.target.value)}
                />
                <button type="submit" className="button button--primary">
                  Send
                </button>
              </form>
              {login.terminal ? (
                <div className="login-dialog__keys" role="group" aria-label="Keys">
                  {KEYS.map(({ key, label }) => (
                    <button key={key} type="button" className="button" onClick={() => void send({ key })}>
                      {label}
                    </button>
                  ))}
                </div>
              ) : null}
            </>
          ) : login.state === "signed_in" ? (
            <p className="login-dialog__done" role="status">
              You are signed in.
            </p>
          ) : (
            <p className="login-dialog__problem" role="alert">
              {login.message ?? "The sign-in ended without success."}
            </p>
          )}
        </>
      )}
      {problem === null ? null : (
        <p className="login-dialog__problem" role="alert">
          {problem}
        </p>
      )}
    </Dialog>
  );
}
