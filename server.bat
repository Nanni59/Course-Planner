@echo off
REM Check if server is already running on port 3000
netstat -ano | findstr ":3000 " >nul 2>&1
if %errorlevel%==0 (
    exit
)
wscript "C:\Users\ibrah\OneDrive\Desktop\Course Planner\Start Background Server.vbs"
exit
