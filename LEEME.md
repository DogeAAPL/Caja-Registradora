# Caja Nirvana

Aplicación de caja registradora de escritorio con gestión de productos, ventas y cierre de caja.

## ⚙️ Compilar el instalador (solo la primera vez, una vez por sistema operativo)

Este paquete trae el **código fuente**. Antes de poder instalar la app en el
computador de la caja, tienes que generar el ejecutable de un solo archivo
**una vez**, en un computador con el mismo sistema operativo donde la vas a usar
(necesita tener Python instalado: https://python.org — marca "Add to PATH" al instalarlo).

### Windows
Doble clic en `build_windows.bat`. Tarda uno o dos minutos. Al terminar, queda
`dist\CajaNirvana.exe` — ese es tu instalador de un solo archivo.

### Linux
```bash
chmod +x build_linux.sh
./build_linux.sh
```
Al terminar, queda `dist/CajaNirvana` — ese es tu instalador de un solo archivo.

> Si tienes `LogoNirvana-Cuadrado.png`, `LogoNirvana-Launcher.png` y `LogoNirvana.ico`
> en esta misma carpeta al compilar, el instalador queda con el ícono correcto: la
> variante "con chip" (fondo oscuro y borde verde) para el `.exe`/acceso directo/panel
> de control, y la variante plana (sin fondo) para el favicon de la app web — así se
> distinguen a simple vista uno del otro.

## 🚀 Instalar y usar (esto sí lo hace cualquier persona, no requiere Python)

1. Copia el archivo `CajaNirvana.exe` (Windows) o `CajaNirvana` (Linux) al
   computador de la caja — puede ir por USB, por correo, como sea.
2. Haz doble clic. La primera vez se abre un pequeño asistente:
   - Pantalla de bienvenida → botón **"Instalar"**.
   - Se instala solo en una carpeta fija (`Documentos`/carpeta personal → `CajaNirvana`)
     y crea el acceso directo **"Caja Nirvana"** en el Escritorio.
   - Botón **"Abrir Caja Nirvana ahora"** → arranca la app.
3. De ahí en adelante, **usa siempre el acceso directo del Escritorio** — ya
   puedes borrar el archivo original que descargaste/copiaste, no se rompe nada.
   Las siguientes veces no vuelve a mostrar el asistente, abre la app directo.
4. No hay ninguna ventana de consola. Mientras la app está abierta, queda un
   panelito pequeño con el logo y el botón **"Cerrar aplicación"** — ese es
   el que usas para cerrar la caja al final del día. Si por error cierras la
   ventana del navegador, ese panel tiene un botón "Abrir de nuevo".

> **Linux:** si el acceso directo del Escritorio no se deja abrir con doble
> clic la primera vez, clic derecho sobre él → "Permitir ejecución" /
> "Confiar y lanzar" (algunas versiones de GNOME lo piden por seguridad).

## 💾 Dónde quedan tus datos

Ya **no se usa el navegador para guardar nada**. Todo vive en archivos de
texto plano (JSON), dentro de la carpeta de instalación:

```
CajaNirvana/
├── CajaNirvana(.exe)      ← el programa
├── caja.html               ← la interfaz
└── datos/
    ├── productos.json      ← tu catálogo
    ├── ventas.json          ← historial completo de ventas
    ├── stats.json           ← totales del día / base de caja
    └── config.json          ← número de WhatsApp guardado, etc.
```

Para respaldar todo, simplemente **copia la carpeta `datos/`** a un USB, a la
nube, donde quieras. Puedes abrir esos archivos con el Bloc de notas si
alguna vez necesitas revisarlos a mano (son JSON: texto con `{ }` y `[ ]`).

Además, desde "Historial" puedes seguir exportando un CSV normal para abrir
en Excel cuando quieras.

## 🔄 Actualización automática de la app (opcional)

El programa puede revisar solo, una vez al día, si hay una versión más
nueva de `caja.html` en un repositorio de GitHub — y si la hay, la
descarga para que quede lista la próxima vez que abras la app. **Solo
actualiza `caja.html`**, nunca el propio programa/instalador; para eso
siempre hay que generar un instalador nuevo como hasta ahora.

Para activarlo, edita `iniciar.py` (antes de compilar) y cambia estas
tres líneas cerca del inicio del archivo:

```python
GITHUB_USER   = "TU_USUARIO_DE_GITHUB"
GITHUB_REPO   = "TU_REPOSITORIO"
GITHUB_BRANCH = "main"
```

Sube todo el proyecto (código completo, no solo `caja.html`) a un
repositorio de GitHub **público** — no necesita llevar ninguna
credencial ni dato del negocio, tus ventas y productos nunca salen de
este computador. No hace falta hacer nada especial cada vez que subas un
cambio a `caja.html`: el programa detecta automáticamente que hay una
versión distinta comparando el identificador que GitHub ya calcula solo
por cada archivo.

Si no configuras esto (dejas los valores de ejemplo tal cual), la app
simplemente nunca revisa nada — funciona exactamente igual que antes,
sin ningún cambio de comportamiento.

## Funciones


- **Venta**: agrega productos al ticket, varias "mesas"/tickets en paralelo,
  elige método de pago (Efectivo/Tarjeta/Nequi/Otros).
  - En **Efectivo**, ingresa el monto recibido y la app calcula el vuelto a
    devolver automáticamente (o te avisa si falta dinero).
- **Productos**: agrega, edita o elimina productos del catálogo con nombre,
  precio, stock e ícono.
- **Historial**: consulta todas las ventas registradas, edítalas o bórralas.
- **Inicio / Cierre de día**: define la base de caja al empezar el día y
  revisa el resumen al cerrar.
  - **📲 Enviar cierre por WhatsApp**: guarda el número una vez (con
    indicativo de país, ej. `573001234567`) y con un clic se abre el reporte
    en PDF (para guardarlo) y una conversación de WhatsApp con el resumen del
    día ya escrito — solo te falta arrastrar el PDF a la conversación y
    darle enviar.
- **Exportar**: descarga un CSV con ventas, inventario y resumen diario.

## Personalización

Edita `caja.html` (dentro de la carpeta de instalación, o en este paquete
antes de compilar) para cambiar colores, agregar métodos de pago, o
modificar campos. Si editas el `caja.html` de este paquete fuente, vuelve a
correr `build_windows.bat` / `build_linux.sh` para generar un instalador
actualizado.
