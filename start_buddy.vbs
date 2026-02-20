' Start Buddy Wake Daemon silently
' This VBS script launches the Python daemon without any visible window

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "c:\Users\h0093\Documents\new"

' Run pythonw with the main script (pythonw = no console)
WshShell.Run "pythonw main.py", 0, False
