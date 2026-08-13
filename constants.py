# constants.py

# ============================================================
#  LABORATORIOS PRINCIPALES (PARA RESERVAS)
# ============================================================

LABORATORIOS = {
    "602": 12,
    "603": 9,
    "604": 8,
    "607": 10,
    "Maquinas A": 4,
    "Maquinas B": 8,
    "Comunicaciones": 8,
    "Automatizacion": 6,
    "Control": 6
}

# ============================================================
#  NOMBRES PARA MOSTRAR EN LA INTERFAZ
# ============================================================

LABS_NAMES = {
    "602": "INST 602",
    "603": "ELEA 603",
    "604": "ELEB 604",
    "Maquinas B": "MAQ B 605",
    "Maquinas A": "MAQ A 606",
    "607": "CIR 607",
    "Comunicaciones": "COM 610",
    "Automatizacion": "AUT 705",
    "Control": "CON 708"
}

# ============================================================
#  LISTAS DE TÉCNICOS, DÍAS Y HORAS
# ============================================================

TECNICOS = [
    "Camilo Pérez", "Carlos Rodriguez", "Vannesa Cadena",
    "Felipe Paez", "Juan Cañas", "Nelson Granados",
    "Santiago Ossa", "María Buitrago", "Paula Mejía",
    "Hellen Galindo", "Karen Niño"
]

DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"]
HORAS = [f"{h:02d}:00-{h+2:02d}:00" for h in range(6, 22, 2)]

DIA_MAP = {
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miercoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sabado",
    "Sunday": "Domingo"
}

# ============================================================
#  ORDEN DE LABORATORIOS (CALENDARIO INTERACTIVO)
# ============================================================

LABS_ORDEN = [
    "602",
    "603",
    "604",
    "Maquinas B",
    "Maquinas A",
    "607",
    "Comunicaciones",
    "Automatizacion",
    "Control"
]

# ============================================================
#  LABORATORIOS DE FÍSICA (SOLO PARA HORARIO FIJO)
# ============================================================

LABS_FISICA_DICT = {
    "FLU 101": 0,
    "PRO 102": 0,
    "MEC 103": 0,
    "NEW 408": 0,
    "ELE 509": 0,
    "OND 510": 0
}

# Unir todos los laboratorios para el horario fijo
LABS_HORARIO = {**LABORATORIOS, **LABS_FISICA_DICT}

# Nombres para mostrar en horario fijo
LABS_NAMES_HORARIO = {
    **LABS_NAMES,
    "FLU 101": "FLU 101",
    "PRO 102": "PRO 102",
    "MEC 103": "MEC 103",
    "NEW 408": "NEW 408",
    "ELE 509": "ELE 509",
    "OND 510": "OND 510"
}

# Orden de laboratorios en horario fijo (con los nuevos)
LABS_ORDEN_HORARIO = [
    "602", "603", "604", "Maquinas B", "Maquinas A", "607",
    "Comunicaciones", "Automatizacion", "Control",
    "FLU 101", "PRO 102", "MEC 103", "NEW 408", "ELE 509", "OND 510"
]

# ============================================================
#  LABORATORIOS DE FÍSICA (LISTA PARA REFERENCIA)
# ============================================================

LABS_FISICA = ["FLU 101", "PRO 102", "MEC 103", "NEW 408", "ELE 509", "OND 510"]