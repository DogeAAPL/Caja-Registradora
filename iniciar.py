#!/usr/bin/env python3
"""
Caja Registradora Nirvana - Instalador + Lanzador (con asistente gráfico)
==========================================================================
Compilado como un solo ejecutable (PyInstaller --onefile --windowed).

Qué hace cada vez que se ejecuta (es seguro correrlo varias veces):
  1. La PRIMERA vez, muestra un pequeño asistente gráfico: instala la app
     en una carpeta fija del usuario (~/CajaNirvana), crea el acceso
     directo en el Escritorio, y ofrece un botón "Abrir ahora".
  2. Las siguientes veces (ya instalada, usando el acceso directo), no
     muestra el asistente: abre la app directamente.
  3. Mientras la app está abierta, se ve un panel de control pequeño
     (con el logo) en vez de una ventana de consola — con un botón real
     "Cerrar aplicación".
  4. Levanta un servidor local (127.0.0.1) que sirve la app y expone una
     mini-API para leer/escribir los datos (productos, ventas, stats,
     configuración) como archivos de texto plano (JSON) en
     ~/CajaNirvana/datos/ — nada se guarda en el navegador.
  5. En segundo plano, revisa (máximo 1 vez por hora, con tiempo límite
     corto) si el caja.html de GitHub (DogeAAPL/Caja-Registradora, rama
     main) es distinto del instalado, y si lo es lo descarga. La ventana
     abierta sigue con la versión que ya cargó y muestra un aviso para
     recargar. Nunca bloquea el arranque.
     Solo actualiza caja.html — el propio .exe/instalador nunca se
     autoactualiza (eso siempre requiere generar un instalador nuevo).

Versión 2 (correcciones de seguridad de datos):
  - Copia de seguridad diaria automática de datos/ en datos/respaldos/
    (se conservan los últimos 30 días).
  - Si un archivo de datos está dañado, el servidor responde con error en
    vez de "vacío", y la app NO sobrescribe nada.
  - Solo una ventana de la caja puede guardar a la vez (la última abierta);
    las demás quedan bloqueadas con un aviso.
  - No se aceptan escrituras desde otras páginas web, y no se puede
    reemplazar ventas.json por una lista mucho más corta por error.
  - caja.html instalado ya no se pisa en cada arranque: solo cuando este
    .exe trae una versión distinta a la que se instaló la última vez.
"""
import os
import sys
import json
import shutil
import subprocess
import webbrowser
import threading
import time
import hashlib
import datetime
import urllib.request
import urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import tkinter as tk
from tkinter import messagebox

APP_NAME = "CajaNirvana"
PORT     = 7331

# ---------------------------------------------------------------------------
# Auto-actualización de caja.html desde GitHub
# ---------------------------------------------------------------------------
# El repositorio es PÚBLICO y no lleva ninguna credencial ni dato sensible —
# tus ventas/productos nunca salen de este computador, viven solo en la
# carpeta datos/, que nunca se sube a GitHub (.gitignore).
#
# Regla: el caja.html que esté en la rama main de GitHub es el que usa la
# caja. Al abrir el programa (máximo una vez por hora) se compara con el
# instalado y, si es distinto, se descarga y queda listo para la próxima vez
# que se recargue la ventana de la caja.
GITHUB_USER   = "DogeAAPL"
GITHUB_REPO   = "Caja-Registradora"
GITHUB_BRANCH = "main"

UPDATE_CHECK_TIMEOUT      = 5   # segundos máximo esperando respuesta de GitHub
UPDATE_CHECK_EVERY_HOURS  = 1   # no revisar más de una vez por hora

