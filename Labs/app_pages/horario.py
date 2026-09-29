from auth import require_section
require_section("horario")

from ui_components import mostrar_horario_general
from app_shell import restaurar_scroll_horario
restaurar_scroll_horario()

mostrar_horario_general()
