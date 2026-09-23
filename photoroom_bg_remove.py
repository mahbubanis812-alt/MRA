from pathlib import Path
import shutil, asyncio, re
from playwright.async_api import async_playwright

BASE = Path(__file__).resolve().parent
PROFILE = BASE / "chrome_profile"
INPUT, OUTPUT, FAILED = BASE/"input", BASE/"output", BASE/"failed"
MAX_TABS = 5
MAX_TRIES = 3
RETRY_GAP_SECONDS = 5
URL = "https://www.photoroom.com/tools/background-remover"
EXTS = {".jpg",".jpeg",".png",".webp",".bmp",".tif",".tiff"}

CLICK_WAIT_MS = 4000
CAPTCHA_POLL_MS = 500
CAPTCHA_CHECK_TIMEOUT_MS = 700
FILE_CHOOSER_TIMEOUT_MS = 2500
PAGE_LOAD_TIMEOUT_MS = 45000
UPLOAD_CONFIRM_TIMEOUT_MS = 45000
DOWNLOAD_TIMEOUT_MS = 45000
POLL_MS = 250
CAPTCHA_GATE = asyncio.Lock()
CAPTCHA_PATTERNS = [
    re.compile(r"\binvalid\s+captcha\b", re.I),
    re.compile(r"\bcode\s*[:#-]?\s*600010\b", re.I),
    re.compile(r"\bi\s*[\'’]?m\s+not\s+a\s+robot\b", re.I),
    re.compile(r"\bverify\s+(?:that\s+)?you\s+are\s+human\b", re.I),
    re.compile(r"\bplease\s+verify\s+(?:that\s+you\s+are\s+)?human\b", re.I),
]
async def click_and_wait(locator):
    await wait_for_captcha_clear(locator.page, label="click")
    await locator.click()
    await locator.page.wait_for_timeout(CLICK_WAIT_MS)
    await wait_for_captcha_clear(locator.page, label="post-click")

async def first_visible(locators):
    for loc in locators:
        try:
            if await loc.count() and await loc.first.is_visible():
                return loc.first
        except Exception:
            pass
    return None


async def captcha_present(page):
    """Return True only for a visible/active CAPTCHA or human-verification state."""
    try:
        body = await page.locator("body").inner_text(timeout=CAPTCHA_CHECK_TIMEOUT_MS)
        text = " ".join(body.split())
        for pattern in CAPTCHA_PATTERNS:
            if pattern.search(text):
                return True
    except Exception:
        pass

    try:
        frames = page.locator(
            'iframe[src*="/challenge" i], '
            'iframe[src*="bframe" i], '
            'iframe[title*="challenge" i], '
            'iframe[aria-label*="challenge" i]'
        )
        for i in range(await frames.count()):
            try:
                frame = frames.nth(i)
                if await frame.is_visible():
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


async def _save_captcha_debug(page, stem):
    try:
        FAILED.mkdir(exist_ok=True)
        await page.screenshot(path=str(FAILED / f"CAPTCHA_{stem}.png"), full_page=True)
        (FAILED / f"CAPTCHA_{stem}.html").write_text(await page.content(), encoding="utf-8")
        (FAILED / f"CAPTCHA_{stem}.txt").write_text(
            (await page.locator("body").inner_text())[:20000], encoding="utf-8"
        )
    except Exception:
        pass


async def wait_for_captcha_clear(page, label="", debug_stem=None):
    """Pause only the affected worker while the user manually clears CAPTCHA."""
    if not await captcha_present(page):
        return

    async with CAPTCHA_GATE:
        if not await captcha_present(page):
            return

        stem = debug_stem or re.sub(r"[^A-Za-z0-9._-]+", "_", label or "unknown")
        await _save_captcha_debug(page, stem)
        print(f"\n[CAPTCHA][Tab/page: {label}] CAPTCHA detected.")
        print("[CAPTCHA] Chrome will remain OPEN. Complete the CAPTCHA manually in THIS tab.")
        print("[CAPTCHA] After solving it, press ENTER here. The script will verify it cleared.")

        while True:
            await asyncio.to_thread(input, "[CAPTCHA] Press ENTER after completing the CAPTCHA: ")
            await page.wait_for_timeout(CAPTCHA_POLL_MS)
            if not await captcha_present(page):
                print(f"[CAPTCHA] {label} — CAPTCHA cleared. Continuing.")
                return
            print("[CAPTCHA] The challenge is still detected. Finish it in the browser, then press ENTER again.")


