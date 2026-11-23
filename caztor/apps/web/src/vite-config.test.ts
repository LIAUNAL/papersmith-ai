import { describe, expect, it } from "vitest";
import config from "../vite.config";

describe("the web build", () => {
  it("keeps fonts as files, since the server's CSP has no font-src for data: URLs", () => {
    const limit = (config as { build?: { assetsInlineLimit?: unknown } }).build?.assetsInlineLimit;
    expect(typeof limit).toBe("function");
    const inline = limit as (file: string, content: Buffer) => boolean | undefined;
    for (const font of ["KaTeX_Size3-Regular.woff2", "a.woff", "a.ttf"]) expect(inline(font, Buffer.alloc(10))).toBe(false);
    expect(inline("icon.svg", Buffer.alloc(10))).toBeUndefined();
  });
});
