from pathlib import Path
import os, subprocess
BASE=Path(__file__).resolve().parent
PROFILE=BASE/"chrome_profile"
PROFILE.mkdir(exist_ok=True)
candidates=[
Path(os.environ.get("PROGRAMFILES",""))/"Google/Chrome/Application/chrome.exe",
Path(os.environ.get("PROGRAMFILES(X86)",""))/"Google/Chrome/Application/chrome.exe",
Path(os.environ.get("LOCALAPPDATA",""))/"Google/Chrome/Application/chrome.exe"]
exe=next((p for p in candidates if p.exists()),None)
if not exe: raise SystemExit("Google Chrome was not found.")
print("Opening NEW dedicated Chrome profile directly at Photoroom.")
print("Log in once, then close that dedicated Chrome window normally.")
subprocess.Popen([str(exe),f"--user-data-dir={PROFILE}","--no-first-run","--no-default-browser-check","https://app.photoroom.com/"])
