from auth import require_section
require_section("cargar-datos")

import streamlit as st
import estudiantes as est
import database as db

st.subheader("Gestión de Estudiantes")

archivo = st.file_uploader(
    "Sube CSV/Excel (codigo, nombres, proyecto, multas, documento/cedula)",
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
