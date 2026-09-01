# app.py
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

import calendario as cal
import database as db
import estudiantes as est
import reportes as rep
import utils
from asistencias_pendientes import mostrar_panel_asistencias_pendientes
from constants import (
    DIAS,
    FIN_CLASES_PERIODO_ACADEMICO,
    INICIO_PERIODO_ACADEMICO,
    LABORATORIOS,
    PERIODO_ACADEMICO,
)
from ui_components import mostrar_deudores, mostrar_horario_general


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


def inicio_semana_actual():
    hoy = datetime.now().date()
    return hoy - timedelta(days=hoy.weekday())


def inicializar_estado():
    valores_por_defecto = {
        "editor_version": 0,
        "eliminar_version": 0,
        "confirmar_inasistencia": False,
        "inasistencias_pendientes": [],
        "cambios_pendientes": [],
        "horario_editar": None,
        "labs_semana_inicio": inicio_semana_actual(),
        "lab_actual": list(LABORATORIOS.keys())[0],
    }

    for clave, valor in valores_por_defecto.items():
        if clave not in st.session_state:
            st.session_state[clave] = valor


def cambiar_semana(dias):
    st.session_state.labs_semana_inicio += timedelta(days=dias)

    lunes = st.session_state.labs_semana_inicio
    hoy = datetime.now().date()
    if lunes == inicio_semana_actual() and hoy.weekday() < len(DIAS):
        idx_dia = hoy.weekday()
    else:
        idx_dia = 0

    dia_semana = DIAS[idx_dia]
    nueva_fecha = lunes + timedelta(days=idx_dia)
    st.session_state.dia_seleccionado_guardado = f"{dia_semana} {nueva_fecha.strftime('%d/%m')}"
    st.session_state.dia_seleccionado_manual = False
    st.rerun()


