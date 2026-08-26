#!/bin/bash
# ============================================================
#  Compila Caja Nirvana como un solo binario para Linux.
#  Ejecuta esto UNA VEZ en el computador Linux donde se usará
#  (o en uno con la misma arquitectura/distro similar).
#  Requiere Python 3.
# ============================================================
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  Preparando herramientas de compilación..."
echo "============================================"
python3 -m pip install pyinstaller --break-system-packages -q 2>/dev/null || python3 -m pip install pyinstaller -q

echo
echo "============================================"
echo "  Compilando CajaNirvana_Instalador ..."
echo "============================================"
if [ -f "LogoNirvana-Cuadrado.png" ]; then
    ICO_ARG=""
    if [ -f "LogoNirvana.ico" ]; then
        ICO_ARG='--add-data=LogoNirvana.ico:.'
    fi
    LAUNCHER_ARG=""
    if [ -f "LogoNirvana-Launcher.png" ]; then
        LAUNCHER_ARG='--add-data=LogoNirvana-Launcher.png:.'
    fi
    FAVICON_ARG=""
    if [ -f "favicon.ico" ]; then
        FAVICON_ARG='--add-data=favicon.ico:.'
    fi
    python3 -m PyInstaller --onefile --name CajaNirvana_Instalador --windowed --clean --noconfirm \
        --add-data "caja.html:." \
        --add-data "LogoNirvana-Cuadrado.png:." \
        $ICO_ARG \
        $LAUNCHER_ARG \
        $FAVICON_ARG \
        iniciar.py
else
    python3 -m PyInstaller --onefile --name CajaNirvana_Instalador --windowed --clean --noconfirm \
        --add-data "caja.html:." \
        iniciar.py
fi

if [ ! -f "dist/CajaNirvana_Instalador" ]; then
    echo
    echo "============================================"
    echo "  ERROR: PyInstaller terminó pero no se generó"
    echo "  dist/CajaNirvana_Instalador. Revisa los mensajes"
    echo "  de arriba en busca de errores."
    echo "============================================"
    exit 1
fi

chmod +x dist/CajaNirvana_Instalador

echo
echo "============================================"
echo "  Listo. Tu instalador de un solo archivo es:"
echo "  dist/CajaNirvana_Instalador"
echo
echo "  Cópialo donde quieras y haz doble clic (o"
echo "  ./CajaNirvana_Instalador desde la terminal) para"
echo "  instalar y abrir la app. Una vez instalado, el"
echo "  programa que queda en el Escritorio se llama"
echo "  simplemente \"Caja Nirvana\"."
echo "============================================"
