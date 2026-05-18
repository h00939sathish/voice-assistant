@echo off
echo ===================================================
echo Installing Playwright Browser Engines for Buddy
echo ===================================================
echo.
echo Step 1/2: Ensuring playwright python package is installed...
pip install playwright

echo.
echo Step 2/2: Downloading chromium browsers...
playwright install chromium

echo.
echo ===================================================
echo Success! Native browser skill is now ready to use.
echo ===================================================
pause
