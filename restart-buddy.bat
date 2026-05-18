@echo off
echo This script will help restart Buddy.
echo.
echo Option 1: Restart your PC (easiest)
echo Option 2: Open Task Scheduler and disable/enable Buddy task
echo.
echo Opening Task Scheduler now...
start taskschd.msc
echo.
echo In Task Scheduler, look in:
echo   - Task Scheduler Library ^> Buddy
echo   - Or Microsoft ^> Windows ^> Startup
echo.
pause