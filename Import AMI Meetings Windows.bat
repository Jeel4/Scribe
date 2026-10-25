@echo off
rem Double-click to import 10 real AMI meetings (with their human reference
rem summaries) into Scribe and analyse them. Run "Start Scribe (Windows).bat"
rem once first, so everything is installed. Close the Scribe window before
rem running this.
setlocal
cd /d "%~dp0"
title Scribe - AMI import
echo === Import AMI meetings into Scribe ===

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Scribe is not installed yet. Double-click "Start Scribe (Windows).bat" once first.
  goto fail
)

netstat -ano | findstr /r /c:":5050 .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo ERROR: Scribe is still running. Close the Scribe window first, then run this again.
  goto fail
)

set "ZIP=ami_public_manual_1.6.2.zip"
set "DEST=ami_annotations"

if exist "%DEST%\words" goto extracted

if exist "%ZIP%" goto have_zip
echo --- Downloading the AMI manual annotations (about 20 MB)
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip' -OutFile '%ZIP%' } catch { exit 1 }"
if errorlevel 1 (
  echo.
  echo The download did not work. Download "ami_public_manual_1.6.2.zip" yourself from the
  echo AMI Corpus website ^(Download section, AMI manual annotations^), put it in this folder:
  echo   %CD%
  echo and double-click this file again.
  if exist "%ZIP%" del "%ZIP%"
  goto fail
)
:have_zip

echo --- Extracting
powershell -NoProfile -Command "Expand-Archive -Force -Path '%ZIP%' -DestinationPath '%DEST%'"
if errorlevel 1 goto fail
if not exist "%DEST%\words" (
  echo ERROR: the zip did not contain a "words" folder. Is it the AMI manual annotations zip?
  goto fail
)
:extracted

echo --- Importing and analysing 10 meetings (about 5-15 minutes with DistilBART)
cd backend
"..\.venv\Scripts\python.exe" scripts\import_ami.py --annotations "..\%DEST%" --only-with-summary --limit 10
if errorlevel 1 (
  cd ..
  echo ERROR: the import stopped. See the messages above.
  goto fail
)
cd ..
echo.
echo Done. Start Scribe with "Start Scribe (Windows).bat" and open the Evaluation page.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
