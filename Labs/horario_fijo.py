# horario_fijo.py

import database as db
from busqueda import normalizar_busqueda
from constants import TECNICOS


# Variantes históricas del mismo monitor. No fusionar personas por parecido.
_ALIAS_MONITORES = {
    "fabian alexander garcia telez": "FABIAN ALEXANDER GARCÍA TÉLLEZ",
    "fabian alexander garcia tellez": "FABIAN ALEXANDER GARCÍA TÉLLEZ",
    "yerson steven rodriguez torres": "YERSON STIVEN RODRIGUEZ TORRES",
    "yerson stiven rodriguez torres": "YERSON STIVEN RODRIGUEZ TORRES",
    "andres felipe gonzales gonzales": "ANDRES FELIPE GONZÁLEZ GONZÁLEZ",
    "andres felipe gonzalez gonzalez": "ANDRES FELIPE GONZÁLEZ GONZÁLEZ",
}


def obtener_monitores():
    """Monitores del horario, excluyendo técnicos y abreviaturas inequívocas."""
    filas = db.ejecutar(
        """SELECT DISTINCT trim(monitor) FROM horario_fijo
           WHERE trim(coalesce(monitor,'')) != '' ORDER BY 1 COLLATE NOCASE""",
        fetch=True,
    )
    monitores = {}
    tecnicos = {normalizar_busqueda(nombre) for nombre in TECNICOS}
    for fila in filas:
        nombre = " ".join(fila[0].split())
        nombre = _ALIAS_MONITORES.get(normalizar_busqueda(nombre), nombre)
        clave = normalizar_busqueda(nombre)
        if len(nombre.split()) >= 2 and clave not in tecnicos:
            monitores.setdefault(clave, nombre)

    def es_abreviatura(corto, completo):
        restantes = iter(completo.split())
        return all(any(palabra == candidata for candidata in restantes) for palabra in corto.split())

    resultado = []
    for clave, nombre in monitores.items():
        coincidencias = [otra for otra in monitores
                         if len(otra.split()) > len(clave.split()) and es_abreviatura(clave, otra)]
        # Solo unir abreviaturas cuando identifican a una única persona.
        if len(coincidencias) != 1:
            resultado.append(nombre)
    return resultado


def obtener_docentes():
    """Docentes disponibles en el horario y en los préstamos ya registrados."""
    filas = db.ejecutar("""SELECT trim(profesor) FROM horario_fijo WHERE trim(coalesce(profesor,'')) != ''
        UNION SELECT trim(nombres) FROM reservas WHERE codigo='PROFESOR'
        AND trim(coalesce(nombres,'')) != '' ORDER BY 1 COLLATE NOCASE""", fetch=True)
    return [fila[0] for fila in filas]

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
    if not str(asignatura or "").strip() and str(carrera or "").strip() == "Adicional":
        asignatura = "Adicional"
    elif not str(asignatura or "").strip() and str(carrera or "").strip() == "Práctica Libre":
        asignatura = "Práctica Libre"

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
