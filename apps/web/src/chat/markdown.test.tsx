import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { parseInline, parseMarkdown } from "./markdown.ts";
import { Markdown } from "./Markdown.tsx";

describe("parseMarkdown", () => {
  it("splits paragraphs on blank lines and joins soft line breaks", () => {
    expect(parseMarkdown("One\ntwo\n\nThree")).toEqual([
      { type: "paragraph", inlines: [{ type: "text", text: "One two" }] },
      { type: "paragraph", inlines: [{ type: "text", text: "Three" }] },
    ]);
  });

  it("reads headings, bullet and numbered lists, quotes and rules", () => {
    const blocks = parseMarkdown("## Title\n- a\n- b\n\n1. x\n2. y\n\n> quoted\n\n---");
    expect(blocks.map((block) => block.type)).toEqual(["heading", "list", "list", "quote", "rule"]);
    expect(blocks[0]).toMatchObject({ level: 2 });
    expect(blocks[1]).toMatchObject({ ordered: false });
    expect(blocks[2]).toMatchObject({ ordered: true });
  });

  it("keeps a fenced block verbatim with its language, and closes an unfinished fence at the end of the text", () => {
    expect(parseMarkdown("```latex\n\\section{A}\n*not italic*\n```\nafter")).toEqual([
      { type: "code", language: "latex", text: "\\section{A}\n*not italic*" },
      { type: "paragraph", inlines: [{ type: "text", text: "after" }] },
    ]);
    expect(parseMarkdown("```\nstill typing")).toEqual([{ type: "code", language: "", text: "still typing" }]);
  });
});

describe("parseInline", () => {
  it("reads code, bold and italic, and leaves unmatched markers as text", () => {
    expect(parseInline("a `b` **c** *d*")).toEqual([
      { type: "text", text: "a " },
      { type: "code", text: "b" },
      { type: "text", text: " " },
      { type: "strong", children: [{ type: "text", text: "c" }] },
      { type: "text", text: " " },
      { type: "em", children: [{ type: "text", text: "d" }] },
    ]);
    expect(parseInline("2 * 3 and **open")).toEqual([{ type: "text", text: "2 * 3 and **open" }]);
  });

  it("does not read emphasis inside code or inside a word", () => {
    expect(parseInline("`**x**` snake_case_name")).toEqual([
      { type: "code", text: "**x**" },
      { type: "text", text: " snake_case_name" },
    ]);
  });

  it("keeps a link only for http, https and mailto, and shows an image as text", () => {
    expect(parseInline("[ok](https://example.com) [bad](javascript:alert(1))")).toEqual([
      { type: "link", href: "https://example.com", children: [{ type: "text", text: "ok" }] },
      { type: "text", text: " bad" },
    ]);
    expect(parseInline("![diagram](https://evil.test/x.png)")).toEqual([{ type: "text", text: "[image: diagram]" }]);
  });
});

describe("Markdown", () => {
  it("renders formatting as elements", () => {
    render(<Markdown text={"# Heading\n\nSome **bold** and `code`.\n\n- one\n- two"} />);
    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("code").tagName).toBe("CODE");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("never turns raw HTML into elements", () => {
    const { container } = render(<Markdown text={'<img src="https://evil.test/x.png" onerror="alert(1)"> <script>alert(1)</script> <a href="javascript:alert(1)">x</a>'} />);
    expect(container.querySelector("img, script, a, iframe")).toBeNull();
    expect(container.textContent).toContain('<img src="https://evil.test/x.png"');
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("opens links in a new context without the opener, and never loads an image", () => {
    const { container } = render(<Markdown text={"[docs](https://example.com/a?b=1) ![pic](https://evil.test/p.png)"} />);
    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("href", "https://example.com/a?b=1");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(link.getAttribute("rel")).toContain("noreferrer");
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows a LaTeX block as code", () => {
    const { container } = render(<Markdown text={"```latex\n\\begin{document}\n\\end{document}\n```"} />);
    const code = container.querySelector("pre code");
    expect(code?.textContent).toBe("\\begin{document}\n\\end{document}");
  });
});
