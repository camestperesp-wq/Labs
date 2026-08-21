# ui_components

import streamlit as st
import pandas as pd
from datetime import datetime
import database as db
import reservas as res
import horario_fijo as hf
import multas
from constants import DIAS, HORAS, LABS_NAMES_HORARIO, LABS_HORARIO, TECNICOS, LABS_ORDEN_HORARIO, LABORATORIOS

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
    Muestra un editor de asistencias con opción para cambiar banco.
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
        st.caption(f"📌 Capacidad del laboratorio: **{capacidad_maxima}** bancos (1-{capacidad_maxima})")
    else:
        capacidad_maxima = 99
        st.caption("Si ingresas un número fuera de rango, el sistema mostrará un error al guardar.")

    # ===== CONFIGURACIÓN DEL DATA_EDITOR =====
    config = {
        "id": st.column_config.TextColumn("ID", width="small", disabled=True),
        "banco": st.column_config.NumberColumn(
            "Banco", 
            width="small",
            min_value=1,
            max_value=capacidad_maxima,
            step=1
        ),
        "asiste": st.column_config.SelectboxColumn("Asiste", options=["", "Si", "No"])
    }
    
    column_order = ['id', 'banco', 'codigo', 'nombres', 'proyecto', 'asiste']

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

    # ===== Botón Guardar cambios =====
    if st.button("Guardar cambios", key=f"save_{key}_{version}"):
        # ===== VALIDACIÓN COMPLETA =====
        errores = []
        cambios = []
        inasistencias = []
        cambios_banco = []
        
        # Primero, validar TODOS los bancos
        for _, row in edited.iterrows():
            id_res = row['id']
            nuevo_banco = row['banco']
            
            # ===== EXCLUIR BANCO 0 DE LA VALIDACIÓN =====
            if nuevo_banco == 0:
                continue  # Saltar reservas de profesor (banco 0)
            
            # Validar rango (solo para bancos > 0)
            if nuevo_banco < 1 or nuevo_banco > capacidad_maxima:
                nombre = df[df['id'] == id_res]['nombres'].iloc[0]
                errores.append(f"❌ **{nombre}**: Banco **{nuevo_banco}** fuera de rango (1-{capacidad_maxima})")
        # Si hay errores, mostrar y DETENER
        if errores:
            st.error("❌ **Errores en los bancos:**")
            for error in errores:
                st.error(error)
            st.warning(f"⚠️ Corrige los bancos a valores entre **1 y {capacidad_maxima}**")
            return
        
        # Si no hay errores, procesar cambios
        for _, row in edited.iterrows():
            id_res = row['id']
            nuevo_banco = row['banco']
            nuevo_estado = row['asiste']
            
            anterior_banco = df[df['id'] == id_res]['banco'].iloc[0]
            anterior_estado = df[df['id'] == id_res]['asiste'].iloc[0]
            
            # Verificar cambio de banco
            if nuevo_banco != anterior_banco:
                cambios_banco.append((id_res, nuevo_banco))
            
            # Verificar cambio de asistencia
            if nuevo_estado != anterior_estado:
                if nuevo_estado == "No":
                    inasistencias.append(id_res)
                cambios.append((id_res, nuevo_estado))
        
        # ===== PROCESAR CAMBIOS DE BANCO =====
        errores_banco = []
        for id_res, nuevo_banco in cambios_banco:
            r = db.ejecutar("SELECT laboratorio, fecha, hora FROM reservas WHERE id=?", (id_res,), fetch=True)
            if r:
                lab, fecha, hora = r[0]
                r_banco = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                                            WHERE laboratorio=? AND fecha=? AND hora=? 
                                            AND banco=? 
                                            AND activo=1 
                                            AND id != ?
                                            AND (asiste != 'No' OR asiste IS NULL OR asiste = '')""", 
                                         (lab, fecha, hora, nuevo_banco, id_res), fetch=True)
                if r_banco[0][0] > 0:
                    nombre = df[df['id'] == id_res]['nombres'].iloc[0]
                    errores_banco.append(f"❌ **{nombre}**: Banco **{nuevo_banco}** ya ocupado")
                else:
                    db.ejecutar("UPDATE reservas SET banco = ? WHERE id = ?", (nuevo_banco, id_res))
        
        if errores_banco:
            for error in errores_banco:
                st.error(error)
            return
        
        # ===== PROCESAR CAMBIOS DE ASISTENCIA =====
        if not cambios and not inasistencias and not cambios_banco:
            st.info("Sin cambios")
            return
        
        if inasistencias:
            st.session_state.inasistencias_pendientes = inasistencias
            st.session_state.cambios_pendientes = cambios
            st.session_state.confirmar_inasistencia = True
            st.rerun()
        else:
            for id_res, nuevo_estado in cambios:
                res.actualizar_asiste(id_res, nuevo_estado, None)
            st.session_state.editor_version += 1
            
            mensajes = []
            if cambios:
                mensajes.append(f"{len(cambios)} cambios de asistencia")
            if cambios_banco:
                mensajes.append(f"{len(cambios_banco)} cambios de banco")
            st.success(f"✅ {' y '.join(mensajes)} guardados")
            st.rerun()

    # ===== CONFIRMACIÓN DE INASISTENCIAS =====
    if st.session_state.confirmar_inasistencia:
        with st.popover("⚠️ Confirmar inasistencia", use_container_width=True):
            st.warning(f"Estás marcando **{len(st.session_state.inasistencias_pendientes)}** reserva(s) como 'No asistió'.")
            st.write("Por favor, confirma con tu nombre:")
            tecnico = st.selectbox("Técnico que marca la inasistencia", TECNICOS, key=f"tecnico_confirm_{key}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Confirmar", key=f"confirmar_{key}"):
                    for id_res, nuevo_estado in st.session_state.cambios_pendientes:
                        res.actualizar_asiste(id_res, nuevo_estado, tecnico)
                    st.session_state.editor_version += 1
                    st.session_state.confirmar_inasistencia = False
                    st.session_state.inasistencias_pendientes = []
                    st.session_state.cambios_pendientes = []
                    st.success(f"Cambios guardados (inasistencias registradas por {tecnico})")
                    st.rerun()
            with col2:
                if st.button("❌ Cancelar", key=f"cancelar_{key}"):
                    st.session_state.confirmar_inasistencia = False
                    st.session_state.inasistencias_pendientes = []
                    st.session_state.cambios_pendientes = []
                    st.rerun()
# ============================================================
#  2. ELIMINADOR DE RESERVAS
# ============================================================

def render_eliminar_reserva(df, key):
    """
    Muestra un selector para eliminar una reserva del DataFrame.
    """
    if df is None or df.empty:
        return

    confirm_key = f"confirm_{key}"
    if confirm_key not in st.session_state:
        st.session_state[confirm_key] = False

    st.divider()
    st.subheader("🗑️ Eliminar reserva")
    
    opts = {}
    for _, row in df.iterrows():
        id_res = row['id']
        desc_parts = []
        
        if 'fecha' in row.index:
            desc_parts.append(str(row['fecha']))
        if 'hora' in row.index:
            desc_parts.append(str(row['hora']))
        if 'laboratorio' in row.index:
            desc_parts.append(str(row['laboratorio']))
        if 'banco' in row.index:
            desc_parts.append(f"B{row['banco']}")
        desc_parts.append(f"- {row['nombres']}")
        opts[id_res] = " ".join(desc_parts)
    
    id_eliminar = st.selectbox(
        "Selecciona la reserva a eliminar",
        list(opts.keys()),
        format_func=lambda x: opts[x],
        key=f"eliminar_select_{key}"
    )
    
    if st.button("🗑️ Eliminar reserva", key=f"eliminar_btn_{key}"):
        st.session_state[confirm_key] = True
        st.session_state[f"id_a_eliminar_{key}"] = id_eliminar
        st.rerun()
    
    if st.session_state[confirm_key]:
        id_res = st.session_state.get(f"id_a_eliminar_{key}")
        if id_res is not None:
            nombre = df[df['id'] == id_res]['nombres'].iloc[0]
            st.warning(f"⚠️ ¿Estás seguro de eliminar la reserva de **{nombre}**?")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Sí, eliminar", key=f"eliminar_confirm_{key}"):
                    res.eliminar_reserva(id_res)
                    st.success(f"✅ Reserva de {nombre} eliminada correctamente")
                    st.session_state[confirm_key] = False
                    if f"id_a_eliminar_{key}" in st.session_state:
                        del st.session_state[f"id_a_eliminar_{key}"]
                    if key.startswith("eliminar_fecha_lab"):
                        if "labs_params" in st.session_state:
                            del st.session_state.labs_params
                    elif key.startswith("eliminar_codigo"):
                        if "labs_codigo_busqueda" in st.session_state:
                            del st.session_state.labs_codigo_busqueda
                    st.rerun()
            with col2:
                if st.button("❌ No, cancelar", key=f"eliminar_cancel_{key}"):
                    st.session_state[confirm_key] = False
                    if f"id_a_eliminar_{key}" in st.session_state:
                        del st.session_state[f"id_a_eliminar_{key}"]
                    st.rerun()
    else:
        st.info("ℹ️ Selecciona una reserva y haz clic en 'Eliminar reserva' para comenzar")


# ============================================================
#  3. HORARIO GENERAL (SIN POPOVER)
# ============================================================
def mostrar_horario_general():
    st.subheader("📅 Horario General de Laboratorios")
    st.caption("Los colores indican la carrera. Selecciona una celda y haz clic en 'Editar celda' para modificarla.")

    opciones_carrera = [
        "Ing. Eléctrica",
        "Ing. Electrónica",
        "Ing. De Sistema",
        "Ing. Industrial",
        "Ing. Catastral",
        "Posgrados",
        "Adicional"
    ]

    colores_carrera = {
        "Ing. Eléctrica": "#FFCCCC",
        "Ing. Electrónica": "#CCE5FF",
        "Ing. De Sistema": "#E6CCFF",
        "Ing. Industrial": "#CCF2FF",
        "Ing. Catastral": "#CCFFCC",
        "Posgrados": "#FFFFCC",
        "Adicional": "#FF8C00"
    }
    dia_seleccionado = st.radio(
        "Selecciona el día",
        DIAS,
        horizontal=True,
        key="horario_dia"
    )

    labs_keys = [lab for lab in LABS_ORDEN_HORARIO if lab in LABS_HORARIO]

    if "horario_editar" not in st.session_state:
        st.session_state.horario_editar = None

    # ===== CONSTRUIR TABLA CON ANCHO FIJO =====
    num_labs = len(labs_keys)
    # ===== ANCHO FIJO EN PÍXELES =====
    ancho_columna = "150px"
    
    html = f"""
    <div style="max-height: 550px; overflow: auto; border: 1px solid #ddd; border-radius: 5px;">
    <table style="width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 0.8rem; table-layout: fixed;">
    <thead>
    <tr>
        <th style="position: sticky; top: 0; background-color: #f0f0f0; z-index: 10; border:1px solid #ddd; padding:8px; text-align:center; font-weight:bold; width:{ancho_columna}; min-width:{ancho_columna};">Hora</th>
    """

    for lab in labs_keys:
        html += f"""
        <th style="position: sticky; top: 0; background-color: #f0f0f0; z-index: 10; border:1px solid #ddd; padding:8px; text-align:center; font-weight:bold; width:{ancho_columna}; min-width:{ancho_columna}; word-wrap:break-word; font-size:0.75rem;">{LABS_NAMES_HORARIO[lab]}</th>
        """

    html += "</tr></thead><tbody>"

    for hora in HORAS:
        html += f"<tr><td style='border:1px solid #ddd; padding:8px; font-weight:bold; text-align:center; background-color:#f9f9f9; width:{ancho_columna}; min-width:{ancho_columna};'>{hora}</td>"
        for lab in labs_keys:
            celda = hf.get_horario_celda(dia_seleccionado, hora, lab)
            
            if celda and celda["asignatura"]:
                carrera = celda.get("carrera", "")
                color_fondo = colores_carrera.get(carrera, "#F0F0F0")
                
                texto = f"""
                    <strong>{celda['asignatura']}</strong><br>
                    {carrera}<br>
                    <span style='font-size:0.7rem;'>
                        Monitor: {celda['monitor']}<br>
                        Prof: {celda['profesor']}
                    </span>
                """
                
                html += f"""
                <td style='
                    border:1px solid #ddd; 
                    padding:6px; 
                    background-color:{color_fondo};
                    text-align:center;
                    vertical-align:middle;
                    width:{ancho_columna};
                    min-width:{ancho_columna};
                    word-wrap:break-word;
                    font-size:0.75rem;
                '>
                    {texto}
                </td>
                """
            else:
                html += f"""
                <td style='
                    border:1px solid #ddd; 
                    padding:6px; 
                    background-color:#E8F5E9;
                    text-align:center;
                    vertical-align:middle;
                    width:{ancho_columna};
                    min-width:{ancho_columna};
                    word-wrap:break-word;
                    font-size:0.75rem;
                '>
                    🟢 Libre
                </td>
                """
        html += "</tr>"
    
    html += "</tbody></table></div>"
    
    st.components.v1.html(html, height=600, scrolling=False)

    # ===== FORMULARIO DE EDICIÓN =====
    st.divider()
    st.subheader("✏️ Editar una celda")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        lab_editar = st.selectbox(
            "Laboratorio",
            labs_keys,
            format_func=lambda x: LABS_NAMES_HORARIO[x],
            key="horario_editar_lab"
        )
    with col2:
        hora_editar = st.selectbox(
            "Hora",
            HORAS,
            key="horario_editar_hora"
        )
    with col3:
        st.write("")
        st.write("")
        if st.button("📝 Editar celda", key="horario_editar_btn", use_container_width=True):
            celda = hf.get_horario_celda(dia_seleccionado, hora_editar, lab_editar)
            st.session_state.horario_editar = {
                "dia": dia_seleccionado,
                "hora": hora_editar,
                "laboratorio": lab_editar,
                "datos": celda
            }
            st.rerun()

    # ===== FORMULARIO INLINE =====
    if st.session_state.horario_editar is not None:
        datos_edit = st.session_state.horario_editar
        dia = datos_edit["dia"]
        hora = datos_edit["hora"]
        lab = datos_edit["laboratorio"]
        datos = datos_edit["datos"] or {}

        st.subheader("📝 Modificar información de la celda")
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
            if st.button("💾 Guardar cambios", use_container_width=True):
                if asignatura.strip():
                    hf.set_horario_celda(dia, hora, lab, asignatura, carrera, monitor, profesor)
                else:
                    hf.delete_horario_celda(dia, hora, lab)
                st.session_state.horario_editar = None
                st.rerun()
        with col2:
            if st.button("🗑️ Eliminar", use_container_width=True):
                hf.delete_horario_celda(dia, hora, lab)
                st.session_state.horario_editar = None
                st.rerun()
        with col3:
            if st.button("❌ Cancelar", use_container_width=True):
                st.session_state.horario_editar = None
                st.rerun()
# ============================================================
#  4. GESTIÓN DE MULTAS (DEUDORES)
# ============================================================

def mostrar_formulario_agregar_multa(codigo):
    """
    Muestra el formulario para agregar una nueva multa a un estudiante.
    """
    st.subheader("➕ Agregar nueva multa")
    with st.form(key=f"form_agregar_{codigo}"):
        col1, col2 = st.columns(2)
        with col1:
            fecha_multa = st.date_input("Fecha de multa", datetime.now().date())
            tecnico_asigna = st.selectbox(
                "Técnico que asigna", 
                TECNICOS,
                key=f"asigna_{codigo}"
            )
        with col2:
            motivo = st.text_area("Motivo", height=80)
            sancion = st.text_input("Sanción")
        
        if st.form_submit_button("💾 Guardar multa"):
            if not motivo:
                st.error("❌ El motivo es obligatorio")
            else:
                multas.agregar_multa(
                    codigo, 
                    fecha_multa.strftime("%Y-%m-%d"), 
                    motivo, 
                    sancion, 
                    tecnico_asigna
                )
                st.success("✅ Multa agregada correctamente")
                st.rerun()


def mostrar_perfil_estudiante(codigo):
    """
    Muestra el perfil completo de un estudiante en formato compacto.
    Optimizado para reducir reruns innecesarios.
    """
    estudiante = db.ejecutar("SELECT nombres, proyecto FROM estudiantes WHERE codigo=?", (codigo,), fetch=True)
    if estudiante:
        nombre, carrera = estudiante[0]
        st.subheader(f"👤 {nombre}")
        st.write(f"**Código:** {codigo}")
        st.write(f"**Carrera:** {carrera if carrera else 'No registrada'}")
    else:
        st.warning("⚠️ Estudiante no encontrado en la tabla de estudiantes.")
        return
    
    df_multas = multas.obtener_multas_estudiante(codigo)
    if df_multas.empty:
        st.info("📭 No hay multas registradas para este estudiante.")
        mostrar_formulario_agregar_multa(codigo)
        return
    
    df_activas = df_multas[df_multas['pagado'] == 'NO']
    df_pagadas = df_multas[df_multas['pagado'] == 'SI']

    # ===== MULTAS ACTIVAS =====
    if not df_activas.empty:
        st.subheader(f"🔴 Multas activas ({len(df_activas)})")
        
        for idx, (_, m) in enumerate(df_activas.iterrows()):
            # Usar un container para cada multa
            with st.container():
                col1, col2, col3 = st.columns([2, 1.2, 0.5])
                
                # Columna 1: Información de la multa
                with col1:
                    st.write(f"**📅 {m['fecha_multa']}**")
                    st.write(f"📝 {m['motivo'] if m['motivo'] else 'Sin motivo'}")
                    if m['sancion']:
                        st.write(f"⚖️ Sanción: {m['sancion']}")
                    st.caption(f"👤 Asignada por: {m['tecnico_asigna']}")
                
                # Columna 2: Botones de acción
                with col2:
                    # Botón Pagar - usar session_state para controlar el modal
                    key_pagar = f"pagar_modal_{m['id']}"
                    if st.button(f"💰 Pagar", key=f"pagar_btn_{m['id']}", use_container_width=True):
                        st.session_state[key_pagar] = not st.session_state.get(key_pagar, False)
                        st.rerun()
                    
                    # Botón Modificar
                    key_modificar = f"modificar_modal_{m['id']}"
                    if st.button(f"✏️ Modificar", key=f"modificar_btn_{m['id']}", use_container_width=True):
                        st.session_state[key_modificar] = not st.session_state.get(key_modificar, False)
                        st.rerun()
                
                # Columna 3: Botón Eliminar
                with col3:
                    key_eliminar = f"eliminar_modal_{m['id']}"
                    if st.button(f"🗑️", key=f"eliminar_btn_{m['id']}", use_container_width=True):
                        st.session_state[key_eliminar] = not st.session_state.get(key_eliminar, False)
                        st.rerun()
                
                # ===== MODAL PAGAR =====
                if st.session_state.get(f"pagar_modal_{m['id']}", False):
                    with st.expander(f"💰 Pagar multa", expanded=True):
                        st.write(f"**Motivo:** {m['motivo']}")
                        if m['sancion']:
                            st.write(f"**Sanción:** {m['sancion']}")
                        
                        tecnico_recibe = st.selectbox(
                            "Técnico que recibe el pago", 
                            TECNICOS, 
                            key=f"tecnico_pago_{m['id']}"
                        )
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button(f"✅ Confirmar", key=f"confirmar_pago_{m['id']}"):
                                multas.pagar_multa(m['id'], tecnico_recibe)
                                st.session_state[f"pagar_modal_{m['id']}"] = False
                                st.rerun()
                        with col_b:
                            if st.button(f"❌ Cancelar", key=f"cancelar_pago_{m['id']}"):
                                st.session_state[f"pagar_modal_{m['id']}"] = False
                                st.rerun()
                
                # ===== MODAL MODIFICAR =====
                if st.session_state.get(f"modificar_modal_{m['id']}", False):
                    with st.expander(f"✏️ Modificar multa", expanded=True):
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
                            if st.button(f"💾 Guardar", key=f"guardar_edit_{m['id']}"):
                                db.ejecutar(
                                    "UPDATE multas SET motivo = ?, sancion = ? WHERE id = ?",
                                    (nuevo_motivo, nueva_sancion, m['id'])
                                )
                                st.session_state[f"modificar_modal_{m['id']}"] = False
                                st.rerun()
                        with col_b:
                            if st.button(f"❌ Cancelar", key=f"cancelar_edit_{m['id']}"):
                                st.session_state[f"modificar_modal_{m['id']}"] = False
                                st.rerun()
                
                # ===== MODAL ELIMINAR =====
                if st.session_state.get(f"eliminar_modal_{m['id']}", False):
                    with st.expander(f"⚠️ Eliminar multa", expanded=True):
                        st.warning(f"¿Estás seguro de eliminar esta multa?")
                        st.write(f"**Motivo:** {m['motivo']}")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button(f"✅ Sí", key=f"confirmar_eliminar_{m['id']}"):
                                multas.eliminar_multa(m['id'])
                                st.session_state[f"eliminar_modal_{m['id']}"] = False
                                st.rerun()
                        with col_b:
                            if st.button(f"❌ No", key=f"cancelar_eliminar_{m['id']}"):
                                st.session_state[f"eliminar_modal_{m['id']}"] = False
                                st.rerun()
                
                st.divider()
    else:
        st.info("✅ No hay multas activas.")

    # ===== HISTORIAL DE MULTAS PAGADAS =====
    if not df_pagadas.empty:
        with st.expander(f"📜 Historial de multas pagadas ({len(df_pagadas)})", expanded=False):
            for _, m in df_pagadas.iterrows():
                st.write(f"**📅 {m['fecha_multa']}** → Pagado: {m['fecha_pago']}")
                st.write(f"📝 {m['motivo']}")
                if m['sancion']:
                    st.write(f"⚖️ Sanción: {m['sancion']}")
                st.caption(f"👤 Recibido por: {m['tecnico_recibe']}")
                st.divider()

    # ===== AGREGAR NUEVA MULTA =====
    mostrar_formulario_agregar_multa(codigo)
def mostrar_deudores():
    st.subheader("💰 Gestión de Deudores")
    st.caption("Estudiantes con multas activas (pagado = 'NO'). Usa el buscador para encontrar cualquier estudiante.")

    search_term = st.text_input("🔍 Buscar por código o nombre", 
                                placeholder="Ej: 20211005067 o 'Juan'", 
                                key="deudor_search")

    df_deudores = multas.obtener_deudores()

    if df_deudores.empty and not search_term:
        st.info("🎉 No hay estudiantes con multas activas.")
        return

    if search_term:
        df_filtrado = df_deudores[
            df_deudores['codigo_estudiante'].str.contains(search_term, case=False, na=False) |
            df_deudores['nombres'].str.contains(search_term, case=False, na=False)
        ]
    else:
        df_filtrado = df_deudores

    # ===== MOSTRAR TABLA DE DEUDORES (SOLO RESUMEN - ACTIVOS) =====
    if not df_filtrado.empty:
        st.subheader("📋 Lista de deudores")
        st.dataframe(
            df_filtrado[['codigo_estudiante', 'nombres', 'carrera', 'numero_multas']],
            column_config={
                "codigo_estudiante": "Código",
                "nombres": "Nombre",
                "carrera": "Carrera",
                "numero_multas": "N° Multas"
            },
            use_container_width=True,
            hide_index=True
        )
        
        # ===== BOTÓN PARA DESCARGAR REPORTE DETALLADO =====
        st.divider()
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader("📊 Reporte detallado de multas")
            st.caption("Descarga un CSV con TODAS las multas (activas y pagadas) con todos los detalles.")
        with col2:
            # ===== GENERAR CSV CON TODAS LAS MULTAS (ACTIVAS Y PAGADAS) =====
            query_detalle = """
                SELECT 
                    m.codigo_estudiante,
                    e.nombres,
                    e.proyecto as carrera,
                    m.fecha_multa,
                    m.motivo,
                    m.sancion,
                    m.tecnico_asigna,
                    m.tecnico_recibe,
                    m.pagado
                FROM multas m
                LEFT JOIN estudiantes e ON m.codigo_estudiante = e.codigo
                ORDER BY e.nombres, m.fecha_multa DESC
            """
            df_detalle = db.fetch_df(query_detalle)
            
            if not df_detalle.empty:
                csv_data = df_detalle.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 Descargar CSV",
                    data=csv_data,
                    file_name=f"reporte_multas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="descargar_deudores_detalle",
                    use_container_width=True
                )

    # ===== RESTO DEL CÓDIGO EXISTENTE (búsqueda y perfiles) =====
    if search_term and df_filtrado.empty:
        st.info("🔍 El estudiante no tiene multas activas. Buscando en la base de datos de estudiantes...")
        df_estudiantes = multas.buscar_estudiantes(search_term)
        
        if df_estudiantes.empty:
            st.warning("⚠️ No se encontró ningún estudiante con ese código o nombre.")
            with st.expander("➕ Registrar nuevo estudiante"):
                nuevo_codigo = st.text_input("Código del estudiante *", key="nuevo_codigo")
                nuevo_nombre = st.text_input("Nombre completo *", key="nuevo_nombre")
                nuevo_proyecto = st.text_input("Carrera/Proyecto", key="nuevo_proyecto")
                if st.button("📥 Registrar estudiante", key="registrar_nuevo"):
                    if nuevo_codigo and nuevo_nombre:
                        db.ejecutar("INSERT INTO estudiantes (codigo, nombres, proyecto) VALUES (?, ?, ?)",
                                    (nuevo_codigo, nuevo_nombre, nuevo_proyecto))
                        st.success(f"✅ Estudiante {nuevo_nombre} registrado. Ahora puedes agregar una multa.")
                        st.rerun()
                    else:
                        st.error("❌ Código y nombre son obligatorios.")
        else:
            st.subheader("📋 Estudiantes encontrados (sin multas activas)")
            for _, row in df_estudiantes.iterrows():
                with st.expander(f"👤 {row['nombres']} ({row['codigo']}) - {row['multas_activas']} multas activas", expanded=False):
                    mostrar_perfil_estudiante(row['codigo'])

    elif search_term and len(df_filtrado) == 1:
        row = df_filtrado.iloc[0]
        codigo = row['codigo_estudiante']
        with st.expander(f"👤 {row['nombres']} ({codigo}) - Detalle completo", expanded=True):
            mostrar_perfil_estudiante(codigo)
    
    elif search_term and len(df_filtrado) > 1:
        st.info(f"🔍 Se encontraron {len(df_filtrado)} estudiantes con multas activas.")
        for _, row in df_filtrado.iterrows():
            codigo = row['codigo_estudiante']
            if st.button(f"Ver historial de {row['nombres']}", key=f"btn_historial_{codigo}"):
                with st.expander(f"👤 {row['nombres']} ({codigo})", expanded=True):
                    mostrar_perfil_estudiante(codigo)
    else:
        if df_deudores.empty:
            st.info("🎉 No hay deudores. Usa el buscador para gestionar multas de estudiantes específicos.")
        else:
            st.caption("💡 Usa el buscador para ver el historial completo de un estudiante.")