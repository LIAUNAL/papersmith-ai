import { describe, expect, it } from "vitest";
import { injectToken, TOKEN_PLACEHOLDER } from "../src/html.ts";

const page = `<meta name="caztor-token" content="${TOKEN_PLACEHOLDER}">`;

describe("injectToken", () => {
  it("replaces the placeholder in the meta tag with the launch token", () => {
    expect(injectToken(page, "abc123")).toBe('<meta name="caztor-token" content="abc123">');
  });

  it("leaves a page without the placeholder unchanged", () => {
    expect(injectToken("<p>hello</p>", "abc123")).toBe("<p>hello</p>");
  });

  it("escapes characters that could break out of the attribute", () => {
    expect(injectToken(page, 'a"><script>x</script>&')).toBe(
      '<meta name="caztor-token" content="a&quot;&gt;&lt;script&gt;x&lt;/script&gt;&amp;">',
    );
  });

  it("inserts the token literally, even when it looks like a replacement pattern", () => {
    expect(injectToken(page, "$&$1")).toBe('<meta name="caztor-token" content="$&amp;$1">');
  });
});
