from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

import database as db
import calendario
import reservas
from constants import LABORATORIOS, TECNICOS


class CapacidadIntercambiosTest(unittest.TestCase):
    fecha = "2026-10-09"
    hora = "08:00-10:00"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temp.name) / "capacidad.db")
        self.db_patch.start()
        db.clear_cache()
        db.init_db()
        st.session_state.pop(reservas.CLAVE_INTERCAMBIOS_RESERVAS, None)

    def tearDown(self):
        st.session_state.pop(reservas.CLAVE_INTERCAMBIOS_RESERVAS, None)
        db.clear_cache()
        self.db_patch.stop()
        self.temp.cleanup()

    def grupo(self, cantidad=8, lab="604"):
        with db.get_connection() as conn:
            conn.executemany(
                """INSERT INTO reservas(fecha,hora,laboratorio,banco,codigo,nombres,proyecto,asiste,activo)
                   VALUES (?,?,?,?,?,?,'Ingeniería','',1)""",
                [(self.fecha, self.hora, lab, i, f"{lab}-{i}", f"Alumno {i}") for i in range(1, cantidad + 1)],
            )
        db.clear_cache()

    def trasladar(self, destino="603"):
        reservas.intercambiar_espacios_sesion(self.fecha, self.hora, "604", self.hora, destino)

    def estado(self, destino="603"):
        base = calendario._obtener_estado_celda("Viernes", "604", self.fecha, self.hora)
        return calendario._ajustar_capacidad_destino(base, self.fecha, self.hora, "604", destino)

    def test_ocho_de_ocho_a_nueve_habilita_banco_nueve_y_se_agota(self):
        self.grupo()
        self.trasladar()
        estado = self.estado()
        self.assertEqual((estado["ocupados"], estado["total"], estado["disponibles"]), (8, 9, 1))
        self.assertEqual(estado["bancos_disponibles"], [9])
        self.assertIn("8/9", estado["etiqueta"])
        self.assertTrue(estado["cupo_intercambio"])
        self.assertTrue(reservas.guardar_reserva((self.fecha, self.hora, "604", 9, "nuevo", "Nuevo", "Ingeniería", "", "", TECNICOS[0])))
        estado = self.estado()
        self.assertEqual((estado["ocupados"], estado["total"], estado["disponibles"]), (9, 9, 0))
        self.assertEqual(estado["bancos_disponibles"], [])
        self.assertEqual(LABORATORIOS["604"], 8)
        self.assertEqual(LABORATORIOS["603"], 9)
        with patch("streamlit.error"):
            self.assertFalse(reservas.guardar_reserva((self.fecha, self.hora, "604", 10, "otro", "Otro", "", "", "", TECNICOS[0])))

    def test_intercambio_rechaza_grupo_que_no_cabe_sin_perder_miembros(self):
        self.grupo()
        self.grupo(9, "603")
        with self.assertRaises(ValueError):
            self.trasladar()
        self.assertEqual(reservas.obtener_intercambios_fecha(self.fecha), {})
        self.assertEqual(db.ejecutar("SELECT COUNT(*) FROM reservas", fetch=True)[0][0], 17)

    def test_misma_capacidad_no_inventa_cupos(self):
        self.grupo()
        self.trasladar("Maquinas B")
        estado = self.estado("Maquinas B")
        self.assertEqual(estado["total"], 8)
        self.assertEqual(estado["disponibles"], 0)

    def test_sala_completa_conserva_ocho_bancos_al_agregar_el_noveno(self):
        db.ejecutar(
            """INSERT INTO reservas(fecha,hora,laboratorio,banco,codigo,nombres,asiste,activo)
               VALUES (?,?, '604',0,'PROFESOR','Docente','Si',1)""", (self.fecha, self.hora),
        )
        self.trasladar()
        self.assertEqual(self.estado()["bancos_disponibles"], [9])
        with patch("streamlit.error"):
            self.assertFalse(reservas.guardar_reserva((self.fecha, self.hora, "604", 1, "ocupado", "Otro", "", "", "", TECNICOS[0])))
        self.assertTrue(reservas.guardar_reserva((self.fecha, self.hora, "604", 9, "nuevo", "Nuevo", "", "", "", TECNICOS[0])))
        self.assertEqual(self.estado()["ocupados"], 9)
        self.assertEqual(self.estado()["disponibles"], 0)

    def test_clase_sin_lista_conserva_ocupacion_al_agregar_cupo_extra(self):
        # Solo el salón de origen tiene clase; el destino está vacío.
        with patch("horario_fijo.get_horario_celda", side_effect=lambda dia, hora, lab: {"asignatura": "Clase", "carrera": "Ingeniería"} if lab == "604" else None):
            self.trasladar()
            self.assertEqual(self.estado()["bancos_disponibles"], [9])
            self.assertTrue(reservas.guardar_reserva((self.fecha, self.hora, "604", 9, "nuevo", "Nuevo", "", "", "", TECNICOS[0])))
            self.assertEqual(self.estado()["ocupados"], 9)
            self.assertEqual(self.estado()["disponibles"], 0)

    def test_capacidad_se_recalcula_en_intercambios_encadenados(self):
        self.grupo()
        self.trasladar()
        reservas.intercambiar_espacios_sesion(self.fecha, self.hora, "603", self.hora, "602")
        self.assertEqual(reservas.capacidad_fisica_grupo(self.fecha, self.hora, "604"), 12)
        self.assertEqual(self.estado("602")["bancos_disponibles"], [9, 10, 11, 12])

    def test_modal_muestra_y_permite_seleccionar_cupo_extra(self):
        self.grupo()
        script = '''
import streamlit as st
import reservas
import calendario
if 'labs_celda_seleccionada' not in st.session_state:
    reservas.intercambiar_espacios_sesion('2026-10-09','08:00-10:00','604','08:00-10:00','603')
    base = calendario._obtener_estado_celda('Viernes','604','2026-10-09','08:00-10:00')
    data = calendario._datos_celda_seleccionada('604','2026-10-09','08:00-10:00',base)
    data['posicion_visual'] = ('08:00-10:00','603')
    st.session_state.labs_celda_seleccionada = data
calendario._render_detalle_celda_contenido()
'''
        app = AppTest.from_string(script).run(timeout=20)
        self.assertFalse(app.exception)
        bancos = [s for s in app.selectbox if "Banco" in s.label]
        self.assertEqual(len(bancos), 1)
        self.assertEqual(bancos[0].options, ["9"])
        self.assertTrue(any("1 banco(s)" in s.value for s in app.success))
        self.assertTrue(any("8/9" in s.value for s in app.markdown))


if __name__ == "__main__":
    unittest.main()