def numero_semana_academica(fecha):
    """Calcula la semana lectiva desde el inicio oficial del periodo."""
    inicio = datetime.strptime(INICIO_PERIODO_ACADEMICO, "%Y-%m-%d").date()
    fin = datetime.strptime(FIN_CLASES_PERIODO_ACADEMICO, "%Y-%m-%d").date()
    if fecha < inicio or fecha > fin:
        return None
    return ((fecha - inicio).days // 7) + 1


def opcion_dia_actual(fechas_semana, opciones_dias):
    hoy = datetime.now().date()
    for i, fecha in enumerate(fechas_semana):
        if fecha == hoy:
            return opciones_dias[i]
    return opciones_dias[0]


st.set_page_config(page_title="LABS", layout="wide")
inicializar_estado()
db.init_db()

st.markdown("""
    <style>
        :root {
            --labs-red: #9f1d24;
            --labs-red-dark: #731116;
            --labs-yellow: #f2c230;
            --labs-yellow-soft: #fff9e6;
            --labs-bg: #f7f7f8;
            --labs-surface: #ffffff;
            --labs-border: #e2d8cb;
            --labs-text: #1e2329;
            --labs-muted: #6b7280;
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
            padding-top: 1.1rem !important;
            padding-left: 2.35rem !important;
            padding-right: 2.35rem !important;
            padding-bottom: 3rem !important;
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
            margin: 0 calc(50% - 50vw) 0 calc(50% - 50vw) !important;
            padding: 1.25rem max(2.35rem, calc((100vw - 1500px) / 2 + 2.35rem)) 1rem max(2.35rem, calc((100vw - 1500px) / 2 + 2.35rem)) !important;
            border-radius: 0 !important;
            border: 0 !important;
            border-top: 0 !important;
            border-bottom: 1px solid var(--labs-line) !important;
            background: var(--labs-surface) !important;
            box-shadow: 0 8px 24px rgba(23, 32, 42, 0.04) !important;
            grid-template-columns: minmax(0, 1fr) auto !important;
            position: relative;
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
            gap: 1.25rem !important;
        }

        .labs-seal {
            width: 108px !important;
            height: 108px !important;
            border-radius: 0 !important;
            background: #ffffff !important;
            border: 0 !important;
            box-shadow: none !important;
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
            margin: 0.2rem 0 0.22rem 0 !important;
            color: #101820 !important;
            font-family: Georgia, Cambria, "Times New Roman", serif !important;
            font-size: clamp(2.15rem, 2.55vw, 3.25rem) !important;
            font-weight: 800 !important;
            line-height: 1.02 !important;
            text-shadow: none !important;
            -webkit-text-stroke: 0 !important;
        }

        .labs-hero p {
            color: var(--labs-muted) !important;
            font-size: 1.02rem !important;
            line-height: 1.5 !important;
            font-weight: 500 !important;
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
            padding: 0.62rem 0.78rem;
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
            gap: 0.75rem;
            margin: 1rem 0 1rem 0;
        }

        .labs-summary-item {
            background: var(--labs-surface);
            border: 1px solid var(--labs-line);
            border-radius: 8px;
            padding: 0.78rem 0.95rem;
            box-shadow: 0 8px 20px rgba(23, 32, 42, 0.055);
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
            margin: -1.65rem calc(50% - 50vw) 0 calc(50% - 50vw) !important;
            padding: 0 max(2.35rem, calc((100vw - 1500px) / 2 + 2.35rem)) !important;
            gap: 0 !important;
            min-height: 64px !important;
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
            min-height: 64px !important;
            padding: 0.9rem 1.25rem 0.9rem 1.62rem !important;
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
fecha_panel = datetime.now().strftime("%d/%m/%Y")

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
                <h1>Centro de Operacion de Laboratorios</h1>
                <p>Panel operativo para coordinar laboratorios, disponibilidad, asistencias y novedades del dia.</p>
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
                <strong id="labs-live-clock">--:--</strong>
                <span>Hora local</span>
            </div>
        </aside>
    </section>
    """,
    unsafe_allow_html=True,
)

st.components.v1.html(
    """
    <script>
    (function () {
        const doc = window.parent.document;
        function updateClock() {
            const clock = doc.getElementById("labs-live-clock");
            if (!clock) return;
            const now = new Date();
            clock.textContent = now.toLocaleTimeString("es-CO", {
                hour: "2-digit",
                minute: "2-digit",
                hour12: false
            });
        }
        updateClock();
        if (window.parent.__labsClockTimer) {
            window.parent.clearInterval(window.parent.__labsClockTimer);
        }
        window.parent.__labsClockTimer = window.parent.setInterval(updateClock, 15000);
    })();
    </script>
    """,
    height=0,
    scrolling=False,
)

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

reservas_actualizadas = utils.actualizar_reservas_vencidas()
if reservas_actualizadas:
    st.toast(f"{reservas_actualizadas} reservas vencidas marcadas como 'No asistió'")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "HORARIO GENERAL",
    "RESERVAS",
    "DEUDORES",
    "BUSCAR CÓDIGO",
    "REPORTES",
    "CARGAR DATOS",
])

with tab1:
    mostrar_panel_asistencias_pendientes()
    mostrar_horario_general()

