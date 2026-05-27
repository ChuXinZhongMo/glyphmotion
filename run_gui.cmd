@echo off
setlocal
set "ROOT=%~dp0"
"%ROOT%.venv\Scripts\pythonw.exe" -m ascii_oneclick.gui
