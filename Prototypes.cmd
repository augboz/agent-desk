@echo off
rem Opens the four scene prototypes. Add --live to use real sessions instead of demo agents.
where pythonw >nul 2>nul && (
  start "" pythonw "%~dp0prototypes.py" %*
) || (
  start "" pyw "%~dp0prototypes.py" %*
)
