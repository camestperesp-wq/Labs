#utils.py
from datetime import datetime
import database as db

def generar_multa(lab, fecha, hora):
    return f"No asisitó Lab {lab} - {datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m/%Y')} {hora}"

def actualizar_reservas_vencidas():
    hoy = datetime.now().date().strftime("%Y-%m-%d")
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""SELECT id, laboratorio, fecha, hora, codigo FROM reservas 
                     WHERE fecha < ? AND (asiste IS NULL OR asiste = '')""", (hoy,))
        rows = c.fetchall()
        for id_res, lab, fecha, hora, codigo in rows:
            
            # ===== NUEVO: Separar estudiantes de docentes =====
            if codigo == "PROFESOR":
                # Docente: solo marcar como 'No', sin multa
                db.ejecutar("UPDATE reservas SET asiste='No' WHERE id=?", (id_res,))
            else:
                # Estudiante: marcar como 'No' y generar multa
                fecha_hoy = datetime.now().date().strftime("%Y-%m-%d")
                motivo = f"No asistió a {lab} - {fecha} {hora}"
                
                estudiante = db.ejecutar("SELECT nombres FROM estudiantes WHERE codigo=?", (codigo,), fetch=True)
                if estudiante:
                    db.ejecutar("""
                        INSERT INTO multas 
                        (codigo_estudiante, fecha_multa, motivo, sancion, tecnico_asigna, pagado)
                        VALUES (?, ?, ?, ?, ?, 'NO')
                    """, (codigo, fecha_hoy, motivo, "", "Sistema (vencida)"))
                
                db.ejecutar("UPDATE reservas SET asiste='No' WHERE id=?", (id_res,))
        
        conn.commit()
        return len(rows)
def parse_fecha_a_espanol(fecha_str):
    """Convierte fecha YYYY-MM-DD a día de la semana en español."""
    from constants import DIA_MAP
    dia_semana = datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%A")
    return DIA_MAP.get(dia_semana, dia_semana)

def formatear_fecha_espanol(fecha_str):
    """Devuelve dd/mm/yyyy."""
    return datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%d/%m/%Y")