import json
import os
import sys
import time


INPUT_SELECTORS = [
    "textarea",
    '[contenteditable="true"][role="textbox"]',
    'rich-textarea [contenteditable="true"]',
]
RESPONSE_SELECTORS = [
    '[data-message-author-role="assistant"]',
    '[data-turn-role="model"]',
    "model-response",
    "message-content",
]
SEND_SELECTORS = [
    'button[aria-label*="Send"]',
    'button[aria-label*="Submit"]',
]
NEW_CHAT_SELECTORS = [
    'button[aria-label*="New chat"]',
    'button:has-text("New chat")',
    'a:has-text("New chat")',
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        emit_error(
            "Playwright is not installed for the system python. Run: pip install playwright && python3 -m playwright install chromium"
        )
        raise SystemExit(1) from exc

    payload = json.load(sys.stdin)
    prompt = payload["prompt"]
    profile_dir = os.path.expanduser(payload["profile_dir"])
    page_url = payload["page_url"]
    timeout_sec = int(payload["timeout_sec"])
    timeout_ms = timeout_sec * 1000

    os.makedirs(profile_dir, exist_ok=True)

    try:
        with sync_playwright() as playwright:
            context = launch_context(playwright, profile_dir)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                click_if_present(page, NEW_CHAT_SELECTORS, 1500)

                input_locator = find_locator(page, INPUT_SELECTORS, min(timeout_ms, 30000))
                if input_locator is None:
                    raise RuntimeError(
                        "Gemini page input not found. Open the Playwright profile once, sign in to Gemini, then retry."
                    )

                baseline = read_latest_response(page)
                fill_prompt(page, input_locator, prompt)

                try:
                    input_locator.press("Enter")
                except Exception:
                    if not click_if_present(page, SEND_SELECTORS, 5000):
                        raise RuntimeError("Could not submit the Gemini prompt from the webpage")

                text = wait_for_response(page, baseline, timeout_ms)
                print(json.dumps({"ok": True, "text": text}))
            finally:
                context.close()
    except Exception as exc:
        emit_error(str(exc))
        raise SystemExit(1)


def launch_context(playwright, profile_dir):
    launch_attempts = [
        {"channel": "chrome", "headless": False},
        {"headless": False},
    ]

    last_error = None
    for kwargs in launch_attempts:
        try:
            return playwright.chromium.launch_persistent_context(
                profile_dir,
                viewport={"width": 1280, "height": 900},
                **kwargs,
            )
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Playwright could not launch a browser: {last_error}")


def find_locator(page, selectors, timeout_ms):
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if locator.count() and locator.is_visible(timeout=250):
                    return locator
            except Exception:
                continue
        page.wait_for_timeout(250)
    return None


def click_if_present(page, selectors, timeout_ms):
    locator = find_locator(page, selectors, timeout_ms)
    if locator is None:
        return False
    try:
        locator.click()
        return True
    except Exception:
        return False


def fill_prompt(page, input_locator, prompt):
    input_locator.click()
    for combo in ("Meta+A", "Control+A"):
        try:
            page.keyboard.press(combo)
            break
        except Exception:
            continue
    try:
        page.keyboard.press("Backspace")
    except Exception:
        pass

    try:
        input_locator.fill(prompt)
        return
    except Exception:
        pass

    page.keyboard.insert_text(prompt)


def read_latest_response(page):
    for selector in RESPONSE_SELECTORS:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:
            continue
        for index in range(count - 1, -1, -1):
            try:
                text = locator.nth(index).inner_text(timeout=500).strip()
            except Exception:
                continue
            if text:
                return text
    return ""


def wait_for_response(page, baseline, timeout_ms):
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_seen = ""
    stable_polls = 0

    while time.monotonic() < deadline:
        current = read_latest_response(page)
        if current and current != baseline:
            if current == last_seen:
                stable_polls += 1
            else:
                last_seen = current
                stable_polls = 1
            if stable_polls >= 2:
                return current
        page.wait_for_timeout(1000)

    if last_seen:
        return last_seen
    raise RuntimeError("Timed out waiting for a Gemini webpage response")


def emit_error(message):
    print(json.dumps({"ok": False, "error": message}))


if __name__ == "__main__":
    main()
