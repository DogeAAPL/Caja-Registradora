# Caja Nirvana

Aplicación de caja registradora de escritorio con gestión de productos, ventas y cierre de caja.

## ⚙️ Compilar el instalador (solo la primera vez, una vez por sistema operativo)

Este paquete trae el **código fuente**. Antes de poder instalar la app en el
computador de la caja, tienes que generar el ejecutable de un solo archivo
**una vez**, en un computador con el mismo sistema operativo donde la vas a usar
(necesita tener Python instalado: https://python.org — marca "Add to PATH" al instalarlo).

### Windows
Doble clic en `build_windows.bat`. Tarda uno o dos minutos. Al terminar, queda
`dist\CajaNirvana_Instalador.exe` — ese es tu instalador de un solo archivo.

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
    ├── config.json          ← número de WhatsApp guardado, etc.
    ├── actualizacion.json   ← última revisión de GitHub (lo maneja el programa)
    └── respaldos/
        └── AAAA-MM-DD/      ← copia automática de todo lo anterior, una por día
```

**Copias automáticas:** la primera vez que la caja guarda algo cada día, se
copia toda la carpeta `datos/` en `datos/respaldos/AAAA-MM-DD/`. Se conservan
los últimos 30 días. Si algún día un archivo se daña, copia el de la fecha
anterior en su lugar.

Para respaldar todo, simplemente **copia la carpeta `datos/`** a un USB, a la
nube, donde quieras. Puedes abrir esos archivos con el Bloc de notas si
alguna vez necesitas revisarlos a mano (son JSON: texto con `{ }` y `[ ]`).

Además, desde "Historial" puedes seguir exportando un CSV normal para abrir
en Excel cuando quieras.

## 🔄 Actualización automática de la caja (activada)

El programa está conectado a este repositorio (**DogeAAPL/Caja-Registradora**,
rama `main`). Cada vez que se abre (como máximo una vez por hora) descarga el
`caja.html` de GitHub y, si es distinto del instalado, lo instala solo:

- Deja el anterior como `caja.html.bak` por si hay que volver atrás.
- La ventana de la caja que ya está abierta sigue funcionando y muestra una
  franja azul **"Hay una versión nueva de la caja"** con un botón para
  recargar (avisa si hay tickets sin cobrar).
- El panelito del programa muestra si la caja está al día o se actualizó.
- Antes de instalar, verifica que el archivo descargado sea de verdad la página
  de la caja (no una página de error ni un archivo a medio subir).

**Para publicar un cambio:** edita `caja.html` y súbelo a la rama `main`. Las
cajas lo toman la próxima vez que se abra el programa.

> ⚠️ Lo que esté en `main` es lo que usan las cajas. No subas a `main` un
> `caja.html` sin probar.

**Solo se actualiza `caja.html`.** Si cambias `iniciar.py` hay que generar un
instalador nuevo (`build_windows.bat`) y reemplazar `CajaNirvana.exe`.

El repositorio debe seguir siendo **público** (no lleva ninguna credencial ni
dato del negocio: la carpeta `datos/` está en `.gitignore` y nunca se sube).
Para desactivar la actualización, vuelve a poner `GITHUB_USER =
"TU_USUARIO_DE_GITHUB"` en `iniciar.py` y compila de nuevo.

## 🛡️ Protección de datos (versión 2)

- **Nunca arranca "en blanco":** si un archivo de `datos/` no se puede leer,
  la caja muestra un aviso rojo y **no guarda nada**, para no borrar la
  información real. El archivo dañado se copia como `*.DANADO-fecha.json`.
- **Una sola ventana a la vez:** si se abre la caja en otra ventana (o con
  "Abrir de nuevo"), la ventana anterior queda bloqueada con un aviso y deja
  de guardar. Así dos ventanas no se pisan las ventas.
- **Aviso si no se está guardando:** si se cierra el programa con la ventana
  de la caja todavía abierta, aparece una franja roja y el botón **Cobrar**
  se desactiva.
- **Números de venta únicos:** el siguiente número es siempre el más alto + 1,
  aunque se borren ventas. Si se cargan datos viejos con números repetidos,
  se corrigen solos.
- **Stock entre tickets:** no se puede vender más de lo que hay repartiéndolo
  en varios tickets abiertos.
- **Seguridad del servidor local:** solo acepta escrituras de la propia caja
  (no de otras páginas web) y no permite reemplazar el historial de ventas por
  uno mucho más corto por error.
- **`caja.html` ya no se pisa en cada arranque:** el programa solo la
  reemplaza cuando el `.exe` trae una versión nueva (deja la anterior como
  `caja.html.bak`).

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
- **Exportar**: descarga un CSV con ventas (incluye número de venta y nota),
  inventario y resumen diario.

## Personalización

Edita `caja.html` (dentro de la carpeta de instalación, o en este paquete
antes de compilar) para cambiar colores, agregar métodos de pago, o
modificar campos. Si editas el `caja.html` de este paquete fuente, vuelve a
correr `build_windows.bat` / `build_linux.sh` para generar un instalador
actualizado.
