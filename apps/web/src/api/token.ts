const PLACEHOLDER = "__CAZTOR_TOKEN__";

/**
 * The launch token the server wrote into `<meta name="caztor-token">`, or null when it is missing,
 * blank or still the placeholder (a page that was not served by the Caztor server).
 */
export function readLaunchToken(doc: Document): string | null {
  const value = doc.querySelector('meta[name="caztor-token"]')?.getAttribute("content")?.trim();
  return value === undefined || value === "" || value === PLACEHOLDER ? null : value;
}
