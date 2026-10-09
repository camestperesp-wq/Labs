from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import database as db
import horario_fijo as hf
import reservas
import calendario


class MonitoresReservasTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temp.name) / "monitores.db")
        self.db_patch.start()
        db.init_db()
        hf.set_horario_celda("Viernes", "08:00-10:00", "604", "Adicional", "Adicional", "ANA TORRES", "")
        hf.set_horario_celda("Lunes", "08:00-10:00", "602", "Adicional", "Adicional", "LUIS PEREZ", "")

    def tearDown(self):
        db.clear_cache()
        self.db_patch.stop()
        self.temp.cleanup()

    def test_cambio_es_por_fecha_y_no_modifica_horario_semanal(self):
        reservas.asignar_monitor_sesion("2026-10-09", "08:00-10:00", "604", "LUIS PEREZ")
        estado = calendario._obtener_estado_celda("Viernes", "604", "2026-10-09", "08:00-10:00")
        self.assertEqual(estado["monitor"], "LUIS PEREZ")
        self.assertEqual(hf.get_horario_celda("Viernes", "08:00-10:00", "604")["monitor"], "ANA TORRES")
        siguiente = calendario._obtener_estado_celda("Viernes", "604", "2026-10-16", "08:00-10:00")
        self.assertEqual(siguiente["monitor"], "ANA TORRES")
        reservas.asignar_monitor_sesion("2026-10-09", "08:00-10:00", "604", "")
        self.assertEqual(calendario._obtener_estado_celda("Viernes", "604", "2026-10-09", "08:00-10:00")["monitor"], "")
        with self.assertRaises(ValueError):
            reservas.asignar_monitor_sesion("2026-10-09", "08:00-10:00", "604", "Desconocido")

    def test_formulario_reservas_guarda_monitor(self):
        app = AppTest.from_string('''
import streamlit as st
import calendario
if 'labs_celda_seleccionada' not in st.session_state:
    estado = calendario._obtener_estado_celda('Viernes','604','2026-10-09','08:00-10:00')
    st.session_state.labs_celda_seleccionada = calendario._datos_celda_seleccionada('604','2026-10-09','08:00-10:00',estado)
calendario._render_detalle_celda_contenido()
''').run(timeout=20)
        self.assertFalse(app.exception)
        selector = next(s for s in app.selectbox if s.label == "Monitor de esta sesión")
        selector.set_value("LUIS PEREZ")
        next(b for b in app.button if b.label == "Guardar monitor").click().run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(reservas.obtener_monitores_sesion("2026-10-09")[("08:00-10:00", "604")], "LUIS PEREZ")


if __name__ == "__main__":
    unittest.main()
