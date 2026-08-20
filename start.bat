@echo off
set PYTHON_EXE=C:\Users\natan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
cd /d %~dp0
"%PYTHON_EXE%" server.py