async def wait_for_download_control(page, timeout_ms=DOWNLOAD_TIMEOUT_MS):
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    while asyncio.get_running_loop().time() < deadline:
        loc = await first_visible([
            page.get_by_role("button", name=re.compile(r"^Download(?:\b|$)", re.I)),
            page.get_by_role("link", name=re.compile(r"^Download(?:\b|$)", re.I)),
            page.locator('[aria-label*="Download" i]'),
            page.get_by_text(re.compile(r"^Download(?:\b|$)", re.I)),
        ])
        if loc:
            return loc
        await page.wait_for_timeout(POLL_MS)
    return None


async def click_file_chooser_and_wait(item, src):
    await wait_for_captcha_clear(item.page, label=src.name)
    chooser_task = asyncio.create_task(item.page.wait_for_event("filechooser", timeout=FILE_CHOOSER_TIMEOUT_MS))
    try:
        await item.click()
        await item.page.wait_for_timeout(CLICK_WAIT_MS)
        await wait_for_captcha_clear(item.page, label=src.name, debug_stem=src.stem)
        chooser = await chooser_task
    except Exception:
        if not chooser_task.done():
            chooser_task.cancel()
        await asyncio.gather(chooser_task, return_exceptions=True)
        raise
    await chooser.set_files(str(src))
    await wait_for_captcha_clear(item.page, label=src.name, debug_stem=src.stem)


