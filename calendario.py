import streamlit as st
from datetime import datetime, timedelta
from constants import LABORATORIOS, LABS_NAMES, DIAS, HORAS, TECNICOS, LABS_ORDEN
from utils import parse_fecha_a_espanol, formatear_fecha_espanol
import reservas as res
import horario_fijo as hf
import estudiantes as est
import database as db
import multas
from ui_components import render_editor_asistencias, render_eliminar_reserva

# ==================== FUNCIONES DE OCUPACIÓN ====================

def get_ocupados(lab, fecha, hora):
    # 1. Contar reservas de bancos individuales (banco > 0, excluyendo profesores con asiste='No')
    r = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                        WHERE laboratorio=? AND fecha=? AND hora=? 
                        AND activo=1 
                        AND (asiste != 'No' OR asiste IS NULL OR asiste = '')
                        AND banco > 0
                        AND NOT (codigo='PROFESOR' AND asiste='No')""", 
                     (lab, fecha, hora), fetch=True)
    reservas = r[0][0] if r else 0
    
    # 2. Verificar reserva de sala completa (banco = 0)
    r_completa = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                                WHERE laboratorio=? AND fecha=? AND hora=? 
                                AND activo=1 
                                AND (asiste != 'No' OR asiste IS NULL OR asiste = '')
                                AND banco = 0
                                AND NOT (codigo='PROFESOR' AND asiste='No')""", 
                             (lab, fecha, hora), fetch=True)
    tiene_reserva_completa = r_completa[0][0] > 0 if r_completa else False
    
    if tiene_reserva_completa:
        return LABORATORIOS.get(lab, 0)
    
    if reservas > 0:
        return reservas
    
    # ===== Verificar si hay reserva de profesor con asiste='No' =====
    r_profesor_no = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                                WHERE laboratorio=? AND fecha=? AND hora=? 
                                AND codigo='PROFESOR' AND asiste='No' AND activo=1""",
                                (lab, fecha, hora), fetch=True)
    if r_profesor_no[0][0] > 0:
        return 0  # Liberar el espacio, ignorar horario fijo
    
    # 3. Verificar horario fijo (solo si no hay reservas y no hay profesor con asiste='No')
    dia_es = parse_fecha_a_espanol(fecha)
    horario = hf.get_horario_celda(dia_es, hora, lab)
    
    if horario and horario["asignatura"] and "adicional" in horario["asignatura"].lower():
        return 0
    
    if horario and horario["asignatura"]:
        return LABORATORIOS.get(lab, 0)
    
    return 0

def get_bancos_ocupados(lab, fecha, hora):
    # Excluir reservas de profesor con asiste='No'
    r = db.ejecutar("""SELECT banco FROM reservas 
                        WHERE laboratorio=? AND fecha=? AND hora=? 
                        AND activo=1 
                        AND (asiste != 'No' OR asiste IS NULL OR asiste = '')
                        AND banco > 0
                        AND NOT (codigo='PROFESOR' AND asiste='No')""", 
                     (lab, fecha, hora), fetch=True)
    bancos_reservados = [x[0] for x in r]
    
    r_completa = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                                WHERE laboratorio=? AND fecha=? AND hora=? 
                                AND activo=1 
                                AND (asiste != 'No' OR asiste IS NULL OR asiste = '')
                                AND banco = 0
                                AND NOT (codigo='PROFESOR' AND asiste='No')""", 
                             (lab, fecha, hora), fetch=True)
    tiene_reserva_completa = r_completa[0][0] > 0 if r_completa else False
    
    if tiene_reserva_completa:
        total = LABORATORIOS.get(lab, 0)
        return list(range(1, total + 1))
    
    if bancos_reservados:
        return bancos_reservados
    
    # Verificar si hay profesor con asiste='No' (para liberar bancos)
    r_profesor_no = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                                WHERE laboratorio=? AND fecha=? AND hora=? 
                                AND codigo='PROFESOR' AND asiste='No' AND activo=1""",
                                (lab, fecha, hora), fetch=True)
    if r_profesor_no[0][0] > 0:
        return []  # No hay bancos ocupados
    
    # Verificar horario fijo (si no hay reservas ni profesor con asiste='No')
    dia_es = parse_fecha_a_espanol(fecha)
    horario = hf.get_horario_celda(dia_es, hora, lab)
    
    if horario and horario["asignatura"] and "adicional" in horario["asignatura"].lower():
        return []
    
    if horario and horario["asignatura"]:
        total = LABORATORIOS.get(lab, 0)
        return list(range(1, total + 1))
    
    return []

# ==================== CALENDARIO INTERACTIVO ====================

def mostrar_calendario_interactivo(dia_seleccionado):
    """
    Muestra la ocupación de TODOS los laboratorios para un día específico.
    El día se selecciona mediante un radio button en app.py.
    """
    st.subheader(f"📅 Ocupación para {dia_seleccionado}")
    hoy = datetime.now().date()
    lunes = st.session_state.labs_semana_inicio
    
    # Obtener el índice del día seleccionado (0=Lunes, 5=Sábado)
    idx = DIAS.index(dia_seleccionado)
    fecha = lunes + timedelta(days=idx)
    fecha_str = fecha.strftime("%Y-%m-%d")
    es_pasado = fecha < hoy
    
    # Cabecera: horas + laboratorios
    cols = st.columns([1] + [1] * len(LABS_ORDEN))
    with cols[0]:
        st.write("**Hora**")
    for i, lab in enumerate(LABS_ORDEN):
        with cols[i+1]:
            st.write(f"**{LABS_NAMES.get(lab, lab)}**")
    
    # Filas: cada hora
    for hora in HORAS:
        cols = st.columns([1] + [1] * len(LABS_ORDEN))
        with cols[0]:
            st.write(hora)
        
        for i, lab in enumerate(LABS_ORDEN):
            total = LABORATORIOS[lab]
            ocupados = get_ocupados(lab, fecha_str, hora)
            disponibles = total - ocupados
            
            with cols[i+1]:
                if es_pasado:
                    st.write(f"🔒 {ocupados}/{total}")
                else:
                    # ==== Verificar reserva de profesor con asistencia ====
                    r_profesor_si = db.ejecutar("""SELECT nombres, proyecto FROM reservas 
                                                WHERE laboratorio=? AND fecha=? AND hora=? 
                                                AND codigo='PROFESOR' AND asiste='Si' AND activo=1
                                                LIMIT 1""",
                                                (lab, fecha_str, hora), fetch=True)
                    tiene_profesor_si = len(r_profesor_si) > 0 if r_profesor_si else False
                    profesor_nombre = r_profesor_si[0][0] if tiene_profesor_si else ""
                    profesor_asignatura = r_profesor_si[0][1] if tiene_profesor_si else ""
                    
                    # Verificar horario fijo
                    horario = hf.get_horario_celda(dia_seleccionado, hora, lab)
                    tiene_asignatura = horario and horario["asignatura"]
                    es_adicional = horario and horario["asignatura"] and "adicional" in horario["asignatura"].lower()
                    
                    if es_adicional:
                        tiene_asignatura = False
                    
                    # Reservas activas (excluyendo profesor con asistencia)
                    r = db.ejecutar("""SELECT COUNT(*) FROM reservas 
                                        WHERE laboratorio=? AND fecha=? AND hora=? 
                                        AND activo=1 
                                        AND (asiste != 'No' OR asiste IS NULL OR asiste = '')
                                        AND codigo != 'PROFESOR'""", 
                                     (lab, fecha_str, hora), fetch=True)
                    reservas_activas = r[0][0] > 0
                    
                    # Construir etiqueta del botón
                    if tiene_profesor_si:
                        label = f"🟢 {profesor_asignatura}\n{profesor_nombre}"
                    elif es_adicional:
                        if reservas_activas or ocupados > 0:
                            label = f"📚 Adicional ({ocupados}/{total})"
                        else:
                            label = "📚 Adicional"
                    elif disponibles > 0:
                        label = f"{ocupados}/{total}"
                        if tiene_asignatura and not reservas_activas:
                            label = f"📚 {horario['asignatura']}"
                    else:
                        if tiene_asignatura and not reservas_activas:
                            label = f"🔴 {horario['asignatura']}"
                        else:
                            label = f"🔴 {ocupados}/{total}"
                    
                    # Botón de celda
                    if st.button(label, key=f"celda_{lab}_{fecha_str}_{hora}"):
                        if tiene_profesor_si:
                            st.session_state.labs_celda_seleccionada = {
                                "fecha": fecha_str,
                                "hora": hora,
                                "laboratorio": lab,
                                "ocupados": ocupados,
                                "total": total,
                                "disponibles": 0,
                                "bancos_disponibles": [],
                                "es_asignatura": True,
                                "asignatura_info": horario,
                                "es_profesor_asistio": True,
                                "profesor_data": {
                                    "nombre": profesor_nombre,
                                    "asignatura": profesor_asignatura
                                }
                            }
                        elif tiene_asignatura and not reservas_activas and disponibles == 0:
                            st.session_state.labs_celda_seleccionada = {
                                "fecha": fecha_str,
                                "hora": hora,
                                "laboratorio": lab,
                                "ocupados": ocupados,
                                "total": total,
                                "disponibles": 0,
                                "bancos_disponibles": [],
                                "es_asignatura": True,
                                "asignatura_info": horario
                            }
                        else:
                            st.session_state.labs_celda_seleccionada = {
                                "fecha": fecha_str,
                                "hora": hora,
                                "laboratorio": lab,
                                "ocupados": ocupados,
                                "total": total,
                                "disponibles": disponibles,
                                "bancos_disponibles": [b for b in range(1, total+1) if b not in get_bancos_ocupados(lab, fecha_str, hora)],
                                "es_asignatura": False
                            }
                        st.rerun()
    
    st.caption("🔒 = Fecha pasada | 🔴 = Completo | 🟢 = Profesor asistió | 📚 = Ocupado por asignatura | 📚 Adicional = Libre para reservas")

# ==================== DETALLE DE CELDA ====================

def mostrar_detalle_celda():
    if "labs_celda_seleccionada" in st.session_state:
        data = st.session_state.labs_celda_seleccionada
        fecha_str = data["fecha"]
        hora = data["hora"]
        lab = data["laboratorio"]
        ocupados = data["ocupados"]
        disponibles = data["disponibles"]
        total = data["total"]
        es_asignatura = data.get("es_asignatura", False)
        asignatura_info = data.get("asignatura_info", None)
        es_profesor_asistio = data.get("es_profesor_asistio", False)
        profesor_data = data.get("profesor_data", None)
        
        df = res.get_reservas_fecha_lab_hora(fecha_str, lab, hora)
        
        titulo = f"📋 Detalle - {LABS_NAMES[lab]} {hora} {formatear_fecha_espanol(fecha_str)}"
        
        # Ajustar título según el caso
        if es_profesor_asistio and profesor_data:
            titulo += f" | ✅ {profesor_data.get('asignatura', 'Clase')} - {profesor_data.get('nombre', 'Profesor')}"
        elif es_asignatura and asignatura_info:
            titulo += f" | Asignatura: {asignatura_info['asignatura']}"
        else:
            titulo += f" (Ocupados: {ocupados}/{total})"
        
        with st.expander(titulo, expanded=True):
            # Si es profesor con asistencia, mostrar mensaje especial
            if es_profesor_asistio and profesor_data:
                st.success(f"✅ **Asistencia registrada para el profesor:** {profesor_data.get('nombre', 'Profesor')}")
                st.info(f"**Asignatura/Motivo:** {profesor_data.get('asignatura', 'Clase')}")
                st.divider()
            
            if not df.empty:
                df_editor = df[['id', 'banco', 'codigo', 'nombres', 'proyecto', 'asiste']].copy()
                render_editor_asistencias(df_editor, f"detalle_{lab}_{fecha_str}_{hora}", lab)
                render_eliminar_reserva(df, f"eliminar_detalle_{lab}_{fecha_str}_{hora}")
            else:
                if es_profesor_asistio and profesor_data:
                    st.info("📋 No hay otras reservas en este bloque. El profesor ya registró su asistencia.")
                    st.divider()
                    st.subheader("RESERVA DOCENTE")
                    st.caption("Reserva TODO el laboratorio para un bloque completo (2 horas)")
                    
                    if st.button("📝 RESERVAR TODO EL ESPACIO", key=f"profesor_reservar_{lab}_{fecha_str}_{hora}", use_container_width=True):
                        st.session_state.labs_profesor_reserva = {
                            "fecha": fecha_str,
                            "hora": hora,
                            "laboratorio": lab
                        }
                        del st.session_state.labs_celda_seleccionada
                        st.rerun()
                        
                elif es_asignatura and asignatura_info:
                    if asignatura_info.get("carrera") == "Adicional":
                        st.info("📚 Espacio marcado como 'Adicional' - disponible para reservas.")
                    else:
                        st.warning(f"🔴 Este espacio está ocupado por la asignatura **{asignatura_info['asignatura']}** ({asignatura_info['carrera']})")
                        st.info(f"Monitor: {asignatura_info['monitor']} | Profesor: {asignatura_info['profesor']}")
                        st.write("No hay reservas en este bloque.")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("📝 Reservar excepcionalmente (habilitar espacio)", key=f"reservar_excepcional_{lab}_{fecha_str}_{hora}"):
                                bancos_disponibles = list(range(1, total+1))
                                st.session_state.labs_reserva_celda = {
                                    "fecha": fecha_str,
                                    "hora": hora,
                                    "laboratorio": lab,
                                    "bancos_disponibles": bancos_disponibles
                                }
                                del st.session_state.labs_celda_seleccionada
                                st.rerun()
                        with col2:
                            if st.button("✅ Marcar asistencia del docente", key=f"asistencia_docente_{lab}_{fecha_str}_{hora}"):
                                st.session_state.asistencia_docente = {
                                    "fecha": fecha_str,
                                    "hora": hora,
                                    "laboratorio": lab,
                                    "asignatura_info": asignatura_info
                                }
                                del st.session_state.labs_celda_seleccionada
                                st.rerun()
                else:
                    st.info("No hay reservas en este bloque.")
                    
                    st.divider()
                    st.subheader("RESERVA DOCENTE")
                    st.caption("Reserva TODO el laboratorio para un bloque completo (2 horas)")
                    
                    if st.button("📝 RESERVAR TODO EL ESPACIO", key=f"profesor_reservar_{lab}_{fecha_str}_{hora}", use_container_width=True):
                        st.session_state.labs_profesor_reserva = {
                            "fecha": fecha_str,
                            "hora": hora,
                            "laboratorio": lab
                        }
                        del st.session_state.labs_celda_seleccionada
                        st.rerun()
            
            # ===== FORMULARIO DE RESERVA INDIVIDUAL INLINE =====
            st.divider()
            
            if disponibles > 0 and not es_asignatura and not es_profesor_asistio:
                st.subheader("➕ Agregar reserva individual")
                st.caption(f"Bancos disponibles: {', '.join(map(str, data['bancos_disponibles']))}")
                
                # ===== Campo de código FUERA del formulario =====
                codigo_key = f"codigo_verificar_{lab}_{fecha_str}_{hora}"
                codigo = st.text_input(
                    "Código del estudiante *", 
                    key=codigo_key,
                    placeholder="Ingresa el código y presiona Enter para verificar"
                )
                
                # Verificar automáticamente cuando el código cambia (al presionar Enter)
                estudiante_info = None
                if codigo:
                    estudiante_info = est.buscar_estudiante(codigo)
                    if estudiante_info:
                        st.success(f"👤 **{estudiante_info[1]}**")
                        if estudiante_info[2]:
                            st.info(f"📚 {estudiante_info[2]}")
                        # Verificar multas activas
                        multas_texto = multas.obtener_texto_multas_activas(codigo)
                        if multas_texto:
                            st.error(f"⚠️ Multas activas:\n{multas_texto}")
                    else:
                        st.error("❌ Código no válido. Verifica el código ingresado.")
                
                # ===== Formulario de guardado (sin el campo código) =====
                with st.form(key=f"form_reserva_guardar_{lab}_{fecha_str}_{hora}"):
                    bancos_disponibles = data.get("bancos_disponibles", [])
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        banco = st.selectbox("Banco", bancos_disponibles, key=f"banco_{lab}_{fecha_str}_{hora}")
                    with col2:
                        tecnico = st.selectbox("Técnico", TECNICOS, key=f"tecnico_{lab}_{fecha_str}_{hora}")
                    
                    observaciones = st.text_area("Observaciones", key=f"obs_{lab}_{fecha_str}_{hora}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Guardar reserva", use_container_width=True):
                            # Validaciones
                            if not codigo:
                                st.error("❌ Primero ingresa un código de estudiante")
                            elif not estudiante_info:
                                st.error("❌ Código no válido. Verifica el código ingresado.")
                            else:
                                # Verificar si ya tiene reserva en este horario
                                if res.verificar_reserva_existente(codigo, fecha_str, hora, None):
                                    st.error("❌ Este estudiante ya tiene una reserva activa en esta fecha y hora en otro laboratorio.")
                                else:
                                    # Preparar datos
                                    datos_reserva = (
                                        fecha_str,
                                        hora,
                                        lab,
                                        banco,
                                        codigo,
                                        estudiante_info[1],
                                        estudiante_info[2] if estudiante_info[2] else "",
                                        "",  # asiste (pendiente)
                                        observaciones,
                                        tecnico
                                    )
                                    if res.guardar_reserva(datos_reserva):
                                        st.success("✅ Reserva guardada correctamente")
                                        # Limpiar el campo de código
                                        if codigo_key in st.session_state:
                                            del st.session_state[codigo_key]
                                        del st.session_state.labs_celda_seleccionada
                                        st.rerun()
                    with col2:
                        if st.form_submit_button("❌ Cancelar", use_container_width=True):
                            # Limpiar el campo de código
                            if codigo_key in st.session_state:
                                del st.session_state[codigo_key]
                            del st.session_state.labs_celda_seleccionada
                            st.rerun()
            else:
                if es_asignatura:
                    st.info("💡 Para reservar en este bloque, usa el botón 'Reservar excepcionalmente' arriba.")
                elif es_profesor_asistio:
                    st.info("💡 El profesor ya registró asistencia en este bloque. No se permiten reservas individuales.")
                else:
                    st.info("❌ No hay bancos disponibles en este bloque.")
            
            if st.button("Cerrar", key=f"cerrar_detalle_{lab}_{fecha_str}_{hora}"):
                del st.session_state.labs_celda_seleccionada
                st.rerun()

# ==================== FORMULARIO DE RESERVA PARA PROFESOR ====================

def mostrar_formulario_reserva_profesor():
    """
    Muestra un formulario inline para que un profesor reserve un laboratorio completo.
    """
    if "labs_profesor_reserva" not in st.session_state:
        return
    
    data = st.session_state.labs_profesor_reserva
    fecha_str = data["fecha"]
    hora = data["hora"]
    lab = data["laboratorio"]
    
    if datetime.strptime(fecha_str, "%Y-%m-%d").date() < datetime.now().date():
        st.error("❌ No se pueden hacer reservas en fechas pasadas.")
        if st.button("Cerrar", key="profesor_cerrar_error"):
            del st.session_state.labs_profesor_reserva
            st.rerun()
        return
    
    st.divider()
    st.subheader("👨‍🏫 Reserva de laboratorio completo")
    st.write(f"**Laboratorio:** {LABS_NAMES[lab]}")
    st.write(f"**Fecha:** {formatear_fecha_espanol(fecha_str)}")
    st.write(f"**Hora:** {hora}")
    st.divider()
    
    with st.form(key=f"form_profesor_{lab}_{fecha_str}_{hora}"):
        col1, col2 = st.columns(2)
        with col1:
            motivo = st.text_input("Motivo de la reserva *", placeholder="Ej: Examen, clase especial...")
            nombre_profesor = st.text_input("Nombre del profesor *", placeholder="Ej: Juan Pérez")
        with col2:
            tecnico = st.selectbox("Técnico responsable", TECNICOS)
        
        st.caption("⚠️ Esta reserva ocupará TODO el laboratorio por 2 horas.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("✅ Confirmar reserva", use_container_width=True):
                if not motivo or not nombre_profesor:
                    st.error("❌ Motivo y nombre del profesor son obligatorios")
                else:
                    if res.guardar_reserva_profesor(fecha_str, hora, lab, motivo, nombre_profesor, tecnico):
                        st.success(f"✅ ¡Laboratorio completo reservado para: {motivo}!")
                        del st.session_state.labs_profesor_reserva
                        st.rerun()
                    else:
                        st.error("❌ No se pudo reservar. El laboratorio ya tiene reservas en este bloque.")
        with col2:
            if st.form_submit_button("❌ Cancelar", use_container_width=True):
                del st.session_state.labs_profesor_reserva
                st.rerun()

# ==================== FORMULARIO DE ASISTENCIA DOCENTE ====================

def mostrar_formulario_asistencia_docente():
    """
    Muestra el formulario inline para registrar asistencia de docente desde horario fijo.
    """
    if "asistencia_docente" not in st.session_state:
        return
    
    data = st.session_state.asistencia_docente
    fecha_str = data["fecha"]
    hora = data["hora"]
    lab = data["laboratorio"]
    info = data["asignatura_info"]
    
    st.divider()
    st.subheader("📝 Registrar asistencia del docente")
    st.write(f"**Laboratorio:** {LABS_NAMES[lab]}")
    st.write(f"**Fecha:** {formatear_fecha_espanol(fecha_str)}")
    st.write(f"**Hora:** {hora}")
    st.write(f"**Asignatura:** {info['asignatura']}")
    st.write(f"**Docente (horario fijo):** {info['profesor']}")
    st.divider()
    
    estado = st.radio("Estado", ["Asistió", "No asistió"], horizontal=True, key="asistencia_estado")
    tecnico = st.selectbox("Técnico que registra", TECNICOS, key="asistencia_tecnico")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Confirmar asistencia", key="confirmar_asistencia", use_container_width=True):
            estado_db = "Si" if estado == "Asistió" else "No"
            res.registrar_asistencia_docente(
                fecha_str, hora, lab, 
                info['profesor'], 
                info['asignatura'], 
                estado_db, 
                tecnico
            )
            st.success(f"✅ Asistencia registrada: {estado}")
            del st.session_state.asistencia_docente
            st.rerun()
    with col2:
        if st.button("❌ Cancelar", key="cancelar_asistencia", use_container_width=True):
            del st.session_state.asistencia_docente
            st.rerun()