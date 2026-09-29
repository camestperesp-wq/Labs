from auth import require_section
require_section("deudores")
import streamlit as st
if "codigo_deudor" in st.query_params:
    st.session_state.deudor_search = st.query_params["codigo_deudor"]
    del st.query_params["codigo_deudor"]


from ui_components import mostrar_deudores
from app_shell import preparar_lector
preparar_lector()

mostrar_deudores()