BACKUP_KEEP_DAYS = 30  # días de copias de seguridad de datos/ que se conservan

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
def bundled_dir() -> Path:
    """Carpeta donde están los recursos empacados (--add-data) o, si se
    corre como script .py normal, la carpeta del propio script."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent

BUNDLE_DIR  = bundled_dir()
INSTALL_DIR = Path.home() / APP_NAME
# Nombre fijo que tendrá el programa YA instalado (siempre el mismo, sin
# importar cómo se llame el instalador que el usuario descargó/compiló).
INSTALLED_EXE_NAME = "CajaNirvana.exe" if sys.platform == "win32" else "CajaNirvana"
DATA_DIR    = INSTALL_DIR / "datos"
BACKUP_DIR  = DATA_DIR / "respaldos"
# Estado de la auto-actualización. Archivo aparte de config.json para que la
# app web (que reescribe config.json completo) nunca lo pise.
UPDATE_STATE = DATA_DIR / "actualizacion.json"
APP_HTML    = INSTALL_DIR / "caja.html"
APP_LOGO    = INSTALL_DIR / "LogoNirvana-Cuadrado.png"
APP_LOGO_LAUNCHER = INSTALL_DIR / "LogoNirvana-Launcher.png"
APP_ICO     = INSTALL_DIR / "LogoNirvana.ico"          # variante con chip: .exe / acceso directo
FAVICON_ICO = INSTALL_DIR / "favicon.ico"               # variante plana: favicon del navegador
# Huella del caja.html que trajo el último .exe instalado (ver ensure_installed)
HTML_VERSION_MARK = INSTALL_DIR / ".caja_html_empacado"

ALLOWED_KEYS = {"productos", "ventas", "stats", "config"}
# Tipo esperado de cada archivo (para no guardar basura por error)
KEY_TYPES = {"productos": list, "ventas": list, "stats": dict, "config": dict}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Instalación (idempotente: correr varias veces no rompe nada)
# ---------------------------------------------------------------------------
def ensure_installed():
    """Copia los archivos de la app y el propio ejecutable a INSTALL_DIR.
    NUNCA toca la carpeta datos/ (ahí vive la info del negocio).
    Devuelve (ruta_del_ejecutable_instalado, es_primera_instalacion)."""
    was_installed_before = INSTALL_DIR.exists() and APP_HTML.exists()

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    src_html = BUNDLE_DIR / "caja.html"
    src_logo = BUNDLE_DIR / "LogoNirvana-Cuadrado.png"
    src_logo_launcher = BUNDLE_DIR / "LogoNirvana-Launcher.png"
    src_ico  = BUNDLE_DIR / "LogoNirvana.ico"
    src_favicon = BUNDLE_DIR / "favicon.ico"

    # caja.html: solo se copia si no existe, o si este .exe trae una versión
    # DISTINTA a la que se instaló la última vez. Así no se pierden cambios
    # hechos a mano ni actualizaciones descargadas de GitHub.
    if src_html.exists():
        bundled_sha = _sha256(src_html)
        try:
            last_sha = HTML_VERSION_MARK.read_text(encoding="utf-8").strip()
        except Exception:
            last_sha = ""
        if not APP_HTML.exists() or bundled_sha != last_sha:
            if APP_HTML.exists():
                try:
                    os.chmod(APP_HTML, 0o644)  # por si quedó de solo lectura
                except Exception:
                    pass
                if _sha256(APP_HTML) != bundled_sha:
                    try:
                        shutil.copy2(APP_HTML, INSTALL_DIR / "caja.html.bak")
                    except Exception:
                        pass
            shutil.copy2(src_html, APP_HTML)
            try:
                HTML_VERSION_MARK.write_text(bundled_sha, encoding="utf-8")
            except Exception:
                pass

    for src, dst in ((src_logo, APP_LOGO), (src_logo_launcher, APP_LOGO_LAUNCHER),
                     (src_ico, APP_ICO), (src_favicon, FAVICON_ICO)):
        if src.exists():
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass  # p. ej. archivo bloqueado; no es crítico

    first_install = not was_installed_before

    if getattr(sys, "frozen", False):
        current_exe = Path(sys.executable).resolve()
        target_exe  = INSTALL_DIR / INSTALLED_EXE_NAME
        if current_exe != target_exe:
            try:
                shutil.copy2(current_exe, target_exe)
                if sys.platform != "win32":
                    os.chmod(target_exe, 0o755)
            except Exception:
                target_exe = current_exe
        return target_exe, first_install

    return Path(__file__).resolve(), first_install


def _read_config() -> dict:
    """Lee datos/config.json completo (puede traer, por ejemplo, el número
    de WhatsApp guardado desde la app). Nunca lanza excepción."""
    f = DATA_DIR / "config.json"
    try:
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


# Un solo escritor a la vez sobre datos/ (servidor y revisión de updates)
_data_lock = threading.Lock()


def _write_config(cfg: dict) -> None:
    """Escritura atómica de config.json, preservando lo que ya había ahí
    (por ejemplo, el número de WhatsApp que guarda la propia app web)."""
    try:
        with _data_lock:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = DATA_DIR / "config.tmp"
            tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(DATA_DIR / "config.json")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Copias de seguridad
# ---------------------------------------------------------------------------
def backup_today() -> None:
    """Copia los JSON de datos/ a datos/respaldos/AAAA-MM-DD/ una vez al día
    (la primera vez que se llama ese día). Conserva los últimos
    BACKUP_KEEP_DAYS días. Nunca lanza excepción."""
    try:
        today = datetime.date.today().isoformat()
        dest = BACKUP_DIR / today
        if dest.exists():
            return
        files = [DATA_DIR / (k + ".json") for k in sorted(ALLOWED_KEYS)]
        files = [f for f in files if f.exists()]
        if not files:
            return
        tmp = BACKUP_DIR / (today + ".tmp")
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copy2(f, tmp / f.name)
        tmp.rename(dest)  # la carpeta del día aparece completa o no aparece
        dias = sorted(p for p in BACKUP_DIR.iterdir()
                      if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")
        for viejo in dias[:-BACKUP_KEEP_DAYS]:
            shutil.rmtree(viejo, ignore_errors=True)
    except Exception:
        pass


def _git_blob_sha(data: bytes) -> str:
    """El mismo identificador que GitHub calcula para cada archivo (SHA-1
    de "blob <tamaño>\\0<contenido>"). Permite saber si el caja.html
    instalado es idéntico al de GitHub sin descargarlo."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _read_update_state() -> dict:
    try:
        if UPDATE_STATE.exists():
            return json.loads(UPDATE_STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_update_state(state: dict) -> None:
    try:
        with _data_lock:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = UPDATE_STATE.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(UPDATE_STATE)
    except Exception:
        pass


# Texto corto que muestra el panel de control sobre la última revisión
update_status = {"texto": ""}


def _html_valido(data: bytes) -> bool:
    """Verificación de cordura antes de reemplazar caja.html: tiene que ser
    la página de la caja (y no, por ejemplo, una página de error)."""
    low = data.lower()
    return (len(data) > 5000 and b"<html" in low and b"/api/data/" in data
            and b"initApp" in data and low.rstrip().endswith(b"</html>"))


def check_for_updates() -> None:
    """Revisa (en un hilo aparte, nunca bloquea la interfaz) si el caja.html
    de GitHub es distinto del instalado. Si lo es, verifica que sea la
    página de la caja y lo instala (dejando el anterior como caja.html.bak).
    La ventana de la caja abierta sigue funcionando con la versión que ya
    cargó; la nueva se usa al recargarla. Cualquier problema (sin internet,
    GitHub caído, etc.) se ignora en silencio. Solo toca caja.html — nunca
    el .exe/instalador ni la carpeta datos/."""
    if GITHUB_USER == "TU_USUARIO_DE_GITHUB" or GITHUB_REPO == "TU_REPOSITORIO":
        return  # todavía no configurado

    state = _read_update_state()
    if time.time() - state.get("ultimaRevision", 0) < UPDATE_CHECK_EVERY_HOURS * 3600:
        return  # ya se revisó hace poco, no molestar a GitHub de más

    # Se descarga directamente el archivo (≈120 KB). No se usa la API de
    # GitHub para no depender de su límite de consultas.
    raw_url = (f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}"
               f"/{GITHUB_BRANCH}/caja.html")
    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "CajaNirvana",
                                                       "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=UPDATE_CHECK_TIMEOUT * 3) as resp:
            nuevo_html = resp.read()
    except Exception:
        update_status["texto"] = "Sin conexión con GitHub (se reintenta al abrir)"
        return  # sin internet, repo no encontrado, timeout, etc. → se reintenta luego

    remote_sha = _git_blob_sha(nuevo_html)
    try:
        local_sha = _git_blob_sha(APP_HTML.read_bytes()) if APP_HTML.exists() else ""
    except Exception:
        local_sha = ""

    if remote_sha == local_sha:
        state["ultimaRevision"] = time.time()
        state["version"] = remote_sha[:7]
        _write_update_state(state)
        update_status["texto"] = f"Caja al día (versión {remote_sha[:7]})"
        return

    # Tiene que ser la página de la caja (no una página de error ni un
    # archivo a medio subir).
    if not _html_valido(nuevo_html):
        update_status["texto"] = "El caja.html de GitHub no parece válido; no se instaló"
        return  # se reintenta la próxima vez

    try:
        if APP_HTML.exists():
            try:
                os.chmod(APP_HTML, 0o644)
            except Exception:
                pass
            shutil.copy2(APP_HTML, INSTALL_DIR / "caja.html.bak")  # respaldo por si acaso
        pendiente = INSTALL_DIR / "caja.html.nuevo"
        pendiente.write_bytes(nuevo_html)
        pendiente.replace(APP_HTML)  # reemplazo atómico
    except Exception:
        return

    state["ultimaRevision"] = time.time()
    state["version"] = remote_sha[:7]
    state["actualizadoEl"] = datetime.datetime.now().isoformat(timespec="seconds")
    _write_update_state(state)
    update_status["texto"] = f"Caja actualizada desde GitHub (versión {remote_sha[:7]})"


