// Universal language detection by extension only (§13). Never sniff content.
// Three-tier resolution, first hit wins: CM6 grammar → legacy-mode → generic.
// Ported verbatim from web/src/lang/registry.ts.
import { LanguageSupport, StreamLanguage } from "@codemirror/language";

export type Resolved = {
	mode: string;
	tier: 1 | 2 | 3;
	loader: () => Promise<LanguageSupport | StreamLanguage<unknown>>;
};

const legacy = (path: string, key: string) => async () => {
	const mod: any = await import(/* @vite-ignore */ `@codemirror/legacy-modes/mode/${path}`);
	return StreamLanguage.define(mod[key]);
};

// Tier 1 — CM6 official grammars, dynamically imported (one grammar per open file).
const T1: Record<string, Resolved> = {
	py: { mode: "python", tier: 1, loader: () => import("@codemirror/lang-python").then((m) => m.python()) },
	ts: {
		mode: "typescript",
		tier: 1,
		loader: () => import("@codemirror/lang-javascript").then((m) => m.javascript({ typescript: true })),
	},
	tsx: {
		mode: "tsx",
		tier: 1,
		loader: () => import("@codemirror/lang-javascript").then((m) => m.javascript({ typescript: true, jsx: true })),
	},
	js: { mode: "javascript", tier: 1, loader: () => import("@codemirror/lang-javascript").then((m) => m.javascript()) },
	jsx: {
		mode: "jsx",
		tier: 1,
		loader: () => import("@codemirror/lang-javascript").then((m) => m.javascript({ jsx: true })),
	},
	rs: { mode: "rust", tier: 1, loader: () => import("@codemirror/lang-rust").then((m) => m.rust()) },
	sql: { mode: "sql", tier: 1, loader: () => import("@codemirror/lang-sql").then((m) => m.sql()) },
	yaml: { mode: "yaml", tier: 1, loader: () => import("@codemirror/lang-yaml").then((m) => m.yaml()) },
	yml: { mode: "yaml", tier: 1, loader: () => import("@codemirror/lang-yaml").then((m) => m.yaml()) },
};

// Tier 2 — legacy-modes collection (~110 more languages), lower quality but present.
const T2: Record<string, Resolved> = {
	go: { mode: "go", tier: 2, loader: legacy("go", "go") },
	rb: { mode: "ruby", tier: 2, loader: legacy("ruby", "ruby") },
	ex: { mode: "elixir", tier: 2, loader: legacy("elixir", "elixir") },
	hs: { mode: "haskell", tier: 2, loader: legacy("haskell", "haskell") },
	clj: { mode: "clojure", tier: 2, loader: legacy("clojure", "clojure") },
	toml: { mode: "toml", tier: 2, loader: legacy("toml", "toml") },
	sh: { mode: "shell", tier: 2, loader: legacy("shell", "shell") },
	c: { mode: "c", tier: 2, loader: legacy("clike", "c") },
	md: { mode: "markdown", tier: 2, loader: legacy("markdown", "markdown") },
};

// Bare filenames with no extension (§13).
const SPECIAL: Record<string, keyof typeof T1 | keyof typeof T2> = {
	dockerfile: "sh",
	makefile: "sh",
	justfile: "sh",
	procfile: "sh",
	".gitignore": "sh",
	".env": "sh",
	"cmakelists.txt": "sh",
};

// Tier 3 — generic keyword fallback so an unknown extension still colours.
const GENERIC: Resolved = {
	mode: "text",
	tier: 3,
	loader: async () =>
		StreamLanguage.define({
			token(stream) {
				if (stream.match(/\/\/.*|#.*/)) return "comment";
				if (stream.match(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/)) return "string";
				if (stream.match(/\b\d[\d_.]*\b/)) return "number";
				if (stream.match(/\b(if|else|for|while|return|function|class|def|let|const|var|import|from)\b/))
					return "keyword";
				stream.next();
				return null;
			},
		}),
};

export function resolve(filename: string): Resolved {
	const lower = filename.toLowerCase();
	const ext = lower.includes(".") ? lower.split(".").pop()! : "";
	return T1[ext] ?? T2[ext] ?? T1[SPECIAL[lower]] ?? T2[SPECIAL[lower]] ?? GENERIC;
}
