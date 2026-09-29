"""Entrada de navegación: ejecuta exclusivamente la página seleccionada."""
import streamlit as st
import auth
import database as db
from routing import SECTIONS, can_access
from app_shell import mostrar_marco, mostrar_navegacion
from app_state import inicializar_estado
from alertas_inasistencias import mostrar_alertas_inasistencias
from asistencias_pendientes import mostrar_panel_asistencias_pendientes

st.set_page_config(page_title="LABS", layout="wide")
usuario_actual = auth.require_login()
user = auth.session(st.context.cookies.get(auth.COOKIE, ""))
if user is None:
    st.stop()

inicializar_estado()
db.ensure_initialized(str(db.DB_PATH.resolve()))
mostrar_marco(usuario_actual)

def abrir_horario():
    auth.require_section("horario")
    st.switch_page(SECTIONS["horario"][1])


# La raíz redirige al horario; no existe una sección de Inicio.
pages = [st.Page(abrir_horario, title="Horario general", default=True, visibility="hidden")]
pages.extend(st.Page(file, title=title, url_path=section)
             for section, (title, file) in SECTIONS.items() if can_access(user[2], section))
page = st.navigation(pages, position="hidden")
mostrar_navegacion(pages[1:], page)

# Compatibilidad con enlaces antiguos; ningún parámetro selecciona código arbitrario.
legacy = st.query_params.get("modulo", "")
destino = {"deudores": "deudores", "prestamos_pasillos": "prestamos"}.get(legacy)
if destino:
    auth.require_section(destino)
    for parametro, state_key in (("codigo_deudor", "deudor_search"),
                                 ("prestamo_id", "pasillos_prestamo_destacado"),
                                 ("codigo_prestamo", "pasillos_codigo_destacado")):
        if parametro in st.query_params:
            st.session_state[state_key] = st.query_params[parametro]
    if destino == "prestamos":
        st.session_state.pasillos_seccion = "Devoluciones"
    st.query_params.clear()
    st.switch_page(SECTIONS[destino][1])

if page.url_path:
    auth.require_section(page.url_path)
    mostrar_panel_asistencias_pendientes()
    mostrar_alertas_inasistencias()
page.run()