def desktop_dir() -> Path:
    if sys.platform.startswith("linux"):
        try:
            out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=2)
            p = Path(out.stdout.strip())
            if out.returncode == 0 and str(p) and p.exists():
                return p
        except Exception:
            pass
        for name in ("Desktop", "Escritorio"):
            p = Path.home() / name
            if p.exists():
                return p
        return Path.home() / "Desktop"

    if sys.platform == "win32":
        # OJO: en muchos equipos con OneDrive, el Escritorio "real" que ve el
        # usuario NO es C:\Users\<usuario>\Desktop, sino algo como
        # C:\Users\<usuario>\OneDrive\Desktop. Windows guarda la ruta
        # verdadera en el registro — la leemos de ahí en vez de asumirla.
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            )
            raw, _ = winreg.QueryValueEx(key, "Desktop")
            winreg.CloseKey(key)
            resolved = Path(os.path.expandvars(raw))
            if resolved.exists():
                return resolved
        except Exception:
            pass
        return Path.home() / "Desktop"

    # Fallback general (otros sistemas)
    return Path.home() / "Desktop"


def _ps_quote(s) -> str:
    """Dentro de comillas simples de PowerShell, una ' se escribe ''."""
    return str(s).replace("'", "''")


def create_shortcut(exe_path: Path) -> None:
    """Crea el acceso directo del Escritorio. Lanza una excepción si algo
    falla (la interfaz gráfica decide cómo mostrarlo); no imprime nada,
    porque la app corre sin consola."""
    dest = desktop_dir()
    dest.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        lnk = dest / "Caja Nirvana.lnk"
        if lnk.exists():
            return
        if APP_ICO.exists():
            icon = APP_ICO
        elif APP_LOGO_LAUNCHER.exists():
            icon = APP_LOGO_LAUNCHER
        elif APP_LOGO.exists():
            icon = APP_LOGO
        else:
            icon = exe_path
        ps_cmd = (
            "$s = (New-Object -COM WScript.Shell).CreateShortcut('{lnk}'); "
            "$s.TargetPath = '{target}'; "
            "$s.WorkingDirectory = '{workdir}'; "
            "$s.IconLocation = '{icon}'; "
            "$s.Save()"
        ).format(lnk=_ps_quote(lnk), target=_ps_quote(exe_path),
                 workdir=_ps_quote(INSTALL_DIR), icon=_ps_quote(icon))
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                        check=True, creationflags=flags)

    else:  # Linux
        desktop_file = dest / "caja-nirvana.desktop"
        if desktop_file.exists():
            return
        if APP_LOGO_LAUNCHER.exists():
            icon = str(APP_LOGO_LAUNCHER)
        elif APP_LOGO.exists():
            icon = str(APP_LOGO)
        else:
            icon = "utilities-terminal"
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Caja Nirvana\n"
            f'Exec="{exe_path}"\n'
            f"Icon={icon}\n"
            "Terminal=false\n"
            "Categories=Office;\n"
        )
        desktop_file.write_text(content, encoding="utf-8")
        os.chmod(desktop_file, 0o755)
        # Mejor esfuerzo: marcar como confiable en GNOME/Nautilus moderno.
        # (si el DE no lo soporta, no es un error real, solo se ignora)
        subprocess.run(["gio", "set", str(desktop_file), "metadata::trusted", "true"], check=False)


