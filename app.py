#app.py
import streamlit as st
from datetime import datetime, timedelta
import database as db
import utils
import estudiantes as est
import calendario as cal
import reportes as rep
from ui_components import mostrar_horario_general
from constants import LABORATORIOS, DIAS
from ui_components import mostrar_horario_general, mostrar_deudores

st.set_page_config(page_title="LABS", layout="wide")
if "editor_version" not in st.session_state:
    st.session_state.editor_version = 0

if "eliminar_version" not in st.session_state:
    st.session_state.eliminar_version = 0

if "confirmar_inasistencia" not in st.session_state:
    st.session_state.confirmar_inasistencia = False
    st.session_state.inasistencias_pendientes = []
    st.session_state.cambios_pendientes = []

if "horario_editar" not in st.session_state:
    st.session_state.horario_editar = None

if "labs_semana_inicio" not in st.session_state:
    st.session_state.labs_semana_inicio = datetime.now().date() - timedelta(days=datetime.now().weekday())

if "lab_actual" not in st.session_state:
    st.session_state.lab_actual = list(LABORATORIOS.keys())[0]
    
# ===== SOLO ESTILOS DE PESTAÑAS (SIN ESTILOS DE BOTONES) =====
st.markdown("""
    <style>
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
            font-size: 1.2rem;
            font-weight: 500;
        }
        .stTabs [data-baseweb="tab-list"] button {
            padding: 0.5rem 1.2rem;
        }
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
            background-color: #f0f2f6;
            border-radius: 4px 4px 0 0;
        }
               /* Normalizar texto en botones del calendario */
        .stButton button {
            text-transform: none !important;
            font-weight: normal !important;
        }
    </style>
""", unsafe_allow_html=True)

st.title("Adicionales")

db.init_db()
res = utils.actualizar_reservas_vencidas()
if res:
    st.toast(f"{res} reservas vencidas marcadas como 'No asistio'")

if "labs_semana_inicio" not in st.session_state:
    st.session_state.labs_semana_inicio = datetime.now().date() - timedelta(days=datetime.now().weekday())

if "lab_actual" not in st.session_state:
    st.session_state.lab_actual = list(LABORATORIOS.keys())[0]

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📅 Horario General",
    "📝 Reserva",
    "💰 Deudores",
    "🔍 Buscar por Lab",
    "🔍 Buscar por Código",
    "📊 Reportes",
    "👥 Cargar datos"
])

with tab1:
    mostrar_horario_general()

with tab2:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("◀ Semana anterior", key="reserva_semana_prev"):
            st.session_state.labs_semana_inicio -= timedelta(days=7)
            st.rerun()
    with col2:
        lunes = st.session_state.labs_semana_inicio
        st.markdown(
            f"<h3 style='text-align: center;'>Semana del {lunes.strftime('%d/%m/%Y')} al {(lunes + timedelta(days=6)).strftime('%d/%m/%Y')}</h3>",
            unsafe_allow_html=True
        )
    with col3:
        if st.button("Siguiente semana ▶", key="reserva_semana_next"):
            st.session_state.labs_semana_inicio += timedelta(days=7)
            st.rerun()
    
    # Calcular fechas de la semana actual
    lunes = st.session_state.labs_semana_inicio
    fechas_semana = [lunes + timedelta(days=i) for i in range(6)]
    
    # Crear opciones con el formato "Lunes 12/08"
    opciones_dias = []
    for i, fecha in enumerate(fechas_semana):
        nombre_dia = DIAS[i]
        fecha_str = fecha.strftime("%d/%m")
        opciones_dias.append(f"{nombre_dia} {fecha_str}")
    
    dia_seleccionado = st.radio(
        "Selecciona el día",
        options=opciones_dias,
        horizontal=True,
        key="reserva_dia_selector"
    )
    
    # Extraer el día real del texto seleccionado
    dia_actual = dia_seleccionado.split(" ")[0]
    
    cal.mostrar_calendario_interactivo(dia_actual)
    cal.mostrar_detalle_celda()
    cal.mostrar_formulario_reserva_profesor()
    cal.mostrar_formulario_asistencia_docente()
with tab3:
    mostrar_deudores()

with tab4:
    rep.mostrar_consulta_fecha_lab()
with tab5:
    rep.mostrar_busqueda_codigo()

with tab6:
    rep.mostrar_reporte_completo()

with tab7:
    st.subheader("Gestión de Estudiantes")
    
    archivo = st.file_uploader(
        "Sube CSV/Excel (codigo, nombres, proyecto, multas)",
        type=['csv', 'xlsx', 'xls'],
        key="labs_archivo_estudiantes"
    )
    
    if archivo and st.button("Cargar", key="labs_cargar_estudiantes"):
        try:
            count = est.cargar_estudiantes(archivo)
            st.success(f"✅ {count} estudiantes procesados")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    total = db.fetch_df("SELECT COUNT(*) FROM estudiantes").iloc[0, 0]
    st.write(f"**Estudiantes actuales:** {total}")