import streamlit as st
import database as db
import pandas as pd
from datetime import datetime, timedelta
from constants import LABS_NAMES, TECNICOS, DIAS
import reservas as res
from utils import parse_fecha_a_espanol

def obtener_hora_inicio(hora_str):
    """
    Extrae la hora de inicio de un bloque horario.
    Ej: "08:00-10:00" -> 8
    """
    try:
        return int(hora_str.split('-')[0].split(':')[0])
    except:
        return 0

def obtener_asistencias_pendientes():
    """
    Obtiene TODAS las reservas del día actual que no tienen asistencia marcada.
    Incluye ESTUDIANTES (de reservas) y DOCENTES (del horario fijo).
    SOLO muestra los que YA PASARON su hora de inicio.
    """
    hoy = datetime.now().date().strftime("%Y-%m-%d")
    dia_semana = parse_fecha_a_espanol(hoy)
    hora_actual = datetime.now().hour
    
    # ===== 1. OBTENER ESTUDIANTES PENDIENTES (de reservas) =====
    query_estudiantes = """
        SELECT 
            id,
            fecha,
            hora,
            laboratorio,
            banco,
            codigo,
            nombres,
            proyecto,
            'Estudiante' as tipo
        FROM reservas
        WHERE (asiste IS NULL OR asiste = '')
        AND fecha = ?
        AND activo = 1
        AND codigo != 'PROFESOR'
    """
    df_estudiantes = db.fetch_df(query_estudiantes, (hoy,))
    
    # Filtrar estudiantes por hora (solo los que ya pasaron)
    if not df_estudiantes.empty:
        df_estudiantes = df_estudiantes[df_estudiantes['hora'].apply(obtener_hora_inicio) <= hora_actual]
    
    # ===== 2. OBTENER DOCENTES DEL HORARIO FIJO =====
    query_docentes = """
        SELECT 
            dia_semana,
            hora,
            laboratorio,
            asignatura,
            profesor
        FROM horario_fijo
        WHERE dia_semana = ?
        AND profesor IS NOT NULL 
        AND profesor != ''
        AND laboratorio NOT IN ('FLU 101', 'PRO 102', 'MEC 103', 'NEW 408', 'ELE 509', 'OND 510')
    """
    df_horario = db.fetch_df(query_docentes, (dia_semana,))
    
    # Filtrar docentes por hora (solo los que ya pasaron)
    if not df_horario.empty:
        df_horario = df_horario[df_horario['hora'].apply(obtener_hora_inicio) <= hora_actual]
    
    # Verificar cuáles ya marcaron asistencia
    docentes_pendientes = []
    if not df_horario.empty:
        for _, row in df_horario.iterrows():
            check_query = """
                SELECT COUNT(*) FROM reservas
                WHERE fecha = ?
                AND hora = ?
                AND laboratorio = ?
                AND codigo = 'PROFESOR'
                AND nombres = ?
                AND activo = 1
            """
            result = db.ejecutar(check_query, (hoy, row['hora'], row['laboratorio'], row['profesor']), fetch=True)
            ya_marcó = result[0][0] > 0 if result else False
            
            if not ya_marcó:
                docentes_pendientes.append({
                    'id': f"prof_{row['profesor']}_{row['hora']}",
                    'fecha': hoy,
                    'hora': row['hora'],
                    'laboratorio': row['laboratorio'],
                    'banco': 0,
                    'codigo': 'PROFESOR',
                    'nombres': row['profesor'],
                    'proyecto': row['asignatura'],
                    'tipo': 'Docente'
                })
    
    df_docentes = pd.DataFrame(docentes_pendientes) if docentes_pendientes else pd.DataFrame()
    
    # ===== 3. COMBINAR =====
    if not df_estudiantes.empty and not df_docentes.empty:
        df_combinado = pd.concat([df_estudiantes, df_docentes], ignore_index=True)
    elif not df_estudiantes.empty:
        df_combinado = df_estudiantes
    elif not df_docentes.empty:
        df_combinado = df_docentes
    else:
        df_combinado = pd.DataFrame()
    
    # Ordenar por hora
    if not df_combinado.empty:
        df_combinado = df_combinado.sort_values('hora')
    
    return df_combinado

def contar_asistencias_pendientes():
    """
    Retorna el número de asistencias pendientes del día actual.
    """
    pendientes = obtener_asistencias_pendientes()
    return len(pendientes)

