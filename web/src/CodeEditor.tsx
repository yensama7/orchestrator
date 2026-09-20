import { Compartment, EditorState } from "@codemirror/state";
import { EditorView, GutterMarker, gutter, lineNumbers } from "@codemirror/view";
import { useEffect, useRef } from "react";
import { resolve } from "./lang/registry";

// agent → blame stripe colour (§19.8). Stable hash into the palette.
const PALETTE = ["#e0a33c", "#7fb894", "#9b8ce0", "#6d8bc7", "#c96a52"];
const blameColor = (a: string) =>
  a ? PALETTE[[...a].reduce((s, c) => s + c.charCodeAt(0), 0) % PALETTE.length] : "transparent";

class BlameMarker extends GutterMarker {
  constructor(private color: string, private agent: string) { super(); }
  toDOM() {
    const el = document.createElement("div");
    el.style.cssText = `width:6px;height:100%;background:${this.color}`;
    el.title = this.agent;
    return el;
  }
}

// minimal dark theme in the product's tokens
const theme = EditorView.theme({
  "&": { height: "100%", background: "var(--ink)", color: "var(--bone)", fontSize: "12.5px" },
  ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.55" },
  ".cm-gutters": { background: "var(--ink)", border: "none", color: "var(--dimmer)" },
  ".cm-activeLineGutter, .cm-activeLine": { background: "transparent" },
  ".cm-blame": { width: "6px", padding: "0" },
  "&.cm-focused": { outline: "none" },
}, { dark: true });

export default function CodeEditor({ filename, content, blame, readOnly }: {
  filename: string; content: string; blame: string[]; readOnly?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView>();
  const langComp = useRef(new Compartment());

  useEffect(() => {
    const blameGutter = gutter({
      class: "cm-blame",
      lineMarker(view, line) {
        const ln = view.state.doc.lineAt(line.from).number;
        const agent = blame[ln - 1] ?? "";
        return new BlameMarker(blameColor(agent), agent);
      },
    });

    const view = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: content,
        extensions: [
          lineNumbers(),
          blameGutter,
          theme,
          EditorView.editable.of(!readOnly),
          EditorState.readOnly.of(!!readOnly),
          langComp.current.of([]),
        ],
      }),
    });
    viewRef.current = view;

    // §13: load exactly one grammar for this extension, lazily.
    resolve(filename).loader().then((lang) =>
      view.dispatch({ effects: langComp.current.reconfigure(lang as any) })
    );

    return () => view.destroy();
    // recreate on file change so doc + blame + grammar all refresh
  }, [filename, content, blame, readOnly]);

  return <div ref={host} style={{ height: "100%", overflow: "hidden" }} />;
}
