import streamlit as st
from datetime import datetime, timedelta
from collections import defaultdict
from constants import LABORATORIOS, LABS_NAMES, DIAS, HORAS, OPCIONES_TECNICOS, es_tecnico_valido, LABS_ORDEN
from utils import parse_fecha_a_espanol, formatear_fecha_espanol
import reservas as res
import horario_fijo as hf
import estudiantes as est
import database as db
import multas
from ui_components import render_editor_asistencias

# ==================== FUNCIONES DE OCUPACIÃ“N ====================

def _es_bloque_reservable(asignatura, carrera=None):
    tipo = str(carrera or "").strip().casefold()
    if tipo in ("adicional", "práctica libre", "practica libre"):
        return True
    texto = str(asignatura or "").strip().casefold()
    return "adicional" in texto or "práctica libre" in texto or "practica libre" in texto


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
    
    if horario and _es_bloque_reservable(horario.get("asignatura"), horario.get("carrera")):
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
    
    if horario and _es_bloque_reservable(horario.get("asignatura"), horario.get("carrera")):
        return []
    
    if horario and horario["asignatura"]:
        total = LABORATORIOS.get(lab, 0)
        return list(range(1, total + 1))
    
    return []


def formatear_etiqueta_horario(horario):
    """
    Construye una etiqueta compacta con la informaciÃ³n del horario fijo.
    """
    if not horario or not horario.get("asignatura"):
        return ""

    asignatura = horario.get("asignatura", "").strip()
    carrera = horario.get("carrera", "").strip()
    profesor = horario.get("profesor", "").strip()

    partes = [asignatura]
    if carrera:
        partes.append(f"({carrera})")
    if profesor:
        partes.append(f"Prof: {profesor}")

    return "\n".join(partes)

# ==================== CALENDARIO INTERACTIVO ====================

