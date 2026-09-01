# ui_components

import streamlit as st
import pandas as pd
from datetime import datetime
import html as html_lib
import json
import io
import unicodedata
import database as db
import reservas as res
import horario_fijo as hf
import multas
from exportaciones import crear_excel_institucional
from constants import DIAS, HORAS, LABS_NAMES_HORARIO, LABS_HORARIO, OPCIONES_TECNICOS, es_tecnico_valido, LABS_ORDEN_HORARIO, LABORATORIOS


def _normalizar_encabezado(valor):
    texto = unicodedata.normalize("NFKD", str(valor).strip())
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def _leer_verificacion_excel(archivo):
    """Lee solo las dos columnas requeridas y devuelve códigos comparables."""
    df = pd.read_excel(io.BytesIO(archivo.getvalue()), dtype=str)
    columnas = {_normalizar_encabezado(c): c for c in df.columns}
    if "codigo" not in columnas or "nombre" not in columnas:
        raise ValueError("El Excel debe contener las columnas Codigo y Nombre.")
    resultado = df[[columnas["codigo"], columnas["nombre"]]].copy()
    resultado.columns = ["Codigo", "Nombre"]
    resultado["Codigo"] = resultado["Codigo"].fillna("").str.strip().str.replace(r"\.0$", "", regex=True)
    resultado["Nombre"] = resultado["Nombre"].fillna("").str.strip()
    return resultado[resultado["Codigo"] != ""].drop_duplicates("Codigo", keep="first")

# ============================================================
#  INICIALIZACIÓN DE ESTADO
# ============================================================

# Inicializar editor_version
if "editor_version" not in st.session_state:
    st.session_state.editor_version = 0

if "eliminar_version" not in st.session_state:
    st.session_state.eliminar_version = 0

if "confirmar_inasistencia" not in st.session_state:
    st.session_state.confirmar_inasistencia = False
    st.session_state.inasistencias_pendientes = []
    st.session_state.cambios_pendientes = []
# ============================================================
#  1. EDITOR DE ASISTENCIAS
# ============================================================
def render_editor_asistencias(df, key, laboratorio=None):
    """
    Muestra un editor de asistencias con opcion para cambiar banco y estudiante.
    """
    if "editor_version" not in st.session_state:
        st.session_state.editor_version = 0
    if "confirmar_inasistencia" not in st.session_state:
        st.session_state.confirmar_inasistencia = False
        st.session_state.inasistencias_pendientes = []
        st.session_state.cambios_pendientes = []
    
    if df is None or df.empty:
        return

    # ===== INICIALIZACIÓN SEGURA =====
    if "editor_version" not in st.session_state:
        st.session_state.editor_version = 0

    # ===== OBTENER CAPACIDAD DEL LABORATORIO =====
    from constants import LABORATORIOS
    
    if laboratorio and laboratorio in LABORATORIOS:
        capacidad_maxima = LABORATORIOS[laboratorio]
        st.caption(f" Capacidad del laboratorio: **{capacidad_maxima}** bancos (1-{capacidad_maxima})")
    else:
        capacidad_maxima = 99
        st.caption("Si ingresas un número fuera de rango, el sistema mostrará un error al guardar.")

    seleccionar_todos_key = f"seleccionar_todos_{key}"

    def reiniciar_editor_asistencia():
        st.session_state.editor_version += 1

    seleccionar_todos = st.checkbox(
        "Seleccionar todos",
        key=seleccionar_todos_key,
        on_change=reiniciar_editor_asistencia,
    )
    df = df.copy()
    df.insert(0, "seleccionar", seleccionar_todos)

    # ===== CONFIGURACIÓN DEL DATA_EDITOR =====
    config = {
        "seleccionar": st.column_config.CheckboxColumn("Seleccionar", width="small"),
        "id": st.column_config.TextColumn("ID", width="small", disabled=True),
        "banco": st.column_config.NumberColumn(
            "Banco", 
            width="small",
            min_value=1,
            max_value=capacidad_maxima,
            step=1
        ),
        "codigo": st.column_config.TextColumn("Codigo", width="medium"),
        "nombres": st.column_config.TextColumn("Nombres", disabled=True),
        "proyecto": st.column_config.TextColumn("Proyecto", disabled=True),
        "asiste": st.column_config.TextColumn("Asistencia", disabled=True, width="small"),
    }
    
    column_order = ['seleccionar', 'id', 'banco', 'codigo', 'nombres', 'proyecto', 'asiste']

    version = st.session_state.editor_version
    editor_key = f"editor_{key}_{version}"

    edited = st.data_editor(
        df,
        column_config=config,
        column_order=column_order,
        use_container_width=True,
        hide_index=True,
        key=editor_key
    )

    col_asistio, col_no_asistio, col_eliminar_masivo = st.columns(3)
    with col_asistio:
        marcar_asistio = st.button(
            "Asistió",
            key=f"marcar_asistio_{key}_{version}",
            use_container_width=True,
        )
    with col_no_asistio:
        marcar_no_asistio = st.button(
            "No asistió",
            key=f"marcar_no_asistio_{key}_{version}",
            use_container_width=True,
        )
    with col_eliminar_masivo:
        solicitar_eliminacion = st.button(
            "Eliminar seleccionadas",
            key=f"eliminar_seleccionadas_{key}_{version}",
            use_container_width=True,
        )

    aplicar_masivo = marcar_asistio or marcar_no_asistio
    estado_masivo = "Si" if marcar_asistio else "No"
    if aplicar_masivo:
        seleccionados = edited["seleccionar"].fillna(False).astype(bool)
        if not seleccionados.any():
            st.warning("Selecciona al menos una reserva.")
            aplicar_masivo = False
        else:
            edited.loc[seleccionados, "asiste"] = estado_masivo

    eliminar_confirm_key = f"confirmar_eliminar_seleccionadas_{key}"
    if solicitar_eliminacion:
        filas_seleccionadas = edited["seleccionar"].fillna(False).astype(bool)
        ids_seleccionados = [int(valor) for valor in edited.loc[filas_seleccionadas, "id"].tolist()]
        if not ids_seleccionados:
            st.warning("Selecciona al menos una reserva para eliminar.")
        else:
            st.session_state[eliminar_confirm_key] = ids_seleccionados

    ids_a_eliminar = st.session_state.get(eliminar_confirm_key, [])
    if ids_a_eliminar:
        nombres_a_eliminar = df[df["id"].isin(ids_a_eliminar)]["nombres"].fillna("Sin nombre").tolist()
        with st.container(border=True):
            st.warning(
                f"Vas a eliminar {len(ids_a_eliminar)} reserva(s): "
                + ", ".join(str(nombre) for nombre in nombres_a_eliminar)
            )
            confirmar_col, cancelar_col = st.columns(2)
            with confirmar_col:
                if st.button("Confirmar eliminacion", key=f"confirmar_eliminacion_masiva_{key}", type="primary", use_container_width=True):
                    for id_reserva in ids_a_eliminar:
                        res.eliminar_reserva(id_reserva)
                    st.session_state.pop(eliminar_confirm_key, None)
                    st.session_state.pop(seleccionar_todos_key, None)
                    st.session_state.editor_version += 1
                    st.success(f"Se eliminaron {len(ids_a_eliminar)} reserva(s).")
                    st.rerun()
            with cancelar_col:
                if st.button("Cancelar", key=f"cancelar_eliminacion_masiva_{key}", use_container_width=True):
                    st.session_state.pop(eliminar_confirm_key, None)
                    st.rerun()

    # ===== Botón Guardar cambios =====
    df_por_id_auto = df.set_index("id")
    cambios_reserva_auto = []
    errores_auto = []

    for _, row in edited.iterrows():
        id_res = int(row["id"])
        nuevo_banco = row["banco"]
        nuevo_codigo = "" if pd.isna(row["codigo"]) else str(row["codigo"]).strip()
        anterior_banco = int(df_por_id_auto.loc[id_res, "banco"])
        anterior_codigo = str(df_por_id_auto.loc[id_res, "codigo"]).strip()

        if nuevo_banco == 0:
            if anterior_codigo != "PROFESOR":
                nombre = df_por_id_auto.loc[id_res, "nombres"]
                errores_auto.append(f" **{nombre}**: Banco **0** solo se usa para reservas docentes")
            continue

        if pd.isna(nuevo_banco) or int(nuevo_banco) < 1 or int(nuevo_banco) > capacidad_maxima:
            nombre = df_por_id_auto.loc[id_res, "nombres"]
            errores_auto.append(f" **{nombre}**: Banco **{nuevo_banco}** fuera de rango (1-{capacidad_maxima})")
            continue

        if nuevo_codigo != anterior_codigo or int(nuevo_banco) != anterior_banco:
            cambios_reserva_auto.append({
                "id": id_res,
                "banco": int(nuevo_banco),
                "codigo": nuevo_codigo,
            })

    if errores_auto:
        for error in errores_auto:
            st.error(error)
        return

    if cambios_reserva_auto:
        ok_reserva, errores_reserva = res.actualizar_reservas_desde_editor(cambios_reserva_auto)
        if not ok_reserva:
            for error in errores_reserva:
                st.error(error)
            return

        cambios_banco_auto = sum(
            1 for cambio in cambios_reserva_auto
            if int(df_por_id_auto.loc[cambio["id"], "banco"]) != cambio["banco"]
        )
        cambios_codigo_auto = sum(
            1 for cambio in cambios_reserva_auto
            if str(df_por_id_auto.loc[cambio["id"], "codigo"]).strip() != cambio["codigo"]
        )
        mensajes_auto = []
        if cambios_banco_auto:
            mensajes_auto.append(f"{cambios_banco_auto} cambios de banco")
        if cambios_codigo_auto:
            mensajes_auto.append(f"{cambios_codigo_auto} cambios de estudiante")
        st.success(f"{' y '.join(mensajes_auto)} guardados automaticamente")

    guardar_cambios = st.button("Guardar cambios", key=f"save_{key}_{version}")
    if guardar_cambios or (aplicar_masivo and edited["seleccionar"].fillna(False).any()):
        # ===== VALIDACIÓN COMPLETA =====
        errores = []
        cambios = []
        cambios_banco = []
        cambios_reserva = []
        df_por_id = df.set_index("id")
        
        # Primero, validar TODOS los bancos
        for _, row in edited.iterrows():
            id_res = int(row['id'])
            nuevo_banco = row['banco']
            anterior_codigo = str(df_por_id.loc[id_res, 'codigo']).strip()
            
            # ===== EXCLUIR BANCO 0 DE LA VALIDACIÓN =====
            if nuevo_banco == 0:
                if anterior_codigo != "PROFESOR":
                    nombre = df_por_id.loc[id_res, 'nombres']
                    errores.append(f" **{nombre}**: Banco **0** solo se usa para reservas docentes")
                continue
            
            # Validar rango (solo para bancos > 0)
            if pd.isna(nuevo_banco) or int(nuevo_banco) < 1 or int(nuevo_banco) > capacidad_maxima:
                nombre = df_por_id.loc[id_res, 'nombres']
                errores.append(f" **{nombre}**: Banco **{nuevo_banco}** fuera de rango (1-{capacidad_maxima})")
        # Si hay errores, mostrar y DETENER
        if errores:
            st.error(" **Errores en los bancos:**")
            for error in errores:
                st.error(error)
            st.warning(f" Corrige los bancos a valores entre **1 y {capacidad_maxima}**")
            return
        
        # Si no hay errores, procesar cambios
        for _, row in edited.iterrows():
            id_res = int(row['id'])
            nuevo_banco = int(row['banco'])
            nuevo_codigo = "" if pd.isna(row['codigo']) else str(row['codigo']).strip()
            nuevo_estado = row['asiste']
            
            anterior_banco = int(df_por_id.loc[id_res, 'banco'])
            anterior_codigo = str(df_por_id.loc[id_res, 'codigo']).strip()
            anterior_estado = df_por_id.loc[id_res, 'asiste']
            
            # Verificar cambio de banco
            if nuevo_banco != anterior_banco:
                cambios_banco.append((id_res, nuevo_banco))

            # Verificar cambio de estudiante o banco
            if nuevo_codigo != anterior_codigo or nuevo_banco != anterior_banco:
                cambios_reserva.append({
                    "id": id_res,
                    "banco": nuevo_banco,
                    "codigo": nuevo_codigo,
                })
            
            # Verificar cambio de asistencia
            if nuevo_estado != anterior_estado:
                cambios.append((id_res, nuevo_estado))
        
        # ===== PROCESAR CAMBIOS DE BANCO / ESTUDIANTE =====
        if cambios_reserva:
            ok_reserva, errores_reserva = res.actualizar_reservas_desde_editor(cambios_reserva)
            if not ok_reserva:
                for error in errores_reserva:
                    st.error(error)
                return

        if errores:
            for error in errores:
                st.error(error)
            return
        
        # ===== PROCESAR CAMBIOS DE ASISTENCIA =====
        if not cambios and not cambios_reserva:
            st.info("Sin cambios")
            return

        for id_res, nuevo_estado in cambios:
            res.actualizar_asiste(id_res, nuevo_estado, None)
        st.session_state.editor_version += 1

        mensajes = []
        if cambios:
            mensajes.append(f"{len(cambios)} cambios de asistencia")
        if cambios_banco:
            mensajes.append(f"{len(cambios_banco)} cambios de banco")
        cambios_codigo = sum(
            1 for cambio in cambios_reserva
            if str(df_por_id.loc[cambio["id"], 'codigo']).strip() != cambio["codigo"]
        )
        if cambios_codigo:
            mensajes.append(f"{cambios_codigo} cambios de estudiante")
        st.success(f"{' y '.join(mensajes)} guardados")
        st.rerun()
