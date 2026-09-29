from auth import require_section
require_section("consultas")

import reportes as rep
from app_shell import preparar_lector
preparar_lector()

rep.mostrar_busqueda_codigo()
