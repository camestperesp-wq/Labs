"""Catálogo cerrado de rutas y permisos, compartido por HTTP y Streamlit."""
SECTIONS = {
    "horario": ("Horario general", "app_pages/horario.py"),
    "reservas": ("Reservas", "app_pages/reservas.py"),
    "prestamos": ("Préstamos pasillos", "app_pages/prestamos.py"),
    "deudores": ("Deudores", "app_pages/deudores.py"),
    "consultas": ("Consultas", "app_pages/consultas.py"),
    "cargar-datos": ("Cargar datos", "app_pages/cargar_datos.py"),
}
ROLE_PERMISSIONS = {role: frozenset((*SECTIONS, "alertas")) for role in ("administrador", "tecnico")}


def can_access(role, section):
    return section in ROLE_PERMISSIONS.get(role, frozenset())
