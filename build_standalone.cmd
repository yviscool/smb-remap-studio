@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0build_standalone.ps1" %*
