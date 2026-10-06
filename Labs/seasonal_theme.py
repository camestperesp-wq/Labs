"""Global seasonal preference and a lightweight browser calendar controller."""
import json
import hashlib
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st
import auth
import database as db

ASSETS = Path(__file__).parent / "assets" / "seasonal"


@lru_cache(maxsize=1)
def themes():
    return json.loads((ASSETS / "themes.json").read_text(encoding="utf-8"))


def preference():
    with db.get_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS seasonal_preference (
            id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL,
            effects INTEGER NOT NULL DEFAULT 0 CHECK(effects IN (0,1)))""")
        row = conn.execute("SELECT mode,effects FROM seasonal_preference WHERE id=1").fetchone()
    return row if row and row[0] in ("auto", *themes()) else ("auto", 0)


def save_preference(mode, effects):
    # Revalidate identity at mutation time, including any rerun.
    user = auth.session(st.context.cookies.get(auth.COOKIE, ""))
    if not user or user[2] != "administrador":
        raise PermissionError("Solo un administrador puede cambiar la temporada")
    if mode not in ("auto", *themes()):
        raise ValueError("Temporada inválida")
    preference()
    with db.get_connection() as conn:
        conn.execute("""INSERT INTO seasonal_preference(id,mode,effects) VALUES(1,?,?)
            ON CONFLICT(id) DO UPDATE SET mode=excluded.mode,effects=excluded.effects""",
                     (mode, int(bool(effects))))


def render_admin(user):
    if user[2] != "administrador":
        return
    mode, effects = preference()
    with st.expander("Temporada visual · Administración"):
        with st.form("seasonal_admin"):
            automatic = st.toggle("Selección automática por calendario", value=mode == "auto")
            choices = list(themes())
            selected = st.selectbox("Temporada manual", choices,
                                    index=choices.index(mode) if mode in choices else 0,
                                    format_func=lambda key: themes()[key]["label"])
            animated = st.toggle("Animación decorativa", value=bool(effects))
            st.caption("Calendario: America/Bogota. La selección manual se usa al desactivar el modo automático.")
            if st.form_submit_button("Aplicar temporada"):
                save_preference("auto" if automatic else selected, animated)
                st.rerun()


def render_theme(username=""):
    mode, effects = preference()
    st.html("<style>" + (ASSETS / "theme.css").read_text(encoding="utf-8") + "</style>")
    floating_svg = '''<svg viewBox="0 0 64 64" focusable="false">
      <g data-float-art="heart"><path d="M32 54 9 31C-5 13 20 1 32 19 44 1 69 13 55 31Z" fill="currentColor"/></g>
      <g data-float-art="bat"><path d="M30 27 25 18l-3 10C12 15 4 17 1 12v27c9-8 14-3 19 5l12-8 12 8c5-8 10-13 19-5V12c-3 5-11 3-21 16l-3-10-5 9Z" fill="currentColor"/><circle cx="29" cy="30" r="2" fill="white"/><circle cx="36" cy="30" r="2" fill="white"/></g>
      <g data-float-art="ghost"><path d="M13 55V26a19 19 0 0 1 38 0v29l-10-6-9 6-9-6Z" fill="currentColor"/><circle cx="25" cy="27" r="3" fill="white"/><circle cx="39" cy="27" r="3" fill="white"/></g>
      <g data-float-art="spider" fill="currentColor"><ellipse cx="32" cy="36" rx="11" ry="14"/><circle cx="32" cy="20" r="8"/><path d="m23 25-10-9-7 8m17 7L9 29l-5 10m19-2L10 43l-2 10m17-10-8 13m24-31 10-9 7 8m-17 7 14-2 5 10m-19-2 13 6 2 10m-17-10 8 13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><circle cx="29" cy="19" r="2" fill="#fff"/><circle cx="35" cy="19" r="2" fill="#fff"/></g>
      <g data-float-art="snow" stroke="currentColor" stroke-width="4" stroke-linecap="round"><path d="M32 8v48M11 20l42 24M11 44l42-24M25 12l7 7 7-7M25 52l7-7 7 7"/></g>
      <g data-float-art="candy" fill="none" stroke-linecap="round"><path d="M25 55V20a12 12 0 0 1 24 0v7" stroke="#fff" stroke-width="12"/><path d="M25 51v-5m0-9v-5m1-13 3-5m10-5 5 4m5 9v5" stroke="#ce2339" stroke-width="10"/></g>
      <g data-float-art="snowman"><circle cx="32" cy="43" r="17" fill="#fff" stroke="#67829b"/><circle cx="32" cy="20" r="11" fill="#fff" stroke="#67829b"/><path d="M20 30h24v6H20Z" fill="#d0253d"/><circle cx="28" cy="18" r="2"/><circle cx="36" cy="18" r="2"/><path d="m32 22 10 3-10 2Z" fill="#eb8b26"/><path d="M20 10h24M24 10V2h16v8" stroke="#244159" stroke-width="5"/></g>
      <g data-float-art="tree"><path d="m32 4 17 23h-9l16 23H8l16-23h-9Z" fill="#19734a"/><path d="M28 50h8v10h-8Z" fill="#885532"/><circle cx="26" cy="30" r="3" fill="#d0253d"/><circle cx="38" cy="42" r="3" fill="#e4be55"/></g>
      <g data-float-art="rain" stroke="#558cae" stroke-width="3" stroke-linecap="round"><path d="m18 9-7 15m31-9-7 15m21 5-7 15m-24-7-7 15"/></g>
      <g data-float-art="flag"><path d="M8 12h48v20H8Z" fill="#f2c500"/><path d="M8 32h48v10H8Z" fill="#123b75"/><path d="M8 42h48v10H8Z" fill="#ce2339"/></g>
      <g data-float-art="football"><circle cx="32" cy="32" r="24" fill="#fff" stroke="#123b75" stroke-width="2"/><path d="m32 20 11 8-4 13H25l-4-13Z" fill="#123b75"/><path d="m13 17 8 11m22 0 8-11M25 41l-7 11m21-11 7 11" stroke="#123b75" stroke-width="3"/></g>
      <g data-float-art="balloon"><ellipse cx="32" cy="23" rx="17" ry="21" fill="#db518f"/><path d="m32 43-4 5h8Z" fill="#db518f"/><path d="M32 48q-10 8 0 14" stroke="#754093" fill="none"/></g>
      <g data-float-art="cake"><path d="M10 32h44v26H10Z" fill="#f3c85e"/><path d="M10 32h44v10q-6 8-11 0-6 8-11 0-6 8-11 0-6 8-11 0Z" fill="#db518f"/><path d="M22 32V21m10 11V19m10 13V21" stroke="#754093" stroke-width="4"/><path d="M22 19q-6-6 0-11 6 5 0 11m10-2q-6-6 0-11 6 5 0 11m10 2q-6-6 0-11 6 5 0 11" fill="#ed932a"/></g>
      </svg>'''
    floating_markup = ''.join(
        f'<span class="season-particle" style="--particle-index:{i};--particle-x:{4 + (i * 37) % 90}%">{floating_svg}</span>'
        for i in range(14))
    rain_svg = '''<svg viewBox="0 0 64 64" focusable="false"><path d="m18 9-7 15m31-9-7 15m21 5-7 15m-24-7-7 15" stroke="#558cae" stroke-width="3" stroke-linecap="round"/></svg>'''
    floating_markup += ''.join(
        f'<span class="season-particle season-rain-extra" style="--particle-index:{i + 14};--particle-x:{1 + (i * 17) % 96}%">{rain_svg}</span>'
        for i in range(42))
    web_svg = '''<svg viewBox="0 0 140 140" focusable="false" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M0 0v138M0 0h138M0 0l130 45M0 0l100 100M0 0l45 130"/>
      <path d="M0 25Q8 20 9 24Q16 18 18 18Q22 9 24 9Q21 3 25 0M0 50Q14 40 18 48Q29 34 35 35Q39 18 48 18Q43 6 50 0M0 80Q22 62 28 76Q47 53 57 57Q62 29 76 28Q68 9 80 0M0 115Q31 89 40 109Q67 75 81 81Q90 40 109 40Q98 13 115 0"/>
      </svg>'''
    floating_markup += ''.join(f'<div class="season-web season-web-{side}">{web_svg}</div>'
                               for side in ("left", "right"))
    corner_svg = (ASSETS / "corners.svg").read_text(encoding="utf-8")
    floating_markup += ''.join(
        f'<div class="season-corner season-corner-{side}">{corner_svg}</div>'
        for side in ("left", "right"))
    floating_markup += '''<div class="season-rain-cat"><svg viewBox="0 0 120 120" focusable="false">
      <path d="M15 38Q60-12 105 38Z" fill="#d989aa"/><path d="M60 38v48q0 14-12 9" stroke="#526071" stroke-width="4" fill="none"/>
      <ellipse cx="65" cy="94" rx="22" ry="18" fill="#444555"/><path d="M48 72 43 49l17 10 14-10 6 24Z" fill="#444555"/>
      <circle cx="55" cy="72" r="3" fill="#f4d16d"/><circle cx="70" cy="72" r="3" fill="#f4d16d"/><path d="m61 79 4 0-2 3Z" fill="#efa6bf"/>
      <path d="M85 100q28-2 18-29" stroke="#444555" stroke-width="8" fill="none" stroke-linecap="round"/>
      <ellipse cx="62" cy="114" rx="46" ry="4" fill="#91bedc" opacity=".5"/></svg></div>'''
    st.html('''<div class="season-decoration" aria-hidden="true">
      <svg viewBox="0 0 64 64" focusable="false">
        <g data-art="hearts" fill="currentColor"><path d="M32 53 9 30C-5 12 20 0 32 18 44 0 69 12 55 30Z"/></g>
        <g data-art="ghost"><path d="M13 55V26a19 19 0 0 1 38 0v29l-10-6-9 6-9-6Z" fill="currentColor"/><circle cx="25" cy="27" r="3" fill="white"/><circle cx="39" cy="27" r="3" fill="white"/></g>
        <g data-art="tree"><path d="m32 5 17 22h-9l15 22H9l15-22h-9Z" fill="currentColor"/><path d="M28 49h8v11h-8Z" fill="var(--season-accent)"/><circle cx="28" cy="31" r="3" fill="#a71930"/><circle cx="38" cy="42" r="3" fill="var(--season-accent)"/></g>
      </svg></div>''')
    config = json.dumps(themes(), ensure_ascii=True)
    source = (ASSETS / "theme.js").read_text(encoding="utf-8")
    account_key = "labs-season:" + hashlib.sha256(username.encode("utf-8")).hexdigest()
    source += f"\nstartSeasonalTheme(window, {config}, {json.dumps(mode)}, {json.dumps(bool(effects))}, 'America/Bogota', {json.dumps(account_key)}, {json.dumps(floating_markup)});"
    # Execute in the host realm so timers survive the component iframe lifecycle.
    encoded = json.dumps(source).replace("<", "\\u003c")
    st.components.v1.html(f"<script>window.parent.Function({encoded})();</script>", height=0)
