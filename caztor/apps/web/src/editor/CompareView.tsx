import { MergeView } from "@codemirror/merge";
import { EditorState, type Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { useEffect, useRef } from "react";
import { languageFor } from "./languages.ts";
import { editorTheme } from "./theme.ts";
import "./CompareView.css";

interface CompareViewProps {
  path: string;
  /** The text on disk, shown on the left. */
  disk: string;
  /** The user's unsaved text, shown on the right. */
  mine: string;
}

/** Both versions side by side with the differences marked. Neither side can be edited here. */
export function CompareView({ path, disk, mine }: CompareViewProps) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const parent = host.current;
    if (parent === null) return;
    const language = languageFor(path);
    const extensions: Extension[] = [
      EditorState.readOnly.of(true),
      EditorView.editable.of(false),
      EditorView.lineWrapping,
      editorTheme,
      ...(language === null ? [] : [language]),
    ];
    const merge = new MergeView({
      parent,
      a: { doc: disk, extensions },
      b: { doc: mine, extensions },
      highlightChanges: true,
      gutter: true,
      collapseUnchanged: { margin: 3, minSize: 6 },
    });
    return () => merge.destroy();
  }, [path, disk, mine]);

  return (
    <div className="compare">
      <div className="compare__labels">
        <span>Disk version</span>
        <span>Your version</span>
      </div>
      <div ref={host} className="compare__body" />
    </div>
  );
}