def mostrar_calendario_interactivo(dia_seleccionado):
    """
    Muestra la ocupaciÃ³n de TODOS los laboratorios para un dÃ­a especÃ­fico.
    El dÃ­a se selecciona mediante un radio button en app.py.
    """
    st.markdown(
        """
        <style>
            div[data-testid="column"] div.stButton > button {
                width: 100% !important;
                height: 108px !important;
                border: 1px solid #d9d9d9 !important;
                border-radius: 4px !important;
                padding: 0.4rem !important;
                white-space: pre-line !important;
                line-height: 1.1 !important;
                text-align: center !important;
                font-size: 0.76rem !important;
                font-weight: 600 !important;
                color: #222 !important;
                background: #ffffff !important;
                box-shadow: none !important;
                overflow: hidden !important;
            }
            div[data-testid="column"] div.stButton > button:hover {
                border-color: #9aa0a6 !important;
                color: #222 !important;
                background: #fafafa !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.subheader(f" OcupaciÃ³n para {dia_seleccionado}")
    hoy = datetime.now().date()
    lunes = st.session_state.labs_semana_inicio
    
    # Obtener el Ã­ndice del dÃ­a seleccionado (0=Lunes, 5=SÃ¡bado)
    idx = DIAS.index(dia_seleccionado)
    fecha = lunes + timedelta(days=idx)
    fecha_str = fecha.strftime("%Y-%m-%d")
    es_pasado = fecha < hoy
    contexto_calendario = _build_contexto_calendario(dia_seleccionado, fecha_str)
    
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
                    st.button(
                        "No se puede reservar\nDÃ­a ya transcurrido",
                        key=f"bloqueado_{lab}_{fecha_str}_{hora}",
                        use_container_width=True,
                        disabled=True,
                    )
                else:
                    # ==== Verificar reserva de profesor con estado ====
                    r_profesor = db.ejecutar("""SELECT nombres, proyecto, asiste FROM reservas 
                                                WHERE laboratorio=? AND fecha=? AND hora=? 
                                                AND codigo='PROFESOR' AND activo=1
                                                AND asiste IS NOT NULL AND asiste != ''
                                                ORDER BY id DESC
                                                LIMIT 1""",
                                                (lab, fecha_str, hora), fetch=True)
                    tiene_profesor = len(r_profesor) > 0 if r_profesor else False
                    profesor_nombre = r_profesor[0][0] if tiene_profesor else ""
                    profesor_asignatura = r_profesor[0][1] if tiene_profesor else ""
                    estado_profesor = r_profesor[0][2] if tiene_profesor else ""
                    
                    # Verificar horario fijo
                    horario = hf.get_horario_celda(dia_seleccionado, hora, lab)
                    tiene_asignatura = horario and horario["asignatura"]
                    es_adicional = bool(horario and _es_bloque_reservable(horario.get("asignatura"), horario.get("carrera")))
                    
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

                    if tiene_profesor and estado_profesor == "Si":
                        label = f"AsistiÃ³\n{profesor_asignatura}\n{profesor_nombre}"
                        help_text = f"AsistiÃ³ | {profesor_asignatura} | {profesor_nombre}"
                    elif tiene_profesor and estado_profesor == "No":
                        label = f"No asistiÃ³\n{profesor_asignatura}\n{profesor_nombre}"
                        help_text = f"No asistiÃ³ | {profesor_asignatura} | {profesor_nombre}"
                    elif tiene_asignatura and not reservas_activas:
                        label = formatear_etiqueta_horario(horario)
                        help_text = label.replace("\n", " | ")
                    elif disponibles > 0:
                        label = f"Libre\n{ocupados}/{total}"
                        help_text = f"Libre | {ocupados}/{total}"
                    else:
                        label = f"Ocupado\n{ocupados}/{total}"
                        help_text = f"Ocupado | {ocupados}/{total}"

                    # BotÃ³n de celda
                    if st.button(
                        label,
                        key=f"celda_{lab}_{fecha_str}_{hora}",
                        use_container_width=True,
                        help=f"{LABS_NAMES.get(lab, lab)} - {hora} | {help_text}",
                    ):
                        if tiene_profesor and estado_profesor == "Si":
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
                                    "asignatura": profesor_asignatura,
                                    "estado": "Si"
                                }
                            }
                        elif tiene_profesor and estado_profesor == "No":
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
                                    "asignatura": profesor_asignatura,
                                    "estado": "No"
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
    
    st.caption(" = Fecha pasada |  = Completo |  = Profesor asistiÃ³ |  = Ocupado por asignatura |  Adicional = Libre para reservas")

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
        
        titulo = f" Detalle - {LABS_NAMES[lab]} {hora} {formatear_fecha_espanol(fecha_str)}"
        
        # Ajustar tÃ­tulo segÃºn el caso
        if es_profesor_asistio and profesor_data:
            titulo += f" |  {profesor_data.get('asignatura', 'Clase')} - {profesor_data.get('nombre', 'Profesor')}"
        elif es_asignatura and asignatura_info:
            titulo += f" | Asignatura: {asignatura_info['asignatura']}"
        else:
            titulo += f" (Ocupados: {ocupados}/{total})"
        
        with st.expander(titulo, expanded=True):
            # Si es profesor con asistencia, mostrar mensaje especial
            if es_profesor_asistio and profesor_data:
                st.success(f" **Asistencia registrada para el profesor:** {profesor_data.get('nombre', 'Profesor')}")
                st.info(f"**Asignatura/Motivo:** {profesor_data.get('asignatura', 'Clase')}")
                st.divider()
            
            if not df.empty:
                df_editor = df[['id', 'banco', 'codigo', 'nombres', 'proyecto', 'asiste']].copy()
                render_editor_asistencias(df_editor, f"detalle_{lab}_{fecha_str}_{hora}", lab)
            else:
                if es_profesor_asistio and profesor_data:
                    st.info(" No hay otras reservas en este bloque. El profesor ya registrÃ³ su asistencia.")
                    st.divider()
                    st.subheader("RESERVA DOCENTE")
                    st.caption("Reserva TODO el laboratorio para un bloque completo (2 horas)")

                    if st.button(" RESERVAR TODO EL ESPACIO", key=f"profesor_reservar_{lab}_{fecha_str}_{hora}", use_container_width=True):
                        st.session_state.labs_profesor_reserva = {
                            "fecha": fecha_str,
                            "hora": hora,
                            "laboratorio": lab,
                            "profesor_sugerido": profesor_nombre,
                        }
                        del st.session_state.labs_celda_seleccionada
                        st.rerun()

                elif es_asignatura and asignatura_info:
                    if asignatura_info.get("carrera") in ("Adicional", "Práctica Libre"):
                        st.info(" Espacio marcado como 'Adicional' - disponible para reservas.")
                    else:
                        st.warning(f" Este espacio estÃ¡ ocupado por la asignatura **{asignatura_info['asignatura']}** ({asignatura_info['carrera']})")
                        st.info(f"Monitor: {asignatura_info['monitor']} | Profesor: {asignatura_info['profesor']}")
                        st.write("No hay reservas en este bloque.")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(" Reservar excepcionalmente (habilitar espacio)", key=f"reservar_excepcional_{lab}_{fecha_str}_{hora}"):
                                bancos_disponibles = list(range(1, total+1))
                                st.session_state.labs_reserva_celda = {
                                    "fecha": fecha_str,
                                    "hora": hora,
                                    "laboratorio": lab,
                                    "bancos_disponibles": bancos_disponibles,
                                    "profesor_sugerido": asignatura_info.get("profesor", ""),
                                }
                                del st.session_state.labs_celda_seleccionada
                                st.rerun()
                        with col2:
                            if st.button(" Marcar asistencia del docente", key=f"asistencia_docente_{lab}_{fecha_str}_{hora}"):
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
                    
                    if st.button(" RESERVAR TODO EL ESPACIO", key=f"profesor_reservar_{lab}_{fecha_str}_{hora}", use_container_width=True):
                        st.session_state.labs_profesor_reserva = {
                            "fecha": fecha_str,
                            "hora": hora,
                            "laboratorio": lab,
                        }
                        del st.session_state.labs_celda_seleccionada
                        st.rerun()
            
            # ===== FORMULARIO DE RESERVA INDIVIDUAL INLINE =====
            st.divider()
            
            if disponibles > 0 and not es_asignatura and not es_profesor_asistio:
                st.subheader(" Agregar reserva individual")
                st.caption(f"Bancos disponibles: {', '.join(map(str, data['bancos_disponibles']))}")
                
                # ===== Campo de cÃ³digo FUERA del formulario =====
                codigo_key = f"codigo_verificar_{lab}_{fecha_str}_{hora}"
                codigo = st.text_input(
                    "CÃ³digo del estudiante *", 
                    key=codigo_key,
                    placeholder="Ingresa el cÃ³digo y presiona Enter para verificar"
                )
                
                # Verificar automÃ¡ticamente cuando el cÃ³digo cambia (al presionar Enter)
                estudiante_info = None
                if codigo:
                    estudiante_info = est.buscar_estudiante(codigo)
                    if estudiante_info:
                        # ===== CONTADOR DE RESERVAS DEL DÃA =====
                        reservas_hoy = est.contar_reservas_hoy(codigo)
                        hoy = datetime.now().date().strftime("%d/%m/%Y")
                        
                        st.success(f" **{estudiante_info[1]}**")
                        st.write(f" **Reservas de hoy ({hoy}):** {reservas_hoy}")
                        if estudiante_info[2]:
                            st.info(f" {estudiante_info[2]}")
                        # Verificar multas activas
                        multas_texto = multas.obtener_texto_multas_activas(codigo)
                        if multas_texto:
                            st.error(f" Multas activas:\n{multas_texto}")
                    else:
                        st.error(" CÃ³digo no vÃ¡lido. Verifica el cÃ³digo ingresado.")
                
                # ===== Formulario de guardado (sin el campo cÃ³digo) =====
                with st.form(key=f"form_reserva_guardar_{lab}_{fecha_str}_{hora}"):
                    bancos_disponibles = data.get("bancos_disponibles", [])
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        banco = st.selectbox("Banco", bancos_disponibles, key=f"banco_{lab}_{fecha_str}_{hora}")
                    with col2:
                        tecnico = st.selectbox("TÃ©cnico", OPCIONES_TECNICOS, index=0, key=f"tecnico_v2_{lab}_{fecha_str}_{hora}")
                    
                    observaciones = st.text_area("Observaciones", key=f"obs_{lab}_{fecha_str}_{hora}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button(" Guardar reserva", use_container_width=True):
                            # Validaciones
                            if not codigo:
                                st.error(" Primero ingresa un cÃ³digo de estudiante")
                            elif not estudiante_info:
                                st.error(" CÃ³digo no vÃ¡lido. Verifica el cÃ³digo ingresado.")
                            else:
                                # Verificar si ya tiene reserva en este horario
                                if res.verificar_reserva_existente(codigo, fecha_str, hora, None):
                                    st.error(" Este estudiante ya tiene una reserva activa en esta fecha y hora en otro laboratorio.")
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
                                        st.success(" Reserva guardada correctamente")
                                        # Limpiar el campo de cÃ³digo
                                        if codigo_key in st.session_state:
                                            del st.session_state[codigo_key]
                                        del st.session_state.labs_celda_seleccionada
                                        st.rerun()
                    with col2:
                        if st.form_submit_button(" Cancelar", use_container_width=True):
                            # Limpiar el campo de cÃ³digo
                            if codigo_key in st.session_state:
                                del st.session_state[codigo_key]
                            del st.session_state.labs_celda_seleccionada
                            st.rerun()
            else:
                if es_asignatura:
                    st.info(" Para reservar en este bloque, usa el botÃ³n 'Reservar excepcionalmente' arriba.")
                elif es_profesor_asistio:
                    st.info(" El profesor ya registrÃ³ asistencia en este bloque. No se permiten reservas individuales.")
                else:
                    st.info(" No hay bancos disponibles en este bloque.")
            
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
    profesor_sugerido = data.get("profesor_sugerido", "").strip()
    
    if datetime.strptime(fecha_str, "%Y-%m-%d").date() < datetime.now().date():
        st.error(" No se pueden hacer reservas en fechas pasadas.")
        if st.button("Cerrar", key="profesor_cerrar_error"):
            del st.session_state.labs_profesor_reserva
            st.rerun()
        return
    
    st.divider()
    st.subheader(" Reserva de laboratorio completo")
    st.write(f"**Laboratorio:** {LABS_NAMES[lab]}")
    st.write(f"**Fecha:** {formatear_fecha_espanol(fecha_str)}")
    st.write(f"**Hora:** {hora}")
    if profesor_sugerido:
        st.info(f"Docente detectado: {profesor_sugerido}")
    st.divider()
    
    with st.form(key=f"form_profesor_{lab}_{fecha_str}_{hora}"):
        col1, col2 = st.columns(2)
        with col1:
            motivo = st.text_input("Motivo de la reserva *", placeholder="Ej: Examen, clase especial...")
            if profesor_sugerido:
                opcion_profesor = st.selectbox(
                    "Docente",
                    [profesor_sugerido, "Otro docente"],
                    key=f"docente_reserva_{lab}_{fecha_str}_{hora}",
                )
                if opcion_profesor == profesor_sugerido:
                    nombre_profesor = profesor_sugerido
                    st.caption("Se usarÃ¡ el docente detectado en el horario.")
                else:
                    nombre_profesor = st.text_input(
                        "Nombre del profesor *",
                        placeholder="Ej: Juan PÃ©rez",
                        key=f"nombre_profesor_otro_{lab}_{fecha_str}_{hora}",
                    )
            else:
                nombre_profesor = st.text_input("Nombre del profesor *", placeholder="Ej: Juan PÃ©rez")
        with col2:
            tecnico = st.selectbox("TÃ©cnico responsable", OPCIONES_TECNICOS, index=0, key=f"tecnico_profesor_v2_{lab}_{fecha_str}_{hora}")
        
        st.caption(" Esta reserva ocuparÃ¡ TODO el laboratorio por 2 horas.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button(" Confirmar reserva", use_container_width=True):
                if not motivo or not nombre_profesor:
                    st.error(" Motivo y nombre del profesor son obligatorios")
                elif not es_tecnico_valido(tecnico):
                    st.error("Selecciona el técnico responsable.")
                else:
                    if res.guardar_reserva_profesor(fecha_str, hora, lab, motivo, nombre_profesor, tecnico):
                        st.success(f" Â¡Laboratorio completo reservado para: {motivo}!")
                        del st.session_state.labs_profesor_reserva
                        st.rerun()
                    else:
                        st.error(" No se pudo reservar. El laboratorio ya tiene reservas en este bloque.")
        with col2:
            if st.form_submit_button(" Cancelar", use_container_width=True):
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
    st.subheader(" Registrar asistencia del docente")
    st.write(f"**Laboratorio:** {LABS_NAMES[lab]}")
    st.write(f"**Fecha:** {formatear_fecha_espanol(fecha_str)}")
    st.write(f"**Hora:** {hora}")
    st.write(f"**Asignatura:** {info['asignatura']}")
    st.write(f"**Docente (horario fijo):** {info['profesor']}")
    st.divider()
    
    estado = st.radio("Estado", ["AsistiÃ³", "No asistiÃ³"], horizontal=True, key="asistencia_estado")
    tecnico = st.selectbox("TÃ©cnico que registra", OPCIONES_TECNICOS, index=0, key="asistencia_tecnico_v2")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button(" Confirmar asistencia", key="confirmar_asistencia", use_container_width=True):
            if not es_tecnico_valido(tecnico):
                st.error("Selecciona el técnico que registra.")
            else:
                estado_db = "Si" if estado == "AsistiÃ³" else "No"
                res.registrar_asistencia_docente(
                    fecha_str, hora, lab,
                    info['profesor'],
                    info['asignatura'],
                    estado_db,
                    tecnico
                )
                st.success(f" Asistencia registrada: {estado}")
                del st.session_state.asistencia_docente
                st.rerun()
    with col2:
        if st.button(" Cancelar", key="cancelar_asistencia", use_container_width=True):
            del st.session_state.asistencia_docente
            st.rerun()
            

# ==================== OVERRIDE LIMPIO ====================

def mostrar_calendario_interactivo(dia_seleccionado):
    """
    Calendario de reserva uniforme, sin colores ni leyendas por estado.
    """
    st.markdown(
        """
        <style>
            div[data-testid="column"] div.stButton > button {
                width: 100% !important;
                height: 108px !important;
                border: 1px solid #d9d9d9 !important;
                border-radius: 4px !important;
                padding: 0.4rem !important;
                white-space: pre-line !important;
                line-height: 1.1 !important;
                text-align: center !important;
                font-size: 0.76rem !important;
                font-weight: 600 !important;
                color: #222 !important;
                background: #ffffff !important;
                box-shadow: none !important;
                overflow: hidden !important;
            }
            div[data-testid="column"] div.stButton > button:hover {
                border-color: #9aa0a6 !important;
                color: #222 !important;
                background: #fafafa !important;
            }
            div[data-testid="column"] div.stButton > button:disabled {
                color: #222 !important;
                background: #ffffff !important;
                opacity: 1 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.subheader(f"?? Ocupación para {dia_seleccionado}")
    hoy = datetime.now().date()
    lunes = st.session_state.labs_semana_inicio
    idx = DIAS.index(dia_seleccionado)
    fecha = lunes + timedelta(days=idx)
    fecha_str = fecha.strftime("%Y-%m-%d")
    es_pasado = fecha < hoy

    cols = st.columns([1] + [1] * len(LABS_ORDEN))
    with cols[0]:
        st.write("**Hora**")
    for i, lab in enumerate(LABS_ORDEN):
        with cols[i + 1]:
            st.write(f"**{LABS_NAMES.get(lab, lab)}**")

    for hora in HORAS:
        cols = st.columns([1] + [1] * len(LABS_ORDEN))
        with cols[0]:
            st.write(hora)

        for i, lab in enumerate(LABS_ORDEN):
            total = LABORATORIOS[lab]
            ocupados = get_ocupados(lab, fecha_str, hora)
            disponibles = total - ocupados

            with cols[i + 1]:
                if es_pasado:
                    st.button(
                        "No se puede reservar\nDía ya transcurrido",
                        key=f"bloqueado_{lab}_{fecha_str}_{hora}",
                        use_container_width=True,
                        disabled=True,
                    )
                    continue

                r_profesor = db.ejecutar(
                    """SELECT nombres, proyecto, asiste FROM reservas
                    WHERE laboratorio=? AND fecha=? AND hora=?
                    AND codigo='PROFESOR' AND activo=1
                    AND asiste IS NOT NULL AND asiste != ''
                    ORDER BY id DESC
                    LIMIT 1""",
                    (lab, fecha_str, hora),
                    fetch=True,
                )
                tiene_profesor = len(r_profesor) > 0 if r_profesor else False
                profesor_nombre = r_profesor[0][0] if tiene_profesor else ""
                profesor_asignatura = r_profesor[0][1] if tiene_profesor else ""
                estado_profesor = r_profesor[0][2] if tiene_profesor else ""

                horario = hf.get_horario_celda(dia_seleccionado, hora, lab)
                tiene_asignatura = bool(horario and horario["asignatura"])

                r = db.ejecutar(
                    """SELECT COUNT(*) FROM reservas
                    WHERE laboratorio=? AND fecha=? AND hora=?
                    AND activo=1
                    AND (asiste != 'No' OR asiste IS NULL OR asiste = '')
                    AND codigo != 'PROFESOR'""",
                    (lab, fecha_str, hora),
                    fetch=True,
                )
                reservas_activas = r[0][0] > 0

                if tiene_profesor and estado_profesor == "Si":
                    label = f"Asistió\n{profesor_asignatura}\n{profesor_nombre}"
                    help_text = f"Asistió | {profesor_asignatura} | {profesor_nombre}"
                elif tiene_profesor and estado_profesor == "No":
                    label = f"No asistió\n{profesor_asignatura}\n{profesor_nombre}"
                    help_text = f"No asistió | {profesor_asignatura} | {profesor_nombre}"
                elif tiene_asignatura and not reservas_activas:
                    label = formatear_etiqueta_horario(horario)
                    help_text = label.replace("\n", " | ")
                elif disponibles > 0:
                    label = f"Libre\n{ocupados}/{total}"
                    help_text = f"Libre | {ocupados}/{total}"
                else:
                    label = f"Ocupado\n{ocupados}/{total}"
                    help_text = f"Ocupado | {ocupados}/{total}"

                if st.button(
                    label,
                    key=f"celda_{lab}_{fecha_str}_{hora}",
                    use_container_width=True,
                    help=f"{LABS_NAMES.get(lab, lab)} - {hora} | {help_text}",
                ):
                    if tiene_profesor and estado_profesor in ("Si", "No"):
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
                                "asignatura": profesor_asignatura,
                                "estado": estado_profesor,
                            },
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
                            "asignatura_info": horario,
                        }
                    else:
                        st.session_state.labs_celda_seleccionada = {
                            "fecha": fecha_str,
                            "hora": hora,
                            "laboratorio": lab,
                            "ocupados": ocupados,
                            "total": total,
                            "disponibles": disponibles,
                            "bancos_disponibles": [
                                b for b in range(1, total + 1)
                                if b not in get_bancos_ocupados(lab, fecha_str, hora)
                            ],
                            "es_asignatura": False,
                        }
                    st.rerun()


