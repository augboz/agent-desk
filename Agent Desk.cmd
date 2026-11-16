@echo off
rem One-click launcher for Agent Desk (no console window stays open).
where pythonw >nul 2>nul && (
  start "" pythonw "%~dp0agent_desk.py"
) || (
  start "" pyw "%~dp0agent_desk.py"
)
