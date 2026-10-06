/* Shared browser/React module. Configuration is injected; no network or assets. */
const seasonalCursorArt = {
  standard: '<path d="M19 16h10v10H19z" fill="#941419"/>',
  friendship: '<path d="M20 20q-12-13-10 0l8 8m8-8q12-13 10 0l-8 8" fill="#fff" stroke="#c987a5"/><circle cx="23" cy="16" r="5" fill="#f2c49d"/><path d="M18 14q5-9 10 0" fill="#e6b946"/><path d="M19 22h8v8h-8Z" fill="#ef8fb4"/><path d="M30 18q7 7 0 14m-2-7h8" fill="none" stroke="#a51f50" stroke-width="1.5"/>',
  halloween: '<ellipse cx="23" cy="23" rx="6" ry="7" fill="#45215f"/><path d="m18 18-5-4m5 8-6-1m6 5-5 4m15-12 4-4m-4 8 4-1m-4 5 4 4" stroke="#45215f" stroke-width="2"/>',
  rain: '<path d="M14 22q9-15 18 0Z" fill="#558cae"/><path d="M23 22v8q0 3-4 1" stroke="#265478" stroke-width="2" fill="none"/>',
  christmas: '<path d="M15 17q1-13 15-7l3 8Z" fill="#d0253d"/><circle cx="33" cy="17" r="3" fill="#fff" stroke="#a5aab2" stroke-width=".7"/><circle cx="23" cy="23" r="9" fill="#f2c49d"/><path d="M14 24q2 13 9 9 8 4 9-9l-9 4Z" fill="#fff" stroke="#a5aab2" stroke-width=".7"/><path d="M14 18h17" stroke="#fff" stroke-width="4"/><circle cx="20" cy="22" r="1"/><circle cx="26" cy="22" r="1"/><circle cx="23" cy="25" r="2" fill="#e28e82"/>',
  colombia: '<circle cx="23" cy="23" r="10" fill="#fff" stroke="#123b75"/><path d="m23 18 5 4-2 6h-6l-2-6Z" fill="#123b75"/><path d="M15 16h16" stroke="#f2c500" stroke-width="4"/>',
  birthday: '<ellipse cx="23" cy="20" rx="7" ry="9" fill="#db518f"/><path d="M23 29v3" stroke="#754093"/>'
};
seasonalCursorArt.birthday_blue = seasonalCursorArt.birthday.replace("#db518f", "#428cca");
const seasonalCursors = Object.fromEntries(Object.entries(seasonalCursorArt).map(([key, art]) => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><g transform="translate(-9 -7)">' + art + '</g></svg>';
  return [key, 'url("data:image/svg+xml,' + encodeURIComponent(svg) + '") 14 15, auto'];
}));
function resolveSeason(themes, mode = "auto", now = new Date(), timeZone = "America/Bogota") {
  if (mode !== "auto") return Object.hasOwn(themes, mode) ? mode : "standard";
  const month = Number(new Intl.DateTimeFormat("en", {month: "numeric", timeZone}).format(now));
  return Object.keys(themes).find(key => themes[key].months.includes(month)) || "standard";
}

function applySeason(root, themes, mode, now, timeZone, effects = false) {
  const key = resolveSeason(themes, mode, now, timeZone);
  const theme = themes[key];
  root.dataset.season = key;
  root.dataset.seasonEffects = String(effects);
  for (const [token, value] of Object.entries(theme.colors)) {
    root.style.setProperty(`--season-${token}`, value);
  }
  root.style.setProperty("--season-font", theme.font);
  root.style.setProperty("--season-icon", JSON.stringify(theme.icon));
  root.style.setProperty("--season-cursor", key === "standard" ? "auto" : seasonalCursors[key] || seasonalCursors.birthday);
  // Existing shell uses these aliases; only presentation tokens are changed.
  const aliases = {red: "primary", "red-dark": "heading", gold: "accent", ink: "text",
    muted: "muted", bg: "background", surface: "surface", line: "border", soft: "soft"};
  for (const [name, token] of Object.entries(aliases)) root.style.setProperty(`--labs-${name}`, theme.colors[token]);
  return key;
}

function startSeasonalTheme(host, themes, initialMode = "auto", effects = false, timeZone = "America/Bogota", storageKey = "labs-season", floatingMarkup = "") {
  if (host.__seasonalTheme) host.__seasonalTheme.dispose();
  // Attach outside Streamlit containers: their stacking contexts can cover or
  // clip fixed decorations. Markup comes exclusively from our local SVG assets.
  const floating = host.document.createElement("div");
  floating.className = "season-floating";
  floating.setAttribute("aria-hidden", "true");
  floating.innerHTML = floatingMarkup;
  host.document.body.appendChild(floating);
  let mode = initialMode;
  try {
    const saved = JSON.parse(host.localStorage.getItem(storageKey));
    if (saved && (saved.mode === "auto" || Object.hasOwn(themes, saved.mode))) {
      mode = saved.mode;
      effects = saved.effects === true;
    }
  } catch (_) { /* Storage may be disabled; controls still work in this page. */ }
  let timer;
  const root = host.document.documentElement;
  const update = () => {
    const key = applySeason(root, themes, mode, new Date(), timeZone, effects);
    const select = host.document.getElementById("season-menu-mode");
    const checkbox = host.document.getElementById("season-menu-effects");
    if (select) select.value = mode;
    if (checkbox) checkbox.checked = effects;
    return key;
  };
  const onChange = event => {
    if (event.target.id === "season-menu-mode") {
      const next = event.target.value;
      if (next !== "auto" && !Object.hasOwn(themes, next)) return;
      mode = next;
    } else if (event.target.id === "season-menu-effects") {
      effects = event.target.checked;
    } else return;
    try { host.localStorage.setItem(storageKey, JSON.stringify({mode, effects})); } catch (_) {}
    update();
  };
  host.document.addEventListener("change", onChange);
  const closeMenu = () => {
    const menu = host.document.querySelector(".labs-user-menu[open]");
    if (menu) menu.open = false;
  };
  const onMenuClick = event => {
    if (event.target.closest && event.target.closest("#season-menu-close")) closeMenu();
    else if (!(event.target.closest && event.target.closest(".labs-user-menu"))) closeMenu();
  };
  const onMenuKey = event => { if (event.key === "Escape") closeMenu(); };
  host.document.addEventListener("click", onMenuClick);
  host.document.addEventListener("keydown", onMenuKey);
  const tick = () => { update(); timer = host.setTimeout(tick, 60000); };
  const onVisible = () => { if (!host.document.hidden) update(); };
  host.document.addEventListener("visibilitychange", onVisible);
  tick();
  const controller = {
    setMode(next) { mode = next; return update(); },
    dispose() {
      floating.remove();
      host.clearTimeout(timer);
      host.document.removeEventListener("visibilitychange", onVisible);
      host.document.removeEventListener("change", onChange);
      host.document.removeEventListener("click", onMenuClick);
      host.document.removeEventListener("keydown", onMenuKey);
    }
  };
  host.__seasonalTheme = controller;
  return controller;
}
