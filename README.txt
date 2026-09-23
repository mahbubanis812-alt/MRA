PHOTOROOM BACKGROUND REMOVER - V17 SUPER FAST HUMAN-IN-THE-LOOP

Windows folder-only automation using Chrome + Playwright async API.

1. Run setup_profile.bat once. A NEW dedicated Chrome profile opens directly at the Background Remover page. Log in once if needed.
2. Put images into input\
3. Run run.bat
4. Transparent PNG files are saved in output\
5. Images that fail all 3 normal attempts are copied to failed\

SUPER-FAST DESIGN:
- Up to 5 browser tabs/workers run concurrently with a shared queue.
- Hidden file-input upload is attempted first, avoiding unnecessary UI clicks when available.
- No fixed 5-second sleep after upload; the script polls for the real Download control every 250 ms.
- Page-load timeout is 45 seconds, upload/editor confirmation is 45 seconds, and download confirmation is 45 seconds.
- File-chooser detection uses a short 2.5-second event window because the chooser event should fire immediately after the click.
- CAPTCHA checks use a short 700 ms DOM read timeout and 500 ms resume polling.

RELIABILITY RULES:
- Exact URL: https://www.photoroom.com/tools/background-remover
- Each image gets at most 3 normal attempts.
- Waits 5 seconds between normal failed attempts.
- EVERY actual UI click is followed by a mandatory 4-second wait.
- CAPTCHA-aware human-in-the-loop: detects the specific visible invalid-CAPTCHA message, Photoroom code 600010, human-verification text, or a visible challenge iframe. The affected tab pauses and stays open. Complete the CAPTCHA manually in that tab, then press ENTER in the console; the script verifies the CAPTCHA cleared before continuing.
- No CAPTCHA solving or bypass.
- Upload success is not assumed merely because set_input_files() succeeds; the script waits for the real Download control.
- Download detection supports button, link, aria-label, and visible text variants.
- Supports export dialog and PNG selection.
- If upload fails, saves DEBUG_upload_<name>.png/.html/.txt in failed\.
- If CAPTCHA is detected, saves CAPTCHA_<name>.png/.html/.txt in failed\.
- No taskkill and no forced Chrome close.
