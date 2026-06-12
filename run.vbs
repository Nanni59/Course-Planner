Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\ibrah\OneDrive\Desktop\Course Planner"
WshShell.Run "cmd /c node server.js > out.log 2> err.log", 0, False
