import { create } from "zustand";

// Phase 1 UI store: just the two durable preferences the old App.tsx tracked by
// hand — Simple/Expert disclosure (localStorage "ui") and theme (localStorage
// "theme", also read pre-paint by apply-initial-theme). Selection (which run is
// open) lands in the URL in Phase 2, not here.
//
// ponytail: hand-rolled localStorage, not zustand/persist middleware — two keys
// read in two places (one pre-paint), persist's rehydration adds nothing here.
export type Mode = "simple" | "expert";
export type Theme = "light" | "dark";

type UiState = {
	mode: Mode;
	theme: Theme;
	setMode: (mode: Mode) => void;
	setTheme: (theme: Theme) => void;
	toggleTheme: () => void;
};

function initialMode(): Mode {
	return localStorage.getItem("ui") === "expert" ? "expert" : "simple";
}

function initialTheme(): Theme {
	// data-theme is set pre-paint by apply-initial-theme; default is dark (:root).
	return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

export const useUiStore = create<UiState>((set, get) => ({
	mode: initialMode(),
	theme: initialTheme(),
	setMode: (mode) => {
		localStorage.setItem("ui", mode);
		set({ mode });
	},
	setTheme: (theme) => {
		localStorage.setItem("theme", theme);
		document.documentElement.setAttribute("data-theme", theme);
		set({ theme });
	},
	toggleTheme: () => get().setTheme(get().theme === "light" ? "dark" : "light"),
}));
