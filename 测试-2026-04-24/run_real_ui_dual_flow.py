from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import Dialog, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


BASE_URL = "http://127.0.0.1:8000/"
TARGET_SESSION_ID = "single_HanHan_wmS8sICwAA7w7s1etSmkPpW45-iOQUFQ"
TEST_MARK = "e2e-ui-20260424"
OUT_DIR = Path(__file__).resolve().parent
EXCEL_FILES = sorted(OUT_DIR.glob("*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
EXCEL_PATH = EXCEL_FILES[0] if EXCEL_FILES else OUT_DIR / "knowledge_import_test_data.xlsx"
RESULT_JSON = OUT_DIR / "ui_dual_flow_result.json"


def text_or_empty(locator) -> str:
    try:
        return (locator.inner_text(timeout=3000) or "").strip()
    except Exception:
        return ""


def file_name(index: int, slug: str, suffix: str) -> str:
    return f"step-{index:02d}-{slug}.{suffix}"


def save_step(page: Page, index: int, slug: str, title: str, records: list[dict], extra: dict | None = None) -> None:
    page.wait_for_timeout(800)
    png = OUT_DIR / file_name(index, slug, "png")
    html = OUT_DIR / file_name(index, slug, "html")
    page.screenshot(path=str(png), full_page=True)
    html.write_text(page.content(), encoding="utf-8")
    records.append(
        {
            "step_index": index,
            "step_slug": slug,
            "title": title,
            "screenshot": png.name,
            "html": html.name,
            **(extra or {}),
        }
    )


def wait_visible_text(page: Page, selector: str, text: str, timeout: int = 30000) -> None:
    page.wait_for_function(
        """([sel, expected]) => {
            const node = document.querySelector(sel);
            return !!node && node.innerText.includes(expected);
        }""",
        arg=[selector, text],
        timeout=timeout,
    )


def get_json_from_pre(page: Page, selector: str) -> dict:
    raw = text_or_empty(page.locator(selector))
    return json.loads(raw) if raw.startswith("{") else {}


def goto_kb(page: Page) -> None:
    page.locator("#main-tab-kb").click()
    page.wait_for_timeout(1500)


def goto_wecom(page: Page) -> None:
    page.locator("#main-tab-wecom").click()
    page.wait_for_timeout(1500)


def open_kb_tab_by_index(page: Page, index: int) -> None:
    page.locator("#kb-tabs button").nth(index - 1).click()
    page.wait_for_timeout(1500)


def open_batch_by_id(page: Page, batch_id: str) -> None:
    page.wait_for_function(
        """batchId => Array.from(document.querySelectorAll('#kb-batches-list > div')).some(node => node.innerText.includes(batchId))""",
        arg=batch_id,
        timeout=30000,
    )
    page.locator("#kb-batches-list > div").filter(has_text=batch_id).first.click(timeout=30000)
    page.wait_for_timeout(1500)
    wait_visible_text(page, "#kb-detail", batch_id, timeout=30000)


def kb_detail_text(page: Page) -> str:
    return text_or_empty(page.locator("#kb-detail"))


def kb_retrieve_result_text(page: Page) -> str:
    return text_or_empty(page.locator("#kb-retrieve-result"))


def analysis_card_text(page: Page, index: int) -> str:
    return page.evaluate(
        """idx => {
            const cards = Array.from(document.querySelectorAll('#analysis-content .pipeline-card'));
            return cards[idx - 1] ? cards[idx - 1].innerText : '';
        }""",
        index,
    )


def operation_status_text(page: Page) -> str:
    return page.evaluate(
        """() => {
            const box = document.getElementById('operation-status');
            return box && !box.classList.contains('hidden') ? box.innerText : '';
        }"""
    )


def scroll_to_analysis_card(page: Page, index: int) -> None:
    page.evaluate(
        """idx => {
            const cards = Array.from(document.querySelectorAll('#analysis-content .pipeline-card'));
            if (cards[idx - 1]) {
                cards[idx - 1].scrollIntoView({block: 'center', inline: 'nearest'});
            }
        }""",
        index,
    )
    page.wait_for_timeout(500)


def save_analysis_step(
    page: Page,
    index: int,
    file_index: int,
    slug: str,
    title: str,
    records: list[dict],
    extra: dict | None = None,
) -> None:
    scroll_to_analysis_card(page, index)
    save_step(
        page,
        file_index,
        slug,
        title,
        records,
        {
            "pipeline_step": index,
            "card_text": analysis_card_text(page, index),
            "operation_status": operation_status_text(page),
            **(extra or {}),
        },
    )


def wait_for_analysis_cards(page: Page, timeout_ms: int = 30000) -> None:
    page.wait_for_function(
        "() => document.querySelectorAll('#analysis-content .pipeline-card').length >= 7",
        timeout=timeout_ms,
    )


def refresh_analysis(page: Page) -> None:
    try:
        page.get_by_role("button", name=re.compile("刷新|Refresh")).first.click(timeout=2500)
        page.wait_for_timeout(1200)
    except Exception:
        pass


def wait_until(predicate, timeout_sec: int, poll_sec: float = 3.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(poll_sec)
    return predicate()


def api_get_json(path: str, timeout: int = 120) -> dict:
    response = requests.get(f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}", timeout=timeout)
    response.raise_for_status()
    return response.json()


def api_post_json(path: str, payload: dict | None = None, timeout: int = 120) -> dict:
    response = requests.post(
        f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def run_flow1(page: Page, records: list[dict], dialogs: list[str]) -> dict:
    batch_id = ""
    preview_data: dict = {}
    commit_data: dict = {}
    imported_doc_ids: list[str] = []
    retrieve_text = ""
    rollback_result: dict | None = None

    goto_kb(page)
    open_kb_tab_by_index(page, 4)
    page.locator("#kb-excel-file").set_input_files(str(EXCEL_PATH))
    page.wait_for_timeout(1200)

    page.locator("#kb-body button").nth(1).click()
    page.wait_for_function(
        """() => {
            const summary = document.getElementById('kb-import-summary');
            const result = document.getElementById('kb-import-result');
            return !!summary && summary.innerText.trim().length > 0 && !!result && result.innerText.includes('valid_count');
        }""",
        timeout=60000,
    )
    preview_data = get_json_from_pre(page, "#kb-import-result")
    save_step(
        page,
        1,
        "kb-preview",
        "Knowledge Import Preview",
        records,
        {"result": preview_data, "excel_path": str(EXCEL_PATH)},
    )

    page.locator("#kb-body button").nth(2).click()
    page.wait_for_function(
        """() => {
            const result = document.getElementById('kb-import-result');
            return !!result && result.innerText.includes('import_batch');
        }""",
        timeout=240000,
    )
    commit_data = get_json_from_pre(page, "#kb-import-result")
    job_result = ((commit_data.get("result") or {}) if commit_data else {}) or {}
    batch_id = job_result.get("import_batch") or commit_data.get("import_batch") or ""
    imported_doc_ids = [item.get("document_id") for item in commit_data.get("created", []) if item.get("document_id")]
    if not batch_id:
        raise RuntimeError(f"Import batch missing in commit result: {commit_data}")
    save_step(
        page,
        2,
        "kb-import-commit",
        "Knowledge Import Commit",
        records,
        {"result": commit_data, "import_batch": batch_id},
    )

    try:
        open_kb_tab_by_index(page, 5)
        open_batch_by_id(page, batch_id)
        batch_detail = kb_detail_text(page)
        save_step(
            page,
            3,
            "kb-batch-detail",
            "Knowledge Batch Detail",
            records,
            {"import_batch": batch_id, "detail_text": batch_detail},
        )

        page.locator("#kb-detail .flex.gap-2 button").nth(0).click()
        page.wait_for_timeout(2500)
        batch_detail = kb_detail_text(page)
        save_step(
            page,
            4,
            "kb-submit-review",
            "Knowledge Submit Review",
            records,
            {"import_batch": batch_id, "detail_text": batch_detail},
        )

        page.locator("#kb-detail .flex.gap-2 button").nth(1).click()
        page.wait_for_timeout(2500)
        batch_detail = kb_detail_text(page)
        save_step(
            page,
            5,
            "kb-approve",
            "Knowledge Approve",
            records,
            {"import_batch": batch_id, "detail_text": batch_detail},
        )

        open_kb_tab_by_index(page, 2)
        page.wait_for_function(
            """ids => Array.from(document.querySelectorAll('#kb-review-list input.kb-select-doc')).some(node => ids.includes(node.value))""",
            arg=imported_doc_ids,
            timeout=30000,
        )
        selected_count = page.evaluate(
            """ids => {
                let count = 0;
                for (const checkbox of Array.from(document.querySelectorAll('#kb-review-list input.kb-select-doc'))) {
                    if (!ids.includes(checkbox.value)) continue;
                    checkbox.checked = true;
                    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                    count += 1;
                }
                if (typeof updateReviewBulkActions === 'function') updateReviewBulkActions();
                return count;
            }""",
            imported_doc_ids,
        )
        if selected_count != len(imported_doc_ids):
            raise RuntimeError(f"Expected {len(imported_doc_ids)} selected docs, got {selected_count}")
        page.wait_for_function(
            "() => !!document.getElementById('kb-review-publish-btn') && !document.getElementById('kb-review-publish-btn').disabled",
            timeout=10000,
        )
        page.locator("#kb-review-publish-btn").click()
        try:
            page.wait_for_function(
                """() => {
                    const dialog = document.getElementById('kb-text-input-dialog');
                    return !!dialog && dialog.classList.contains('flex');
                }""",
                timeout=30000,
            )
            dialog = page.locator("#kb-text-input-dialog")
            dialog.locator("#kb-textarea-field").fill(
                "UI E2E validation for an isolated imported batch. Force publish is used only because the governance gate covers broader regression cases than this 4-record test batch, and the batch will be rolled back after retrieval validation."
            )
            dialog.locator("#kb-text-input-confirm").click()
            page.wait_for_function(
                """() => {
                    const dialog = document.getElementById('kb-text-input-dialog');
                    return !dialog || !dialog.classList.contains('flex');
                }""",
                timeout=30000,
            )
        except PlaywrightTimeoutError:
            page.wait_for_timeout(2000)

        batch_state: dict = {}

        def publish_ready() -> bool:
            nonlocal batch_state
            batch_state = api_get_json(f"/api/kb/import_batches/{batch_id}")
            counts = ((batch_state.get("summary") or {}).get("status_counts") or {})
            return int(counts.get("active") or 0) == len(imported_doc_ids)

        if not wait_until(publish_ready, timeout_sec=90, poll_sec=3):
            raise RuntimeError(f"Batch publish not confirmed by API: {batch_state}")
        save_step(
            page,
            6,
            "kb-publish",
            "Knowledge Publish",
            records,
            {
                "import_batch": batch_id,
                "selected_count": selected_count,
                "dialogs": list(dialogs),
                "batch_state": batch_state,
            },
        )

        open_kb_tab_by_index(page, 7)
        page.locator("#kb-retrieve-query").fill(
            "How should we respond if the client asks whether the English to French urgent surcharge is fixed and what the baseline quote is?"
        )
        try:
            page.locator("#kb-retrieve-type").select_option("semantic")
        except Exception:
            pass
        try:
            page.locator("#kb-retrieve-topk").fill("5")
        except Exception:
            pass
        page.locator("#kb-body button").first.click()
        page.wait_for_function(
            """() => {
                const box = document.getElementById('kb-retrieve-result');
                return !!box && !box.innerText.includes('检索中');
            }""",
            timeout=90000,
        )
        retrieve_text = kb_retrieve_result_text(page)
        if TEST_MARK not in retrieve_text:
            raise RuntimeError(f"Retrieve result did not hit the test knowledge: {retrieve_text}")
        save_step(
            page,
            7,
            "kb-retrieve",
            "Knowledge Retrieve",
            records,
            {"import_batch": batch_id, "retrieve_text": retrieve_text},
        )

        rollback_result = api_post_json(f"/api/kb/import_batches/{batch_id}/rollback")
        save_step(
            page,
            8,
            "kb-rollback",
            "Knowledge Rollback Cleanup",
            records,
            {"import_batch": batch_id, "rollback_result": rollback_result},
        )
        return {
            "import_batch": batch_id,
            "preview": preview_data,
            "commit": commit_data,
            "retrieve_text": retrieve_text,
            "rollback_result": rollback_result,
        }
    finally:
        if batch_id and rollback_result is None:
            try:
                api_post_json(f"/api/kb/import_batches/{batch_id}/rollback")
            except Exception:
                pass


def run_flow2(page: Page, records: list[dict], dialogs: list[str]) -> dict:
    goto_wecom(page)
    page.wait_for_selector("#sync-btn", timeout=30000)
    page.locator("#sync-btn").click()
    page.wait_for_timeout(2500)
    save_step(
        page,
        9,
        "wecom-sync",
        "WeCom Sync",
        records,
        {"operation_status": operation_status_text(page)},
    )

    selector = f"#session-{TARGET_SESSION_ID}"
    page.locator(selector).scroll_into_view_if_needed(timeout=30000)
    page.locator(selector).click(timeout=30000)
    wait_for_analysis_cards(page, timeout_ms=30000)

    save_analysis_step(page, 1, 10, "reply-step1-input", "Reply Chain Step 1 Input", records, {"session_id": TARGET_SESSION_ID})
    save_analysis_step(page, 2, 11, "reply-step2-fastscan", "Reply Chain Step 2 Fast Scan", records, {"session_id": TARGET_SESSION_ID})

    scroll_to_analysis_card(page, 3)
    page.locator("#analysis-content .pipeline-card").nth(2).locator("button").first.click()
    page.wait_for_timeout(6000)

    def step3_ready() -> bool:
        try:
            wait_for_analysis_cards(page, timeout_ms=10000)
            text = analysis_card_text(page, 3)
            return ("重新提取" in text or "已提取" in text) and "等待提取" not in text
        except PlaywrightTimeoutError:
            refresh_analysis(page)
            return False

    step3_ok = wait_until(step3_ready, timeout_sec=180, poll_sec=4)
    save_analysis_step(page, 3, 12, "reply-step3-llm1", "Reply Chain Step 3 LLM1", records, {"session_id": TARGET_SESSION_ID, "completed": step3_ok})
    save_analysis_step(page, 4, 13, "reply-step4-crm", "Reply Chain Step 4 CRM", records, {"session_id": TARGET_SESSION_ID, "data_source": "old_crm_read_only"})

    scroll_to_analysis_card(page, 6)
    page.locator("#analysis-content .pipeline-card").nth(5).locator("button").first.click()
    page.wait_for_timeout(6000)

    def step6_ready() -> bool:
        try:
            wait_for_analysis_cards(page, timeout_ms=10000)
            text = analysis_card_text(page, 6)
            return ("已生成" in text or "复制" in text) and "等待生成" not in text
        except PlaywrightTimeoutError:
            refresh_analysis(page)
            return False

    step6_ok = wait_until(step6_ready, timeout_sec=240, poll_sec=4)
    save_analysis_step(page, 5, 14, "reply-step5-kb", "Reply Chain Step 5 Knowledge", records, {"session_id": TARGET_SESSION_ID, "completed_after_step6": step6_ok})
    save_analysis_step(page, 6, 15, "reply-step6-llm2", "Reply Chain Step 6 LLM2", records, {"session_id": TARGET_SESSION_ID, "completed": step6_ok})
    save_analysis_step(page, 7, 16, "reply-step7-validation", "Reply Chain Step 7 Validation", records, {"session_id": TARGET_SESSION_ID, "completed_after_step6": step6_ok})
    return {
        "session_id": TARGET_SESSION_ID,
        "step3_completed": step3_ok,
        "step6_completed": step6_ok,
        "dialogs": list(dialogs),
    }


def handle_dialog(dialog: Dialog, dialogs: list[str]) -> None:
    dialogs.append(dialog.message)
    dialog.accept()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    dialogs: list[str] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1680, "height": 1100}, device_scale_factor=1)
        page.on("dialog", lambda dialog: handle_dialog(dialog, dialogs))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        flow1 = run_flow1(page, records, dialogs)
        flow2 = run_flow2(page, records, dialogs)

        RESULT_JSON.write_text(
            json.dumps(
                {
                    "base_url": BASE_URL,
                    "excel_path": str(EXCEL_PATH),
                    "flow1": flow1,
                    "flow2": flow2,
                    "dialogs": dialogs,
                    "console_errors": console_errors,
                    "page_errors": page_errors,
                    "steps": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()


if __name__ == "__main__":
    main()