# ---------------------------------------------------------------------------
# Servidor local + mini-API de datos en texto plano
# ---------------------------------------------------------------------------
STATIC_FILES = {
    "/": "caja.html",
    "/caja.html": "caja.html",
    "/LogoNirvana-Cuadrado.png": "LogoNirvana-Cuadrado.png",
    "/favicon.ico": "favicon.ico",
}
MIME = {".html": "text/html; charset=utf-8", ".png": "image/png", ".ico": "image/x-icon"}


# Solo se atienden peticiones dirigidas a este servidor (evita "DNS
# rebinding") y solo se aceptan escrituras hechas desde la propia caja.
ALLOWED_HOSTS   = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGINS = {"http://" + h for h in ALLOWED_HOSTS}

# Solo la ventana de la caja abierta más recientemente puede guardar. Así
# dos ventanas abiertas a la vez no se pisan los datos entre sí.
_session = {"activa": None, "html_sha": None}


def _html_sha_actual():
    """Huella del caja.html instalado (para avisar a la ventana abierta de
    que se descargó una versión nueva)."""
    try:
        return _sha256(APP_HTML)
    except Exception:
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silenciar logs de consola

    def _nocache(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._nocache()
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _same_origin_write(self) -> bool:
        # Un fetch() de la propia caja siempre manda Origin. Exigir además
        # application/json obliga a cualquier otra página a pasar por CORS,
        # que este servidor nunca autoriza.
        if self.headers.get("Origin") not in ALLOWED_ORIGINS:
            return False
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        return ctype == "application/json"

    def do_GET(self):
        if not self._host_ok():
            self.send_response(403)
            self.end_headers()
            return
        path = self.path.split("?", 1)[0]

        # Cada ventana de la caja pide un token al arrancar; la última que
        # lo pide queda como la única que puede guardar.
        if path == "/api/session":
            token = os.urandom(12).hex()
            _session["activa"] = token
            _session["html_sha"] = _html_sha_actual()
            self._json(200, {"sesion": token})
            return

        # La caja consulta esto cada 10 s para saber si el programa sigue
        # abierto y si ella sigue siendo la ventana activa.
        if path == "/api/ping":
            token = self.headers.get("X-Caja-Sesion")
            nueva = bool(_session.get("html_sha")) and _html_sha_actual() != _session.get("html_sha")
            self._json(200, {"ok": True,
                             "activa": bool(token) and token == _session["activa"],
                             "nuevaVersion": nueva})
            return

        if path.startswith("/api/data/"):
            key = path.split("/api/data/", 1)[1]
            if key not in ALLOWED_KEYS:
                self._json(404, {"error": "clave no válida"})
                return
            f = DATA_DIR / f"{key}.json"
            if not f.exists():
                self._json(200, None)  # primer arranque: todavía no hay datos
                return
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                # Archivo dañado: NO se responde "vacío" (la app lo
                # sobrescribiría y se perdería todo). Se deja una copia para
                # poder revisarlo y se avisa con un error.
                try:
                    copia = DATA_DIR / f"{key}.DANADO-{datetime.date.today().isoformat()}.json"
                    if not copia.exists():
                        shutil.copy2(f, copia)
                except Exception:
                    pass
                self._json(500, {"error": f"El archivo {f.name} está dañado y no se pudo leer."})
                return
            self._json(200, data)
            return

        fname = STATIC_FILES.get(path)
        if fname:
            fpath = INSTALL_DIR / fname
            if not fpath.exists():
                self.send_response(404)
                self.end_headers()
                return
            body = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", MIME.get(fpath.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self._nocache()
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if not self._host_ok() or not self._same_origin_write():
            self._json(403, {"error": "origen no permitido"})
            return
        path = self.path.split("?", 1)[0]
        if not path.startswith("/api/data/"):
            self.send_response(404)
            self.end_headers()
            return
        key = path.split("/api/data/", 1)[1]
        if key not in ALLOWED_KEYS:
            self._json(404, {"error": "clave no válida"})
            return

        token = self.headers.get("X-Caja-Sesion")
        if not token or token != _session["activa"]:
            self._json(409, {"error": "sesion",
                             "detalle": "La caja se abrió en otra ventana. Esta ventana ya no puede guardar."})
            return

        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"null"
            value = json.loads(raw)
        except Exception:
            self._json(400, {"error": "JSON inválido"})
            return

        if not isinstance(value, KEY_TYPES[key]):
            self._json(400, {"error": f"Formato inválido para {key}"})
            return

        f = DATA_DIR / f"{key}.json"
        with _data_lock:
            # Protección: ventas.json no se puede reemplazar por una lista
            # mucho más corta (desde la app solo se borra de a una venta),
            # salvo en una importación explícita.
            if key == "ventas" and f.exists() and self.headers.get("X-Caja-Reemplazo") != "1":
                try:
                    actuales = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    self._json(409, {"error": "ventas.json está dañado; no se sobrescribe."})
                    return
                if isinstance(actuales, list) and len(value) < len(actuales) - 1:
                    self._json(409, {"error": "proteccion",
                                     "detalle": f"Se intentó borrar {len(actuales) - len(value)} "
                                                "ventas de golpe; se bloqueó por seguridad."})
                    return

            backup_today()  # primera escritura del día → copia de seguridad
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(f)  # escritura atómica: evita archivos a medio escribir
            except Exception as e:
                self._json(500, {"error": f"No se pudo escribir: {e}"})
                return
        self._json(200, {"ok": True})


def try_start_server():
    try:
        server = HTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def open_browser() -> bool:
    time.sleep(0.4)
    url = f"http://127.0.0.1:{PORT}/caja.html"

    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/brave-browser",
            "/snap/bin/chromium",
        ]

    for path in candidates:
        if os.path.exists(path):
            try:
                subprocess.Popen([path, f"--app={url}", "--window-size=1280,800"])
                return True
            except Exception:
                continue

    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Interfaz gráfica: asistente de instalación + panel de control
