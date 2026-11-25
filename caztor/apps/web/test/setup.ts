import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom does no layout. CodeMirror measures text with these, so give it empty answers.
const noRects = Object.assign([], { item: () => null });
Range.prototype.getClientRects ??= () => noRects as unknown as DOMRectList;
Range.prototype.getBoundingClientRect ??= () => new DOMRect(0, 0, 0, 0);

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
