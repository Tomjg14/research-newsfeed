# Build a Windows .exe

Package into a single-file Windows executable using **PyInstaller**.

## Steps (Windows, PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install pyinstaller

pyinstaller --onefile --name "AI_Research_Feed" run_app.py

# The exe will be in .\dist\AI_Research_Feed.exe
.\dist\AI_Research_Feed.exe
```
