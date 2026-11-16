# Security

Agent Desk runs only on your computer.

- **No network access.** It never connects to the internet.
- **Read-only access to Claude Code's files.** It reads `~/.claude/sessions/` and `~/.claude/projects/`, and never changes, uploads or logs what's in them.
- **No credentials.** It never touches `~/.claude/.credentials.json` or any login token.
- **The only files it writes:**
  - `%APPDATA%\AgentDesk\config.json` (window position and your picks).
  - `%APPDATA%\AgentDesk\agent_desk.log` (error tracebacks only).
  - A Startup-folder shortcut, but only if you tick "Start with Windows".
- **The only programs it starts:**
  - Windows PowerShell, by its full System32 path, to run the bundled `taskbar_layout.ps1`. That script reads where the taskbar buttons are through UI Automation.
  - The same PowerShell, to create the Startup shortcut. Everything it needs is passed in through environment variables, never pasted into the command.

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's private vulnerability reporting instead: on the **Security** tab, click **Report a vulnerability**. You'll get a reply within a week.

Only the latest version on `main` is supported.
