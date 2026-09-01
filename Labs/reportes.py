# reportes.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from constants import LABORATORIOS, HORAS
import reservas as res
from ui_components import render_editor_asistencias
from exportaciones import crear_excel_institucional as _crear_excel_institucional


def _render_editor_paginado(df, key, laboratorio=None, tamano=5):
    pagina_key = f"pagina_{key}"
    total = len(df)
    total_paginas = max(1, (total + tamano - 1) // tamano)
    pagina = min(max(1, int(st.session_state.get(pagina_key, 1))), total_paginas)
    st.session_state[pagina_key] = pagina
    inicio = (pagina - 1) * tamano
    render_editor_asistencias(df.iloc[inicio:inicio + tamano].copy(), f"{key}_p{pagina}", laboratorio)

    anterior, info, siguiente = st.columns([1, 2, 1])
    with anterior:
        if st.button("Anterior", key=f"anterior_{key}", disabled=pagina == 1, use_container_width=True):
            st.session_state[pagina_key] = pagina - 1
            st.rerun()
    info.markdown(
        f"<div style='text-align:center;padding:.55rem;color:#5f6368'>Registros {inicio + 1}–{min(inicio + tamano, total)} de {total}</div>",
        unsafe_allow_html=True,
    )
    with siguiente:
        if st.button("Siguiente", key=f"siguiente_{key}", disabled=pagina == total_paginas, use_container_width=True):
            st.session_state[pagina_key] = pagina + 1
            st.rerun()


def mostrar_consulta_fecha_lab():
    st.subheader("Consultar por día, laboratorio y hora")
    fecha = st.date_input("Día", datetime.now().date(), key="labs_fecha_consulta")
    lab_cons = st.selectbox("Laboratorio", list(LABORATORIOS.keys()), key="labs_lab_consulta")
    hora_cons = st.selectbox("Hora", ["Todas"] + HORAS, key="labs_hora_consulta")

    if st.button("Buscar", key="labs_buscar_fecha_lab"):
        st.session_state.pagina_labs_fecha_lab = 1
        st.session_state.labs_params = {
            "fecha": fecha,
            "lab": lab_cons,
            "hora": hora_cons
        }
        st.rerun()

    if "labs_params" in st.session_state:
        params = st.session_state.labs_params
        fecha_str = params["fecha"].strftime("%Y-%m-%d")
        
        if params["hora"] == "Todas":
            df = res.get_reservas_fecha_lab(fecha_str, params["lab"])
        else:
            df = res.get_reservas_fecha_lab_hora(fecha_str, params["lab"], params["hora"])
            if 'hora' in df.columns:
                df = df.drop(columns=['hora'])

        if df.empty:
            st.info(f"No hay reservas para el {params['fecha'].strftime('%d/%m/%Y')} en {params['lab']}" + 
                    (f" a las {params['hora']}" if params['hora'] != "Todas" else ""))
        else:
            st.success(f"Reservas: {len(df)} encontradas")
            _render_editor_paginado(df, "labs_fecha_lab", params["lab"])

def mostrar_busqueda_codigo():
    st.subheader("Buscar por código")
    termino = st.text_input("Código", key="labs_termino_persona")

    if st.button("Buscar", key="labs_buscar_codigo"):
        if termino and len(termino) >= 3:
            st.session_state.labs_codigo_busqueda = termino
            st.session_state.pagina_labs_persona = 1
            st.rerun()
        else:
            st.warning("Ingresa al menos 3 caracteres")

    if "labs_codigo_busqueda" in st.session_state:
        termino = st.session_state.labs_codigo_busqueda
        df_persona = res.buscar_reservas_persona(termino)
        
        if df_persona.empty:
            st.info("Sin reservas.")
        else:
            st.success(f"{len(df_persona)} reservas encontradas")
            _render_editor_paginado(df_persona, "labs_persona")

def mostrar_reporte_completo():
    st.subheader("Reporte completo de reservas")
    st.caption("Incluye reservas de estudiantes (bancos individuales) y docentes (sala completa).")
    
    c1, c2 = st.columns(2)
    with c1:
        fecha_desde = st.date_input("Desde", datetime.now().date() - timedelta(days=30), key="labs_reporte_desde")
    with c2:
        fecha_hasta = st.date_input("Hasta", datetime.now().date(), key="labs_reporte_hasta")
    
    # Filtro adicional para tipo de reserva
    tipo_reserva = st.selectbox(
        "Tipo de reserva",
        ["Todas", "Estudiantes (bancos individuales)", "Docentes (sala completa)"],
        key="labs_reporte_tipo"
    )
    
    if st.button("Generar reporte", key="labs_generar_reporte"):
        if fecha_desde > fecha_hasta:
            st.error("Fecha 'Desde' > 'Hasta'")
        else:
            df = res.get_reporte_completo(fecha_desde.strftime("%Y-%m-%d"), fecha_hasta.strftime("%Y-%m-%d"))
            
            if df.empty:
                st.info("Sin reservas en el rango.")
                return
            
            # Aplicar filtro por tipo de reserva
            if tipo_reserva == "Estudiantes (bancos individuales)":
                df = df[df['banco'] > 0]
            elif tipo_reserva == "Docentes (sala completa)":
                df = df[df['banco'] == 0]
            # "Todas" no aplica filtro
            
            if df.empty:
                st.info("No hay reservas de este tipo en el rango seleccionado.")
                return
            
            # Mostrar el reporte
            st.dataframe(df, use_container_width=True, hide_index=True)
            etiquetas = {
                "fecha": "Fecha", "hora": "Hora", "laboratorio": "Laboratorio",
                "banco": "Banco", "codigo": "Código", "nombres": "Persona",
                "proyecto": "Programa / Asignatura", "observaciones": "Observaciones",
                "tecnico": "Técnico", "estado": "Estado",
            }
            df_exportar = df.rename(columns=etiquetas)
            excel = _crear_excel_institucional(
                df_exportar,
                "Reporte ejecutivo de reservas",
                "Control de ocupación y asistencia de laboratorios",
                [
                    ("Periodo", f"{fecha_desde.strftime('%d/%m/%Y')} al {fecha_hasta.strftime('%d/%m/%Y')}"),
                    ("Tipo de reserva", tipo_reserva),
                    ("Total de registros", len(df_exportar)),
                ],
            )
            st.download_button(
                "Descargar Excel institucional",
                excel,
                f"reporte_reservas_{fecha_desde.strftime('%Y%m%d')}_{fecha_hasta.strftime('%Y%m%d')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="labs_descargar_reporte",
            )
            
            # Mostrar resumen estadístico
            st.subheader(" Resumen del reporte")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total de reservas", len(df))
            with col2:
                asistencias = len(df[df['estado'] == 'Asistio'])
                st.metric("Asistieron", asistencias)
            with col3:
                no_asistencias = len(df[df['estado'] == 'No asistio'])
                st.metric("No asistieron", no_asistencias)

def mostrar_reporte_asistencia_docentes():
    """
    Reporte específico para asistencia de docentes.
    Filtra reservas con banco = 0 (sala completa) y codigo = 'PROFESOR'.
    """
    st.subheader(" Reporte de asistencia de docentes")
    st.caption("Muestra solo las reservas de sala completa (docentes).")
    
    c1, c2 = st.columns(2)
    with c1:
        fecha_desde = st.date_input(
            "Desde",
            datetime.now().date() - timedelta(days=30),
            key="doc_reporte_desde"
        )
    with c2:
        fecha_hasta = st.date_input(
            "Hasta",
            datetime.now().date(),
            key="doc_reporte_hasta"
        )
    
    # Filtro por laboratorio
    lab_filter = st.selectbox(
        "Laboratorio",
        ["Todos"] + list(LABORATORIOS.keys()),
        format_func=lambda x: "Todos" if x == "Todos" else LABORATORIOS.get(x, x),
        key="doc_reporte_lab"
    )
    
    if st.button("Generar reporte docentes", key="doc_generar_reporte"):
        if fecha_desde > fecha_hasta:
            st.error("Fecha 'Desde' > 'Hasta'")
            return
        
        # Obtener solo registros de docentes (banco = 0, codigo = 'PROFESOR')
        df = res.get_reporte_docentes(
            fecha_desde.strftime("%Y-%m-%d"),
            fecha_hasta.strftime("%Y-%m-%d")
        )
        
        if df.empty:
            st.info("No hay registros de asistencia de docentes en el rango seleccionado.")
            return
        
        # Aplicar filtro de laboratorio
        if lab_filter != "Todos":
            df = df[df['laboratorio'] == lab_filter]
        
        if df.empty:
            st.info(f"No hay registros para el laboratorio seleccionado en este rango.")
            return
        
        # Mostrar el reporte
        st.dataframe(
            df[['fecha', 'hora', 'laboratorio', 'nombres', 'proyecto', 'asiste', 'tecnico', 'observaciones']],
            column_config={
                "fecha": "Fecha",
                "hora": "Hora",
                "laboratorio": "Laboratorio",
                "nombres": "Docente",
                "proyecto": "Asignatura/Motivo",
                "asiste": "Estado",
                "tecnico": "Técnico",
                "observaciones": "Observaciones"
            },
            use_container_width=True,
            hide_index=True
        )
        
        columnas_reporte = {
            "fecha": "Fecha", "hora": "Hora", "laboratorio": "Laboratorio",
            "nombres": "Docente", "proyecto": "Asignatura / Motivo",
            "asiste": "Estado", "tecnico": "Técnico", "observaciones": "Observaciones",
        }
        df_exportar = df[list(columnas_reporte)].rename(columns=columnas_reporte)
        df_exportar["Estado"] = df_exportar["Estado"].map(
            {"Si": "Asistió", "No": "No asistió"}
        ).fillna("Pendiente")
        laboratorio_reporte = "Todos los laboratorios" if lab_filter == "Todos" else LABORATORIOS.get(lab_filter, lab_filter)
        excel_docentes = _crear_excel_institucional(
            df_exportar,
            "Reporte de asistencia docente",
            "Seguimiento institucional de clases en laboratorios",
            [
                ("Periodo", f"{fecha_desde.strftime('%d/%m/%Y')} al {fecha_hasta.strftime('%d/%m/%Y')}"),
                ("Laboratorio", laboratorio_reporte),
                ("Total de clases", len(df_exportar)),
                ("Asistieron", int((df["asiste"] == "Si").sum())),
                ("No asistieron", int((df["asiste"] == "No").sum())),
            ],
        )
        st.download_button(
            "Descargar Excel institucional",
            excel_docentes,
            f"reporte_docentes_{fecha_desde.strftime('%Y%m%d')}_{fecha_hasta.strftime('%Y%m%d')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="doc_descargar_reporte",
        )
        
        # Resumen
        st.subheader(" Resumen de asistencias de docentes")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total de clases registradas", len(df))
        with col2:
            asistencias = len(df[df['asiste'] == 'Si'])
            st.metric("Asistieron", asistencias)
        with col3:
            no_asistencias = len(df[df['asiste'] == 'No'])
            st.metric("No asistieron", no_asistencias)
