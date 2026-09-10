@echo off
setlocal
cd /d "%~dp0"
echo ZPSI Catalogue - installation Windows 10/11 x64
echo Python 3.13, Poppler et Tesseract seront installes via WinGet.
echo Internet est requis. Les configurations existantes seront conservees.
echo Fermez ZPSI Catalogue avant une mise a jour.
choice /c ON /m "Installer les composants et accepter leurs conditions de distribution ?"
if errorlevel 2 exit /b 0
where winget >nul 2>&1
if errorlevel 1 (
 echo WinGet est absent. Installez App Installer depuis le Microsoft Store,
 echo puis relancez ce fichier. Aucune installation terminee.
 pause
 exit /b 1
)
winget install --id Python.Python.3.13 --exact --source winget --scope user --accept-package-agreements --accept-source-agreements
winget install --id oschwartz10612.Poppler --exact --source winget --accept-package-agreements --accept-source-agreements
winget install --id UB-Mannheim.TesseractOCR --exact --source winget --accept-package-agreements --accept-source-agreements
set "ZPSI_PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if exist "%ZPSI_PY%" goto install
for /f "delims=" %%P in ('py -3.13 -c "import sys; print(sys.executable)" 2^>nul') do set "ZPSI_PY=%%P"
:install
if not exist "%ZPSI_PY%" (
 echo Python introuvable. Consultez les messages ci-dessus et relancez.
 pause
 exit /b 1
)
"%ZPSI_PY%" installer_windows.py
if errorlevel 1 (
 echo Installation incomplete. Consultez le message ci-dessus.
 pause
 exit /b 1
)
echo Installation terminee. Ouvrez ZPSI Catalogue depuis le menu Demarrer.
pause
