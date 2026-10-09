from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

import database as db
import multas
import prestamos_pasillos as prestamos
import reservas
from constants import TECNICOS


class CorreccionesModulosTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temporal.name) / "prueba.db")
        self.db_patch.start()
        db.init_db()
        prestamos._invalidar_cache_lecturas()
        st.session_state.pop(reservas.CLAVE_INTERCAMBIOS_RESERVAS, None)

    def tearDown(self):
        prestamos._invalidar_cache_lecturas()
        st.session_state.pop(reservas.CLAVE_INTERCAMBIOS_RESERVAS, None)
        self.db_patch.stop()
        self.temporal.cleanup()

    def equipos(self):
        for i in range(3):
            prestamos.registrar_equipo(str(i), f"Equipo {i}", f"INT-{i}")
        return prestamos.obtener_equipos()["id"].tolist()

    def test_ampliacion_devolucion_parcial_y_cierre(self):
        a, b, c = self.equipos()
        prestamo = prestamos.crear_prestamo([a], "123", TECNICOS[0])
        self.assertEqual(prestamo, prestamos.crear_prestamo([b, c], "123", TECNICOS[1]))
        self.assertEqual(len(prestamos.obtener_prestamos("PRESTADO")), 1)
        prestamos.registrar_devolucion(prestamo, TECNICOS[0], equipos_ids=[b])
        self.assertEqual(set(prestamos.obtener_elementos_pendientes(prestamo)["id"]), {a, c})
        self.assertIn(b, prestamos.obtener_equipos(True)["id"].tolist())
        self.assertEqual(int(prestamos.obtener_prestamos("PRESTADO").iloc[0]["cantidad_equipos"]), 2)
        with self.assertRaises(ValueError):
            prestamos.registrar_devolucion(prestamo, TECNICOS[0], equipos_ids=[b])
        prestamos.registrar_devolucion(prestamo, TECNICOS[0])
        self.assertTrue(prestamos.obtener_prestamos("PRESTADO").empty)
        self.assertEqual(len(prestamos.obtener_equipos(True)), 3)

    def test_ampliacion_rechazada_es_atomica(self):
        a, b, c = self.equipos()
        prestamo = prestamos.crear_prestamo([a], "123", TECNICOS[0])
        prestamos.crear_prestamo([c], "456", TECNICOS[0])
        with self.assertRaises(ValueError):
            prestamos.crear_prestamo([b, c], "123", TECNICOS[0])
        self.assertEqual(prestamos.obtener_elementos_pendientes(prestamo)["id"].tolist(), [a])
        self.assertIn(b, prestamos.obtener_equipos(True)["id"].tolist())

    def test_fecha_retorno_prevalece_sobre_estado_antiguo(self):
        a, _, _ = self.equipos()
        prestamo = prestamos.crear_prestamo([a], "123", TECNICOS[0])
        db.ejecutar("UPDATE prestamos_pasillo SET fecha_retorno='2026-10-01 10:00:00' WHERE id=?", (prestamo,))
        self.assertTrue(prestamos.obtener_prestamos("PRESTADO").empty)
        self.assertIn(a, prestamos.obtener_equipos(True)["id"].tolist())
        db.init_db()
        db.init_db()
        self.assertEqual(db.ejecutar("SELECT estado FROM prestamos_pasillo WHERE id=?", (prestamo,), fetch=True)[0][0], "DEVUELTO")
        self.assertEqual(len(prestamos.obtener_prestamos("DEVUELTO")), 1)

    def test_intercambio_incluye_todos_y_encadena_con_salon_vacio(self):
        filas = pd.DataFrame([
            {"id": i, "fecha": "2026-10-09", "hora": "08:00-10:00", "laboratorio": lab, "asiste": estado}
            for i, (lab, estado) in enumerate([
                ("602", "Si"), ("602", "No"), ("602", ""),
                ("603", "Si"), ("603", ""),
            ])
        ])
        reservas.intercambiar_espacios_sesion("2026-10-09", "08:00-10:00", "602", "08:00-10:00", "603")
        resultado = reservas.aplicar_intercambios_busqueda(filas)
        self.assertEqual(resultado.laboratorio.tolist(), ["603"] * 3 + ["602"] * 2)
        reservas.intercambiar_espacios_sesion("2026-10-09", "08:00-10:00", "603", "10:00-12:00", "604")
        resultado = reservas.aplicar_intercambios_busqueda(filas)
        self.assertEqual(resultado.laboratorio.tolist(), ["604"] * 3 + ["602"] * 2)
        self.assertEqual(reservas.coordenada_origen_visual("2026-10-09", "10:00-12:00", "604"), ("08:00-10:00", "602"))
        self.assertEqual(resultado.id.tolist(), filas.id.tolist())
        self.assertEqual(resultado.asiste.tolist(), filas.asiste.tolist())

    def test_sanciones_editar_levantar_y_conflicto(self):
        multas.agregar_multa("123", "2026-10-09", "Motivo", "Inicial", TECNICOS[0])
        multa_id = db.ejecutar("SELECT id FROM multas", fetch=True)[0][0]
        multas.actualizar_sanciones_tabla([(multa_id, "Inicial", TECNICOS[0], "Nueva", TECNICOS[1])])
        with self.assertRaises(ValueError):
            multas.actualizar_sanciones_tabla([(multa_id, "Inicial", TECNICOS[0], "Vieja", TECNICOS[0])])
        multas.actualizar_sanciones_tabla([(multa_id, "Nueva", TECNICOS[1], "", TECNICOS[1])])
        self.assertEqual(db.ejecutar("SELECT sancion,tecnico_asigna FROM multas", fetch=True)[0], ("", TECNICOS[1]))

    def test_pantallas_deudores_y_reportes_sin_excepciones(self):
        multas.agregar_multa("123", "2026-10-09", "Motivo", "Inicial", TECNICOS[0])
        with patch("auth.require_section"), patch("auth.require_login", return_value="tecnico"):
            app = AppTest.from_string("from ui_components import mostrar_deudores\nmostrar_deudores()").run(timeout=20)
        self.assertFalse(app.exception)
        app = AppTest.from_string("from reportes import mostrar_reporte_asistencia_docentes\nmostrar_reporte_asistencia_docentes()").run(timeout=20)
        self.assertFalse(app.exception)
        labels = [s.label for s in app.selectbox]
        self.assertIn("Laboratorio", labels)
        self.assertIn("INST 602", app.selectbox[0].options)


if __name__ == "__main__":
    unittest.main()
