from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:8010/"
TARGET_SESSION_ID = "single_joycesheng_wmS8sICwAAa55HEd90VALjoRBvCJE43g"
OUT_DIR = Path(__file__).resolve().parent


def safe_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")


def card_text(page, index: int) -> str:
    return page.evaluate(
        """idx => {
            const cards = Array.from(document.querySelectorAll('#analysis-content .pipeline-card'));
            return cards[idx - 1] ? cards[idx - 1].innerText : '';
        }""",
        index,
    )


def operation_status_text(page) -> str:
    return page.evaluate(
        """() => {
            const box = document.getElementById('operation-status');
            return box && !box.classList.contains('hidden') ? box.innerText : '';
        }"""
    )


def scroll_to_card(page, index: int) -> None:
    page.evaluate(
        """idx => {
            const cards = Array.from(document.querySelectorAll('#analysis-content .pipeline-card'));
            if (cards[idx - 1]) cards[idx - 1].scrollIntoView({block: 'center', inline: 'nearest'});
        }""",
        index,
    )
    page.wait_for_timeout(500)


def save_step(page, step: int, slug: str, results: list[dict], extra: dict | None = None) -> None:
    scroll_to_card(page, step)
    png = OUT_DIR / f"step-{step:02d}-{slug}.png"
    html = OUT_DIR / f"step-{step:02d}-{slug}.html"
    page.screenshot(path=str(png), full_page=False)
    html.write_text(page.content(), encoding="utf-8")
    results.append(
        {
            "step": step,
            "slug": slug,
            "screenshot": png.name,
            "html": html.name,
            "card_text": card_text(page, step),
            "operation_status": operation_status_text(page),
            **(extra or {}),
        }
    )


def click_card_button(page, card_index: int, pattern: str) -> None:
    scroll_to_card(page, card_index)
    card = page.locator("#analysis-content .pipeline-card").nth(card_index - 1)
    card.get_by_role("button", name=re.compile(pattern)).click()


def wait_for_cards(page, timeout_ms: int = 30000) -> None:
    page.wait_for_function(
        "() => document.querySelectorAll('#analysis-content .pipeline-card').length >= 7",
        timeout=timeout_ms,
    )


def refresh_analysis_from_ui(page) -> None:
    try:
        scroll_to_card(page, 2)
        page.get_by_role("button", name=re.compile("刷新")).first.click(timeout=2500)
        wait_for_cards(page, timeout_ms=15000)
    except PlaywrightTimeoutError:
        pass


def wait_until(page, predicate, timeout_ms: int, poll_ms: int = 5000) -> bool:
    deadline = datetime.now().timestamp() + timeout_ms / 1000
    while datetime.now().timestamp() < deadline:
        try:
            wait_for_cards(page, timeout_ms=15000)
            if predicate():
                return True
            refresh_analysis_from_ui(page)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(poll_ms)
        page.wait_for_timeout(poll_ms)
    return predicate()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dialogs: list[str] = []
    console_errors: list[str] = []
    results: list[dict] = []
    sync_result = {"attempted": False, "dialog_messages": dialogs}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1680, "height": 1050}, device_scale_factor=1)
        page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector("#sync-btn", timeout=30000)

        sync_result["attempted"] = True
        page.locator("#sync-btn").click()
        page.wait_for_timeout(2500)
        sync_png = OUT_DIR / "sync-real-ui-status.png"
        page.screenshot(path=str(sync_png), full_page=False)
        try:
            page.wait_for_function("() => !document.querySelector('#sync-btn')?.disabled", timeout=90000)
        except PlaywrightTimeoutError:
            sync_result["timeout"] = True
        sync_result["operation_status"] = operation_status_text(page)
        sync_result["screenshot"] = sync_png.name

        selector = f"#session-{TARGET_SESSION_ID}"
        page.locator(selector).scroll_into_view_if_needed(timeout=30000)
        page.locator(selector).click(timeout=30000)
        wait_for_cards(page, timeout_ms=30000)

        save_step(page, 1, "conversation-input", results, {"data_type": "real_wecom_history"})
        save_step(page, 2, "fast-track-scan", results, {"data_type": "real_wecom_history"})

        click_card_button(page, 3, "提取|重新提取")
        page.wait_for_timeout(7000)
        step3_ok = wait_until(
            page,
            lambda: "重新提取" in card_text(page, 3) and "等待提取" not in card_text(page, 3),
            timeout_ms=180000,
        )
        save_step(page, 3, "llm1-feature-extract", results, {"completed": step3_ok})

        save_step(page, 4, "crm-profile", results, {"data_type": "old_crm_read_only"})

        click_card_button(page, 6, "生成回复|重新生成")
        page.wait_for_timeout(7000)
        step6_ok = wait_until(
            page,
            lambda: "已生成" in card_text(page, 6) and "复制" in card_text(page, 6),
            timeout_ms=240000,
        )
        save_step(page, 5, "knowledge-evidence", results, {"completed_after_step6": step6_ok})
        save_step(page, 6, "llm2-final-reply", results, {"completed": step6_ok})
        save_step(page, 7, "output-validation", results, {"completed_after_step6": step6_ok})

        (OUT_DIR / "ui_test_result.json").write_text(
            json.dumps(
                {
                    "base_url": BASE_URL,
                    "target_session_id": TARGET_SESSION_ID,
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "sync": sync_result,
                    "steps": results,
                    "dialogs": dialogs,
                    "console_errors": console_errors,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()


if __name__ == "__main__":
    main()
