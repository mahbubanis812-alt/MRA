FINAL V7 - Photoroom background remover

Windows folder-only automation using Chrome + Playwright async API.

Features:
- Dedicated Chrome profile in ./chrome_profile
- Directly opens https://app.photoroom.com/
- Up to 5 concurrent tabs with queue behavior
- 3 attempts per image
- 5-second retry gap
- Mandatory 4-second wait after every UI click
- Transparent PNG output in ./output
- Failed originals copied to ./failed after all attempts fail
- No Chrome force-close
- No Chrome 3-dot menu automation
- No address-bar paste automation

Setup:
1. Run setup_profile.bat
2. Log in to Photoroom once in the dedicated Chrome window, then close it normally.
3. Put images into input\
4. Run run.bat