async def upload(page, src):
    await page.goto(URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
    await page.wait_for_timeout(500)
    await wait_for_captcha_clear(page, label=src.name, debug_stem=src.stem)

    async def set_any_file_input():
        inputs = page.locator('input[type="file"]')
        count = await inputs.count()
        for i in range(count):
            try:
                await inputs.nth(i).set_input_files(str(src))
                await wait_for_captcha_clear(page, label=src.name, debug_stem=src.stem)
                return True
            except Exception:
                pass
        return False

    async def confirm_editor():
        await wait_for_captcha_clear(page, label=src.name, debug_stem=src.stem)
        loc = await wait_for_download_control(page, UPLOAD_CONFIRM_TIMEOUT_MS)
        return bool(loc)

    if await set_any_file_input():
        if await confirm_editor():
            return
        raise RuntimeError(f"File input accepted the image, but Background Remover did not reach the editor. URL={page.url}")

    candidates = [
        page.get_by_role("button", name=re.compile(r"Start from a photo|Upload|Select photos|Choose (?:a )?photo(?:s)?|Add image(?:s)?|Upload image(?:s)?", re.I)),
        page.get_by_role("link", name=re.compile(r"Start from a photo|Upload|Select photos|Choose (?:a )?photo(?:s)?|Add image(?:s)?|Upload image(?:s)?", re.I)),
        page.locator('[aria-label*="Start from a photo" i]'),
        page.locator('[aria-label*="Upload" i]'),
        page.locator('[aria-label*="Select photos" i]'),
        page.locator('[aria-label*="Choose photo" i]'),
        page.locator('[aria-label*="Add image" i]'),
        page.get_by_text(re.compile(r"^Start from a photo$|^Upload(?: image(?:s)?)?$|^Select photos$|^Choose (?:a )?photo(?:s)?$|^Add images?$", re.I)),
    ]

    for control in candidates:
        try:
            count = await control.count()
            for i in range(min(count, 5)):
                item = control.nth(i)
                try:
                    if not await item.is_visible():
                        continue
                except Exception:
                    continue
                try:
                    await click_file_chooser_and_wait(item, src)
                    if await confirm_editor():
                        return
                except Exception:
                    pass
                if await set_any_file_input():
                    if await confirm_editor():
                        return
        except Exception:
            pass

    broad = page.locator('button, a, [role="button"]').filter(
        has_text=re.compile(r"upload|start from a photo|select photos|choose photo|add images?|add photo", re.I)
    )
    try:
        count = await broad.count()
        for i in range(min(count, 10)):
            item = broad.nth(i)
            if not await item.is_visible():
                continue
            try:
                await click_file_chooser_and_wait(item, src)
                if await confirm_editor():
                    return
            except Exception:
                pass
            if await set_any_file_input():
                if await confirm_editor():
                    return
    except Exception:
        pass

    try:
        await page.screenshot(path=str(FAILED / f"DEBUG_upload_{src.stem}.png"), full_page=True)
        (FAILED / f"DEBUG_upload_{src.stem}.html").write_text(await page.content(), encoding="utf-8")
        (FAILED / f"DEBUG_upload_{src.stem}.txt").write_text((await page.locator("body").inner_text())[:20000], encoding="utf-8")
    except Exception:
        pass
    raise RuntimeError(f"Background Remover upload failed. URL={page.url}")


async def download_png(page, src_name):
    download = await wait_for_download_control(page, DOWNLOAD_TIMEOUT_MS)
    if not download:
        raise RuntimeError(f"Download control not found after {DOWNLOAD_TIMEOUT_MS/1000:.0f}s. URL={page.url}")

    out = OUTPUT / (Path(src_name).stem + ".png")

    try:
        async with page.expect_download(timeout=7000) as info:
            await click_and_wait(download)
        dl = await info.value
        await dl.save_as(str(out))
        return
    except Exception:
        pass

    await page.wait_for_timeout(800)
    png = await first_visible([
        page.get_by_role("radio", name=re.compile(r"^PNG$", re.I)),
        page.get_by_role("option", name=re.compile(r"^PNG$", re.I)),
        page.get_by_text(re.compile(r"^PNG$", re.I)),
        page.locator('[aria-label="PNG" i]'),
        page.locator('[data-format="png" i]'),
    ])
    if png:
        await click_and_wait(png)

    final_download = await wait_for_download_control(page, 30000)
    if not final_download:
        raise RuntimeError("Final Download control not found after export dialog.")

    async with page.expect_download(timeout=30000) as info:
        await click_and_wait(final_download)
    dl = await info.value
    await dl.save_as(str(out))


async def process(context, src, slot):
    page = await context.new_page()
    try:
        for attempt in range(1, MAX_TRIES+1):
            try:
                print(f"[Tab {slot}] {src.name} — try {attempt}/{MAX_TRIES}")
                await upload(page, src)
                await download_png(page, src.name)
                print(f"[Tab {slot}] OK: {src.name}")
                return
            except Exception as e:
                print(f"[Tab {slot}] FAIL: {src.name} — {e}")
                if attempt < MAX_TRIES:
                    await asyncio.sleep(RETRY_GAP_SECONDS)
                    try:
                        await page.goto(URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
                    except Exception:
                        pass
        shutil.copy2(src, FAILED/src.name)
        print(f"[Tab {slot}] FAILED: {src.name}")
    finally:
        await page.close()

async def worker(context, queue, slot):
    while True:
        src = await queue.get()
        if src is None:
            queue.task_done()
            return
        try:
            await process(context, src, slot)
        finally:
            queue.task_done()

async def main():
    if not PROFILE.exists():
        raise SystemExit("Dedicated profile missing. Run setup_profile.bat first.")
    for d in (INPUT, OUTPUT, FAILED): d.mkdir(exist_ok=True)
    files = sorted(p for p in INPUT.iterdir() if p.is_file() and p.suffix.lower() in EXTS)
    print(f"Dedicated profile: {PROFILE}")
    print(f"Images found: {len(files)}")
    if not files: return

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="chrome", headless=False,
            accept_downloads=True, viewport={"width":1440,"height":900})
        try:
            q = asyncio.Queue()
            for f in files: await q.put(f)
            n = min(MAX_TABS, len(files))
            workers = [asyncio.create_task(worker(context,q,i+1)) for i in range(n)]
            await q.join()
            for _ in workers: await q.put(None)
            await asyncio.gather(*workers)
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
