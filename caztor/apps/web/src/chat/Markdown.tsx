import { createElement, type ReactNode } from "react";
import { parseMarkdown, type Block, type Inline } from "./markdown.ts";
import "./Markdown.css";

function renderInlines(inlines: Inline[]): ReactNode[] {
  return inlines.map((inline, index) => {
    switch (inline.type) {
      case "text":
        return inline.text;
      case "code":
        return <code key={index}>{inline.text}</code>;
      case "strong":
        return <strong key={index}>{renderInlines(inline.children)}</strong>;
      case "em":
        return <em key={index}>{renderInlines(inline.children)}</em>;
      case "link":
        return (
          <a key={index} href={inline.href} target="_blank" rel="noopener noreferrer nofollow">
            {renderInlines(inline.children)}
          </a>
        );
    }
  });
}

function renderBlock(block: Block, index: number): ReactNode {
  switch (block.type) {
    case "paragraph":
      return <p key={index}>{renderInlines(block.inlines)}</p>;
    case "heading":
      // Headings in a message are small: they never outrank the pane's own title.
      return createElement(`h${Math.min(6, block.level + 2)}`, { key: index, className: "markdown__heading" }, renderInlines(block.inlines));
    case "code":
      return (
        <pre key={index} className="markdown__code" data-language={block.language === "" ? undefined : block.language}>
          <code>{block.text}</code>
        </pre>
      );
    case "list": {
      const items = block.items.map((item, at) => <li key={at}>{renderInlines(item)}</li>);
      return block.ordered ? <ol key={index}>{items}</ol> : <ul key={index}>{items}</ul>;
    }
    case "quote":
      return <blockquote key={index}>{renderInlines(block.inlines)}</blockquote>;
    case "rule":
      return <hr key={index} />;
  }
}

/** Assistant text as safe elements: nothing in it can become markup, a script, or a request. */
export function Markdown({ text }: { text: string }) {
  return <div className="markdown">{parseMarkdown(text).map(renderBlock)}</div>;
}