def mostrar_panel_asistencias_pendientes():
    """
    Muestra un panel con el contador de asistencias pendientes del día actual.
    La lista de pendientes está dentro de un expander para no ocupar espacio.
    """
    pendientes = obtener_asistencias_pendientes()
    total_pendientes = len(pendientes)
    hora_actual = datetime.now().strftime("%H:%M")
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")
    
    # Contar cuántos son docentes y estudiantes
    if not pendientes.empty:
        docentes_pendientes = len(pendientes[pendientes['tipo'] == 'Docente'])
        estudiantes_pendientes = len(pendientes[pendientes['tipo'] == 'Estudiante'])
    else:
        docentes_pendientes = 0
        estudiantes_pendientes = 0
    
    # ===== CONTADOR VISUAL =====
    st.divider()
    
    if total_pendientes > 0:
        st.markdown(f"""
        <div style="
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 8px;
            padding: 12px 16px;
        ">
            <h4 style="margin: 0; color: #856404;">⚠️ Asistencias Pendientes - Hoy ({fecha_hoy})</h4>
            <p style="margin: 4px 0 0 0; color: #856404;">
                Total: <strong>{total_pendientes}</strong> 
                | Docentes: <strong>{docentes_pendientes}</strong> 
                | Estudiantes: <strong>{estudiantes_pendientes}</strong>
                <br><small style="color: #856404;">Hora actual: {hora_actual}</small>
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="
            background-color: #d4edda;
            border: 1px solid #28a745;
            border-radius: 8px;
            padding: 12px 16px;
        ">
            <h4 style="margin: 0; color: #155724;">✅ Todo al día</h4>
            <p style="margin: 4px 0 0 0; color: #155724;">
                No hay asistencias pendientes de marcar para hoy.
                <br><small>Hora actual: {hora_actual}</small>
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # ===== LISTA DENTRO DE EXPANDER =====
    if total_pendientes > 0:
        with st.expander(f"📋 Ver y marcar asistencias ({total_pendientes} pendientes)", expanded=False):
            st.caption("Haz clic en 'Asistió' o 'No asistió' para cada persona")
            st.divider()
            
            for idx, row in pendientes.iterrows():
                col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
                
                with col1:
                    st.write(row['hora'])
                with col2:
                    st.write(row['laboratorio'])
                with col3:
                    st.write(f"{row['nombres']} ({row['tipo']})")
                with col4:
                    if st.button("Asistió", key=f"asi_{idx}_{row['id']}", use_container_width=True):
                        if row['codigo'] == 'PROFESOR':
                            res.registrar_asistencia_docente(
                                row['fecha'],
                                row['hora'],
                                row['laboratorio'],
                                row['nombres'],
                                row['proyecto'],
                                "Si",
                                None
                            )
                        else:
                            res.actualizar_asiste(row['id'], "Si", None)
                        st.rerun()
                with col5:
                    if st.button("No asistió", key=f"no_{idx}_{row['id']}", use_container_width=True):
                        st.session_state[f"tecnico_no_{idx}_{row['id']}"] = True
                        st.rerun()
                
                # Modal para técnico
                if st.session_state.get(f"tecnico_no_{idx}_{row['id']}", False):
                    with st.popover(f"Confirmar inasistencia", use_container_width=True):
                        st.warning(f"Marcar como 'No asistió' a {row['nombres']}")
                        tecnico = st.selectbox(
                            "Técnico", 
                            TECNICOS, 
                            key=f"tecnico_confirm_{idx}_{row['id']}"
                        )
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Confirmar", key=f"confirm_no_{idx}_{row['id']}"):
                                if row['codigo'] == 'PROFESOR':
                                    res.registrar_asistencia_docente(
                                        row['fecha'],
                                        row['hora'],
                                        row['laboratorio'],
                                        row['nombres'],
                                        row['proyecto'],
                                        "No",
                                        tecnico
                                    )
                                else:
                                    res.actualizar_asiste(row['id'], "No", tecnico)
                                del st.session_state[f"tecnico_no_{idx}_{row['id']}"]
                                st.rerun()
                        with col2:
                            if st.button("Cancelar", key=f"cancel_no_{idx}_{row['id']}"):
                                del st.session_state[f"tecnico_no_{idx}_{row['id']}"]
                                st.rerun()
                
                st.divider()
    else:
        st.button("Sin pendientes hoy", disabled=True, use_container_width=True)
    
    st.divider()