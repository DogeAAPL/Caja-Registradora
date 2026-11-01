"""Pruebas de las protecciones de datos del servidor local (iniciar.py).

Correr desde la carpeta del repositorio:  python -m unittest discover tests
Usan una carpeta temporal: nunca tocan la carpeta datos/ real.
"""
import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import iniciar  # noqa: E402

HOST = f"127.0.0.1:{iniciar.PORT}"
ORIGIN = "http://" + HOST


class ServidorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        iniciar.DATA_DIR = Path(self.tmp.name)
        iniciar.BACKUP_DIR = iniciar.DATA_DIR / "respaldos"
        iniciar._session["activa"] = "t"
        self.server = HTTPServer(("127.0.0.1", 0), iniciar.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def pedir(self, metodo, ruta, cuerpo=None, **cabeceras):
        h = {"Host": HOST, "Origin": ORIGIN, "Content-Type": "application/json",
             "X-Caja-Sesion": "t", "Sec-Fetch-Site": "same-origin"}
        h.update(cabeceras)
        h = {k: v for k, v in h.items() if v is not None}
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        c.request(metodo, ruta, body=None if cuerpo is None else json.dumps(cuerpo), headers=h)
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"null")

    def ventas(self, n):
        return [{"id": f"V{i:03d}", "total": 1000} for i in range(1, n + 1)]

    def test_no_se_borran_muchas_ventas_de_golpe(self):
        self.assertEqual(self.pedir("POST", "/api/data/ventas", self.ventas(5))[0], 200)
        self.assertEqual(self.pedir("POST", "/api/data/ventas", self.ventas(3))[0], 409)
        self.assertEqual(self.pedir("POST", "/api/data/ventas", self.ventas(4))[0], 200)  # borrar 1 sí
        self.assertEqual(len(self.pedir("GET", "/api/data/ventas")[1]), 4)

    def test_otra_pagina_no_puede_guardar(self):
        # Sin cuerpo: el servidor rechaza antes de leerlo (y Windows cortaría la conexión)
        self.assertEqual(self.pedir("POST", "/api/data/ventas", Origin="http://malo.com")[0], 403)
        self.assertEqual(self.pedir("POST", "/api/data/ventas", **{"X-Caja-Sesion": "otra"})[0], 409)
        self.assertEqual(self.pedir("POST", "/api/data/ventas", {"no": "lista"})[0], 400)

    def test_otra_pagina_no_puede_pedir_sesion(self):
        self.assertEqual(self.pedir("GET", "/api/session", **{"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(iniciar._session["activa"], "t")  # la caja sigue pudiendo guardar
        self.assertEqual(self.pedir("GET", "/api/session")[0], 200)

    def test_archivo_danado_no_se_lee_como_vacio(self):
        (iniciar.DATA_DIR / "ventas.json").write_text("{roto", encoding="utf-8")
        self.assertEqual(self.pedir("GET", "/api/data/ventas")[0], 500)
        self.assertEqual(self.pedir("POST", "/api/data/ventas", [])[0], 409)
        self.assertEqual((iniciar.DATA_DIR / "ventas.json").read_text(encoding="utf-8"), "{roto")


    def test_pdf_solo_para_la_caja(self):
        self.assertEqual(self.pedir("POST", "/api/pdf", **{"X-Caja-Sesion": "otra"})[0], 409)

    def test_pdf_del_reporte(self):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=90)
        c.request("POST", "/api/pdf", body=json.dumps({"html": "<html><body><h1>Cierre</h1></body></html>"}),
                  headers={"Host": HOST, "Origin": ORIGIN, "Content-Type": "application/json", "X-Caja-Sesion": "t"})
        r = c.getresponse()
        cuerpo = r.read()
        if r.status == 500 and not any(Path(p).exists() for p in iniciar._navegadores()):
            self.skipTest("no hay Edge ni Chrome en este computador")
        self.assertEqual(r.status, 200, cuerpo[:200])
        self.assertTrue(cuerpo.startswith(b"%PDF"))


class HtmlValidoTest(unittest.TestCase):
    def test_solo_acepta_la_pagina_de_la_caja(self):
        caja = (Path(__file__).resolve().parent.parent / "caja.html").read_bytes()
        self.assertTrue(iniciar._html_valido(caja))
        self.assertFalse(iniciar._html_valido(b"404: Not Found"))
        self.assertFalse(iniciar._html_valido(caja[: len(caja) // 2]))  # a medio subir


if __name__ == "__main__":
    unittest.main()
