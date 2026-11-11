@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PORT=8095"
title Сибирский форум - локальный сервер

rem Вариант 1: Python 3.9+. Проверяем запуском, чтобы не принять за Python ярлык Microsoft Store.
set "PY="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=py -3"

if defined PY (
  echo Запускаю сайт через Python...
  set "PYTHONIOENCODING=utf-8"
  %PY% server\server.py --port %PORT% --open
  goto :end
)

rem Вариант 2: Docker. Отдельный проект siberianforum-proto - другие контейнеры не затрагиваются.
docker version >nul 2>&1
if errorlevel 1 goto :nothing
echo Python не найден - запускаю в Docker, контейнер siberianforum-proto...
call "%~dp0start-site-docker.bat" nopause
goto :end

:nothing
echo.
echo Не найден ни Python 3.9+, ни Docker.
echo  - установите Python: https://www.python.org/downloads/ - отметьте "Add python.exe to PATH";
echo  - или откройте site\index.html двойным кликом: сайт заработает в демо-режиме,
echo    заявки будут сохраняться только в браузере.

:end
echo.
pause
