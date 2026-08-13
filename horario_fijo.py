# horario_fijo.py

import database as db

def normalizar(texto):
    """Elimina espacios extra y convierte a minúsculas para comparar."""
    return texto.strip().lower()

def get_horario_celda(dia, hora, laboratorio):
    """
    Busca horario fijo normalizando el nombre del laboratorio.
    """
    lab_norm = normalizar(laboratorio)

    r = db.ejecutar("""SELECT asignatura, carrera, monitor, profesor 
                        FROM horario_fijo 
                        WHERE dia_semana=? AND hora=? AND LOWER(TRIM(laboratorio))=?""", 
                     (dia, hora, lab_norm), fetch=True)
    
    if r:
        return {"asignatura": r[0][0], "carrera": r[0][1], "monitor": r[0][2], "profesor": r[0][3]}
    
    return None

def set_horario_celda(dia, hora, laboratorio, asignatura, carrera, monitor, profesor):
    """Guarda el laboratorio sin modificar (tal como viene)."""
    existente = db.ejecutar("""SELECT COUNT(*) FROM horario_fijo 
                               WHERE dia_semana=? AND hora=? AND LOWER(TRIM(laboratorio))=LOWER(TRIM(?))""",
                            (dia, hora, laboratorio), fetch=True)
    if existente[0][0] > 0:
        db.ejecutar("""UPDATE horario_fijo 
                       SET asignatura=?, carrera=?, monitor=?, profesor=?
                       WHERE dia_semana=? AND hora=? AND LOWER(TRIM(laboratorio))=LOWER(TRIM(?))""",
                    (asignatura, carrera, monitor, profesor, dia, hora, laboratorio))
    else:
        db.ejecutar("""INSERT INTO horario_fijo 
                       (dia_semana, hora, laboratorio, asignatura, carrera, monitor, profesor)
                       VALUES (?,?,?,?,?,?,?)""",
                    (dia, hora, laboratorio, asignatura, carrera, monitor, profesor))

def delete_horario_celda(dia, hora, laboratorio):
    """Elimina usando normalización."""
    db.ejecutar("DELETE FROM horario_fijo WHERE dia_semana=? AND hora=? AND LOWER(TRIM(laboratorio))=LOWER(TRIM(?))", 
                 (dia, hora, laboratorio))