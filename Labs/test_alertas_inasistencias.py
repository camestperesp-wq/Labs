from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

import database as db
import reservas
import multas
import prestamos_pasillos as prestamos
from alertas_inasistencias import obtener_alertas
from constants import TECNICOS
from utils import actualizar_reservas_vencidas
from unittest.mock import patch


class RevisionTest(unittest.TestCase):
    def setUp(self):
        self.original = db.DB_PATH
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "prueba.db"
        db.init_db()
        prestamos._invalidar_cache_lecturas()
        self.fecha = (datetime.now() - timedelta(days=1)).date().isoformat()
        db.ejecutar("INSERT INTO estudiantes(codigo,nombres,proyecto) VALUES ('123','Ana Perez','Proyecto')")
        db.ejecutar("""INSERT INTO reservas(fecha,hora,laboratorio,banco,codigo,nombres,proyecto,asiste,activo)
                      VALUES (?, '08:00-10:00', 'ELE 505',1,'123','Ana Perez','Proyecto','',1)""", (self.fecha,))
        self.id = db.ejecutar("SELECT id FROM reservas", fetch=True)[0][0]

    def tearDown(self):
        prestamos._invalidar_cache_lecturas()
        db.DB_PATH = self.original
        self.temp.cleanup()

    def test_vencimiento_solo_alerta_y_revision_manual_idempotente(self):
        actualizar_reservas_vencidas()
        self.assertEqual(len(obtener_alertas()), 1)
        self.assertEqual(db.ejecutar("SELECT count(*) FROM multas", fetch=True)[0][0], 0)
        reservas.revisar_inasistencia(self.id, 'No', TECNICOS[0], 'Observación de prueba', 'Revisión manual')
        self.assertTrue(obtener_alertas().empty)
        self.assertFalse(reservas.verificar_reserva_existente('123', self.fecha, '08:00-10:00'))
        multa = multas.obtener_multas_estudiante('123').iloc[0]
        self.assertEqual(multa.observaciones, 'Observación de prueba')
        with self.assertRaises(ValueError):
            reservas.revisar_inasistencia(self.id, 'No', TECNICOS[0])
        self.assertEqual(len(multas.obtener_multas_estudiante('123')), 1)
        self.assertTrue(reservas.guardar_reserva((self.fecha,'08:00-10:00','ELE 505',1,'456','Otro','Proyecto','','',TECNICOS[0])))

    def test_asistio_no_multa_y_busqueda_nombre(self):
        self.assertEqual(len(reservas.buscar_reservas_persona('Ana')), 1)
        reservas.revisar_inasistencia(self.id, 'Si', TECNICOS[0])
        self.assertTrue(obtener_alertas().empty)
        self.assertTrue(multas.obtener_multas_estudiante('123').empty)

    def test_no_asistio_fuera_de_revision_no_genera_multa(self):
        reservas.actualizar_asiste(self.id, 'No')
        self.assertTrue(multas.obtener_multas_estudiante('123').empty)
        self.assertEqual(db.ejecutar("SELECT asiste FROM reservas", fetch=True)[0][0], 'No')

    def test_consumible_nombre_y_restriccion_solo_artix(self):
        for nombre, interno, consumible in [('Cable personalizado', '', True), ('FPGA Basys', 'B', False), ('Artix 7', 'A', False)]:
            prestamos.registrar_equipo('', nombre, interno, consumible)
        equipos = prestamos.obtener_equipos()
        for fila in equipos.itertuples():
            prestamo_id = prestamos.crear_prestamo([fila.id], '123', TECNICOS[0])
            limite = db.ejecutar('SELECT limite_fpga FROM prestamos_pasillo WHERE id=?', (prestamo_id,), fetch=True)[0][0]
            self.assertEqual(bool(limite), 'Artix' in fila.nombre)
        vista = prestamos.obtener_prestamos_activos_codigo('123')
        self.assertTrue(vista.equipos.str.contains('Cable personalizado', na=False).any())
        db.ejecutar("UPDATE prestamos_pasillo SET fecha_salida=?", (self.fecha + ' 08:00:00',))
        prestamos.sincronizar_incumplimientos()
        self.assertTrue(multas.obtener_multas_estudiante('123').empty)

    @patch("auth.require_section")
    def test_interfaz_revision_guarda_observaciones(self, _authorized):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string('from alertas_inasistencias import mostrar_alertas_inasistencias\nmostrar_alertas_inasistencias()').run()
        self.assertFalse(app.exception)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        app.selectbox[0].select(TECNICOS[0])
        app.text_area[0].input('Confirmado por el técnico')
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(multas.obtener_multas_estudiante('123').iloc[0].observaciones, 'Confirmado por el técnico')

    def test_migracion_limites_prestamos_existentes(self):
        prestamos.registrar_equipo('', 'FPGA genérica', 'F')
        equipo = int(prestamos.obtener_equipos().iloc[0].id)
        prestamo = prestamos.crear_prestamo([equipo], '123', TECNICOS[0])
        db.ejecutar("UPDATE prestamos_pasillo SET limite_fpga='2026-01-01 10:00:00' WHERE id=?", (prestamo,))
        db.init_db()
        self.assertIsNone(db.ejecutar('SELECT limite_fpga FROM prestamos_pasillo WHERE id=?', (prestamo,), fetch=True)[0][0])


if __name__ == '__main__':
    unittest.main()
