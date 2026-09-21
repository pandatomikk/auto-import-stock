@echo off
cd /d "%~dp0"
py -3 lancer.py --client
if errorlevel 1 pause
