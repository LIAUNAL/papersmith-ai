import { Fragment } from "react";
import "./LoginHint.css";

/** Text written with commands between backticks, shown with each command as code. */
export function HintText({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((part, index) => (
        // Odd parts sit between a pair of backticks.
        <Fragment key={index}>{index % 2 === 1 ? <code>{part}</code> : part}</Fragment>
      ))}
    </>
  );
}

interface LoginHintProps {
  /** The terminal step that signs in to the provider's CLI. */
  hint: string;
}

/** What to do in a terminal to sign in to the provider's CLI, shown in account mode while no login is known to exist. */
export function LoginHint({ hint }: LoginHintProps) {
  return (
    <p className="login-hint" data-testid="login-hint">
      <HintText text={hint} />
    </p>
  );
}
