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
  5. En segundo plano, revisa (máximo 1 vez al día, con tiempo límite
     corto) si hay una versión más nueva de caja.html en GitHub, y si la
     hay la descarga para la PRÓXIMA vez que se abra el programa. Nunca
     bloquea el arranque ni reemplaza el archivo mientras está en uso.
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
# Cámbialos por los tuyos. El repositorio debe ser PÚBLICO (no lleva ninguna
# credencial ni dato sensible — tus ventas/productos nunca salen de este
# computador, viven solo en la carpeta datos/, que nunca se sube a GitHub).
GITHUB_USER   = "TU_USUARIO_DE_GITHUB"
GITHUB_REPO   = "TU_REPOSITORIO"
GITHUB_BRANCH = "main"

UPDATE_CHECK_TIMEOUT      = 3   # segundos máximo esperando respuesta de GitHub
UPDATE_CHECK_EVERY_HOURS  = 24  # no revisar más de una vez al día

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


def check_for_updates() -> None:
    """Revisa (en un hilo aparte, nunca bloquea la interfaz) si hay una
    versión más nueva de caja.html en GitHub. Si la hay, la descarga y la
    deja lista para la PRÓXIMA vez que se abra el programa — nunca
    reemplaza el archivo mientras la app está en uso. Cualquier problema
    (sin internet, GitHub caído, repo sin configurar, etc.) se ignora en
    silencio: la app sigue funcionando normalmente con lo que ya tiene.
    Solo toca caja.html — nunca el .exe/instalador."""
    if GITHUB_USER == "TU_USUARIO_DE_GITHUB" or GITHUB_REPO == "TU_REPOSITORIO":
        return  # todavía no configurado

    cfg = _read_config()
    last_check = cfg.get("lastUpdateCheck", 0)
    if time.time() - last_check < UPDATE_CHECK_EVERY_HOURS * 3600:
        return  # ya se revisó hace poco, no molestar a GitHub de más

    api_url = (f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}"
               f"/contents/caja.html?ref={GITHUB_BRANCH}")
    try:
        req = urllib.request.Request(
            api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": "CajaNirvana"}
        )
        with urllib.request.urlopen(req, timeout=UPDATE_CHECK_TIMEOUT) as resp:
            info = json.loads(resp.read().decode("utf-8"))
        remote_sha = info.get("sha")
    except Exception:
        return  # sin internet, repo no encontrado, timeout, etc.

    cfg["lastUpdateCheck"] = time.time()

    if not remote_sha or remote_sha == cfg.get("lastCajaHtmlSha"):
        _write_config(cfg)  # está al día; igual guardamos la fecha de revisión
        return

    raw_url = (f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}"
               f"/{GITHUB_BRANCH}/caja.html")
    try:
        req2 = urllib.request.Request(raw_url, headers={"User-Agent": "CajaNirvana"})
        with urllib.request.urlopen(req2, timeout=UPDATE_CHECK_TIMEOUT) as resp2:
            nuevo_html = resp2.read()
        # Verificación mínima de cordura antes de reemplazar nada
        if len(nuevo_html) < 500 or b"<html" not in nuevo_html.lower():
            _write_config(cfg)
            return
    except Exception:
        _write_config(cfg)
        return

    try:
        if APP_HTML.exists():
            shutil.copy2(APP_HTML, INSTALL_DIR / "caja.html.bak")  # respaldo por si acaso
        pendiente = INSTALL_DIR / "caja.html.nuevo"
        pendiente.write_bytes(nuevo_html)
        pendiente.replace(APP_HTML)  # reemplazo atómico
        cfg["lastCajaHtmlSha"] = remote_sha
    except Exception:
        pass

    _write_config(cfg)


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
_session = {"activa": None}


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
            self._json(200, {"sesion": token})
            return

        # La caja consulta esto cada 10 s para saber si el programa sigue
        # abierto y si ella sigue siendo la ventana activa.
        if path == "/api/ping":
            token = self.headers.get("X-Caja-Sesion")
            self._json(200, {"ok": True, "activa": bool(token) and token == _session["activa"]})
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
        root.geometry("380x430")
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
                 wraplength=320, justify="center").pack(pady=(0, 20))

        tk.Button(self.container, text="Abrir de nuevo", command=self.abrir_de_nuevo,
                  bg=BG2, fg="white", font=FONT_B, relief="flat", padx=14, pady=7,
                  cursor="hand2").pack(pady=(0, 8))
        tk.Button(self.container, text="Cerrar aplicación", command=self.cerrar_app,
                  bg="#2a1c1c", fg=RED, font=FONT_B, relief="flat", padx=14, pady=7,
                  cursor="hand2").pack()

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
