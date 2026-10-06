from datetime import datetime, timedelta, timezone
import json
from html import escape
from pathlib import Path
import streamlit as st


@st.cache_data(show_spinner=False)
def imagen_asset(nombre_archivo):
    import base64

    ruta = Path(__file__).parent / "assets" / nombre_archivo
    if not ruta.exists():
        return None

    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(ruta.suffix.lower(), "image/png")

    data = base64.b64encode(ruta.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def mostrar_navegacion(pages, selected):
    """Barra institucional con enlaces nativos: conserva rutas y ejecución diferida."""
    st.html("""
    <style>
    .st-key-labs_navigation {
        background: #941419;
        border-bottom: 3px solid #c8a21a;
        box-shadow: 0 6px 14px rgba(95,13,20,.14);
        padding: .4rem .8rem;
        margin-bottom: 1.1rem;
        border-radius: 0;
    }
    .st-key-labs_navigation > div {
        flex-wrap: wrap !important;
        gap: .35rem .8rem !important;
        overflow: visible;
    }
    .st-key-labs_navigation [data-testid="stLayoutWrapper"]:has([data-testid="stPageLink"]) {
        flex: 0 0 auto !important;
        min-width: max-content !important;
    }
    .st-key-labs_navigation [data-testid="stPageLink"] {
        min-width: max-content;
    }
    .st-key-labs_navigation [data-testid="stVerticalBlock"] {
        gap: 0;
    }
    .st-key-labs_navigation [data-testid="stPageLink"] a {
        display: flex;
        position: relative;
        align-items: center;
        min-height: 56px;
        padding: .8rem 1.25rem .8rem 1.8rem;
        border-radius: 0;
        text-decoration: none;
        color: white !important;
        white-space: nowrap;
    }
    .st-key-labs_navigation [data-testid="stPageLink"] a::before {
        content: "";
        position: absolute;
        left: .65rem;
        top: 50%;
        width: 2px;
        height: 25px;
        background: #d6b438;
        transform: translateY(-50%) rotate(22deg);
        pointer-events: none;
    }
    .st-key-labs_navigation [data-testid="stPageLink"] p {
        color: white !important;
        font-size: .95rem !important;
        font-weight: 850 !important;
        letter-spacing: .015em;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    .st-key-labs_alertas_globales {
        border-left: 5px solid #c8a21a !important;
        background: #fffdf5;
        padding: 1rem 1.25rem !important;
        margin-bottom: 1.25rem;
    }
    .st-key-labs_alertas_globales button p {
        white-space: normal !important;
        overflow-wrap: anywhere;
        line-height: 1.5;
    }
    .st-key-labs_alertas_globales button {
        min-height: 48px;
        padding: .65rem 1rem;
    }
    .st-key-labs_navigation [data-testid="stPageLink"] a:hover {
        background: rgba(255,255,255,.10);
    }
    .st-key-labs_navigation [data-testid="stPageLink"] a:focus-visible {
        outline: 2px solid #f2c230;
        outline-offset: -3px;
    }
    .st-key-labs_nav_active {
        background: #7d1015;
        box-shadow: inset 0 -5px 0 #c8a21a;
    }
    @media (max-width: 700px) {
        .st-key-labs_navigation { padding: .35rem; }
        .st-key-labs_navigation [data-testid="stPageLink"] a { padding: .75rem 1rem .75rem 1.6rem; }
    }
    </style>
    """)
    with st.container(key="labs_navigation", horizontal=True, gap="small"):
        for index, page in enumerate(pages):
            key = "labs_nav_active" if page.url_path == selected.url_path else f"labs_nav_{index}"
            with st.container(key=key, width="content"):
                st.page_link(page, label=page.title.upper(), width="content")


def mostrar_marco(usuario_actual):
    st.markdown("""
        <style>
            :root {
                --labs-red: #9f1d24;
                --labs-red-dark: #731116;
                --labs-yellow: #f2c230;
                --labs-yellow-soft: #fff9e6;
                --labs-bg: #f4f6f8;
                --labs-surface: #ffffff;
                --labs-border: #dfe4ea;
                --labs-text: #1e2329;
                --labs-muted: #6b7280;
            }

            html, body, .stApp, [class*="css"] {
                font-family: Inter, Roboto, Montserrat, "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
            }

            .stApp {
                background:
                    linear-gradient(180deg, rgba(159, 29, 36, 0.035), rgba(247, 247, 248, 0) 180px),
                    var(--labs-bg);
                color: var(--labs-text);
            }

            .block-container {
                padding-top: 2rem;
                padding-bottom: 3rem;
            }

            h1 {
                color: var(--labs-red-dark);
                font-weight: 800 !important;
                letter-spacing: 0 !important;
                border-left: 8px solid var(--labs-yellow);
                padding-left: 0.85rem !important;
                line-height: 1.1 !important;
            }

            h2, h3 {
                color: var(--labs-red-dark);
                letter-spacing: 0 !important;
            }

            .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
                font-size: 1rem;
                font-weight: 700;
            }
            .stTabs [data-baseweb="tab-list"] button {
                padding: 0.65rem 1rem;
                border-radius: 6px 6px 0 0;
                color: var(--labs-muted);
            }
            .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
                background-color: var(--labs-surface);
                color: var(--labs-red-dark);
                border-bottom: 4px solid var(--labs-yellow);
            }

            .stTabs [data-baseweb="tab-border"] {
                background-color: var(--labs-border);
            }

            .stButton button {
                text-transform: none !important;
                font-weight: 700 !important;
                border-radius: 6px !important;
                border: 1px solid var(--labs-red) !important;
                color: var(--labs-red-dark) !important;
                background: #ffffff !important;
                transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
            }
            .stButton button:hover {
                border-color: var(--labs-yellow) !important;
                box-shadow: 0 2px 10px rgba(115, 17, 22, 0.16);
                transform: translateY(-1px);
            }
            .stButton button:disabled {
                color: #222 !important;
                background-color: #ffffff !important;
                border: 1px solid var(--labs-border) !important;
                opacity: 1 !important;
            }

            div[data-testid="stRadio"] label p,
            div[data-testid="stSelectbox"] label p,
            div[data-testid="stTextInput"] label p,
            div[data-testid="stTextArea"] label p {
                color: var(--labs-red-dark);
                font-weight: 700;
            }

            div[data-testid="stCaptionContainer"] {
                color: var(--labs-muted);
            }

            /* Controles sobrios y consistentes: superficie blanca, borde neutro. */
            div[data-baseweb="select"] > div,
            div[data-testid="stTextInput"] input,
            div[data-testid="stTextArea"] textarea {
                background: #ffffff !important;
                border-color: #d9dde2 !important;
                box-shadow: none !important;
            }
            div[data-baseweb="popover"] ul,
            div[data-baseweb="popover"] [role="listbox"] {
                background: #ffffff !important;
                border: 1px solid #d9dde2 !important;
                box-shadow: 0 10px 28px rgba(31, 35, 41, 0.12) !important;
            }
            div[data-testid="stExpander"] {
                background: #ffffff;
                border: 1px solid #dfe2e6;
                border-radius: 8px;
                box-shadow: none;
            }

            /* Mensajes institucionales neutros: el color queda reservado al acento. */
            div[data-testid="stAlert"] {
                background: #ffffff !important;
                border: 1px solid #dfe2e6 !important;
                border-left: 4px solid var(--labs-yellow) !important;
                color: var(--labs-text) !important;
            }
            div[data-testid="stAlert"] svg {
                fill: #ad5a00 !important;
                color: #ad5a00 !important;
            }

            .labs-section-title {
                margin: 0.35rem 0 1rem 0;
                padding: 1rem 1.15rem;
                background: #ffffff;
                border: 1px solid var(--labs-border);
                border-left: 8px solid var(--labs-red);
                border-radius: 8px;
                box-shadow: 0 6px 18px rgba(43, 31, 20, 0.06);
            }

            .labs-section-title h2 {
                margin: 0;
                font-size: 1.35rem;
                line-height: 1.2;
                color: var(--labs-red-dark);
            }

            .labs-section-title p {
                margin: 0.35rem 0 0 0;
                color: var(--labs-muted);
                font-size: 0.92rem;
            }

            .labs-topbar {
                margin: -2rem calc(50% - 50vw) 1.6rem calc(50% - 50vw);
                padding: 0.85rem max(1rem, calc((100vw - 1180px) / 2));
                background: #18212c;
                color: #e8edf2;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
                font-size: 0.92rem;
                box-shadow: 0 2px 12px rgba(24, 33, 44, 0.16);
            }

            .labs-topbar strong {
                color: var(--labs-yellow);
                font-weight: 800;
            }

            .labs-topbar nav {
                display: flex;
                gap: 0.8rem;
                color: #d5dbe2;
                font-weight: 700;
                white-space: nowrap;
            }

            .labs-topbar nav span + span {
                border-left: 1px solid rgba(255,255,255,0.24);
                padding-left: 0.8rem;
            }

            .labs-hero {
                position: relative;
                overflow: hidden;
                margin: 0 0 1.1rem 0;
                padding: 1.35rem 1.45rem;
                border-radius: 14px;
                background:
                    linear-gradient(135deg, rgba(115,17,22,0.98) 0%, rgba(159,29,36,0.96) 48%, rgba(255,248,217,0.94) 48.2%, rgba(255,255,255,0.98) 100%);
                border: 1px solid rgba(226, 216, 203, 0.95);
                box-shadow: 0 14px 34px rgba(43, 31, 20, 0.10);
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto;
                gap: 1.25rem;
                align-items: center;
            }

            .labs-hero-main {
                color: #ffffff;
                display: grid;
                grid-template-columns: auto minmax(0, 1fr);
                gap: 1rem;
                align-items: center;
            }

            .labs-seal {
                width: 154px;
                height: 154px;
                border-radius: 18px;
                border: 1px solid rgba(255,255,255,0.72);
                background:
                    linear-gradient(135deg, rgba(255,255,255,0.96) 0%, rgba(255,248,217,0.92) 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0.65rem;
                box-shadow:
                    inset 0 0 0 6px rgba(159,29,36,0.05),
                    0 12px 28px rgba(70, 8, 12, 0.20);
                color: var(--labs-yellow);
                font-weight: 900;
                font-size: 1.05rem;
                line-height: 1.05;
                text-align: center;
            }

            .labs-seal img,
            .labs-brand-logo img {
                max-width: 100%;
                max-height: 100%;
                object-fit: contain;
            }

            .labs-hero-kicker {
                display: inline-flex;
                align-items: center;
                width: fit-content;
                max-width: 100%;
                padding: 0.32rem 0.72rem;
                border-radius: 999px;
                background: rgba(242, 194, 48, 0.18);
                color: #ffe183;
                font-size: 0.72rem;
                font-weight: 900;
                letter-spacing: 0.03em;
                text-transform: uppercase;
                line-height: 1.25;
            }

            .labs-hero h1 {
                border-left: 0;
                padding-left: 0 !important;
                margin: 0.55rem 0 0.35rem 0;
                color: #fffaf1;
                font-size: clamp(1.9rem, 3vw, 3rem);
                font-weight: 900 !important;
                line-height: 1 !important;
                text-shadow:
                    0 2px 0 rgba(70, 8, 12, 0.72),
                    0 8px 22px rgba(70, 8, 12, 0.30);
                -webkit-text-stroke: 0.35px rgba(70, 8, 12, 0.45);
            }

            .labs-hero p {
                margin: 0;
                max-width: 720px;
                color: #fff2c8;
                font-size: 0.96rem;
                line-height: 1.6;
                font-weight: 650;
                text-shadow: 0 1px 10px rgba(70, 8, 12, 0.34);
            }

            .labs-hero-aside {
                display: flex;
                align-items: center;
                justify-content: flex-end;
                gap: 0.75rem;
                min-width: 330px;
            }

            .labs-user-menu {
                position: relative;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                line-height: 1;
            }

            .labs-user-menu summary {
                width: 48px;
                height: 48px;
                border: 1px solid #d9dde2;
                border-radius: 14px;
                display: inline-grid;
                place-items: center;
                background: #ffffff;
                color: var(--labs-red-dark);
                font-size: 1.35rem;
                font-weight: 900;
                cursor: pointer;
                list-style: none;
                box-shadow: 0 8px 22px rgba(24,33,44,0.10);
                padding: 0;
                user-select: none;
            }

            .labs-user-menu[open] summary {
                border-color: var(--labs-red);
                box-shadow: 0 10px 26px rgba(148,20,25,0.18);
            }

            .labs-user-menu summary::-webkit-details-marker {
                display: none;
            }

            .labs-user-menu-panel {
                position: absolute;
                right: 0;
                top: calc(100% + 0.55rem);
                width: 178px;
                padding: 0.45rem;
                border: 1px solid var(--labs-border);
                border-radius: 14px;
                background: #ffffff;
                box-shadow: 0 18px 42px rgba(24,33,44,0.18);
                z-index: 1000;
            }

            .labs-user-menu-panel a {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 38px;
                padding: 0.65rem 0.75rem;
                border-radius: 10px;
                color: var(--labs-red-dark);
                text-decoration: none;
                font-family: Inter, Roboto, Montserrat, "Segoe UI", system-ui, sans-serif;
                font-size: 0.92rem;
                font-weight: 800;
                letter-spacing: 0.01em;
            }

            .labs-user-menu-panel a:hover {
                background: #fff4f4;
            }

            .labs-brand-logo {
                width: 164px;
                height: 88px;
                border-radius: 12px;
                background: rgba(255,255,255,0.88);
                border: 1px solid rgba(226,216,203,0.95);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0.7rem;
                color: var(--labs-red-dark);
                font-weight: 900;
                text-align: center;
                box-shadow: 0 10px 24px rgba(43,31,20,0.08);
            }

            @media (max-width: 900px) {
                .labs-topbar,
                .labs-topbar nav {
                    align-items: flex-start;
                    flex-direction: column;
                    white-space: normal;
                }

                .labs-topbar nav span + span {
                    border-left: 0;
                    padding-left: 0;
                }

                .labs-hero {
                    grid-template-columns: 1fr;
                    padding: 1.15rem;
                    background: linear-gradient(180deg, #731116 0%, #9f1d24 68%, #fffaf1 68.2%, #ffffff 100%);
                }

                .labs-hero-main {
                    grid-template-columns: 1fr;
                }

                .labs-seal {
                    width: 112px;
                    height: 112px;
                }

                .labs-hero-aside {
                    justify-content: flex-start;
                    min-width: 0;
                    flex-wrap: wrap;
                }
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("""
        <style>
            :root {
                --labs-red: #8f1720;
                --labs-red-dark: #5f0d14;
                --labs-gold: #c8a21a;
                --labs-ink: #17202a;
                --labs-muted: #667085;
                --labs-bg: #f5f7fb;
                --labs-surface: #ffffff;
                --labs-line: #d8dee8;
                --labs-soft: #eef2f7;
            }

            html, body, .stApp, [class*="css"] {
                font-family: "Segoe UI", "Inter", "Roboto", Arial, sans-serif !important;
            }

            .stApp {
                background:
                    linear-gradient(180deg, rgba(143, 23, 32, 0.075), rgba(245, 247, 251, 0) 260px),
                    var(--labs-bg) !important;
                color: var(--labs-ink) !important;
            }

            .block-container {
                max-width: 1500px;
                padding-top: 0 !important;
                padding-left: 2.35rem !important;
                padding-right: 2.35rem !important;
                padding-bottom: 1rem !important;
            }

            html, body, .stApp, .stMarkdown, .stText, label {
                font-size: 16.5px !important;
            }

            div[data-testid="stMarkdownContainer"] p,
            div[data-testid="stMarkdownContainer"] li,
            .stDataFrame,
            .stTable {
                font-size: 1rem !important;
            }

            h1, h2, h3 {
                color: var(--labs-red-dark) !important;
                letter-spacing: 0 !important;
            }

            .labs-topbar {
                display: none !important;
            }

            .labs-topbar strong {
                color: #ffffff !important;
                font-weight: 850 !important;
            }

            .labs-topbar nav {
                color: rgba(255,255,255,0.82) !important;
                font-size: 0.82rem;
                letter-spacing: 0.01em;
            }

            .labs-hero {
                margin: -0.35rem calc(50% - 50vw) 0 calc(50% - 50vw) !important;
                padding: 0.72rem max(2.35rem, calc((100vw - 1500px) / 2 + 2.35rem)) 0.62rem max(2.35rem, calc((100vw - 1500px) / 2 + 2.35rem)) !important;
                border-radius: 0 !important;
                border: 0 !important;
                border-top: 0 !important;
                border-bottom: 1px solid var(--labs-line) !important;
                background:
                    linear-gradient(90deg, rgba(143,23,32,0.055), rgba(255,255,255,0) 38%),
                    var(--labs-surface) !important;
                box-shadow: 0 10px 28px rgba(23, 32, 42, 0.055) !important;
                grid-template-columns: minmax(0, 1fr) auto !important;
                position: sticky;
                top: 0;
                z-index: 10;
                backdrop-filter: blur(14px);
            }

            .labs-hero::after {
                content: "";
                position: absolute;
                left: max(2.35rem, calc((100vw - 1500px) / 2 + 2.35rem));
                right: max(2.35rem, calc((100vw - 1500px) / 2 + 2.35rem));
                bottom: 0;
                height: 4px;
                background: linear-gradient(90deg, var(--labs-red) 0 72%, var(--labs-gold) 72% 100%);
            }

            .labs-hero-main {
                color: var(--labs-ink) !important;
                gap: 0.75rem !important;
            }

            .labs-seal {
                width: clamp(74px, 7vw, 98px) !important;
                height: clamp(78px, 7.5vw, 104px) !important;
                border-radius: 16px !important;
                background: rgba(255,255,255,0.82) !important;
                border: 1px solid rgba(216,222,232,0.9) !important;
                box-shadow: 0 12px 30px rgba(23,32,42,0.08) !important;
                padding: 0.35rem !important;
            }

            .labs-hero-kicker {
                display: none !important;
            }

            .labs-title-meta {
                display: inline-flex;
                align-items: center;
                gap: 0.45rem;
                margin-top: 0.35rem;
                color: var(--labs-muted);
                font-size: 0.82rem;
                font-weight: 650;
            }

            .labs-title-meta span + span {
                border-left: 1px solid var(--labs-line);
                padding-left: 0.45rem;
            }

            .labs-hero h1 {
                margin: 0.08rem 0 0.18rem 0 !important;
                color: var(--labs-red-dark) !important;
                font-family: Inter, Montserrat, "Segoe UI", system-ui, sans-serif !important;
                font-size: clamp(1.85rem, 2.8vw, 3.05rem) !important;
                font-weight: 900 !important;
                line-height: 0.98 !important;
                letter-spacing: -0.045em !important;
                text-shadow: 0 1px 0 rgba(255,255,255,0.8) !important;
                -webkit-text-stroke: 0 !important;
            }

            .labs-hero p {
                color: #475467 !important;
                font-size: 0.94rem !important;
                line-height: 1.35 !important;
                margin: 0.12rem 0 !important;
                font-weight: 560 !important;
                text-shadow: none !important;
            }

            .labs-brand-logo {
                width: 138px !important;
                height: 72px !important;
                border-radius: 8px !important;
                border: 0 !important;
                background: #ffffff !important;
                box-shadow: none !important;
            }

            .labs-status-chip {
                min-width: 112px;
                border: 1px solid var(--labs-line);
                border-radius: 8px;
                padding: 0.4rem 0.6rem;
                background: #f8fafc;
                text-align: left;
            }

            .labs-status-chip strong {
                display: block;
                color: var(--labs-red-dark);
                font-size: 0.98rem;
                line-height: 1.1;
                font-weight: 850;
            }

            .labs-status-chip span {
                display: block;
                margin-top: 0.16rem;
                color: var(--labs-muted);
                font-size: 0.72rem;
                font-weight: 750;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .labs-summary {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                grid-auto-rows: 1fr;
                align-items: stretch;
                gap: 0.75rem;
                margin: 1rem 0 1rem 0;
            }

            .labs-summary-item {
                background: var(--labs-surface);
                border: 1px solid var(--labs-line);
                border-radius: 8px;
                padding: 0.78rem 0.95rem;
                box-shadow: 0 8px 20px rgba(23, 32, 42, 0.055);
                min-height: 86px;
                height: 100%;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }

            .labs-summary-item strong {
                display: block;
                color: var(--labs-red-dark);
                font-size: 1.28rem;
                line-height: 1.1;
                font-weight: 850;
            }

            .labs-summary-item span {
                display: block;
                margin-top: 0.18rem;
                color: var(--labs-muted);
                font-size: 0.78rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .stTabs [data-baseweb="tab-list"] {
                position: relative;
                margin: -1.65rem calc(50% - 50vw) 0 calc(50% - 50vw) !important;
                padding: 0 max(2.35rem, calc((100vw - 1500px) / 2 + 2.35rem));
                gap: 0;
                background: #941419;
                border: 0;
                border-radius: 0;
                box-shadow: 0 6px 14px rgba(95, 13, 20, 0.14);
                overflow-x: auto;
            }

            .stTabs {
                margin-top: 0 !important;
            }

            .stTabs [data-baseweb="tab-list"] button {
                position: relative;
                min-height: 64px;
                border-radius: 0 !important;
                border: 0 !important;
                padding: 0.9rem 1.25rem 0.9rem 1.62rem !important;
                background: transparent !important;
                text-transform: uppercase;
            }

            .stTabs [data-baseweb="tab-list"] button::before {
                content: "/";
                position: absolute;
                left: 0.35rem;
                top: 50%;
                transform: translateY(-50%) skewX(-12deg);
                color: #c8a21a;
                font-size: 1.55rem;
                font-weight: 300;
                line-height: 1;
            }

            .stTabs [data-baseweb="tab-list"] button:first-child::before {
                content: "";
            }

            .stTabs [data-baseweb="tab-list"] button:hover {
                background: rgba(255,255,255,0.08) !important;
            }

            .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
                font-size: 1.03rem !important;
                font-weight: 900 !important;
                color: #ffffff !important;
                letter-spacing: 0 !important;
                white-space: nowrap;
            }

            .stTabs [data-baseweb="tab-panel"] {
                padding-top: 0.85rem !important;
            }

            div[data-testid="stElementContainer"]:has(.labs-hero) {
                margin-bottom: 0 !important;
            }

            .labs-weekbar-title {
                margin: 0 !important;
                text-align: center;
                color: var(--labs-red-dark);
                font-family: Georgia, Cambria, "Times New Roman", serif;
                font-size: clamp(1.28rem, 1.5vw, 1.85rem);
                font-weight: 800;
                line-height: 1.15;
            }

            .labs-day-label {
                margin: 0.1rem 0 0.55rem 0;
                color: var(--labs-muted);
                font-weight: 800;
                font-size: 1rem;
            }

            .labs-day-today-indicator {
                height: 1.45rem;
                margin: 0 0 0.18rem 0;
                text-align: center;
                color: transparent;
                font-size: 0.82rem;
                font-weight: 900;
                line-height: 1.2;
                text-transform: uppercase;
                letter-spacing: 0.03em;
            }

            .labs-day-today-indicator.is-today {
                color: var(--labs-red-dark);
            }

            div[data-testid="stHorizontalBlock"]:has(.labs-weekbar-title) {
                align-items: center;
                margin-bottom: 0.45rem;
            }

            div[data-testid="stHorizontalBlock"]:has(.labs-weekbar-title) .stButton button {
                min-height: 46px;
                font-weight: 850 !important;
            }

            .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
                background: #7d1015 !important;
                border-bottom: 0 !important;
            }

            .stTabs [data-baseweb="tab-list"] button[aria-selected="true"]::after {
                content: "";
                position: absolute;
                left: 1.45rem;
                right: 0.85rem;
                bottom: 0;
                height: 5px;
                background: #c8a21a;
            }

            .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] [data-testid="stMarkdownContainer"] p {
                color: #ffffff !important;
            }

            div[role="dialog"] div[data-testid="stAlert"] {
                background: #f7f7f8 !important;
                border: 1px solid #dedfe3 !important;
                color: #ad5a00 !important;
            }
            div[role="dialog"] div[data-testid="stAlert"] svg { fill:#ad5a00 !important; color:#ad5a00 !important; }
            div[role="dialog"] button[aria-label="Close"],
            div[data-testid="stDialog"] button[aria-label="Close"] {
                display:inline-flex !important; color:#731116 !important;
                background:#fff7d6 !important; border:1px solid #d6a81f !important; opacity:1 !important;
            }
            button[aria-pressed="true"], [role="radiogroup"] label:has(input:checked) {
                background:#fff2bf !important; color:#68131a !important; border-color:#d6a81f !important;
            }
            input:focus, textarea:focus, select:focus {
                border-color:#9f1d24 !important; box-shadow:0 0 0 1px #9f1d24 !important; outline:none !important;
            }
            .stButton button {
                border-radius: 6px !important;
                border-color: var(--labs-line) !important;
                color: var(--labs-red-dark) !important;
                background: #ffffff !important;
                box-shadow: 0 1px 2px rgba(23, 32, 42, 0.06);
            }

            .stButton button:hover {
                border-color: var(--labs-red) !important;
                box-shadow: 0 8px 20px rgba(143, 23, 32, 0.12) !important;
                transform: translateY(-1px);
            }

            div[data-testid="stDataFrame"],
            div[data-testid="stDataEditor"],
            div[data-testid="stTable"] {
                border: 1px solid var(--labs-line);
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 8px 22px rgba(23, 32, 42, 0.05);
            }

            .labs-section-title {
                background: transparent !important;
                border: 0 !important;
                border-left: 5px solid var(--labs-red) !important;
                border-radius: 0 !important;
                box-shadow: none !important;
                padding: 0.2rem 0 0.25rem 0.8rem !important;
                margin: 0.45rem 0 0.55rem 0 !important;
            }

            .labs-section-title h2 {
                color: var(--labs-ink) !important;
                font-size: 1.25rem !important;
                font-weight: 850 !important;
            }

            .labs-section-title p {
                color: var(--labs-muted) !important;
                font-size: 0.88rem !important;
            }

            /* Navegación institucional compatible con la estructura actual de Streamlit. */
            div[data-testid="stTabs"] div[role="tablist"],
            .stTabs div[role="tablist"] {
                position: relative !important;
                margin: -0.55rem calc(50% - 50vw) 0 calc(50% - 50vw) !important;
                padding: 0 max(2.35rem, calc((100vw - 1500px) / 2 + 2.35rem)) !important;
                gap: 0 !important;
                min-height: 48px !important;
                background: #941419 !important;
                border: 0 !important;
                border-radius: 0 !important;
                box-shadow: 0 6px 14px rgba(95, 13, 20, 0.14) !important;
                overflow-x: auto !important;
            }

            div[data-testid="stTabs"] [role="tab"],
            .stTabs [role="tab"] {
                position: relative !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                flex: 0 0 auto !important;
                min-height: 48px !important;
                padding: 0.5rem 1rem 0.5rem 1.35rem !important;
                border: 0 !important;
                border-radius: 0 !important;
                background: transparent !important;
                color: #ffffff !important;
            }

            div[data-testid="stTabs"] [role="tab"] [data-testid="stMarkdownContainer"] p,
            div[data-testid="stTabs"] [role="tab"] p,
            div[data-testid="stTabs"] [role="tab"] span,
            .stTabs [role="tab"] p,
            .stTabs [role="tab"] span {
                color: #ffffff !important;
                font-size: 1.03rem !important;
                font-weight: 900 !important;
                white-space: nowrap !important;
            }

            div[data-testid="stTabs"] [role="tab"]::before,
            .stTabs [role="tab"]::before {
                content: "/";
                position: absolute;
                left: 0.35rem;
                top: 50%;
                transform: translateY(-50%) skewX(-12deg);
                color: #c8a21a;
                font-size: 1.55rem;
                font-weight: 300;
            }

            div[data-testid="stTabs"] [role="tab"]:first-child::before,
            .stTabs [role="tab"]:first-child::before {
                content: "";
            }

            div[data-testid="stTabs"] [role="tab"][aria-selected="true"],
            .stTabs [role="tab"][aria-selected="true"] {
                background: #7d1015 !important;
                box-shadow: inset 0 -5px 0 #c8a21a !important;
            }

            div[data-testid="stTabs"] [role="tab"]:hover,
            .stTabs [role="tab"]:hover {
                background: rgba(255,255,255,0.08) !important;
            }

            @media (max-width: 1000px) {
                .labs-summary {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }

                .labs-hero {
                    grid-template-columns: 1fr !important;
                }

                .labs-hero-main {
                    grid-template-columns: auto minmax(0, 1fr) !important;
                }

                .labs-hero-aside {
                    justify-content: flex-start !important;
                }
            }

            @media (max-width: 620px) {
                .block-container {
                    padding-left: 1rem !important;
                    padding-right: 1rem !important;
                }

                .labs-hero {
                    padding-left: 1rem !important;
                    padding-right: 1rem !important;
                }

                .labs-hero::after {
                    left: 1rem;
                    right: 1rem;
                }

                .stTabs [data-baseweb="tab-list"],
                .stTabs div[role="tablist"] {
                    padding-left: 1rem;
                    padding-right: 1rem;
                }

                .labs-summary {
                    grid-template-columns: 1fr;
                }

                .labs-hero-main {
                    grid-template-columns: 1fr !important;
                }
            }
        </style>
    """, unsafe_allow_html=True)

    escudo_src = imagen_asset("escudo_ud.png") or imagen_asset("escudo_ud.jpg") or imagen_asset("escudo_ud.svg")

    labs_src = imagen_asset("logo_labs.png") or imagen_asset("logo_labs.jpg") or imagen_asset("logo_labs.svg")

    facultad_src = imagen_asset("logo_ingenieria.png") or imagen_asset("logo_ingenieria.jpg") or imagen_asset("logo_ingenieria.svg")

    escudo_html = f'<img src="{escudo_src}" alt="Escudo Universidad Distrital">' if escudo_src else "UD<br>LABS"

    labs_logo_html = f'<img src="{labs_src}" alt="Laboratorios de Ingenieria">' if labs_src else "LABS"

    facultad_logo_html = f'<img src="{facultad_src}" alt="Facultad de Ingenieria">' if facultad_src else "Ingenieria"

    ahora_local = datetime.now(timezone(timedelta(hours=-5)))
    fecha_panel = ahora_local.strftime("%d/%m/%Y")
    hora_panel = ahora_local.strftime("%H:%M")

    usuario_menu = escape(str(usuario_actual))

    if labs_src:
        st.markdown(
            f"""
            <style>
                .stApp::before {{
                    content: "";
                    position: fixed;
                    inset: 0;
                    pointer-events: none;
                    z-index: 0;
                    background-image: url('{labs_src}');
                    background-repeat: repeat;
                    background-size: 220px auto;
                    opacity: 0.1;
                    transform: rotate(-18deg) scale(1.22);
                    transform-origin: center;
                }}
                .stApp > * {{
                    position: relative;
                    z-index: 1;
                }}
                .block-container {{
                    background: rgba(255,255,255,0.68);
                    border: 1px solid rgba(216,222,232,0.72);
                    border-radius: 24px;
                    box-shadow: 0 22px 70px rgba(23,32,42,0.08);
                    margin-top: 0.85rem;
                }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="labs-topbar">
            <div><strong>Universidad Distrital Francisco José de Caldas</strong> · Sistema institucional de gestión de laboratorios</div>
            <nav>
                <span>Horario y reservas</span>
                <span>Asistencias</span>
                <span>Multas y reportes</span>
            </nav>
        </div>
        <section class="labs-hero">
            <div class="labs-hero-main">
                <div class="labs-seal">{escudo_html}</div>
                <div>
                    <div class="labs-hero-kicker">Sistema de Laboratorios de Electrica, Electronica y Física</div>
                    <h1>GESTIÓN DE LABORATORIOS</h1>
                    <p>Reservas, préstamos y atención a la comunidad académica.</p>
                    <div class="labs-title-meta">
                        <span>Facultad de Ingenieria</span>
                        <span>Gestion academica y tecnica</span>
                    </div>
                </div>
            </div>
            <aside class="labs-hero-aside">
                <div class="labs-status-chip">
                    <strong>{fecha_panel}</strong>
                    <span>Fecha</span>
                </div>
                <div class="labs-status-chip">
                    <strong id="labs-live-clock">{hora_panel}</strong>
                    <span>Hora local</span>
                </div>
                <details class="labs-user-menu">
                    <summary aria-label="Menu de usuario">☰</summary>
                    <div class="labs-user-menu-panel">
                        <button type="button" id="season-menu-close" aria-label="Cerrar menú">×</button>
                        <label for="season-menu-mode">Temporada visual</label>
                        <select id="season-menu-mode" aria-label="Temporada visual">
                            <option value="auto">Automática por calendario</option>
                            <option value="standard">Marca institucional</option>
                            <option value="friendship">Amor y Amistad</option>
                            <option value="halloween">Halloween</option>
                            <option value="rain">Noviembre · Lluvia</option>
                            <option value="christmas">Navidad</option>
                            <option value="birthday">Cumpleaños · Rosa</option>
                            <option value="birthday_blue">Cumpleaños · Azul</option>
                            <option value="colombia">Selección Colombia</option>
                        </select>
                        <label class="season-menu-effects"><input id="season-menu-effects" type="checkbox"> Iconos flotantes</label>
                        <a href="/logout" target="_self">Cerrar sesión</a>
                    </div>
                </details>
            </aside>
        </section>
        """,
        unsafe_allow_html=True,
    )


    # El reloj pertenece a la cabecera, no a las páginas con lector de códigos.
    # Ejecutarlo en la ventana principal evita perder el timer al desmontar iframes.
    clock_script = """
        const host = window;
        if (host.__labsClockTimer) host.clearInterval(host.__labsClockTimer);
        function updateClock() {
            const clock = host.document.getElementById("labs-live-clock");
            if (!clock) return;
            clock.textContent = new Intl.DateTimeFormat("es-CO", {
                timeZone: "America/Bogota", hour: "2-digit", minute: "2-digit",
                hourCycle: "h23"
            }).format(new Date());
        }
        updateClock();
        host.__labsClockTimer = host.setInterval(updateClock, 1000);
    """
    st.iframe("<script>window.parent.Function(" + json.dumps(clock_script) + ")();</script>",
              height=1, tab_index=-1)


def preparar_lector():
    st.components.v1.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            function normalizeScan(value, allowBase64 = true) {
                const text = String(value || "").trim();
                if (!text) return text;
                const documentKeys = ["nid", "cc", "cedula", "c?dula", "documento", "identificacion", "identificaci?n", "nro_identificacion"];
                try {
                    const parsed = JSON.parse(text);
                    if (parsed && typeof parsed === "object") {
                        for (const key of documentKeys) {
                            if (parsed[key] !== undefined) {
                                const clean = String(parsed[key]).replace(/\D/g, "");
                                if (clean.length >= 6 && clean.length <= 10) return clean;
                            }
                        }
                        const fallback = JSON.stringify(parsed).match(/\d{6,10}/);
                        if (fallback) return fallback[0];
                    }
                } catch (error) {}
                const match = text.match(/"(?:nid|cc|cedula|c?dula|documento|identificacion|identificaci?n|nro_identificacion)"\s*:\s*"?(\d{6,10})"?/i);
                if (match) return match[1];
                if (/nid|[\[\]{}*\u00d1\u00f1]/i.test(text)) {
                    const dirtyMatch = text.match(/\d{6,10}/);
                    if (dirtyMatch) return dirtyMatch[0];
                }
                if (allowBase64) {
                    const chunks = text.match(/[A-Za-z0-9+/=_-]{8,}/g) || [];
                    chunks.sort((a, b) => b.length - a.length);
                    for (const chunk of chunks) {
                        const stripped = chunk.replace(/=+$/g, "");
                        const fragments = [];
                        for (let start = 0; start <= Math.max(0, stripped.length - 8); start++) {
                            for (let end = stripped.length; end >= start + 8; end--) {
                                fragments.push(stripped.slice(start, end));
                            }
                        }
                        fragments.sort((a, b) => b.length - a.length);
                        const seen = new Set();
                        for (const fragment of fragments) {
                            if (seen.has(fragment)) continue;
                            seen.add(fragment);
                            try {
                                const piece = fragment.replace(/-/g, "+").replace(/_/g, "/");
                                const padded = piece + "=".repeat((4 - (piece.length % 4)) % 4);
                                const decoded = decodeURIComponent(escape(window.parent.atob(padded)));
                                if (decoded && /\d{6,10}|nid|cc|cedula|documento|identificacion|{/i.test(decoded)) {
                                    return normalizeScan(decoded, false);
                                }
                            } catch (error) {}
                        }
                    }
                }
                return text;
            }
                return text;
            }

            if (window.parent.__labsScannerCleanup) {
                window.parent.__labsScannerCleanup();
            }
            const onScanEnter = function (event) {
                const target = event.target;
                if (!target || target.tagName !== "INPUT") return;
                if (event.key !== "Enter") return;
                const clean = normalizeScan(target.value);
                if (clean !== target.value) {
                    target.value = clean;
                    target.dispatchEvent(new Event("input", { bubbles: true }));
                    target.dispatchEvent(new Event("change", { bubbles: true }));
                }
            };
            doc.addEventListener("keydown", onScanEnter, true);
            window.parent.__labsScannerCleanup = function () {
                doc.removeEventListener("keydown", onScanEnter, true);
            };
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )


def restaurar_scroll_horario():
    st.components.v1.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            const savedY = window.parent.sessionStorage.getItem("horario-window-y");
            const savedX = window.parent.sessionStorage.getItem("horario-body-x");
            const savedAnchor = window.parent.sessionStorage.getItem("horario-restore-anchor");

            if (savedY === null && savedX === null && savedAnchor === null) return;

            try {
                window.parent.history.scrollRestoration = "manual";
            } catch (error) {}

            function uniqueElements(elements) {
                return elements.filter(function (element, index) {
                    return element && elements.indexOf(element) === index;
                });
            }

            function possibleScrollContainers() {
                return uniqueElements([
                    doc.scrollingElement,
                    doc.documentElement,
                    doc.body,
                    doc.querySelector("[data-testid='stAppViewContainer']"),
                    doc.querySelector("section.main"),
                    doc.querySelector(".stApp")
                ]);
            }

            function restore() {
                if (savedY !== null) {
                    const y = Number(savedY) || 0;
                    window.parent.scrollTo({ top: y, left: 0, behavior: "auto" });
                    possibleScrollContainers().forEach(function (element) {
                        if (element && typeof element.scrollTop === "number") {
                            element.scrollTop = y;
                        }
                    });
                } else if (savedAnchor !== null) {
                    const anchor = doc.getElementById(savedAnchor);
                    if (anchor) {
                        anchor.scrollIntoView({ block: "start", inline: "nearest", behavior: "auto" });
                    }
                }

                if (savedX !== null) {
                    const x = Number(savedX) || 0;
                    const headers = doc.querySelectorAll(".horario-general-header-scroll");
                    const bodies = doc.querySelectorAll(".horario-general-body-scroll");
                    const header = headers[headers.length - 1];
                    const body = bodies[bodies.length - 1];
                    if (header) header.scrollLeft = x;
                    if (body) body.scrollLeft = x;
                }
            }

            [0, 60, 140, 280, 520, 900, 1400, 2200].forEach(function (delay) {
                window.setTimeout(restore, delay);
            });

            window.setTimeout(function () {
                restore();
                window.parent.sessionStorage.removeItem("horario-window-y");
                window.parent.sessionStorage.removeItem("horario-body-x");
                window.parent.sessionStorage.removeItem("horario-restore-anchor");
            }, 2600);
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )
