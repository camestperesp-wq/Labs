import auth
"""Alertas derivadas de reservas pendientes; nunca crean multas al consultar."""
from datetime import datetime

import streamlit as st
import database as db
import reservas
from constants import OPCIONES_TECNICOS


def obtener_alertas():
    ahora = datetime.now()
    return db.fetch_df(
        """SELECT id, nombres, codigo, fecha, hora, laboratorio, banco, proyecto
           FROM reservas
           WHERE activo=1 AND coalesce(asiste, '')=''
             AND codigo!='PROFESOR'
             AND (fecha < ? OR (fecha=? AND substr(hora,1,5) <= ?))
           ORDER BY fecha, hora, nombres""",
        (ahora.date().isoformat(), ahora.date().isoformat(), ahora.strftime('%H:%M')),
    )


@st.fragment(run_every="60s")
def mostrar_alertas_inasistencias():
    auth.require_section("alertas")
    alertas = obtener_alertas()
    with st.expander(f"Alertas para técnicos · {len(alertas)} pendientes",
                     expanded=st.session_state.get("revision_inasistencia_id") is not None):
        st.caption("Una reserva iniciada sin asistencia registrada requiere revisión. Esta alerta no implica una multa.")
        seleccion = st.session_state.get("revision_inasistencia_id")
        if seleccion is not None:
            filas = alertas[alertas.id == seleccion]
            if filas.empty:
                st.session_state.pop("revision_inasistencia_id", None)
                st.info("La reserva ya fue revisada.")
            else:
                fila = filas.iloc[0]
                st.subheader("Revisión de Inasistencia")
                st.write(f"**{fila.nombres}** · {fila.codigo}")
                st.write(f"{fila.fecha} · {fila.hora} · Salón {fila.laboratorio} · Cupo {fila.banco}")
                with st.form(f"revision_inasistencia_{seleccion}"):
                    tecnico = st.selectbox("Técnico responsable", OPCIONES_TECNICOS)
                    observaciones = st.text_area("Observaciones")
                    sancion = st.text_input("Sanción")
                    asistio = st.form_submit_button("Asistió")
                    no_asistio = st.form_submit_button("No asistió y aplicar multa manualmente")
                if asistio or no_asistio:
                    try:
                        reservas.revisar_inasistencia(seleccion, "Si" if asistio else "No", tecnico, observaciones, sancion)
                        st.session_state.pop("revision_inasistencia_id", None)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
                if st.button("Volver a las alertas"):
                    st.session_state.pop("revision_inasistencia_id", None)
                    st.rerun()
                return
        termino = st.text_input("Buscar alertas por nombre", key="buscar_alertas")
        if termino:
            alertas = alertas[alertas.nombres.str.contains(termino, case=False, regex=False, na=False)]
        if alertas.empty:
            st.info("No hay alertas pendientes.")
        for fila in alertas.itertuples():
            if st.button(f"{fila.nombres} · {fila.fecha} {fila.hora} · Salón {fila.laboratorio}", key=f"alerta_inasistencia_{fila.id}", width="stretch"):
                st.session_state.revision_inasistencia_id = int(fila.id)
                st.rerun()
