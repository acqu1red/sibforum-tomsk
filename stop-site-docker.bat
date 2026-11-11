@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Останавливает и удаляет только контейнер проекта siberianforum-proto. Данные в server\data сохраняются.
docker compose -p siberianforum-proto -f docker-compose.yml down
echo.
pause
