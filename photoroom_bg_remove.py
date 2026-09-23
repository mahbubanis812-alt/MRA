from pathlib import Path
import shutil, asyncio, re
from playwright.async_api import async_playwright

BASE = Path(__file__).resolve().parent
PROFILE = BASE / "chrome_profile"
INPUT, OUTPUT, FAILED = BASE/"input", BASE/"output", BASE/"failed"

MAX_TABS = 5
MAX_TRIES = 3
RETRY_GAP_SECONDS = 5
URL = "https://app.photoroom.com/"
EXTS = {".jpg",".jpeg",".png",".webp",".bmp",".tif",".tiff"}
CLICK_WAIT_MS = 4000

async def click_and_wait(locator):
    await locator.click()
    await locator.page.wait_for_timeout(CLICK_WAIT_MS)

async def first_visible(locators):
    for loc in locators:
        try:
            if await loc.count() and await loc.first.is_visible():
                return loc.first
        except Exception:
            pass
    return None

async def upload(page, src):
    await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    if "login" in page.url.lower():
        raise RuntimeError("Not logged in to Photoroom. Run setup_profile.bat and log in once.")
    await page.wait_for_timeout(3000)

    async def set_any_file_input():
        inputs = page.locator('input[type="file"]')
        for i in range(await inputs.count()):
            try:
                await inputs.nth(i).set_input_files(str(src))
                return True
            except Exception:
                pass
        return False

    if await set_any_file_input():
        return

    candidates = [
        page.get_by_role("button", name=re.compile(r"Select photos|Upload(?: a photo)?|Choose (?:a )?photo(?:s)?|Start creating", re.I)),
        page.get_by_role("link", name=re.compile(r"Select photos|Upload(?: a photo)?|Choose (?:a )?photo(?:s)?|Start creating", re.I)),
        page.locator('[aria-label*="Select photos" i]'),
        page.locator('[aria-label*="Upload" i]'),
        page.locator('[aria-label*="Choose photo" i]'),
        page.get_by_text(re.compile(r"Select photos|Upload(?: a photo)?|Choose (?:a )?photo(?:s)?|Start creating", re.I)),
    ]

    for control in candidates:
        try:
            if not await control.count():
                continue
            for i in range(min(await control.count(), 3)):
                item = control.nth(i)
                try:
                    if not await item.is_visible():
                        continue
                except Exception:
                    pass
                try:
                    async with page.expect_file_chooser(timeout=5000) as info:
                        await item.click()
                    chooser = await info.value
                    await page.wait_for_timeout(CLICK_WAIT_MS)
                    await chooser.set_files(str(src))
                    return
                except Exception:
                    pass
                await page.wait_for_timeout(1000)
                if await set_any_file_input():
                    return
        except Exception:
            pass

    broad = page.locator('button, a, [role="button"]').filter(
        has_text=re.compile(r"upload|select photos|choose photo|start creating", re.I)
    )
    try:
        for i in range(min(await broad.count(), 5)):
            item = broad.nth(i)
            if not await item.is_visible():
                continue
            try:
                async with page.expect_file_chooser(timeout=5000) as info:
                    await item.click()
                chooser = await info.value
                await page.wait_for_timeout(CLICK_WAIT_MS)
                await chooser.set_files(str(src))
                return
            except Exception:
                pass
            await page.wait_for_timeout(1000)
            if await set_any_file_input():
                return
    except Exception:
        pass

    raise RuntimeError(f"Photoroom upload control not found. URL={page.url}")

async def download_png(page, src_name):
    download = await first_visible([
        page.get_by_role("button", name=re.compile(r"^Download", re.I)),
        page.get_by_role("link", name=re.compile(r"^Download", re.I)),
        page.locator('[aria-label*="Download" i]'),
    ])
    if not download:
        raise RuntimeError(f"Download control not found. URL={page.url}")

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
        page.get_by_role("radio", name=re.compile(r"PNG", re.I)),
        page.get_by_role("option", name=re.compile(r"PNG", re.I)),
        page.get_by_text(re.compile(r"^PNG$", re.I)),
        page.locator('[aria-label*="PNG" i]'),
    ])
    if png:
        try:
            await click_and_wait(png)
        except Exception:
            pass

    final_download = await first_visible([
        page.get_by_role("button", name=re.compile(r"^Download$", re.I)),
        page.get_by_role("button", name=re.compile(r"Download", re.I)),
        page.locator('[aria-label*="Download" i]'),
    ])
    if not final_download:
        raise RuntimeError("Final Download button not found after export dialog.")

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
                await page.wait_for_timeout(2500)
                await download_png(page, src.name)
                print(f"[Tab {slot}] OK: {src.name}")
                return
            except Exception as e:
                print(f"[Tab {slot}] FAIL: {src.name} — {e}")
                if attempt < MAX_TRIES:
                    await asyncio.sleep(RETRY_GAP_SECONDS)
                    try:
                        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
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
    for d in (INPUT, OUTPUT, FAILED):
        d.mkdir(exist_ok=True)

    files = sorted(p for p in INPUT.iterdir() if p.is_file() and p.suffix.lower() in EXTS)
    print(f"Dedicated profile: {PROFILE}")
    print(f"Images found: {len(files)}")
    if not files:
        return

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="chrome", headless=False,
            accept_downloads=True, viewport={"width":1440,"height":900})
        try:
            q = asyncio.Queue()
            for f in files:
                await q.put(f)
            n = min(MAX_TABS, len(files))
            workers = [asyncio.create_task(worker(context, q, i+1)) for i in range(n)]
            await q.join()
            for _ in workers:
                await q.put(None)
            await asyncio.gather(*workers)
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
