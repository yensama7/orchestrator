// Runs before first paint (imported first in main.tsx) so the native window
// never flashes the wrong theme. Dark is the default (:root); light is the
// override via data-theme, matching tokens.css + the reference.
const stored = localStorage.getItem("theme");
if (stored === "light" || stored === "dark") {
  document.documentElement.setAttribute("data-theme", stored);
}