def mostrar_detalle_celda():
    if "labs_celda_seleccionada" not in st.session_state:
        return

    if not st.session_state.get("labs_modal_reserva_pendiente", False):
        if st.session_state.get("labs_modal_reserva_renderizado", False):
            if "labs_celda_seleccionada" in st.session_state:
                del st.session_state.labs_celda_seleccionada
            st.session_state.labs_modal_reserva_renderizado = False
        return

    st.markdown(
        """
        <style>
            div[role="dialog"] {
                width: min(98vw, 1170px) !important;
                max-width: 1170px !important;
            }
            div[role="dialog"] > div {
                max-width: 1170px !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

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

    titulo = f"?? Detalle - {LABS_NAMES[lab]} {hora} {formatear_fecha_espanol(fecha_str)}"
    if es_profesor_asistio and profesor_data:
        estado = profesor_data.get("estado", "")
        if estado == "Si":
            titulo += f" | Asistió: {profesor_data.get('asignatura', 'Clase')} - {profesor_data.get('nombre', 'Profesor')}"
        elif estado == "No":
            titulo += f" | No asistió: {profesor_data.get('asignatura', 'Clase')} - {profesor_data.get('nombre', 'Profesor')}"
    elif es_asignatura and asignatura_info:
        titulo += f" | Asignatura: {asignatura_info['asignatura']}"
    else:
        titulo += f" (Ocupados: {ocupados}/{total})"

    with st.expander(titulo, expanded=True):
        if es_profesor_asistio and profesor_data:
            estado = profesor_data.get("estado", "")
            if estado == "Si":
                st.success(f"Asistió: {profesor_data.get('nombre', 'Profesor')}")
            elif estado == "No":
                st.warning(f"No asistió: {profesor_data.get('nombre', 'Profesor')}")
            else:
                st.info(profesor_data.get("nombre", "Profesor"))
            st.info(f"Asignatura/Motivo: {profesor_data.get('asignatura', 'Clase')}")
            st.divider()

        if not df.empty:
            df_editor = df[["id", "banco", "codigo", "nombres", "proyecto", "asiste"]].copy()
            render_editor_asistencias(df_editor, f"detalle_{lab}_{fecha_str}_{hora}", lab)
        else:
            if es_profesor_asistio and profesor_data:
                estado = profesor_data.get("estado", "")
                if estado == "Si":
                    st.info("No hay otras reservas en este bloque. El profesor asistió.")
                elif estado == "No":
                    st.info("No hay otras reservas en este bloque. El profesor no asistió.")
                else:
                    st.info("No hay otras reservas en este bloque.")
                st.divider()
                st.subheader("RESERVA DOCENTE")
                st.caption("Reserva TODO el laboratorio para un bloque completo (2 horas)")

                if st.button("RESERVAR TODO EL ESPACIO", key=f"profesor_reservar_{lab}_{fecha_str}_{hora}", use_container_width=True):
                    st.session_state.labs_profesor_reserva = {
                        "fecha": fecha_str,
                        "hora": hora,
                        "laboratorio": lab,
                        "profesor_sugerido": profesor_data.get("nombre", ""),
                    }
                    del st.session_state.labs_celda_seleccionada
                    st.rerun()

            elif es_asignatura and asignatura_info:
                if asignatura_info.get("carrera") in ("Adicional", "Práctica Libre"):
                    st.info("Espacio adicional disponible para reservas.")
                else:
                    st.warning(
                        f"Este espacio está ocupado por la asignatura {asignatura_info['asignatura']} "
                        f"({asignatura_info['carrera']})"
                    )
                    st.info(f"Monitor: {asignatura_info['monitor']} | Profesor: {asignatura_info['profesor']}")
                    st.write("No hay reservas en este bloque.")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Reservar excepcionalmente (habilitar espacio)", key=f"reservar_excepcional_{lab}_{fecha_str}_{hora}"):
                            bancos_disponibles = list(range(1, total + 1))
                            st.session_state.labs_reserva_celda = {
                                "fecha": fecha_str,
                                "hora": hora,
                                "laboratorio": lab,
                                "bancos_disponibles": bancos_disponibles,
                                "profesor_sugerido": asignatura_info.get("profesor", ""),
                            }
                            del st.session_state.labs_celda_seleccionada
                            st.rerun()
                    with col2:
                        if st.button("Marcar asistencia del docente", key=f"asistencia_docente_{lab}_{fecha_str}_{hora}"):
                            st.session_state.asistencia_docente = {
                                "fecha": fecha_str,
                                "hora": hora,
                                "laboratorio": lab,
                                "asignatura_info": asignatura_info,
                            }
                            del st.session_state.labs_celda_seleccionada
                            st.rerun()
            else:
                st.info("No hay reservas en este bloque.")
                st.divider()
                st.subheader("RESERVA DOCENTE")
                st.caption("Reserva TODO el laboratorio para un bloque completo (2 horas)")

                if st.button("RESERVAR TODO EL ESPACIO", key=f"profesor_reservar_{lab}_{fecha_str}_{hora}", use_container_width=True):
                    st.session_state.labs_profesor_reserva = {
                        "fecha": fecha_str,
                        "hora": hora,
                        "laboratorio": lab,
                    }
                    del st.session_state.labs_celda_seleccionada
                    st.rerun()


# ==================== GRILLA HTML UNIFORME ====================

def _limpiar_parametros_reserva():
    try:
        for nombre in ("lab", "fecha", "hora", "reserva"):
            if nombre in st.query_params:
                del st.query_params[nombre]
    except Exception:
        st.experimental_set_query_params()


def _cerrar_detalle_celda(rerun=True):
    if "labs_celda_seleccionada" in st.session_state:
        del st.session_state.labs_celda_seleccionada
    st.session_state.labs_modal_reserva_pendiente = False
    st.session_state.labs_modal_reserva_renderizado = False
    _limpiar_parametros_reserva()
    if rerun:
        st.rerun()


def _cerrar_detalle_celda_por_dismiss():
    _cerrar_detalle_celda(rerun=False)


def _normalizar_lab(lab):
    return str(lab).strip().lower()


def _build_contexto_calendario(dia_seleccionado, fecha_str):
    reservas = db.ejecutar(
        """SELECT id, hora, laboratorio, banco, codigo, nombres, proyecto, asiste
        FROM reservas
        WHERE fecha=? AND activo=1""",
        (fecha_str,),
        fetch=True,
    ) or []
    horarios = db.ejecutar(
        """SELECT hora, laboratorio, asignatura, carrera, monitor, profesor
        FROM horario_fijo
        WHERE dia_semana=?""",
        (dia_seleccionado,),
        fetch=True,
    ) or []

    slots = defaultdict(lambda: {
        "bancos": set(),
        "sala_completa": False,
        "profesor_no": False,
        "reservas_activas": False,
        "profesor": None,
    })

    for reserva_id, hora_reserva, lab_reserva, banco, codigo, nombres, proyecto, asiste in reservas:
        clave = (_normalizar_lab(lab_reserva), hora_reserva)
        slot = slots[clave]
        codigo = codigo or ""
        asistencia = asiste or ""
        activa_para_ocupacion = asistencia != "No"
        es_profesor_no = codigo == "PROFESOR" and asistencia == "No"

        if es_profesor_no:
            slot["profesor_no"] = True

        if codigo == "PROFESOR" and asistencia:
            profesor_actual = slot["profesor"]
            if profesor_actual is None or reserva_id > profesor_actual["id"]:
                slot["profesor"] = {
                    "id": reserva_id,
                    "nombre": nombres or "",
                    "asignatura": proyecto or "",
                    "estado": asistencia,
                }

        if activa_para_ocupacion and not es_profesor_no:
            if int(banco or 0) > 0:
                slot["bancos"].add(int(banco))
            elif int(banco or 0) == 0:
                slot["sala_completa"] = True

            if codigo != "PROFESOR":
                slot["reservas_activas"] = True

    horarios_por_celda = {
        (_normalizar_lab(lab_horario), hora_horario): {
            "asignatura": asignatura,
            "carrera": carrera,
            "monitor": monitor,
            "profesor": profesor,
        }
        for hora_horario, lab_horario, asignatura, carrera, monitor, profesor in horarios
    }

    return {"slots": slots, "horarios": horarios_por_celda}


def _obtener_estado_celda(dia_seleccionado, lab, fecha_str, hora, contexto=None):
    total = LABORATORIOS[lab]
    horario = None
    reservas_activas = False
    profesor_nombre = ""
    profesor_asignatura = ""
    estado_profesor = ""

    if contexto:
        clave = (_normalizar_lab(lab), hora)
        slot = contexto["slots"].get(clave)
        horario = contexto["horarios"].get(clave)

        if slot and slot["sala_completa"]:
            ocupados = total
        elif slot and slot["bancos"]:
            ocupados = len(slot["bancos"])
        elif slot and slot["profesor_no"]:
            ocupados = 0
        elif horario and _es_bloque_reservable(horario.get("asignatura"), horario.get("carrera")):
            ocupados = 0
        elif horario and horario["asignatura"]:
            ocupados = total
        else:
            ocupados = 0

        if slot:
            reservas_activas = slot["reservas_activas"]
            profesor = slot["profesor"]
            if profesor:
                profesor_nombre = profesor["nombre"]
                profesor_asignatura = profesor["asignatura"]
                estado_profesor = profesor["estado"]
    else:
        ocupados = get_ocupados(lab, fecha_str, hora)

        r_profesor = db.ejecutar(
            """SELECT nombres, proyecto, asiste FROM reservas
            WHERE laboratorio=? AND fecha=? AND hora=?
            AND codigo='PROFESOR' AND activo=1
            AND asiste IS NOT NULL AND asiste != ''
            ORDER BY id DESC
            LIMIT 1""",
            (lab, fecha_str, hora),
            fetch=True,
        )
        tiene_profesor_respaldo = len(r_profesor) > 0 if r_profesor else False
        profesor_nombre = r_profesor[0][0] if tiene_profesor_respaldo else ""
        profesor_asignatura = r_profesor[0][1] if tiene_profesor_respaldo else ""
        estado_profesor = r_profesor[0][2] if tiene_profesor_respaldo else ""

        horario = hf.get_horario_celda(dia_seleccionado, hora, lab)

        r = db.ejecutar(
            """SELECT COUNT(*) FROM reservas
            WHERE laboratorio=? AND fecha=? AND hora=?
            AND activo=1
            AND (asiste != 'No' OR asiste IS NULL OR asiste = '')
            AND codigo != 'PROFESOR'""",
            (lab, fecha_str, hora),
            fetch=True,
        )
        reservas_activas = r[0][0] > 0

    disponibles = total - ocupados

    tiene_profesor = bool(estado_profesor)
    tiene_asignatura = bool(horario and horario["asignatura"])
    es_adicional = bool(horario and _es_bloque_reservable(horario.get("asignatura"), horario.get("carrera")))

    if tiene_profesor and estado_profesor == "Si":
        estado = "profesor_si"
        etiqueta = f"DOCENTE ASISTIO\n{profesor_asignatura}\n{profesor_nombre}"
        detalle = f"(Asistió) | {profesor_asignatura} | {profesor_nombre}"
    elif tiene_profesor and estado_profesor == "No":
        estado = "profesor_no"
        etiqueta = f"DOCENTE NO ASISTIO\nHabilitado\n{ocupados}/{total}"
        detalle = f"(No asistió) | {profesor_asignatura} | {profesor_nombre} | {ocupados}/{total}"
    elif es_adicional:
        nombre_bloque = horario.get("asignatura") or "Adicional"
        es_practica_libre = "práctica libre" in nombre_bloque.lower() or "practica libre" in nombre_bloque.lower()
        estado = "practica_libre" if es_practica_libre else "adicional"
        if reservas_activas or ocupados > 0:
            etiqueta = f"{nombre_bloque}\n{ocupados}/{total}"
            detalle = f"{nombre_bloque} ocupado | {ocupados}/{total}"
        else:
            etiqueta = f"{nombre_bloque}\n{ocupados}/{total}"
            detalle = f"{nombre_bloque} libre | {ocupados}/{total}"
    elif tiene_asignatura and not reservas_activas:
        estado = "asignatura"
        etiqueta = formatear_etiqueta_horario(horario)
        detalle = etiqueta.replace("\n", " | ")
    elif disponibles > 0:
        estado = "libre"
        etiqueta = f"Libre\n{ocupados}/{total}"
        detalle = f"Libre | {ocupados}/{total}"
    else:
        estado = "ocupado"
        etiqueta = f"Ocupado\n{ocupados}/{total}"
        detalle = f"Ocupado | {ocupados}/{total}"

    return {
        "total": total,
        "ocupados": ocupados,
        "disponibles": disponibles,
        "horario": horario,
        "tiene_asignatura": tiene_asignatura,
        "reservas_activas": reservas_activas,
        "tiene_profesor": tiene_profesor,
        "profesor_nombre": profesor_nombre,
        "profesor_asignatura": profesor_asignatura,
        "estado_profesor": estado_profesor,
        "estado": estado,
        "etiqueta": etiqueta,
        "detalle": detalle,
    }


def _datos_celda_seleccionada(sel_lab, sel_fecha, sel_hora, estado):
    return {
        "fecha": sel_fecha,
        "hora": sel_hora,
        "laboratorio": sel_lab,
        "ocupados": estado["ocupados"],
        "total": estado["total"],
        "disponibles": estado["disponibles"],
        "bancos_disponibles": [
            b for b in range(1, estado["total"] + 1)
            if b not in get_bancos_ocupados(sel_lab, sel_fecha, sel_hora)
        ],
        "es_asignatura": estado["estado"] in ("asignatura", "adicional", "practica_libre", "profesor_si", "profesor_no"),
        "asignatura_info": estado["horario"],
        "es_profesor_asistio": estado["estado"] == "profesor_si",
        "es_profesor_no_asistio": estado["estado"] == "profesor_no",
        "profesor_data": {
            "nombre": estado["profesor_nombre"],
            "asignatura": estado["profesor_asignatura"],
            "estado": estado["estado_profesor"],
        },
    }


def _seleccionar_celda_reserva(lab, fecha_str, hora, estado):
    st.session_state.labs_celda_seleccionada = _datos_celda_seleccionada(lab, fecha_str, hora, estado)
    st.session_state.labs_modal_reserva_pendiente = True
    st.session_state.labs_modal_reserva_renderizado = False
    _limpiar_parametros_reserva()
    st.rerun()


def _estilo_celda_reserva(estado):
    estilos_estado = {
        "profesor_si": {
            "background": "#16A34A",
            "color": "#FFFFFF",
            "border": "#087A2F",
            "shadow": "inset 0 0 0 3px rgba(255,255,255,0.35), 0 8px 18px rgba(22,163,74,0.28)",
            "weight": "900",
        },
        "profesor_no": {
            "background": "#DC2626",
            "color": "#FFFFFF",
            "border": "#991B1B",
            "shadow": "inset 0 0 0 3px rgba(255,255,255,0.35), 0 8px 18px rgba(220,38,38,0.30)",
            "weight": "900",
        },
        "adicional": {
            "background": "#E8C766",
            "color": "#2E1A00",
            "border": "#C5A13A",
            "shadow": "none",
            "weight": "750",
        },
        "practica_libre": {
            "background": "#E7D8CC",
            "color": "#4A2E22",
            "border": "#B88968",
            "shadow": "none",
            "weight": "800",
        },
        "asignatura": {
            "background": "#FDE2E2",
            "color": "#222222",
            "border": "#E5A3A3",
            "shadow": "none",
            "weight": "650",
        },
        "libre": {
            "background": "#FFFFFF",
            "color": "#222222",
            "border": "#22C55E",
            "shadow": "inset 0 0 0 2px rgba(34,197,94,0.20)",
            "weight": "700",
        },
        "ocupado": {
            "background": "#F3F4F6",
            "color": "#222222",
            "border": "#9CA3AF",
            "shadow": "none",
            "weight": "650",
        },
        "pasado": {
            "background": "#F3F4F6",
            "color": "#6B7280",
            "border": "#DDDDDD",
            "shadow": "none",
            "weight": "650",
        },
    }
    return estilos_estado.get(estado.get("estado"), estilos_estado["libre"])


def _id_css_celda_reserva(key):
    return "css_" + "".join(ch if ch.isalnum() else "_" for ch in key)


def _inyectar_estilo_boton_celda(marker_id, estilo):
    st.markdown(
        f"""
        <style id="{marker_id}">
            div[data-testid="stElementContainer"]:has(style#{marker_id}) + div[data-testid="stElementContainer"] button {{
                background: {estilo["background"]} !important;
                height: 220px !important;
                min-height: 220px !important;
                border: 2px solid {estilo["border"]} !important;
                border-radius: 4px !important;
                padding: 0.55rem !important;
                white-space: pre-wrap !important;
                line-height: 1.16 !important;
                text-align: center !important;
                font-size: 0.76rem !important;
                font-weight: {estilo["weight"]} !important;
                color: {estilo["color"]} !important;
                box-shadow: {estilo["shadow"]} !important;
                overflow: hidden !important;
                overflow-wrap: anywhere !important;
                word-break: break-word !important;
                cursor: pointer !important;
            }}
            div[data-testid="stElementContainer"]:has(style#{marker_id}) + div[data-testid="stElementContainer"] button p,
            div[data-testid="stElementContainer"]:has(style#{marker_id}) + div[data-testid="stElementContainer"] button div {{
                white-space: pre-wrap !important;
                line-height: 1.16 !important;
                overflow-wrap: anywhere !important;
                word-break: break-word !important;
                margin: 0 !important;
                max-height: none !important;
            }}
            div[data-testid="stElementContainer"]:has(style#{marker_id}) + div[data-testid="stElementContainer"] button:hover {{
                background: {estilo["background"]} !important;
                border-color: {estilo["border"]} !important;
                filter: brightness(0.98);
                box-shadow: {estilo["shadow"]} !important;
            }}
            div[data-testid="stElementContainer"]:has(style#{marker_id}) + div[data-testid="stElementContainer"] button:focus {{
                box-shadow: none !important;
            }}
            div[data-testid="stElementContainer"]:has(style#{marker_id}) + div[data-testid="stElementContainer"] button:disabled {{
                background: #ffffff !important;
                color: #6b7280 !important;
                border-color: #ddd !important;
                opacity: 1 !important;
                cursor: default !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def mostrar_calendario_interactivo(dia_seleccionado):
    """
    Grilla de reserva con botones nativos para abrir el modal sin navegar.
    """
    st.subheader(f"Ocupación para {dia_seleccionado}")
    hoy = datetime.now().date()
    lunes = st.session_state.labs_semana_inicio
    idx = DIAS.index(dia_seleccionado)
    fecha = lunes + timedelta(days=idx)
    fecha_str = fecha.strftime("%Y-%m-%d")
    es_pasado = fecha < hoy
    contexto_calendario = _build_contexto_calendario(dia_seleccionado, fecha_str)

    st.markdown(
        """
        <style>
            .reserva-native-header {
                height: 44px;
                border: 1px solid #ddd;
                background: #f0f0f0;
                display: flex;
                align-items: center;
                justify-content: center;
                text-align: center;
                padding: 8px;
                font-size: 0.88rem;
                font-weight: 700;
                box-sizing: border-box;
                overflow: hidden;
            }
            .reserva-native-time {
                height: 220px;
                border: 1px solid #ddd;
                background: #f9f9f9;
                display: flex;
                align-items: center;
                justify-content: center;
                text-align: center;
                padding: 8px;
                font-size: 0.88rem;
                font-weight: 700;
                box-sizing: border-box;
                overflow: hidden;
            }
            .reserva-sticky-labs {
                display:grid; grid-template-columns:repeat(10,minmax(0,1fr)); gap:0.75rem;
                background:#f7f4ef; padding:0.45rem 0; box-shadow:0 7px 14px rgba(34,30,31,0.12);
            }
            .reserva-sticky-lab {
                min-height:44px; display:flex; align-items:center; justify-content:center;
                background:#f0f0f0; border:1px solid #d7d7d7; padding:0.35rem;
                box-sizing:border-box; text-align:center; font-size:0.78rem; font-weight:850;
            }
            .reserva-sticky-day {
                background:#731116; color:#ffffff; border-bottom:4px solid #d6a81f;
                border-radius:8px 8px 0 0; padding:0.55rem 0.8rem;
                font-weight:900; text-align:center; box-shadow:0 8px 18px rgba(71,18,22,0.16);
            }
            div[data-testid="stElementContainer"]:has(.reserva-sticky-day) {
                position:sticky; top:3.7rem; z-index:1202; margin-bottom:0 !important;
            }
            div[data-testid="stHorizontalBlock"]:has(.reserva-native-header) > div[data-testid="column"]:first-child,
            div[data-testid="stHorizontalBlock"]:has(.reserva-native-time) > div[data-testid="column"]:first-child {
                position:sticky; left:0; z-index:1203; background:#f7f4ef;
                box-shadow:5px 0 10px rgba(34,30,31,0.10);
            }
            div[data-testid="stHorizontalBlock"]:has(.reserva-native-header) {
                position:sticky; top:6.35rem; z-index:1201;
                background:#f7f4ef; box-shadow:0 6px 14px rgba(34,30,31,0.10);
            }

            div[data-testid="column"] {
                padding-left: 0 !important;
                padding-right: 0 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    encabezados = ["Hora"] + [LABS_NAMES.get(lab, lab) for lab in LABS_ORDEN]
    encabezados_html = "".join(
        f"<div class='reserva-sticky-lab'>{nombre}</div>" for nombre in encabezados
    )
    st.markdown(
        f"""
        <div class='reserva-sticky-day'>{dia_seleccionado} · {formatear_fecha_espanol(fecha_str)}</div>
        <div class='reserva-sticky-labs'>{encabezados_html}</div>
        """,
        unsafe_allow_html=True,
    )
    for hora in HORAS:
        cols = st.columns([1] + [1] * len(LABS_ORDEN), gap="small")
        with cols[0]:
            st.markdown(f"<div class='reserva-native-time'>{hora}</div>", unsafe_allow_html=True)

        for i, lab in enumerate(LABS_ORDEN, start=1):
            estado = _obtener_estado_celda(dia_seleccionado, lab, fecha_str, hora, contexto_calendario)
            key = f"reserva_celda_{fecha_str}_{hora}_{lab}"
            estilo = _estilo_celda_reserva({"estado": "pasado"} if es_pasado else estado)
            with cols[i]:
                _inyectar_estilo_boton_celda(_id_css_celda_reserva(key), estilo)
                if es_pasado:
                    st.button(
                        "No se puede reservar",
                        key=f"{key}_pasado",
                        use_container_width=True,
                        disabled=True,
                    )
                elif st.button(
                    estado["etiqueta"],
                    key=key,
                    help=estado["detalle"],
                    use_container_width=True,
                ):
                    _seleccionar_celda_reserva(lab, fecha_str, hora, estado)


def _render_formulario_reserva_individual(data, puede_reservar_individual):
    data = st.session_state.labs_celda_seleccionada
    fecha_str = data["fecha"]
    hora = data["hora"]
    lab = data["laboratorio"]

    if not puede_reservar_individual:
        st.info("No hay bancos disponibles para reservar en este bloque.")
        return

    st.subheader("Agregar reserva individual")
    st.caption(f"Bancos disponibles: {', '.join(map(str, data['bancos_disponibles']))}")

    codigo_key = f"codigo_verificar_{lab}_{fecha_str}_{hora}"
    codigo_limpieza_key = f"limpiar_codigo_verificar_{lab}_{fecha_str}_{hora}"
    if st.session_state.pop(codigo_limpieza_key, False):
        # Se ejecuta antes de instanciar el widget en el nuevo render.
        st.session_state[codigo_key] = ""
    codigo = st.text_input(
        "Código del estudiante *",
        key=codigo_key,
        placeholder="Ingresa el código y presiona Enter para verificar",
    )

    estudiante_info = None
    reservas_fecha = 0
    multas_activas = 0
    autorizacion_key = f"autoriza_multas_{lab}_{fecha_str}_{hora}_{codigo}"
    if codigo:
        estudiante_info = est.buscar_estudiante(codigo)
        if estudiante_info:
            reservas_fecha = est.contar_reservas_fecha(codigo, fecha_str)
            fecha_mostrada = formatear_fecha_espanol(fecha_str)
            st.success(f"{estudiante_info[1]}")
            st.write(f"Reservas de ese dia ({fecha_mostrada}): {reservas_fecha}")
            if reservas_fecha >= 2:
                siguiente_reserva = reservas_fecha + 1
                st.warning(
                    f"Atencion: esta seria la reserva numero {siguiente_reserva} "
                    "del estudiante en este dia. El tecnico debe decidir si la autoriza."
                )
            if estudiante_info[2]:
                st.info(estudiante_info[2])
            multas_activas = multas.contar_multas_activas(codigo)
            multas_texto = multas.obtener_texto_multas_activas(codigo)
            if multas_texto:
                st.error(f"Multas activas:\n{multas_texto}")
        else:
            st.error("Código no válido. Verifica el código ingresado.")

    requiere_autorizacion = bool(estudiante_info and multas_activas > 3)
    if requiere_autorizacion:
        st.error(
            f"ALERTA CRÍTICA: el estudiante registra {multas_activas} multas activas. "
            "El préstamo está bloqueado hasta que un técnico tome una decisión."
        )
        autorizar_col, negar_col = st.columns(2)
        with autorizar_col:
            if st.button("Autorizar de manera excepcional", key=f"btn_{autorizacion_key}", use_container_width=True):
                st.session_state[autorizacion_key] = True
                st.rerun()
        with negar_col:
            if st.button("Negar préstamo", key=f"negar_{autorizacion_key}", use_container_width=True):
                st.session_state.pop(autorizacion_key, None)
                _cerrar_detalle_celda()
        if st.session_state.get(autorizacion_key):
            st.success("Préstamo autorizado excepcionalmente por el técnico.")
    with st.form(key=f"form_reserva_guardar_{lab}_{fecha_str}_{hora}"):
        bancos_disponibles = data.get("bancos_disponibles", [])
        col1, col2 = st.columns(2)
        with col1:
            banco = st.selectbox("Banco", bancos_disponibles, key=f"banco_{lab}_{fecha_str}_{hora}")
        with col2:
            tecnico = st.selectbox("Técnico", OPCIONES_TECNICOS, index=0, key=f"tecnico_v2_{lab}_{fecha_str}_{hora}")

        observaciones = st.text_area("Observaciones", key=f"obs_{lab}_{fecha_str}_{hora}")
        autoriza_reservas_extra = True
        if estudiante_info and reservas_fecha >= 2:
            autoriza_reservas_extra = st.checkbox(
                f"Autorizo asignar la reserva numero {reservas_fecha + 1} de este estudiante en el dia",
                key=f"autoriza_reserva_extra_{lab}_{fecha_str}_{hora}_{codigo}",
            )

        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Guardar reserva", use_container_width=True):
                if not codigo:
                    st.error("Primero ingresa un código de estudiante")
                elif not estudiante_info:
                    st.error("Código no válido. Verifica el código ingresado.")
                elif not es_tecnico_valido(tecnico):
                    st.error("Selecciona el técnico responsable.")
                elif requiere_autorizacion and not st.session_state.get(autorizacion_key, False):
                    st.error("Debes autorizar excepcionalmente el préstamo o negarlo.")
                elif res.verificar_reserva_existente(codigo, fecha_str, hora, None):
                    st.error("Este estudiante ya tiene una reserva activa en esta fecha y hora en otro laboratorio.")
                elif not autoriza_reservas_extra:
                    st.error("El tecnico debe autorizar esta tercera reserva o adicional antes de guardarla.")
                else:
                    datos_reserva = (
                        fecha_str,
                        hora,
                        lab,
                        banco,
                        codigo,
                        estudiante_info[1],
                        estudiante_info[2] if estudiante_info[2] else "",
                        "",
                        observaciones,
                        tecnico,
                    )
                    if res.guardar_reserva(datos_reserva):
                        st.success("Reserva guardada correctamente")
                        st.session_state[codigo_limpieza_key] = True
                        data["bancos_disponibles"] = [
                            disponible for disponible in data.get("bancos_disponibles", [])
                            if disponible != banco
                        ]
                        data["ocupados"] = min(data.get("total", 0), data.get("ocupados", 0) + 1)
                        data["disponibles"] = max(0, data.get("disponibles", 0) - 1)
                        for campo_key in (
                            f"banco_{lab}_{fecha_str}_{hora}",
                            f"obs_{lab}_{fecha_str}_{hora}",
                        ):
                            st.session_state.pop(campo_key, None)
                        st.session_state.labs_modal_reserva_pendiente = True
                        st.session_state.labs_modal_reserva_renderizado = False
                        st.rerun()
        with col2:
            if st.form_submit_button("Cancelar", use_container_width=True):
                if codigo_key in st.session_state:
                    del st.session_state[codigo_key]
                _cerrar_detalle_celda()


def _render_formulario_reserva_docente(data, profesor_data=None):
    fecha_str = data["fecha"]
    hora = data["hora"]
    lab = data["laboratorio"]
    profesor_sugerido = ""
    if profesor_data:
        profesor_sugerido = profesor_data.get("nombre", "").strip()

    st.subheader("Reserva docente")
    st.caption("Reserva TODO el laboratorio para un bloque completo (2 horas)")

    with st.form(key=f"form_profesor_modal_{lab}_{fecha_str}_{hora}"):
        col1, col2 = st.columns(2)
        with col1:
            motivo = st.text_input("Motivo de la reserva *", placeholder="Ej: Examen, clase especial...")
            if profesor_sugerido:
                opcion_profesor = st.selectbox(
                    "Docente",
                    [profesor_sugerido, "Otro docente"],
                    key=f"docente_modal_{lab}_{fecha_str}_{hora}",
                )
                if opcion_profesor == profesor_sugerido:
                    nombre_profesor = profesor_sugerido
                else:
                    nombre_profesor = st.text_input(
                        "Nombre del profesor *",
                        placeholder="Ej: Juan Pérez",
                        key=f"nombre_profesor_modal_otro_{lab}_{fecha_str}_{hora}",
                    )
            else:
                nombre_profesor = st.text_input("Nombre del profesor *", placeholder="Ej: Juan Pérez")
        with col2:
            tecnico = st.selectbox("Técnico responsable", OPCIONES_TECNICOS, index=0, key=f"tecnico_profesor_modal_v2_{lab}_{fecha_str}_{hora}")

        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Confirmar reserva docente", use_container_width=True):
                if not motivo or not nombre_profesor:
                    st.error("Motivo y nombre del profesor son obligatorios")
                elif not es_tecnico_valido(tecnico):
                    st.error("Selecciona el técnico responsable.")
                elif res.guardar_reserva_profesor(fecha_str, hora, lab, motivo, nombre_profesor, tecnico):
                    st.success(f"Laboratorio completo reservado para: {motivo}")
                    _cerrar_detalle_celda()
                else:
                    st.error("No se pudo reservar. El laboratorio ya tiene reservas en este bloque.")
        with col2:
            if st.form_submit_button("Cancelar", use_container_width=True):
                _cerrar_detalle_celda()


def _render_formulario_asistencia_docente_modal(data, asignatura_info, profesor_data=None):
    fecha_str = data["fecha"]
    hora = data["hora"]
    lab = data["laboratorio"]
    profesor_actual = ""
    asignatura_actual = ""

    if profesor_data and profesor_data.get("nombre"):
        profesor_actual = profesor_data.get("nombre", "")
        asignatura_actual = profesor_data.get("asignatura", "")
    if asignatura_info:
        profesor_actual = profesor_actual or asignatura_info.get("profesor", "")
        asignatura_actual = asignatura_actual or asignatura_info.get("asignatura", "")

    st.subheader("Asistencia docente")
    st.write(f"**Asignatura:** {asignatura_actual if asignatura_actual else 'Clase'}")
    st.write(f"**Docente:** {profesor_actual if profesor_actual else 'No registrado'}")

    with st.form(key=f"form_asistencia_docente_modal_{lab}_{fecha_str}_{hora}"):
        estado = st.radio("Estado", ["Asistió", "No asistió"], horizontal=True, key=f"estado_docente_modal_{lab}_{fecha_str}_{hora}")
        tecnico = st.selectbox("Técnico que registra", OPCIONES_TECNICOS, index=0, key=f"tecnico_docente_modal_v2_{lab}_{fecha_str}_{hora}")

        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Confirmar asistencia", use_container_width=True):
                if not profesor_actual:
                    st.error("No hay docente para registrar en este bloque.")
                    return
                if not es_tecnico_valido(tecnico):
                    st.error("Selecciona el técnico que registra.")
                    return
                estado_db = "Si" if estado == "Asistió" else "No"
                res.registrar_asistencia_docente(
                    fecha_str,
                    hora,
                    lab,
                    profesor_actual,
                    asignatura_actual if asignatura_actual else "Clase",
                    estado_db,
                    tecnico,
                )
                st.success(f"Asistencia registrada: {estado}")
                _cerrar_detalle_celda()
        with col2:
            if st.form_submit_button("Cancelar", use_container_width=True):
                _cerrar_detalle_celda()


def _seleccionar_accion_modal(opciones, key):
    if len(opciones) == 1:
        return opciones[0]
    if hasattr(st, "segmented_control"):
        return st.segmented_control("Acción", opciones, default=opciones[0], key=key)
    return st.radio("Acción", opciones, horizontal=True, key=key)


def _render_detalle_celda_contenido():
    data = st.session_state.labs_celda_seleccionada
    fecha_str = data["fecha"]
    hora = data["hora"]
    lab = data["laboratorio"]
    ocupados = data["ocupados"]
    total = data["total"]
    disponibles = data["disponibles"]
    es_asignatura = data.get("es_asignatura", False)
    asignatura_info = data.get("asignatura_info", None)
    es_adicional = bool(asignatura_info and asignatura_info.get("carrera") in ("Adicional", "Práctica Libre"))
    es_profesor_asistio = data.get("es_profesor_asistio", False)
    es_profesor_no_asistio = data.get("es_profesor_no_asistio", False)
    profesor_data = data.get("profesor_data", None)
    tiene_docente_en_clase = bool(
        asignatura_info
        and asignatura_info.get("profesor")
        and not es_adicional
    )
    asistencia_docente_registrada = bool(profesor_data and profesor_data.get("estado") in ("Si", "No"))
    puede_reservar_individual = disponibles > 0 and not es_profesor_asistio and (
        not es_asignatura or es_adicional or es_profesor_no_asistio
    )

    st.markdown(
        f"""
        <div style="background:linear-gradient(100deg,#731116,#9f1d24); border-bottom:5px solid #d6a81f; border-radius:10px; padding:0.9rem 1.1rem; margin-bottom:0.65rem; color:#fff;">
            <div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:0.12em; color:#ffe99a; font-weight:800;">Laboratorio seleccionado</div>
            <div style="font-size:clamp(1.55rem,3vw,2.3rem); line-height:1.05; font-weight:950; margin-top:0.2rem;">{LABS_NAMES[lab]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write(f"**Fecha:** {formatear_fecha_espanol(fecha_str)}")
    st.write(f"**Hora:** {hora}")
    st.write(f"**Ocupación:** {ocupados}/{total}")

    df = res.get_reservas_fecha_lab_hora(fecha_str, lab, hora)

    if es_profesor_asistio and profesor_data:
        estado = profesor_data.get("estado", "")
        if estado == "Si":
            st.success(f"Asistió: {profesor_data.get('nombre', 'Profesor')}")
        elif estado == "No":
            st.warning(f"No asistió: {profesor_data.get('nombre', 'Profesor')}")
        st.info(f"Asignatura/Motivo: {profesor_data.get('asignatura', 'Clase')}")
        st.divider()

    if not df.empty:
        df_editor = df[["id", "banco", "codigo", "nombres", "proyecto", "asiste"]].copy()
        render_editor_asistencias(df_editor, f"detalle_{lab}_{fecha_str}_{hora}", lab)
    else:
        if es_profesor_asistio and profesor_data:
            estado = profesor_data.get("estado", "")
            if estado == "Si":
                st.info("No hay otras reservas en este bloque. El profesor asistió.")
            elif estado == "No":
                st.info("No hay otras reservas en este bloque. El profesor no asistió.")
        elif es_asignatura and asignatura_info:
            if es_adicional:
                st.info("Espacio adicional disponible para reservas.")
            else:
                st.warning(
                    f"Este espacio está ocupado por la asignatura {asignatura_info['asignatura']} "
                    f"({asignatura_info['carrera']})"
                )
                st.info(f"Monitor: {asignatura_info['monitor']} | Profesor: {asignatura_info['profesor']}")
                st.write("No hay reservas en este bloque.")
        else:
            st.info("No hay reservas en este bloque.")

    acciones = []
    if tiene_docente_en_clase and not asistencia_docente_registrada:
        acciones.append("Asistencia docente")
    if puede_reservar_individual:
        acciones.append("Reserva individual")
    if not es_asignatura and not es_profesor_asistio and df.empty:
        acciones.append("Reserva docente")

    if acciones:
        st.divider()
        accion = _seleccionar_accion_modal(acciones, f"accion_modal_{lab}_{fecha_str}_{hora}")
        if accion == "Reserva individual":
            _render_formulario_reserva_individual(data, puede_reservar_individual)
        elif accion == "Reserva docente":
            _render_formulario_reserva_docente(data, profesor_data)
        elif accion == "Asistencia docente":
            _render_formulario_asistencia_docente_modal(data, asignatura_info, profesor_data)
    elif es_asignatura and asignatura_info and not es_adicional:
        st.info("Marca primero si el docente asistió o no asistió para definir si se habilitan reservas.")
    elif es_profesor_asistio:
        st.info("El profesor ya registró asistencia en este bloque. No se permiten reservas individuales.")

    if st.button("Cerrar", key=f"cerrar_detalle_{lab}_{fecha_str}_{hora}"):
        _cerrar_detalle_celda()


def mostrar_detalle_celda():
    if "labs_celda_seleccionada" not in st.session_state:
        return

    if not st.session_state.get("labs_modal_reserva_pendiente", False):
        if st.session_state.get("labs_modal_reserva_renderizado", False):
            if "labs_celda_seleccionada" in st.session_state:
                del st.session_state.labs_celda_seleccionada
            st.session_state.labs_modal_reserva_renderizado = False
        return

    st.markdown(
        """
        <style>
            div[data-testid="stDialog"] div[role="dialog"],
            div[role="dialog"] {
                width: min(98vw, 1170px) !important;
                max-width: 1170px !important;
            }
            div[data-testid="stDialog"] div[role="dialog"] > div,
            div[role="dialog"] > div {
                max-width: 1170px !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    data = st.session_state.labs_celda_seleccionada
    fecha_str = data["fecha"]
    hora = data["hora"]
    lab = data["laboratorio"]
    titulo = f"Detalle - {LABS_NAMES[lab]} {hora} {formatear_fecha_espanol(fecha_str)}"

    if hasattr(st, "dialog"):
        @st.dialog(titulo, width="large", on_dismiss=_cerrar_detalle_celda_por_dismiss)
        def detalle_dialog():
            _render_detalle_celda_contenido()

        detalle_dialog()
        st.session_state.labs_modal_reserva_pendiente = True
        st.session_state.labs_modal_reserva_renderizado = True
    else:
        with st.expander(titulo, expanded=True):
            _render_detalle_celda_contenido()
        st.session_state.labs_modal_reserva_pendiente = True
        st.session_state.labs_modal_reserva_renderizado = True
