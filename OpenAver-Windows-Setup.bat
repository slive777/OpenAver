@echo off
chcp 65001
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 | iex"
pause
