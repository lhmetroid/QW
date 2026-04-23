from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import inspect, text

from config import settings
from database import Base, SessionLocal
from embedding_service import EmbeddingService
from intent_engine import IntentEngine

def _is_placeholder(value: str | None) -> bool:
    text_value = str(value or "").strip()
    return not text_value or text_value.startswith("your-")


def assert_real_config(include_crm: bool = False) -> None:
    db_configured = bool(settings.DATABASE_URL and not _is_placeholder(settings.DATABASE_URL)) or not any(
        _is_placeholder(value)
        for value in [settings.DB_NAME, settings.DB_USER, settings.DB_PASSWORD]
    )
    required = {
        "EMBEDDING_API_URL": settings.EMBEDDING_API_URL,
        "EMBEDDING_MODEL": settings.EMBEDDING_MODEL,
        "LLM1_API_KEY": settings.LLM1_API_KEY,
        "LLM2_API_KEY": settings.LLM2_API_KEY,
    }
    if include_crm:
        required.update({
            "CRM_DBName": settings.CRM_DBName,
            "CRM_DBUserId": settings.CRM_DBUserId,
            "CRM_DBPassword": settings.CRM_DBPassword,
        })
    missing = [name for name, value in required.items() if _is_placeholder(value)]
    if not db_configured:
        missing.insert(0, "DATABASE_URL 或 DB_NAME/DB_USER/DB_PASSWORD")
    if missing:
        raise RuntimeError(f"真实联调配置缺失或仍为占位值: {', '.join(missing)}")


def check_schema_alignment() -> dict:
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        report = {}
        for table in Base.metadata.sorted_tables:
            db_columns = {col["name"] for col in inspector.get_columns(table.name)}
            orm_columns = {col.name for col in table.columns}
            report[table.name] = {
                "ok": orm_columns.issubset(db_columns),
                "missing_in_db": sorted(orm_columns - db_columns),
                "extra_in_db": sorted(db_columns - orm_columns),
            }
        return report
    finally:
        db.close()


def assert_schema_ok(report: dict) -> None:
    failed = {name: item for name, item in report.items() if not item["ok"]}
    if failed:
        raise RuntimeError("数据库字段与 ORM 不对齐: " + json.dumps(failed, ensure_ascii=False, default=str))


def load_query_features(args: argparse.Namespace) -> dict | None:
    if args.query_features_file:
        path = Path(args.query_features_file).resolve()
        if not path.exists():
            raise FileNotFoundError(f"query features 文件不存在: {path}")
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return json.loads(args.query_features) if args.query_features else None


async def run_flow(args: argparse.Namespace) -> dict:
    excel_path = Path(args.excel).resolve()
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel 文件不存在: {excel_path}")

    db = SessionLocal()
    try:
        from main import _commit_kb_excel_import_raw, publish_kb_import_batch, submit_review_kb_import_batch

        raw = excel_path.read_bytes()
        import_result = _commit_kb_excel_import_raw(
            db,
            raw=raw,
            filename=excel_path.name,
            import_type=args.import_type,
            owner="real_e2e_check",
        )
        import_batch = import_result["import_batch"]
        await submit_review_kb_import_batch(import_batch, db)
        publish_result = await publish_kb_import_batch(import_batch, db)
        retrieve_result = IntentEngine.retrieve_knowledge_v2(
            args.query,
            query_features=load_query_features(args),
            top_k=args.top_k,
            request_id="real_e2e_check",
            session_id=args.external_userid or "real_e2e_check",
        )
        if args.include_crm:
            if not args.external_userid:
                raise RuntimeError("--include-crm 需要同时提供 --external-userid")
            crm_context = IntentEngine.get_crm_context(args.external_userid, strict=True)
        else:
            crm_context = {"crm_profile_status": "not_requested"}
        summary_json = {
            "topic": args.query,
            "core_demand": args.query,
            "key_facts": [],
            "todo_items": [],
            "risks": "",
            "to_be_confirmed": "",
            "status": "e2e_check",
        }
        assist = IntentEngine.generate_sales_assist_bundle(summary_json, retrieve_result, crm_context)
        return {
            "import": import_result,
            "publish": publish_result,
            "retrieve": retrieve_result,
            "crm": crm_context,
            "assist": assist,
        }
    finally:
        db.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run real PostgreSQL/Ollama/LLM knowledge-base E2E check. CRM is optional.")
    parser.add_argument("--excel", required=True, help="真实业务 Excel 路径")
    parser.add_argument("--import-type", default="faq", choices=["faq", "pricing", "process", "capability", "case", "script", "email_digest"])
    parser.add_argument("--query", required=True, help="真实检索问题")
    parser.add_argument("--query-features", default="", help='JSON，例如 {"business_line":"translation"}')
    parser.add_argument("--query-features-file", default="", help="query_features JSON 文件路径，避免 PowerShell JSON 转义问题")
    parser.add_argument("--external-userid", default="", help="真实 CRM / 企微外部联系人 ID；仅 --include-crm 时必填")
    parser.add_argument("--include-crm", action="store_true", help="同时联调只读 CRM 客户画像")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    assert_real_config(include_crm=args.include_crm)
    schema_report = check_schema_alignment()
    assert_schema_ok(schema_report)

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()

    embedding = EmbeddingService.embed("真实联调 embedding 探测")
    if not embedding:
        raise RuntimeError("Embedding 返回为空")

    result = await run_flow(args)
    print(json.dumps({
        "status": "success",
        "schema": schema_report,
        "embedding_dim": len(embedding),
        "flow": result,
    }, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