# ---------------------------------------------------------------------------
BG      = "#12181f"
BG2     = "#1c2430"
GREEN   = "#00d084"
RED     = "#ff6b6b"
TEXT2   = "#9aa5b1"
TEXT3   = "#6b7480"
FONT_T  = ("Segoe UI", 15, "bold")
FONT_B  = ("Segoe UI", 10)
FONT_BTN = ("Segoe UI", 11, "bold")


def load_logo(root, max_size=132):
    """Carga el logo (variante con chip, para distinguirlo del ícono de la
    app web) como PhotoImage de tkinter (Tk 8.6+ lee PNG nativo).
    Devuelve None si no se pudo cargar (la UI sigue funcionando sin logo)."""
    source = APP_LOGO_LAUNCHER if APP_LOGO_LAUNCHER.exists() else APP_LOGO
    if not source.exists():
        return None
    try:
        img = tk.PhotoImage(master=root, file=str(source))
        w = img.width()
        if w > max_size:
            factor = max(1, round(w / max_size))
            img = img.subsample(factor, factor)
        return img
    except Exception:
        return None


class App:
    def __init__(self, root: tk.Tk, exe_path: Path, first_install: bool):
        self.root = root
        self.exe_path = exe_path
        self.server = None

        root.title("Caja Nirvana")
        root.geometry("380x450")
        root.resizable(False, False)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.cerrar_app)

        self.logo_img = load_logo(root)
        if self.logo_img is not None:
            try:
                root.iconphoto(True, self.logo_img)
            except Exception:
                pass
        if sys.platform == "win32" and APP_ICO.exists():
            try:
                # default=... deja el ícono puesto también para los cuadros de
                # diálogo (messagebox) y es lo que Windows usa de forma más
                # confiable para la barra de tareas.
                root.iconbitmap(default=str(APP_ICO))
            except Exception:
                pass

        self.container = tk.Frame(root, bg=BG)
        self.container.pack(expand=True, fill="both", padx=26, pady=26)

        # Copia de seguridad del día de datos/ (en segundo plano)
        threading.Thread(target=backup_today, daemon=True).start()

        # Revisión de actualizaciones de caja.html en segundo plano: nunca
        # bloquea la interfaz, y si falla (sin internet, etc.) no se nota.
        threading.Thread(target=check_for_updates, daemon=True).start()

        if first_install:
            self.show_welcome()
        else:
            self.crear_acceso_directo_silencioso()
            self.start_and_show_panel()

    # -- utilidades de UI --------------------------------------------------
    def clear(self):
        for w in self.container.winfo_children():
            w.destroy()

    def logo_label(self, pady=(6, 14)):
        if self.logo_img is not None:
            tk.Label(self.container, image=self.logo_img, bg=BG).pack(pady=pady)

    def boton(self, text, cmd, bg=GREEN, fg="black"):
        return tk.Button(self.container, text=text, command=cmd, bg=bg, fg=fg,
                          font=FONT_BTN, relief="flat", padx=18, pady=9,
                          activebackground=bg, cursor="hand2")

    # -- Paso 1: bienvenida --------------------------------------------------
    def show_welcome(self):
        self.clear()
        self.logo_label()
        tk.Label(self.container, text="Bienvenido a Caja Nirvana", font=FONT_T,
                 fg="white", bg=BG).pack()
        tk.Label(self.container,
                 text="Este asistente instalará la aplicación en\n"
                      "este computador y creará un acceso directo\n"
                      "en el Escritorio.",
                 font=FONT_B, fg=TEXT2, bg=BG, justify="center").pack(pady=(10, 26))
        self.boton("Instalar", self.do_install).pack()

    # -- Paso 2: instalando ---------------------------------------------------
    def do_install(self):
        self.clear()
        lbl = tk.Label(self.container, text="Instalando…", font=FONT_B, fg="white", bg=BG)
        lbl.pack(expand=True)
        self.root.update()
        try:
            create_shortcut(self.exe_path)
        except Exception as e:
            messagebox.showwarning(
                "Caja Nirvana",
                "No se pudo crear el acceso directo automáticamente.\n"
                f"Detalle: {e}\n\n"
                f"Puedes abrir la app manualmente desde:\n{self.exe_path}"
            )
        self.root.after(300, self.show_done)

    def crear_acceso_directo_silencioso(self):
        try:
            create_shortcut(self.exe_path)
        except Exception:
            pass  # ya está instalado; si falla no interrumpe el uso normal

    # -- Paso 3: listo ---------------------------------------------------------
    def show_done(self):
        self.clear()
        self.logo_label()
        tk.Label(self.container, text="¡Listo! ✓", font=FONT_T, fg=GREEN, bg=BG).pack()
        tk.Label(self.container,
                 text="Se instaló correctamente y se creó el\n"
                      "acceso directo en tu Escritorio.",
                 font=FONT_B, fg=TEXT2, bg=BG, justify="center").pack(pady=(10, 26))
        self.boton("Abrir Caja Nirvana ahora", self.start_and_show_panel).pack()

    # -- Arranque del servidor + navegador -------------------------------------
    def start_and_show_panel(self):
        self.clear()
        tk.Label(self.container, text="Iniciando…", font=FONT_B, fg="white", bg=BG).pack(expand=True)
        self.root.update()
        if self.server is None:
            self.server = try_start_server()
        threading.Thread(target=open_browser, daemon=True).start()
        self.root.after(500, self.show_panel)

    # -- Panel de control (reemplaza la consola) -------------------------------
    def show_panel(self):
        self.clear()
        self.logo_label(pady=(2, 10))
        tk.Label(self.container, text="Caja Nirvana", font=FONT_T, fg="white", bg=BG).pack()

        if self.server is not None:
            estado, color = "Funcionando ✓", GREEN
        else:
            estado, color = "Ya había una instancia abierta", "#f5a623"
        tk.Label(self.container, text=estado, font=FONT_B, fg=color, bg=BG).pack(pady=(2, 16))

        tk.Label(self.container, text="Datos guardados en:", font=("Segoe UI", 8), fg=TEXT3, bg=BG).pack()
        tk.Label(self.container, text=str(DATA_DIR), font=("Segoe UI", 8), fg=TEXT3, bg=BG,
                 wraplength=320, justify="center").pack(pady=(0, 6))
        self.update_lbl = tk.Label(self.container, text=update_status["texto"], font=("Segoe UI", 8),
                                   fg=TEXT2, bg=BG, wraplength=320, justify="center")
        self.update_lbl.pack(pady=(0, 12))
        self._refrescar_estado_update()

        tk.Button(self.container, text="Abrir de nuevo", command=self.abrir_de_nuevo,
                  bg=BG2, fg="white", font=FONT_B, relief="flat", padx=14, pady=7,
                  cursor="hand2").pack(pady=(0, 8))
        tk.Button(self.container, text="Cerrar aplicación", command=self.cerrar_app,
                  bg="#2a1c1c", fg=RED, font=FONT_B, relief="flat", padx=14, pady=7,
                  cursor="hand2").pack()

    def _refrescar_estado_update(self):
        # La revisión corre en otro hilo; tkinter solo se toca desde aquí.
        try:
            if self.update_lbl.winfo_exists():
                self.update_lbl.config(text=update_status["texto"])
                self.root.after(2000, self._refrescar_estado_update)
        except Exception:
            pass

    def abrir_de_nuevo(self):
        threading.Thread(target=open_browser, daemon=True).start()

    def cerrar_app(self):
        try:
            if self.server is not None:
                threading.Thread(target=self.server.shutdown, daemon=True).start()
        except Exception:
            pass
        self.root.destroy()
        sys.exit(0)


if __name__ == "__main__":
    try:
        exe_path, first_install = ensure_installed()
    except Exception as e:
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("Caja Nirvana", f"No se pudo preparar la instalación:\n{e}")
        except Exception:
            pass
        sys.exit(1)

    root = tk.Tk()
    try:
        app = App(root, exe_path, first_install)
        root.mainloop()
    except Exception as e:
        try:
            messagebox.showerror("Caja Nirvana", f"Ocurrió un error inesperado:\n{e}")
        except Exception:
            pass
        sys.exit(1)