with tab2:
    col1, col2, col3 = st.columns([1.35, 5, 1.35], gap="large")
    with col1:
        if st.button("< Semana anterior", key="reserva_semana_prev", use_container_width=True):
            cambiar_semana(-7)

    with col2:
        lunes = st.session_state.labs_semana_inicio
        semana_academica = numero_semana_academica(lunes)
        etiqueta_academica = (
            f"Semana académica {semana_academica} · {PERIODO_ACADEMICO}"
            if semana_academica is not None
            else f"Fuera del periodo lectivo · {PERIODO_ACADEMICO}"
        )
        st.markdown(
            f"<h3 class='labs-weekbar-title'>{etiqueta_academica}<br>"
            f"<span style='font-size:0.78em; font-weight:700;'>"
            f"{lunes.strftime('%d/%m/%Y')} al {(lunes + timedelta(days=6)).strftime('%d/%m/%Y')}"
            f"</span></h3>",
            unsafe_allow_html=True,
        )

    with col3:
        if st.button("Siguiente semana >", key="reserva_semana_next", use_container_width=True):
            cambiar_semana(7)

    lunes = st.session_state.labs_semana_inicio
    fechas_semana = [lunes + timedelta(days=i) for i in range(6)]

    opciones_dias = []
    for i, fecha in enumerate(fechas_semana):
        nombre_dia = DIAS[i]
        fecha_str = fecha.strftime("%d/%m")
        opciones_dias.append(f"{nombre_dia} {fecha_str}")

    opcion_hoy = opcion_dia_actual(fechas_semana, opciones_dias)

    if "dia_seleccionado_guardado" not in st.session_state:
        st.session_state.dia_seleccionado_guardado = opcion_hoy
        st.session_state.dia_seleccionado_manual = False
    elif (
        not st.session_state.get("dia_seleccionado_manual", False)
        and st.session_state.labs_semana_inicio == inicio_semana_actual()
    ):
        st.session_state.dia_seleccionado_guardado = opcion_hoy
    elif st.session_state.dia_seleccionado_guardado not in opciones_dias:
        st.session_state.dia_seleccionado_guardado = opciones_dias[0]
        st.session_state.dia_seleccionado_manual = False

    st.markdown("<div class='labs-day-label'>Selecciona el dia</div>", unsafe_allow_html=True)
    cols = st.columns(len(opciones_dias))

    for i, opcion in enumerate(opciones_dias):
        with cols[i]:
            es_hoy_visible = (
                st.session_state.labs_semana_inicio == inicio_semana_actual()
                and opcion == opcion_hoy
            )
            if es_hoy_visible:
                st.markdown("<div class='labs-day-today-indicator is-today'>▼ Hoy</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='labs-day-today-indicator'>&nbsp;</div>", unsafe_allow_html=True)

            seleccionada = opcion == st.session_state.dia_seleccionado_guardado
            if seleccionada:
                selected_marker = f"labs_selected_day_{i}"
                st.markdown(
                    f"""
                    <style id="{selected_marker}">
                        div[data-testid="stElementContainer"]:has(style#{selected_marker}) + div[data-testid="stElementContainer"] button:disabled {{
                            background: #fff7d6 !important;
                            border: 2px solid #d6a81f !important;
                            color: #68131a !important;
                            box-shadow: 0 6px 16px rgba(104, 19, 26, 0.14) !important;
                            font-weight: 900 !important;
                            opacity: 1 !important;
                        }}
                    </style>
                    """,
                    unsafe_allow_html=True,
                )

            def seleccionar_dia(valor=opcion):
                st.session_state.dia_seleccionado_guardado = valor
                st.session_state.dia_seleccionado_manual = True

            st.button(
                opcion,
                key=f"dia_btn_{i}",
                use_container_width=True,
                disabled=seleccionada,
                on_click=seleccionar_dia,
            )

    dia_actual = st.session_state.dia_seleccionado_guardado.split(" ")[0]

    cal.mostrar_calendario_interactivo(dia_actual)
    cal.mostrar_detalle_celda()
    cal.mostrar_formulario_reserva_profesor()
    cal.mostrar_formulario_asistencia_docente()

with tab3:
    mostrar_deudores()

with tab4:
    rep.mostrar_busqueda_codigo()

with tab5:
    rep.mostrar_reporte_completo()

with tab6:
    st.subheader("Gestión de Estudiantes")

    archivo = st.file_uploader(
        "Sube CSV/Excel (codigo, nombres, proyecto, multas)",
        type=["csv", "xlsx", "xls"],
        key="labs_archivo_estudiantes",
    )

    if archivo and st.button("Cargar", key="labs_cargar_estudiantes"):
        try:
            count = est.cargar_estudiantes(archivo)
            st.success(f"{count} estudiantes procesados")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {str(e)}")

    total = db.fetch_df("SELECT COUNT(*) FROM estudiantes").iloc[0, 0]
    st.write(f"**Estudiantes actuales:** {total}")
