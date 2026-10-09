from auth import require_section
require_section("reservas")

from datetime import datetime, timedelta
import streamlit as st
import calendario as cal
import reportes as rep
from constants import DIAS, PERIODO_ACADEMICO
from app_state import *
from app_shell import preparar_lector
inicializar_estado()
preparar_lector()

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
panel_reportes = st.expander("Reportes y descarga de reservas", on_change="rerun")
if panel_reportes.open:
    with panel_reportes:
        tipo_reporte = st.segmented_control(
            "Contenido del reporte", ["Reservas registradas", "Asistencia docente", "Ocupación de salones"],
            default="Reservas registradas", key="tipo_reporte_reservas",
        )
        if tipo_reporte == "Ocupación de salones":
            rep.mostrar_reporte_ocupacion()
        elif tipo_reporte == "Asistencia docente":
            rep.mostrar_reporte_asistencia_docentes()
        else:
            rep.mostrar_reporte_completo()
