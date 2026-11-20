import { plainPage } from "@caztor/api";

/** The value `index.html` carries in `<meta name="caztor-token">` until the server substitutes the launch token. */
export const TOKEN_PLACEHOLDER = "__CAZTOR_TOKEN__";

const ATTRIBUTE_ESCAPES: Readonly<Record<string, string>> = {
  "&": "&amp;",
  '"': "&quot;",
  "<": "&lt;",
  ">": "&gt;",
};

function escapeAttribute(value: string): string {
  return value.replace(/[&"<>]/g, (character) => ATTRIBUTE_ESCAPES[character] ?? character);
}

/** Puts the token for whoever asked (the launch token for the host, a session's own token for a collaborator) into the page. The token is escaped for an attribute and inserted literally. */
export function injectToken(html: string, token: string): string {
  const safe = escapeAttribute(token);
  return html.replaceAll(TOKEN_PLACEHOLDER, () => safe);
}

/** What a browser without a session gets when the server is exposed: no app and no token. */
export const NO_SESSION_PAGE = plainPage("Caztor", "Ask the host for an invite link and its access key. Open the link and type the key to sign in on this browser.");
