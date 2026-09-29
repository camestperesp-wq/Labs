from auth import require_section
require_section("prestamos")
import streamlit as st
if "prestamo_id" in st.query_params:
    st.session_state.pasillos_seccion = "Devoluciones"
    st.session_state.pasillos_prestamo_destacado = st.query_params["prestamo_id"]
    del st.query_params["prestamo_id"]
if "codigo_prestamo" in st.query_params:
    st.session_state.pasillos_codigo_destacado = st.query_params["codigo_prestamo"]
    del st.query_params["codigo_prestamo"]


from prestamos_pasillos_ui import mostrar_prestamos_pasillos
from app_shell import preparar_lector
preparar_lector()

mostrar_prestamos_pasillos()
