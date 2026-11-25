import katex from "katex";
import "katex/dist/katex.min.css";
import { useMemo } from "react";
import "./TexMath.css";

/**
 * Typeset TeX from assistant text. KaTeX escapes everything it emits and, with `trust` off, renders no links,
 * classes, styles or HTML from the input, so its output is safe to insert; expansion and sizes are bounded so a
 * hostile macro cannot hang the page. TeX that KaTeX cannot read (a whole LaTeX document, an unknown command) is
 * shown as its source, as code.
 */
export function TexMath({ tex, display }: { tex: string; display: boolean }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(tex, {
        displayMode: display,
        throwOnError: true,
        trust: false,
        strict: "ignore",
        maxSize: 20,
        maxExpand: 300,
        output: "htmlAndMathml",
      });
    } catch {
      return null;
    }
  }, [tex, display]);
  if (html === null) {
    return display ? (
      <pre className="markdown__code tex-math--source">
        <code>{tex}</code>
      </pre>
    ) : (
      <code className="tex-math--source">{tex}</code>
    );
  }
  // eslint-disable-next-line react/no-danger -- KaTeX output, see above.
  return display ? <div className="tex-math tex-math--display" dangerouslySetInnerHTML={{ __html: html }} /> : <span className="tex-math" dangerouslySetInnerHTML={{ __html: html }} />;
}
