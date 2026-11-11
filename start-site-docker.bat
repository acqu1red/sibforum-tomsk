@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PORT=8095"

rem Отдельный Docker-проект siberianforum-proto: собирается и запускается только его контейнер.
docker version >nul 2>&1
if errorlevel 1 (
  echo Docker не запущен или не установлен. Запустите Docker Desktop и повторите.
  goto :end
)
docker compose -p siberianforum-proto -f docker-compose.yml up -d --build
if errorlevel 1 (
  echo Не удалось запустить контейнер siberianforum-proto - подробности выше.
  goto :end
)
echo Ждём запуска сервера...
timeout /t 3 /nobreak >nul
start "" "http://localhost:%PORT%/"
echo.
echo Сайт: http://localhost:%PORT%/
echo Заявки сохраняются в server\data. Остановить контейнер: stop-site-docker.bat

:end
if /i not "%~1"=="nopause" (
  echo.
  pause
)