# ============================================================
#  2. HORARIO GENERAL (SIN POPOVER)
# ============================================================
def mostrar_horario_general():
    st.markdown(
        """
        <div class="labs-section-title">
            <h2>Horario General de Laboratorios</h2>
            <p>Los colores indican la carrera. Haz clic derecho sobre una celda del horario para editarla.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    opciones_carrera = [
        "Ing. Eléctrica",
        "Ing. Electrónica",
        "Ing. De Sistema",
        "Ing. Industrial",
        "Ing. Catastral",
        "Posgrados",
        "Adicional",
        "Práctica Libre"
    ]

    colores_carrera = {
        "Ing. Eléctrica": "#FFCCCC",
        "Ing. Electrónica": "#F6D9DB",
        "Ing. De Sistema": "#E6CCFF",
        "Ing. Industrial": "#F1E7D8",
        "Ing. Catastral": "#DDF5DC",
        "Posgrados": "#FFF0B8",
        "Adicional": "#E8C766",
        "Práctica Libre": "#E7D8CC"
    }
    idx_hoy = datetime.now().date().weekday()
    dia_hoy = DIAS[idx_hoy] if idx_hoy < len(DIAS) else DIAS[0]
    if (
        "horario_dia" not in st.session_state
        or not st.session_state.get("horario_dia_manual", False)
    ):
        st.session_state.horario_dia = dia_hoy

    def marcar_horario_dia_manual():
        st.session_state.horario_dia_manual = True

    dia_seleccionado = st.radio(
        "Selecciona el día",
        DIAS,
        horizontal=True,
        key="horario_dia",
        on_change=marcar_horario_dia_manual
    )

    labs_keys = [lab for lab in LABS_ORDEN_HORARIO if lab in LABS_HORARIO]

    if "horario_editar" not in st.session_state:
        st.session_state.horario_editar = None

    params = st.query_params
    def _qp_value(name):
        value = params.get(name)
        if isinstance(value, list):
            return value[0] if value else None
        return value

    limpiar_url_horario = False
    accion_horario = _qp_value("accion_horario")

    if accion_horario in ("guardar", "liberar", "free"):
        limpiar_url_horario = True
        accion = accion_horario
        lab_param = _qp_value("lab")
        hora_param = _qp_value("hora")
        dia_param = _qp_value("dia")
        accion_token = _qp_value("_") or f"{accion}:{dia_param}:{hora_param}:{lab_param}"

        if st.session_state.get("horario_ultimo_token") != accion_token:
            st.session_state.horario_ultimo_token = accion_token

            if lab_param in labs_keys and hora_param in HORAS and dia_param in DIAS:
                if accion in ("liberar", "free"):
                    hf.delete_horario_celda(dia_param, hora_param, lab_param)
                    st.toast("Celda marcada como libre")
                else:
                    asignatura_param = (_qp_value("asignatura") or "").strip()
                    carrera_param = _qp_value("carrera") or opciones_carrera[0]
                    monitor_param = (_qp_value("monitor") or "").strip()
                    profesor_param = (_qp_value("profesor") or "").strip()

                    if asignatura_param:
                        hf.set_horario_celda(
                            dia_param,
                            hora_param,
                            lab_param,
                            asignatura_param,
                            carrera_param,
                            monitor_param,
                            profesor_param,
                        )
                        st.toast("Celda actualizada")
                    else:
                        hf.delete_horario_celda(dia_param, hora_param, lab_param)
                        st.toast("Celda marcada como libre")
            else:
                st.toast("No se pudo identificar la celda seleccionada")

    if False and _qp_value("editar_horario") == "1":
        lab_param = _qp_value("lab")
        hora_param = _qp_value("hora")
        dia_param = _qp_value("dia")

        if lab_param in labs_keys and hora_param in HORAS and dia_param in DIAS:
            celda = hf.get_horario_celda(dia_param, hora_param, lab_param)
            st.session_state.horario_editar = {
                "dia": dia_param,
                "hora": hora_param,
                "laboratorio": lab_param,
                "datos": celda,
            }
        else:
            st.toast("No se pudo identificar la celda seleccionada")

        for key in ["editar_horario", "lab", "hora", "dia", "_"]:
            if key in st.query_params:
                del st.query_params[key]
        st.rerun()

    # ===== CONSTRUIR TABLA CON ANCHO FIJO =====
    num_labs = len(labs_keys)
    # ===== ANCHO FIJO EN PÍXELES =====
    ancho_columna = "150px"
    ancho_total = (len(labs_keys) + 1) * 150

    st.markdown(
        """
        <style>
            div[data-testid="stHtml"],
            div[data-testid="stHtml"] > div {
                overflow: visible !important;
            }
            .horario-general-header-scroll::-webkit-scrollbar,
            .horario-general-body-scroll::-webkit-scrollbar {
                height: 12px;
            }
            .horario-general-header-scroll::-webkit-scrollbar-track,
            .horario-general-body-scroll::-webkit-scrollbar-track {
                background: #f3eadf;
                border-radius: 999px;
            }
            .horario-general-header-scroll::-webkit-scrollbar-thumb,
            .horario-general-body-scroll::-webkit-scrollbar-thumb {
                background: #9f1d24;
                border: 3px solid #f3eadf;
                border-radius: 999px;
            }
            .horario-editable-cell {
                cursor: context-menu;
                transition: transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease;
            }
            .horario-editable-cell:hover {
                border-color: #8f1720 !important;
                box-shadow: inset 0 0 0 2px rgba(143,23,32,0.22);
                transform: translateY(-1px);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    html = f"""
    <div id="horario-general-anchor" style="position: relative; top: -96px;"></div>
    <div style="border: 1px solid #d8dee8; border-radius: 8px; width: 100%; overflow: visible; background: #ffffff; box-shadow: 0 12px 30px rgba(23,32,42,0.08);">
    <div class="horario-general-header-scroll" style="position: sticky; top: 3.75rem; z-index: 1000; width: 100%; overflow-x: auto; overflow-y: hidden; background: #ffffff; border-bottom: 3px solid #c8a21a;">
    <table style="width:max-content; min-width:{ancho_total}px; border-collapse: collapse; font-family: Segoe UI, Arial, sans-serif; font-size: 0.8rem; table-layout: fixed;">
    <tr>
        <th style="position: sticky; left: 0; z-index: 30; background: #5f0d14; color: #ffffff; border:1px solid #5f0d14; padding:10px 8px; text-align:center; font-weight:800; width:{ancho_columna}; min-width:{ancho_columna}; box-shadow: 2px 2px 0 #c8a21a;">Hora</th>
    """

    for lab in labs_keys:
        html += f"""
        <th style="background: #5f0d14; color: #ffffff; z-index: 20; border:1px solid #5f0d14; border-bottom: 4px solid #c8a21a; padding:10px 8px; text-align:center; font-weight:800; width:{ancho_columna}; min-width:{ancho_columna}; word-wrap:break-word; font-size:0.76rem; box-shadow: 0 2px 0 #c8a21a;">{LABS_NAMES_HORARIO[lab]}</th>
        """

    html += f"""
    </tr>
    </table>
    </div>
    <div class="horario-general-body-scroll" style="width: 100%; overflow-x: auto; overflow-y: visible;">
    <table style="width:max-content; min-width:{ancho_total}px; border-collapse: collapse; font-family: Segoe UI, Arial, sans-serif; font-size: 0.8rem; table-layout: fixed;">
    <tbody>
    """

    for hora in HORAS:
        html += f"<tr><td style='position: sticky; left: 0; z-index: 10; border:1px solid #d8dee8; padding:8px; font-weight:800; text-align:center; color:#5f0d14; background-color:#f7f9fc; width:{ancho_columna}; min-width:{ancho_columna}; box-shadow: 2px 0 0 #c8a21a;'>{hora}</td>"
        for lab in labs_keys:
            celda = hf.get_horario_celda(dia_seleccionado, hora, lab)
            data = celda or {}
            data_attrs = (
                f'data-dia="{html_lib.escape(dia_seleccionado, quote=True)}" '
                f'data-hora="{html_lib.escape(hora, quote=True)}" '
                f'data-lab="{html_lib.escape(lab, quote=True)}" '
                f'data-lab-nombre="{html_lib.escape(LABS_NAMES_HORARIO[lab], quote=True)}" '
                f'data-asignatura="{html_lib.escape(data.get("asignatura", "") or "", quote=True)}" '
                f'data-carrera="{html_lib.escape(data.get("carrera", "") or "", quote=True)}" '
                f'data-monitor="{html_lib.escape(data.get("monitor", "") or "", quote=True)}" '
                f'data-profesor="{html_lib.escape(data.get("profesor", "") or "", quote=True)}"'
            )
            
            if celda and celda["asignatura"]:
                carrera = celda.get("carrera", "")
                color_fondo = colores_carrera.get(carrera, "#F0F0F0")
                
                texto = f"""
                    <strong>{celda['asignatura']}</strong><br>
                    {carrera}<br>
                    <span style='font-size:0.7rem; color:#3f4650;'>
                        Monitor: {celda['monitor']}<br>
                        Prof: {celda['profesor']}
                    </span>
                """
                
                html += f"""
                <td class='horario-editable-cell' {data_attrs} style='
                    border:1px solid #d8dee8; 
                    padding:8px; 
                    background-color:{color_fondo};
                    text-align:center;
                    vertical-align:middle;
                    width:{ancho_columna};
                    min-width:{ancho_columna};
                    word-wrap:break-word;
                    font-size:0.75rem;
                    line-height:1.38;
                    color:#17202a;
                '>
                    {texto}
                </td>
                """
            else:
                html += f"""
                <td class='horario-editable-cell' {data_attrs} style='
                    border:1px solid #d8dee8; 
                    padding:8px; 
                    background-color:#f8fafc;
                    text-align:center;
                    vertical-align:middle;
                    width:{ancho_columna};
                    min-width:{ancho_columna};
                    word-wrap:break-word;
                    color:#667085;
                    font-size:0.75rem;
                    line-height:1.45;
                '>
                     Libre
                </td>
                """
        html += "</tr>"
    
    html += "</tbody></table></div></div>"
    
    st.html(html)

    if limpiar_url_horario:
        st.components.v1.html(
            """
            <script>
            (function () {
                const url = new URL(window.parent.location.href);
                ["accion_horario", "lab", "hora", "dia", "asignatura", "carrera", "monitor", "profesor", "_"].forEach(function (key) {
                    url.searchParams.delete(key);
                });
                window.parent.history.replaceState({}, "", url.toString());
            })();
            </script>
            """,
            height=0,
            scrolling=False,
        )

    opciones_carrera_js = json.dumps(opciones_carrera, ensure_ascii=False)

    st.components.v1.html(
        """
        <script>
        (function () {
            function setup() {
                const doc = window.parent.document;
                const headers = doc.querySelectorAll(".horario-general-header-scroll");
                const bodies = doc.querySelectorAll(".horario-general-body-scroll");
                const header = headers[headers.length - 1];
                const body = bodies[bodies.length - 1];
                const horarioUiVersion = "20260825-scroll-restore-v14";
                const carreraOptions = __OPCIONES_CARRERA__;

                if (!header || !body) {
                    window.setTimeout(setup, 100);
                    return;
                }

                const previousTransition = doc.getElementById("horario-transition-state");
                if (previousTransition) {
                    previousTransition.style.display = "none";
                }

                function getParentScrollY() {
                    const scrollingElement = doc.scrollingElement || doc.documentElement || doc.body;
                    return window.parent.scrollY || window.parent.pageYOffset || scrollingElement.scrollTop || doc.body.scrollTop || 0;
                }

                function saveHorarioPosition() {
                    window.parent.sessionStorage.setItem("horario-window-y", String(getParentScrollY()));
                    window.parent.sessionStorage.setItem("horario-body-x", String(body.scrollLeft || header.scrollLeft || 0));
                    window.parent.sessionStorage.setItem("horario-restore-anchor", "horario-general-anchor");
                    try {
                        window.parent.history.scrollRestoration = "manual";
                    } catch (error) {}
                }

                const savedWindowY = window.parent.sessionStorage.getItem("horario-window-y");
                const savedBodyX = window.parent.sessionStorage.getItem("horario-body-x");
                if (savedWindowY !== null || savedBodyX !== null) {
                    const restorePosition = function () {
                        if (savedBodyX !== null) {
                            body.scrollLeft = Number(savedBodyX) || 0;
                            header.scrollLeft = Number(savedBodyX) || 0;
                        }
                        if (savedWindowY !== null) {
                            window.parent.scrollTo({ top: Number(savedWindowY) || 0, left: 0, behavior: "auto" });
                        }
                    };
                    [40, 120, 260, 520, 900].forEach(function (delay) {
                        window.setTimeout(restorePosition, delay);
                    });
                    window.setTimeout(function () {
                        window.parent.sessionStorage.removeItem("horario-window-y");
                        window.parent.sessionStorage.removeItem("horario-body-x");
                    }, 1200);
                }

                if (window.parent.__horarioScrollCleanup) {
                    window.parent.__horarioScrollCleanup();
                }

                let syncingScroll = false;
                function syncHorizontal(from, to) {
                    if (syncingScroll) return;
                    syncingScroll = true;
                    to.scrollLeft = from.scrollLeft;
                    window.requestAnimationFrame(function () {
                        syncingScroll = false;
                    });
                }

                function onBodyScroll() {
                    syncHorizontal(body, header);
                }

                function onHeaderScroll() {
                    syncHorizontal(header, body);
                }

                body.addEventListener("scroll", onBodyScroll, { passive: true });
                header.addEventListener("scroll", onHeaderScroll, { passive: true });
                header.scrollLeft = body.scrollLeft;

                window.parent.__horarioScrollCleanup = function () {
                    body.removeEventListener("scroll", onBodyScroll);
                    header.removeEventListener("scroll", onHeaderScroll);
                    window.parent.__horarioScrollCleanup = null;
                };

                let menu = doc.getElementById("horario-context-menu");
                if (menu && menu.dataset.version !== horarioUiVersion) {
                    menu.remove();
                    menu = null;
                }
                if (!menu) {
                    menu = doc.createElement("div");
                    menu.id = "horario-context-menu";
                    menu.dataset.version = horarioUiVersion;
                    menu.innerHTML = "<button type='button'>Editar celda</button>";
                    menu.style.position = "fixed";
                    menu.style.display = "none";
                    menu.style.zIndex = "999999";
                    menu.style.background = "#ffffff";
                    menu.style.border = "1px solid #e2d8cb";
                    menu.style.borderRadius = "8px";
                    menu.style.boxShadow = "0 12px 28px rgba(43,31,20,0.18)";
                    menu.style.padding = "0.35rem";
                    menu.style.minWidth = "150px";
                    menu.querySelector("button").style.display = "block";
                    menu.querySelector("button").style.width = "100%";
                    menu.querySelector("button").style.boxSizing = "border-box";
                    menu.querySelector("button").style.border = "0";
                    menu.querySelector("button").style.borderRadius = "6px";
                    menu.querySelector("button").style.padding = "0.6rem 0.75rem";
                    menu.querySelector("button").style.background = "#f5f6f8";
                    menu.querySelector("button").style.color = "#731116";
                    menu.querySelector("button").style.fontWeight = "800";
                    menu.querySelector("button").style.cursor = "pointer";
                    doc.body.appendChild(menu);
                }

                function hideMenu() {
                    menu.style.display = "none";
                }

                let modal = doc.getElementById("horario-edit-modal");
                if (modal && modal.dataset.version !== horarioUiVersion) {
                    modal.remove();
                    modal = null;
                }
                if (!modal) {
                    modal = doc.createElement("div");
                    modal.id = "horario-edit-modal";
                    modal.dataset.version = horarioUiVersion;
                    modal.style.position = "fixed";
                    modal.style.inset = "0";
                    modal.style.zIndex = "999998";
                    modal.style.display = "none";
                    modal.style.alignItems = "center";
                    modal.style.justifyContent = "center";
                    modal.style.background = "rgba(24,33,44,0.42)";
                    modal.style.backdropFilter = "blur(2px)";
                    modal.innerHTML = `
                        <div class="horario-edit-card" style="width:min(720px, calc(100vw - 32px)); background:#fff; border:1px solid #e2d8cb; border-radius:14px; box-shadow:0 24px 60px rgba(24,33,44,0.28); overflow:hidden; font-family:Arial,sans-serif;">
                            <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; padding:1rem 1.15rem; background:#f5f6f8; border-bottom:1px solid #e2d8cb;">
                                <div>
                                    <div style="color:#731116; font-weight:900; font-size:1.05rem;">Editar celda del horario</div>
                                    <div id="horario-modal-lab" style="display:inline-flex; margin-top:0.45rem; padding:0.35rem 0.7rem; border-radius:999px; background:#731116; color:#ffffff; font-size:1rem; font-weight:900; box-shadow:0 4px 12px rgba(115,17,22,0.18);"></div>
                                    <div id="horario-modal-meta" style="color:#6b4f00; font-size:0.82rem; margin-top:0.35rem;"></div>
                                </div>
                                <button type="button" data-action="close" style="border:0; background:#fff; color:#731116; border-radius:999px; width:34px; height:34px; font-size:1.1rem; font-weight:900; cursor:pointer;">×</button>
                            </div>
                            <div style="padding:1rem 1.15rem;">
                                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.85rem;">
                                    <label style="display:grid; gap:0.35rem; color:#731116; font-weight:800; font-size:0.86rem;">Asignatura
                                        <input id="horario-modal-asignatura" style="border:1px solid #e2d8cb; border-radius:8px; padding:0.7rem; font:inherit; outline:none; box-shadow:none; accent-color:#9f1d24;" />
                                    </label>
                                    <label style="display:grid; gap:0.35rem; color:#731116; font-weight:800; font-size:0.86rem;">Carrera
                                        <select id="horario-modal-carrera" style="border:1px solid #e2d8cb; border-radius:8px; padding:0.7rem; font:inherit; background:#fff; outline:none; box-shadow:none; accent-color:#9f1d24;"></select>
                                    </label>
                                    <label style="display:grid; gap:0.35rem; color:#731116; font-weight:800; font-size:0.86rem;">Monitor
                                        <input id="horario-modal-monitor" style="border:1px solid #e2d8cb; border-radius:8px; padding:0.7rem; font:inherit; outline:none; box-shadow:none; accent-color:#9f1d24;" />
                                    </label>
                                    <label style="display:grid; gap:0.35rem; color:#731116; font-weight:800; font-size:0.86rem;">Profesor
                                        <input id="horario-modal-profesor" style="border:1px solid #e2d8cb; border-radius:8px; padding:0.7rem; font:inherit; outline:none; box-shadow:none; accent-color:#9f1d24;" />
                                    </label>
                                </div>
                                <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:0.7rem; margin-top:1.1rem;">
                                    <a id="horario-modal-save" data-action="save" href="#" target="_parent" style="border:1px solid #9f1d24; background:#9f1d24; color:#fff; border-radius:8px; padding:0.75rem; font-weight:900; cursor:pointer; text-align:center; text-decoration:none;">Guardar</a>
                                    <a id="horario-modal-free" data-action="free" href="#" target="_parent" style="border:1px solid #f2c230; background:#fff8d9; color:#731116; border-radius:8px; padding:0.75rem; font-weight:900; cursor:pointer; text-align:center; text-decoration:none;">Dejar libre</a>
                                    <button type="button" data-action="cancel" style="border:1px solid #e2d8cb; background:#fff; color:#731116; border-radius:8px; padding:0.75rem; font-weight:900; cursor:pointer;">Cancelar</button>
                                </div>
                            </div>
                        </div>
                    `;
                    doc.body.appendChild(modal);
                }

                const carreraSelect = doc.getElementById("horario-modal-carrera");
                if (carreraSelect && carreraSelect.dataset.version !== horarioUiVersion) {
                    carreraSelect.innerHTML = "";
                    carreraOptions.forEach(function (carrera) {
                        const option = doc.createElement("option");
                        option.value = carrera;
                        option.textContent = carrera;
                        carreraSelect.appendChild(option);
                    });
                    carreraSelect.dataset.version = horarioUiVersion;
                }

                if (carreraSelect && carreraSelect.dataset.practiceBound !== "true") {
                    carreraSelect.dataset.practiceBound = "true";
                    carreraSelect.addEventListener("change", function () {
                        if (carreraSelect.value === "Práctica Libre") {
                            doc.getElementById("horario-modal-asignatura").value = "Práctica Libre";
                        }
                        refreshActionLinks();
                    });
                }

                function openEditModalFromCell(cell) {
                    modal.dataset.dia = cell.dataset.dia || "";
                    modal.dataset.hora = cell.dataset.hora || "";
                    modal.dataset.lab = cell.dataset.lab || "";
                    doc.getElementById("horario-modal-lab").textContent = `Salón ${cell.dataset.labNombre || cell.dataset.lab}`;
                    doc.getElementById("horario-modal-meta").textContent = `${cell.dataset.dia} · ${cell.dataset.hora}`;
                    doc.getElementById("horario-modal-asignatura").value = cell.dataset.asignatura || "";
                    const carreraActual = cell.dataset.carrera || carreraOptions[0] || "";
                    if (carreraActual && carreraSelect && !Array.from(carreraSelect.options).some(function (option) { return option.value === carreraActual; })) {
                        const option = doc.createElement("option");
                        option.value = carreraActual;
                        option.textContent = carreraActual;
                        carreraSelect.appendChild(option);
                    }
                    doc.getElementById("horario-modal-carrera").value = carreraActual;
                    doc.getElementById("horario-modal-monitor").value = cell.dataset.monitor || "";
                    doc.getElementById("horario-modal-profesor").value = cell.dataset.profesor || "";
                    doc.getElementById("horario-modal-save").href = buildHorarioUrl("guardar");
                    doc.getElementById("horario-modal-free").href = buildHorarioUrl("liberar");
                    modal.style.display = "flex";
                    window.setTimeout(function () {
                        doc.getElementById("horario-modal-asignatura").focus();
                    }, 0);
                }

                function closeEditModal() {
                    modal.style.display = "none";
                }

                function buildHorarioUrl(action) {
                    const url = new URL(window.parent.location.href);
                    url.searchParams.set("accion_horario", action);
                    url.searchParams.set("dia", modal.dataset.dia);
                    url.searchParams.set("hora", modal.dataset.hora);
                    url.searchParams.set("lab", modal.dataset.lab);
                    if (action === "guardar") {
                        url.searchParams.set("asignatura", doc.getElementById("horario-modal-asignatura").value);
                        url.searchParams.set("carrera", doc.getElementById("horario-modal-carrera").value);
                        url.searchParams.set("monitor", doc.getElementById("horario-modal-monitor").value);
                        url.searchParams.set("profesor", doc.getElementById("horario-modal-profesor").value);
                    }
                    url.searchParams.set("_", Date.now().toString());
                    return url.toString();
                }

                function submitEditModal(action) {
                    saveHorarioPosition();
                    window.parent.location.href = buildHorarioUrl(action);
                }

                function refreshActionLinks() {
                    doc.getElementById("horario-modal-save").href = buildHorarioUrl("guardar");
                    doc.getElementById("horario-modal-free").href = buildHorarioUrl("liberar");
                }

                if (modal.dataset.bound !== "true") {
                    modal.dataset.bound = "true";
                    ["horario-modal-asignatura", "horario-modal-carrera", "horario-modal-monitor", "horario-modal-profesor"].forEach(function (id) {
                        const field = doc.getElementById(id);
                        if (field) {
                            field.addEventListener("input", refreshActionLinks);
                            field.addEventListener("change", refreshActionLinks);
                        }
                    });
                    modal.addEventListener("click", function (event) {
                        if (event.target === modal) closeEditModal();
                        const actionButton = event.target.closest("[data-action]");
                        const action = actionButton ? actionButton.dataset.action : "";
                        if (action === "close" || action === "cancel") closeEditModal();
                        if (action === "save" || action === "free") {
                            const nextAction = action === "save" ? "guardar" : "liberar";
                            actionButton.href = buildHorarioUrl(nextAction);
                            saveHorarioPosition();
                            if (actionButton.tagName === "A") return;
                            event.preventDefault();
                            submitEditModal(nextAction);
                        }
                    });
                }

                if (body.dataset.horarioContextVersion !== horarioUiVersion) {
                    body.dataset.horarioContextBound = "false";
                    body.dataset.horarioContextVersion = horarioUiVersion;
                }
                if (body.dataset.horarioContextBound !== "true") {
                    body.dataset.horarioContextBound = "true";

                    body.addEventListener("contextmenu", function (event) {
                        const cell = event.target.closest(".horario-editable-cell");
                        if (!cell || !body.contains(cell)) return;

                        event.preventDefault();
                        menu.currentCell = cell;

                        const menuWidth = 160;
                        const menuHeight = 44;
                        const left = Math.min(event.clientX, doc.documentElement.clientWidth - menuWidth - 8);
                        const top = Math.min(event.clientY, doc.documentElement.clientHeight - menuHeight - 8);
                        menu.style.left = Math.max(8, left) + "px";
                        menu.style.top = Math.max(8, top) + "px";
                        menu.style.display = "block";
                    });

                    menu.querySelector("button").addEventListener("click", function () {
                        if (menu.currentCell) {
                            openEditModalFromCell(menu.currentCell);
                        }
                        hideMenu();
                    });

                    doc.addEventListener("click", hideMenu);
                    doc.addEventListener("keydown", function (event) {
                        if (event.key === "Escape") hideMenu();
                    });
                    body.addEventListener("scroll", hideMenu, { passive: true });
                }
            }

            setup();
        })();
        </script>
        """.replace("__OPCIONES_CARRERA__", opciones_carrera_js),
        height=0,
        scrolling=False,
    )

    # ===== FORMULARIO DE EDICIÓN =====
    # ===== FORMULARIO INLINE =====
    @st.dialog("Editar celda del horario")
    def mostrar_dialogo_editar_horario():
        datos_edit = st.session_state.horario_editar
        dia = datos_edit["dia"]
        hora = datos_edit["hora"]
        lab = datos_edit["laboratorio"]
        datos = datos_edit["datos"] or {}

        st.markdown(
            f"""
            <div style="background:#ffffff; border:1px solid #e2d8cb; border-left:6px solid #9f1d24; border-radius:8px; padding:0.8rem 1rem; margin-bottom:1rem;">
                <strong style="color:#731116;">{LABS_NAMES_HORARIO[lab]}</strong>
                <div style="color:#6b4f00; font-size:0.9rem;">{dia} | {hora}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            asignatura = st.text_input("Asignatura", value=datos.get("asignatura", ""))
            carrera_index = opciones_carrera.index(datos.get("carrera", "")) if datos.get("carrera") in opciones_carrera else 0
            carrera = st.selectbox(
                "Carrera",
                options=opciones_carrera,
                index=carrera_index,
                key="horario_carrera_select_dialog",
            )
        with col2:
            monitor = st.text_input("Monitor", value=datos.get("monitor", ""))
            profesor = st.text_input("Profesor", value=datos.get("profesor", ""))

        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Guardar cambios", use_container_width=True):
                if asignatura.strip():
                    hf.set_horario_celda(dia, hora, lab, asignatura, carrera, monitor, profesor)
                else:
                    hf.delete_horario_celda(dia, hora, lab)
                st.session_state.horario_editar = None
                st.rerun()
        with col2:
            if st.button("Eliminar", use_container_width=True):
                hf.delete_horario_celda(dia, hora, lab)
                st.session_state.horario_editar = None
                st.rerun()
        with col3:
            if st.button("Cancelar", use_container_width=True):
                st.session_state.horario_editar = None
                st.rerun()

    if False and st.session_state.horario_editar is not None:
        mostrar_dialogo_editar_horario()

    if False and st.session_state.horario_editar is not None:
        datos_edit = st.session_state.horario_editar
        dia = datos_edit["dia"]
        hora = datos_edit["hora"]
        lab = datos_edit["laboratorio"]
        datos = datos_edit["datos"] or {}

        st.subheader(" Modificar información de la celda")
        st.write(f"**Día:** {dia} | **Hora:** {hora} | **Laboratorio:** {LABS_NAMES_HORARIO[lab]}")
        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            asignatura = st.text_input("Asignatura", value=datos.get("asignatura", ""))
            carrera_index = opciones_carrera.index(datos.get("carrera", "")) if datos.get("carrera") in opciones_carrera else 0
            carrera = st.selectbox(
                "Carrera",
                options=opciones_carrera,
                index=carrera_index,
                key="horario_carrera_select"
            )
        with col2:
            monitor = st.text_input("Monitor", value=datos.get("monitor", ""))
            profesor = st.text_input("Profesor", value=datos.get("profesor", ""))

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button(" Guardar cambios", use_container_width=True):
                if asignatura.strip():
                    hf.set_horario_celda(dia, hora, lab, asignatura, carrera, monitor, profesor)
                else:
                    hf.delete_horario_celda(dia, hora, lab)
                st.session_state.horario_editar = None
                st.rerun()
        with col2:
            if st.button(" Eliminar", use_container_width=True):
                hf.delete_horario_celda(dia, hora, lab)
                st.session_state.horario_editar = None
                st.rerun()
        with col3:
            if st.button(" Cancelar", use_container_width=True):
                st.session_state.horario_editar = None
                st.rerun()
# ============================================================
#  4. GESTIÓN DE MULTAS (DEUDORES)
# ============================================================

def mostrar_formulario_agregar_multa(codigo):
    """
    Muestra el formulario para agregar una nueva multa a un estudiante.
    """
    st.markdown('<p class="deudores-panel-title">Agregar nueva multa</p>', unsafe_allow_html=True)
    with st.form(key=f"form_agregar_{codigo}"):
        col1, col2 = st.columns(2)
        with col1:
            fecha_multa = st.date_input("Fecha de multa", datetime.now().date())
            tecnico_asigna = st.selectbox(
                "Técnico que asigna", 
                OPCIONES_TECNICOS,
                index=0,
                key=f"asigna_v2_{codigo}"
            )
        with col2:
            motivo = st.text_area("Motivo", height=80)
            sancion = st.text_input("Sanción")
        
        if st.form_submit_button(" Guardar multa"):
            if not motivo:
                st.error(" El motivo es obligatorio")
            elif not es_tecnico_valido(tecnico_asigna):
                st.error("Selecciona el técnico que asigna.")
            else:
                multas.agregar_multa(
                    codigo, 
                    fecha_multa.strftime("%Y-%m-%d"), 
                    motivo, 
                    sancion, 
                    tecnico_asigna
                )
                st.success(" Multa agregada correctamente")
                st.rerun()


def mostrar_perfil_estudiante(codigo):
    """
    Muestra el perfil completo de un estudiante en formato compacto.
    Optimizado para reducir reruns innecesarios.
    """
    estudiante = db.ejecutar("SELECT nombres, proyecto FROM estudiantes WHERE codigo=?", (codigo,), fetch=True)
    if estudiante:
        nombre, carrera = estudiante[0]
        st.markdown(f'<p class="deudores-panel-title">{nombre}</p>', unsafe_allow_html=True)
        st.write(f"**Código:** {codigo}")
        st.write(f"**Carrera:** {carrera if carrera else 'No registrada'}")
    else:
        st.warning(" Estudiante no encontrado en la tabla de estudiantes.")
        return
    
    df_multas = multas.obtener_multas_estudiante(codigo)
    if df_multas.empty:
        st.info(" No hay multas registradas para este estudiante.")
        return
    
    df_activas = df_multas[df_multas['pagado'] == 'NO']
    df_pagadas = df_multas[df_multas['pagado'] == 'SI']

    # ===== MULTAS ACTIVAS =====
    if not df_activas.empty:
        st.markdown(f'<p class="deudores-panel-title">Multas activas ({len(df_activas)})</p>', unsafe_allow_html=True)
        
        for idx, (_, m) in enumerate(df_activas.iterrows()):
            # Usar un container para cada multa
            with st.container():
                col1, col2, col3 = st.columns([2, 1.2, 0.5])
                
                # Columna 1: Información de la multa
                with col1:
                    st.write(f"** {m['fecha_multa']}**")
                    st.write(f" {m['motivo'] if m['motivo'] else 'Sin motivo'}")
                    if m['sancion']:
                        st.write(f" Sanción: {m['sancion']}")
                    st.caption(f" Asignada por: {m['tecnico_asigna']}")
                
                # Columna 2: Botones de acción
                with col2:
                    # Botón Pagar - usar session_state para controlar el modal
                    key_pagar = f"pagar_modal_{m['id']}"
                    if st.button(f" Pagar", key=f"pagar_btn_{m['id']}", use_container_width=True):
                        st.session_state[key_pagar] = not st.session_state.get(key_pagar, False)
                        st.rerun()
                    
                    # Botón Modificar
                    key_modificar = f"modificar_modal_{m['id']}"
                    if st.button(f" Modificar", key=f"modificar_btn_{m['id']}", use_container_width=True):
                        st.session_state[key_modificar] = not st.session_state.get(key_modificar, False)
                        st.rerun()
                
                # Columna 3: Botón Eliminar
                with col3:
                    key_eliminar = f"eliminar_modal_{m['id']}"
                    if st.button("Eliminar", key=f"eliminar_btn_{m['id']}", use_container_width=True):
                        st.session_state[key_eliminar] = not st.session_state.get(key_eliminar, False)
                        st.rerun()
                
                # ===== MODAL PAGAR =====
                if st.session_state.get(f"pagar_modal_{m['id']}", False):
                    with st.expander(f" Pagar multa", expanded=True):
                        st.write(f"**Motivo:** {m['motivo']}")
                        if m['sancion']:
                            st.write(f"**Sanción:** {m['sancion']}")
                        
                        tecnico_recibe = st.selectbox(
                            "Técnico que recibe el pago", 
                            OPCIONES_TECNICOS,
                            index=0,
                            key=f"tecnico_pago_v2_{m['id']}"
                        )
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button(f" Confirmar", key=f"confirmar_pago_{m['id']}"):
                                if not es_tecnico_valido(tecnico_recibe):
                                    st.error("Selecciona el técnico que recibe el pago.")
                                else:
                                    multas.pagar_multa(m['id'], tecnico_recibe)
                                    st.session_state[f"pagar_modal_{m['id']}"] = False
                                    st.rerun()
                        with col_b:
                            if st.button(f" Cancelar", key=f"cancelar_pago_{m['id']}"):
                                st.session_state[f"pagar_modal_{m['id']}"] = False
                                st.rerun()
                
                # ===== MODAL MODIFICAR =====
                if st.session_state.get(f"modificar_modal_{m['id']}", False):
                    with st.expander(f" Modificar multa", expanded=True):
                        nuevo_motivo = st.text_input(
                            "Motivo", 
                            value=m['motivo'] if m['motivo'] else "",
                            key=f"edit_motivo_{m['id']}"
                        )
                        nueva_sancion = st.text_input(
                            "Sanción", 
                            value=m['sancion'] if m['sancion'] else "",
                            key=f"edit_sancion_{m['id']}"
                        )
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button(f" Guardar", key=f"guardar_edit_{m['id']}"):
                                db.ejecutar(
                                    "UPDATE multas SET motivo = ?, sancion = ? WHERE id = ?",
                                    (nuevo_motivo, nueva_sancion, m['id'])
                                )
                                st.session_state[f"modificar_modal_{m['id']}"] = False
                                st.rerun()
                        with col_b:
                            if st.button(f" Cancelar", key=f"cancelar_edit_{m['id']}"):
                                st.session_state[f"modificar_modal_{m['id']}"] = False
                                st.rerun()
                
                # ===== MODAL ELIMINAR =====
                if st.session_state.get(f"eliminar_modal_{m['id']}", False):
                    with st.expander(f" Eliminar multa", expanded=True):
                        st.warning(f"¿Estás seguro de eliminar esta multa?")
                        st.write(f"**Motivo:** {m['motivo']}")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button(f" Sí", key=f"confirmar_eliminar_{m['id']}"):
                                multas.eliminar_multa(m['id'])
                                st.session_state[f"eliminar_modal_{m['id']}"] = False
                                st.rerun()
                        with col_b:
                            if st.button(f" No", key=f"cancelar_eliminar_{m['id']}"):
                                st.session_state[f"eliminar_modal_{m['id']}"] = False
                                st.rerun()
                
                st.divider()
    else:
        st.info(" No hay multas activas.")

    # ===== HISTORIAL DE MULTAS PAGADAS =====
    if not df_pagadas.empty:
        with st.expander(f" Historial de multas pagadas ({len(df_pagadas)})", expanded=False):
            for _, m in df_pagadas.iterrows():
                st.write(f"** {m['fecha_multa']}** → Pagado: {m['fecha_pago']}")
                st.write(f" {m['motivo']}")
                if m['sancion']:
                    st.write(f" Sanción: {m['sancion']}")
                st.caption(f" Recibido por: {m['tecnico_recibe']}")
                st.divider()

def mostrar_deudores():
    df_deudores = multas.obtener_deudores()

    st.markdown(
        """
        <div class="labs-section-title">
            <h2>Gestion de Deudores</h2>
            <p>Seguimiento de estudiantes con multas activas, historial de pagos y registro de nuevas sanciones.</p>
        </div>
        <style>
            .deudores-summary {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.85rem;
                margin: 0.75rem 0 1rem 0;
            }
            .deudores-card {
                background: #ffffff;
                border: 1px solid #e2d8cb;
                border-left: 7px solid #9f1d24;
                border-radius: 8px;
                padding: 0.85rem 1rem;
                box-shadow: 0 6px 18px rgba(43,31,20,0.06);
            }
            .deudores-card strong {
                display: block;
                color: #731116;
                font-size: 1.55rem;
                line-height: 1.1;
            }
            .deudores-card span {
                color: #6b7280;
                font-size: 0.82rem;
                font-weight: 700;
            }
            .deudores-card.accent {
                border-left-color: #f2c230;
            }
            .deudores-panel-title {
                color: #731116;
                font-weight: 800;
                margin: 0.75rem 0 0.15rem 0;
            }
            .deudores-panel-copy {
                color: #6b7280;
                margin: 0 0 0.75rem 0;
                font-size: 0.9rem;
            }
            @media (max-width: 900px) {
                .deudores-summary {
                    grid-template-columns: 1fr;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    total_deudores = len(df_deudores)
    total_multas = int(df_deudores["numero_multas"].sum()) if not df_deudores.empty else 0
    max_multas = int(df_deudores["numero_multas"].max()) if not df_deudores.empty else 0

    st.markdown(
        f"""
        <div class="deudores-summary">
            <div class="deudores-card">
                <strong>{total_deudores}</strong>
                <span>Estudiantes con multas activas</span>
            </div>
            <div class="deudores-card accent">
                <strong>{total_multas}</strong>
                <span>Multas activas acumuladas</span>
            </div>
            <div class="deudores-card">
                <strong>{max_multas}</strong>
                <span>Mayor numero de multas por estudiante</span>
            </div>
        </div>
        <p class="deudores-panel-title">Busqueda y seguimiento</p>
        <p class="deudores-panel-copy">Busca por codigo o nombre para abrir el historial completo de un estudiante.</p>
        """,
        unsafe_allow_html=True,
    )

    def limpiar_busqueda_deudor():
        st.session_state.deudor_search = ""
        st.session_state.deudores_pagina = 1
        st.session_state.deudores_estudiantes_pagina = 1

    def reiniciar_paginas_deudores():
        st.session_state.deudores_pagina = 1
        st.session_state.deudores_estudiantes_pagina = 1

    buscar_col, volver_col = st.columns([4, 1])
    with buscar_col:
        search_term = st.text_input(
            "Buscar por código o nombre",
            placeholder="Ej: 20211005067 o Juan",
            key="deudor_search",
            on_change=reiniciar_paginas_deudores,
        )
    with volver_col:
        st.write("")
        st.button(
            "Volver a la lista",
            key="limpiar_busqueda_deudor",
            use_container_width=True,
            disabled=not bool(search_term),
            on_click=limpiar_busqueda_deudor,
        )
    if "deudor_mostrar_nueva_multa" not in st.session_state:
        st.session_state.deudor_mostrar_nueva_multa = False
    if "deudor_mostrar_verificacion" not in st.session_state:
        st.session_state.deudor_mostrar_verificacion = False

    col_nueva_multa, col_importar, _ = st.columns([1, 1.45, 2])
    with col_nueva_multa:
        if st.button("Nueva multa", key="abrir_nueva_multa", use_container_width=True):
            st.session_state.deudor_mostrar_nueva_multa = True
            st.rerun()
    with col_importar:
        if st.button("Importar Excel de Verificacion", key="abrir_verificacion", use_container_width=True):
            st.session_state.deudor_mostrar_verificacion = True
            st.rerun()

    if st.session_state.deudor_mostrar_verificacion:
        with st.container(border=True):
            titulo_col, cerrar_col = st.columns([10, 1])
            titulo_col.markdown("#### Verificacion masiva de paz y salvos")
            with cerrar_col:
                if st.button("X", key="cerrar_verificacion", help="Cerrar", use_container_width=True):
                    st.session_state.deudor_mostrar_verificacion = False
                    st.session_state.pop("excel_verificacion", None)
                    st.rerun()
            st.caption("Carga un .xlsx con las columnas Codigo y Nombre. El archivo se procesa en memoria y no se almacena.")
            archivo = st.file_uploader(
                "Archivo de verificacion", type=["xlsx"], key="excel_verificacion",
                label_visibility="collapsed",
            )
            if archivo is not None:
                try:
                    verificacion = _leer_verificacion_excel(archivo)
                    conteos = {
                        str(row["codigo_estudiante"]).strip(): int(row["numero_multas"])
                        for _, row in df_deudores.iterrows()
                    }
                    verificacion["Multas activas"] = verificacion["Codigo"].map(conteos).fillna(0).astype(int)
                    verificacion["Estado"] = verificacion["Multas activas"].apply(
                        lambda n: "Apto para Paz y Salvo" if n == 0 else "No Apto / Con Deuda Activa"
                    )
                    aptos = verificacion[verificacion["Multas activas"] == 0]
                    no_aptos = verificacion[verificacion["Multas activas"] > 0]
                    col_apto, col_no_apto = st.columns(2)
                    col_apto.metric("Aptos para Paz y Salvo", len(aptos))
                    col_no_apto.metric("No aptos / Con deuda", len(no_aptos))
                    st.markdown("**Apto para Paz y Salvo**")
                    st.dataframe(aptos[["Codigo", "Nombre", "Estado"]], hide_index=True, use_container_width=True)
                    st.markdown("**No Apto / Con Deuda Activa**")
                    if no_aptos.empty:
                        st.success("Ninguno de los estudiantes importados tiene deudas activas.")
                    else:
                        st.dataframe(no_aptos, hide_index=True, use_container_width=True)
                        codigo_pago = st.selectbox(
                            "Estudiante para registrar pago",
                            no_aptos["Codigo"].tolist(),
                            format_func=lambda codigo: f"{no_aptos.loc[no_aptos['Codigo'] == codigo, 'Nombre'].iloc[0]} ({codigo})",
                            key="verificacion_codigo_pago",
                        )
                        activas = multas.obtener_multas_activas_estudiante(codigo_pago)
                        if not activas.empty:
                            opciones_multa = {
                                int(row["id"]): f"{row['fecha_multa']} - {row['motivo']}"
                                for _, row in activas.iterrows()
                            }
                            id_multa = st.selectbox(
                                "Multa a pagar", list(opciones_multa),
                                format_func=lambda multa_id: opciones_multa[multa_id],
                                key="verificacion_multa_pago",
                            )
                            tecnico_pago = st.selectbox("Tecnico que recibe", OPCIONES_TECNICOS, index=0, key="verificacion_tecnico_pago_v2")
                            if st.button("Registrar pago", key="verificacion_registrar_pago", type="primary"):
                                if not es_tecnico_valido(tecnico_pago):
                                    st.error("Selecciona el técnico que recibe el pago.")
                                else:
                                    multas.pagar_multa(id_multa, tecnico_pago)
                                    st.success("Pago registrado. La clasificacion ha sido actualizada.")
                                    st.rerun()
                except ImportError:
                    st.error("Falta el lector de Excel. Instala la dependencia con: pip install openpyxl")
                except (ValueError, TypeError) as error:
                    st.error(str(error))
                except Exception as error:
                    st.error(f"No fue posible procesar el Excel: {error}")

    if st.session_state.deudor_mostrar_nueva_multa:
        with st.expander("Registrar nueva multa", expanded=True):
            col_title, col_cancel = st.columns([4, 1])
            with col_cancel:
                if st.button("Cancelar", key="cancelar_nueva_multa", use_container_width=True):
                    st.session_state.deudor_mostrar_nueva_multa = False
                    for key in [
                        "deudor_nueva_multa_busqueda",
                        "deudor_nueva_multa_codigo",
                        "multa_nuevo_codigo",
                        "multa_nuevo_nombre",
                        "multa_nuevo_proyecto",
                        "directa_fecha_multa",
                        "directa_tecnico_asigna_v2",
                        "directa_motivo_multa",
                        "directa_sancion_multa",
                    ]:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()

            with col_title:
                st.caption("Busca el estudiante y registra una multa activa sin salir de esta pantalla.")
            multa_busqueda = st.text_input(
                "Estudiante",
                placeholder="Codigo o nombre del estudiante",
                key="deudor_nueva_multa_busqueda",
            )

            if multa_busqueda:
                df_estudiantes_multa = multas.buscar_estudiantes(multa_busqueda)

                if df_estudiantes_multa.empty:
                    st.warning("No se encontro ningun estudiante con ese codigo o nombre.")
                    with st.form("form_registrar_estudiante_multa"):
                        nuevo_codigo = st.text_input("Codigo del estudiante *", key="multa_nuevo_codigo")
                        nuevo_nombre = st.text_input("Nombre completo *", key="multa_nuevo_nombre")
                        nuevo_proyecto = st.text_input("Carrera/Proyecto", key="multa_nuevo_proyecto")
                        registrar = st.form_submit_button("Registrar estudiante")

                    if registrar:
                        if nuevo_codigo and nuevo_nombre:
                            db.ejecutar(
                                "INSERT INTO estudiantes (codigo, nombres, proyecto) VALUES (?, ?, ?)",
                                (nuevo_codigo, nuevo_nombre, nuevo_proyecto),
                            )
                            st.success(f"Estudiante {nuevo_nombre} registrado. Ya puedes buscarlo para agregar la multa.")
                            st.rerun()
                        else:
                            st.error("Codigo y nombre son obligatorios.")
                else:
                    opciones = {
                        row["codigo"]: f"{row['nombres']} ({row['codigo']}) - {row['carrera'] if row['carrera'] else 'Sin carrera'}"
                        for _, row in df_estudiantes_multa.iterrows()
                    }
                    codigo_multa = st.selectbox(
                        "Selecciona el estudiante",
                        list(opciones.keys()),
                        format_func=lambda codigo: opciones[codigo],
                        key="deudor_nueva_multa_codigo",
                    )

                    with st.form("form_nueva_multa_directa"):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            fecha_multa = st.date_input("Fecha de multa", datetime.now().date(), key="directa_fecha_multa")
                            tecnico_asigna = st.selectbox(
                                "Tecnico que asigna",
                                OPCIONES_TECNICOS,
                                index=0,
                                key="directa_tecnico_asigna_v2",
                            )
                        with col_b:
                            motivo = st.text_area("Motivo *", height=90, key="directa_motivo_multa")
                            sancion = st.text_input("Sancion", key="directa_sancion_multa")

                        guardar_multa = st.form_submit_button("Guardar multa")

                    if guardar_multa:
                        if not motivo.strip():
                            st.error("El motivo es obligatorio.")
                        elif not es_tecnico_valido(tecnico_asigna):
                            st.error("Selecciona el técnico que asigna.")
                        else:
                            multas.agregar_multa(
                                codigo_multa,
                                fecha_multa.strftime("%Y-%m-%d"),
                                motivo.strip(),
                                sancion.strip(),
                                tecnico_asigna,
                            )
                            st.session_state.deudor_mostrar_nueva_multa = False
                            st.success("Multa agregada correctamente.")
                            st.rerun()
            else:
                st.info("Escribe un codigo o nombre para buscar al estudiante.")

    if df_deudores.empty and not search_term:
        st.info("No hay estudiantes con multas activas.")
        return

    if search_term:
        df_filtrado = df_deudores[
            df_deudores["codigo_estudiante"].str.contains(search_term, case=False, na=False)
            | df_deudores["nombres"].str.contains(search_term, case=False, na=False)
        ]
    else:
        df_filtrado = df_deudores

    if not df_filtrado.empty:
        st.markdown('<p class="deudores-panel-title">Lista de deudores</p>', unsafe_allow_html=True)
        pagina_key = "deudores_pagina"
        total_paginas = max(1, (len(df_filtrado) + 4) // 5)
        st.session_state[pagina_key] = min(max(1, st.session_state.get(pagina_key, 1)), total_paginas)
        pagina = st.session_state[pagina_key]
        inicio = (pagina - 1) * 5
        df_pagina = df_filtrado.iloc[inicio:inicio + 5]
        encabezado = st.columns([1.2, 2.4, 2.2, 1.3])
        for columna, texto in zip(encabezado, ("Código", "Estudiante", "Carrera", "Estado")):
            columna.markdown(f"**{texto}**")

        for indice_local, (_, row) in enumerate(df_pagina.iterrows()):
            indice = inicio + indice_local
            codigo = str(row["codigo_estudiante"])
            cantidad = int(row["numero_multas"])
            estado = "Crítica" if cantidad > 3 else "Advertencia"
            if cantidad > 3:
                fondo_estado, borde_estado, texto_estado = "#f9d8da", "#e8a8ad", "#85151d"
            else:
                fondo_estado, borde_estado, texto_estado = "#fff2bf", "#e7cf72", "#725900"
            fila_marker = f"deudor_fila_{indice}"
            st.markdown(
                f"""
                <style id="{fila_marker}">
                    div[data-testid="stElementContainer"]:has(style#{fila_marker}) + div[data-testid="stHorizontalBlock"] {{
                        background:{'#ffffff' if indice % 2 == 0 else '#f5f6f8'};
                        border-bottom:1px solid #e6e8ec; padding:0.38rem 0.5rem; border-radius:6px;
                        align-items:center;
                    }}
                </style>
                """,
                unsafe_allow_html=True,
            )
            columnas = st.columns([1.2, 2.4, 2.2, 1.3])
            columnas[0].write(codigo)
            columnas[1].write(row["nombres"] or "Sin nombre")
            columnas[2].write(row["carrera"] or "No registrada")
            with columnas[3]:
                if cantidad > 3:
                    fondo_estado, borde_estado, texto_estado = "#f9d8da", "#e8a8ad", "#85151d"
                else:
                    fondo_estado, borde_estado, texto_estado = "#fff2bf", "#e7cf72", "#725900"
                st.markdown(
                    f"""
                    <span style="display:inline-flex; width:100%; justify-content:center; box-sizing:border-box;
                        background:{fondo_estado}; border:1px solid {borde_estado}; color:{texto_estado};
                        border-radius:7px; padding:0.48rem 0.6rem; font-weight:850; white-space:nowrap;">
                        {estado} · {cantidad}
                    </span>
                    """,
                    unsafe_allow_html=True,
                )
        nav_anterior, nav_info, nav_siguiente = st.columns([1, 2, 1])
        with nav_anterior:
            if st.button("Anterior", key="deudores_anterior", disabled=pagina == 1, use_container_width=True):
                st.session_state[pagina_key] -= 1
                st.rerun()
        nav_info.markdown(
            f"<div style='text-align:center;padding:.55rem;color:#5f6368'>Mostrar registros {inicio + 1}–{min(inicio + 5, len(df_filtrado))} de {len(df_filtrado)}</div>",
            unsafe_allow_html=True,
        )
        with nav_siguiente:
            if st.button("Siguiente", key="deudores_siguiente", disabled=pagina == total_paginas, use_container_width=True):
                st.session_state[pagina_key] += 1
                st.rerun()
        st.divider()
        st.markdown('<p class="deudores-panel-title">Reporte detallado de multas</p>', unsafe_allow_html=True)
        st.caption("Informe institucional completo para seguimiento administrativo, conciliación de pagos y auditoría.")
        query_detalle = """
            SELECT
                m.codigo_estudiante,
                e.nombres,
                e.proyecto as carrera,
                m.fecha_multa,
                m.fecha_pago,
                m.motivo,
                m.sancion,
                m.tecnico_asigna,
                m.tecnico_recibe,
                CASE WHEN m.pagado = 'SI' THEN 'Pagada' ELSE 'Activa' END AS estado
            FROM multas m
            LEFT JOIN estudiantes e ON m.codigo_estudiante = e.codigo
            ORDER BY CASE WHEN m.pagado = 'NO' THEN 0 ELSE 1 END, e.nombres, m.fecha_multa DESC
        """
        df_detalle = db.fetch_df(query_detalle)
        if not df_detalle.empty:
            filtro_col, descarga_col = st.columns([2.2, 1])
            with filtro_col:
                filtro_estado = st.segmented_control(
                    "Estado incluido",
                    ["Todas", "Activas", "Pagadas"],
                    default="Todas",
                    key="filtro_reporte_multas",
                )
            if filtro_estado == "Activas":
                df_reporte = df_detalle[df_detalle["estado"] == "Activa"].copy()
            elif filtro_estado == "Pagadas":
                df_reporte = df_detalle[df_detalle["estado"] == "Pagada"].copy()
            else:
                df_reporte = df_detalle.copy()

            total_reporte = len(df_reporte)
            activas_reporte = int((df_reporte["estado"] == "Activa").sum())
            pagadas_reporte = int((df_reporte["estado"] == "Pagada").sum())
            estudiantes_reporte = int(df_reporte["codigo_estudiante"].nunique())
            metrica_1, metrica_2, metrica_3, metrica_4 = st.columns(4)
            metrica_1.metric("Registros", total_reporte)
            metrica_2.metric("Activas", activas_reporte)
            metrica_3.metric("Pagadas", pagadas_reporte)
            metrica_4.metric("Estudiantes", estudiantes_reporte)

            nombres_columnas = {
                "codigo_estudiante": "Código",
                "nombres": "Estudiante",
                "carrera": "Proyecto curricular",
                "fecha_multa": "Fecha de multa",
                "fecha_pago": "Fecha de pago",
                "motivo": "Motivo",
                "sancion": "Sanción",
                "tecnico_asigna": "Técnico que asigna",
                "tecnico_recibe": "Técnico que recibe",
                "estado": "Estado",
            }
            df_exportar = df_reporte.rename(columns=nombres_columnas)
            excel_multas = crear_excel_institucional(
                df_exportar,
                "Reporte detallado de multas",
                "Seguimiento de obligaciones, sanciones y paz y salvos",
                [
                    ("Filtro", filtro_estado),
                    ("Registros", total_reporte),
                    ("Multas activas", activas_reporte),
                    ("Multas pagadas", pagadas_reporte),
                    ("Estudiantes incluidos", estudiantes_reporte),
                ],
                nombre_hoja="Multas",
            )
            with descarga_col:
                st.write("")
                st.write("")
                st.download_button(
                    label="Descargar Excel institucional",
                    data=excel_multas,
                    file_name=f"reporte_multas_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="descargar_deudores_detalle",
                    use_container_width=True,
                )

    if search_term and df_filtrado.empty:
        st.info("El estudiante no tiene multas activas. Buscando en la base de datos de estudiantes...")
        df_estudiantes = multas.buscar_estudiantes(search_term)

        if df_estudiantes.empty:
            st.warning("No se encontro ningun estudiante con ese codigo o nombre.")
            with st.expander("Registrar nuevo estudiante"):
                nuevo_codigo = st.text_input("Codigo del estudiante *", key="nuevo_codigo")
                nuevo_nombre = st.text_input("Nombre completo *", key="nuevo_nombre")
                nuevo_proyecto = st.text_input("Carrera/Proyecto", key="nuevo_proyecto")
                if st.button("Registrar estudiante", key="registrar_nuevo"):
                    if nuevo_codigo and nuevo_nombre:
                        db.ejecutar(
                            "INSERT INTO estudiantes (codigo, nombres, proyecto) VALUES (?, ?, ?)",
                            (nuevo_codigo, nuevo_nombre, nuevo_proyecto),
                        )
                        st.success(f"Estudiante {nuevo_nombre} registrado. Ahora puedes agregar una multa.")
                        st.rerun()
                    else:
                        st.error("Codigo y nombre son obligatorios.")
        else:
            st.markdown('<p class="deudores-panel-title">Estudiantes encontrados</p>', unsafe_allow_html=True)
            pagina_est_key = "deudores_estudiantes_pagina"
            total_paginas_est = max(1, (len(df_estudiantes) + 4) // 5)
            pagina_est = min(max(1, st.session_state.get(pagina_est_key, 1)), total_paginas_est)
            st.session_state[pagina_est_key] = pagina_est
            inicio_est = (pagina_est - 1) * 5
            df_estudiantes_pagina = df_estudiantes.iloc[inicio_est:inicio_est + 5]
            for _, row in df_estudiantes_pagina.iterrows():
                with st.expander(f"{row['nombres']} ({row['codigo']}) - {row['multas_activas']} multas activas"):
                    mostrar_perfil_estudiante(row["codigo"])
            anterior_est, info_est, siguiente_est = st.columns([1, 2, 1])
            with anterior_est:
                if st.button("Anterior", key="deudores_estudiantes_anterior", disabled=pagina_est == 1, use_container_width=True):
                    st.session_state[pagina_est_key] = pagina_est - 1
                    st.rerun()
            info_est.markdown(
                f"<div style='text-align:center;padding:.55rem;color:#5f6368'>Registros {inicio_est + 1}–{min(inicio_est + 5, len(df_estudiantes))} de {len(df_estudiantes)}</div>",
                unsafe_allow_html=True,
            )
            with siguiente_est:
                if st.button("Siguiente", key="deudores_estudiantes_siguiente", disabled=pagina_est == total_paginas_est, use_container_width=True):
                    st.session_state[pagina_est_key] = pagina_est + 1
                    st.rerun()

    elif search_term and len(df_filtrado) == 1:
        row = df_filtrado.iloc[0]
        codigo = row["codigo_estudiante"]
        with st.expander(f"{row['nombres']} ({codigo}) - Detalle completo", expanded=True):
            mostrar_perfil_estudiante(codigo)

    elif search_term and len(df_filtrado) > 1:
        st.info(f"Se encontraron {len(df_filtrado)} estudiantes con multas activas.")
        for _, row in df_pagina.iterrows():
            codigo = row["codigo_estudiante"]
            if st.button(f"Ver historial de {row['nombres']}", key=f"btn_historial_{codigo}"):
                with st.expander(f"{row['nombres']} ({codigo})", expanded=True):
                    mostrar_perfil_estudiante(codigo)

    elif df_deudores.empty:
        st.info("No hay deudores. Usa el buscador para gestionar multas de estudiantes especificos.")
    else:
        st.caption("Usa el buscador para ver el historial completo de un estudiante.")
