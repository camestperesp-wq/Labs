from datetime import datetime, timedelta
import streamlit as st
from constants import DIAS, LABORATORIOS, INICIO_PERIODO_ACADEMICO, FIN_CLASES_PERIODO_ACADEMICO


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
