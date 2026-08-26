@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
REM ============================================================
REM  Compila Caja Nirvana como un solo .exe para Windows.
REM  Ejecuta esto UNA VEZ en tu computador con Windows (no en el
REM  computador de la caja, a menos que sea el mismo).
REM  Requiere tener Python instalado (https://python.org).
REM ============================================================
title Compilando Caja Nirvana...

echo ============================================
echo   Preparando herramientas de compilacion...
echo ============================================
python -m pip install pyinstaller
if %errorlevel% neq 0 (
    echo.
    echo ============================================
    echo   ERROR: no se pudo instalar/verificar PyInstaller.
    echo   Revisa que Python este instalado y en el PATH
    echo   ^(prueba abrir una consola y escribir: python --version^)
    echo ============================================
    pause
    exit /b 1
)

if not exist "caja.html" (
    echo.
    echo ============================================
    echo   ERROR: no se encuentra caja.html en esta carpeta.
    echo   Asegurate de correr este .bat desde la misma
    echo   carpeta donde lo descomprimiste todo.
    echo ============================================
    pause
    exit /b 1
)
if not exist "iniciar.py" (
    echo.
    echo ============================================
    echo   ERROR: no se encuentra iniciar.py en esta carpeta.
    echo ============================================
    pause
    exit /b 1
)

REM Arma la lista de --add-data solo con los archivos que realmente existen,
REM para que la falta de un logo opcional nunca tumbe toda la compilacion.
REM Se usa la forma "--add-data=archivo;." (un solo token, sin espacios) para
REM no depender de comillas anidadas, que son fragiles en cmd.exe.
set "ADDDATA=--add-data=caja.html;."
set "ICONFLAG="

if exist "LogoNirvana-Cuadrado.png" (
    set "ADDDATA=!ADDDATA! --add-data=LogoNirvana-Cuadrado.png;."
) else (
    echo   Aviso: no se encontro LogoNirvana-Cuadrado.png ^(se compilara sin ese icono^).
)
if exist "LogoNirvana-Launcher.png" (
    set "ADDDATA=!ADDDATA! --add-data=LogoNirvana-Launcher.png;."
) else (
    echo   Aviso: no se encontro LogoNirvana-Launcher.png ^(se compilara sin ese icono^).
)
if exist "favicon.ico" (
    set "ADDDATA=!ADDDATA! --add-data=favicon.ico;."
) else (
    echo   Aviso: no se encontro favicon.ico ^(el favicon del navegador quedara por defecto^).
)
if exist "LogoNirvana.ico" (
    set "ADDDATA=!ADDDATA! --add-data=LogoNirvana.ico;."
    set "ICONFLAG=--icon=LogoNirvana.ico"
) else (
    echo   Aviso: no se encontro LogoNirvana.ico ^(el .exe quedara con el icono por defecto^).
)

echo.
echo ============================================
echo   Compilando CajaNirvana_Instalador.exe ...
echo ============================================
python -m PyInstaller --onefile --name CajaNirvana_Instalador --windowed --clean --noconfirm !ADDDATA! !ICONFLAG! iniciar.py

if %errorlevel% neq 0 (
    echo.
    echo ============================================
    echo   ERROR: la compilacion fallo. Copia el mensaje
    echo   de error de arriba para que lo revisemos.
    echo ============================================
    pause
    exit /b 1
)

if not exist "dist\CajaNirvana_Instalador.exe" (
    echo.
    echo ============================================
    echo   ERROR: PyInstaller termino pero no se genero
    echo   dist\CajaNirvana_Instalador.exe. Revisa los
    echo   mensajes de arriba en busca de errores.
    echo ============================================
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Listo. Tu instalador de un solo archivo es:
echo   dist\CajaNirvana_Instalador.exe
echo.
echo   Copialo donde quieras (USB, Descargas, etc.)
echo   y haz doble clic para instalar y abrir la app.
echo   (Una vez instalado, el programa que queda en el
echo   Escritorio se llama simplemente "Caja Nirvana".)
echo ============================================
pause
