# -*- coding: utf-8 -*-
"""
CRM 合同同步到本地 PostgreSQL 脚本。
从 CRM 数据库中提取所有符合条件的合同并批量写入/更新到本地 mail_contract_case 表。
"""

import sys
import os
import datetime
from pathlib import Path
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from database import SessionLocal, init_db, MailContractCase
from crm_database import CRMSessionLocal
from main import _mail_contract_case_to_candidate

def parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime.datetime):
        return val
    try:
        return datetime.datetime.fromisoformat(val)
    except Exception:
        return None

def main():
    print("Dropping existing mail_contract_case table if it exists...")
    from database import engine
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS mail_contract_case CASCADE"))
        conn.commit()

    print("Initializing local database and ensuring tables exist...")
    init_db()

    print("Connecting to CRM database...")
    crm_db = CRMSessionLocal()
    local_db = SessionLocal()

    try:
        sql = text("""
            SELECT
                c.ContractId,
                c.CustomerId,
                c.ContactId,
                (ISNULL(c.Money1,0)+ISNULL(c.Money2,0)+ISNULL(c.Money3,0)) AS TotalMoney,
                c.ProductNameAll,
                c.BusinessType,
                c.ContractDescription,
                c.InputTime,
                c.ContractTime,
                c.StartTime,
                c.EndTime,
                cust.CompanyName
            FROM usrContract c
            LEFT JOIN usrCustomer cust ON c.CustomerId = cust.CustomerId AND cust.Deleter IS NULL
            WHERE c.ContractId LIKE '%XS%'
              AND c.Deleter IS NULL
              AND (ISNULL(c.Money1,0)+ISNULL(c.Money2,0)+ISNULL(c.Money3,0)) >= 5000
            ORDER BY c.InputTime DESC, c.ContractId DESC
        """)
        print("Executing CRM query to fetch all eligible contracts...")
        rows = crm_db.execute(sql).fetchall()
        total_fetched = len(rows)
        print(f"Fetched {total_fetched} contracts from CRM.")

        print("Fetching existing local contract IDs...")
        existing_ids = {r[0] for r in local_db.query(MailContractCase.contract_id).all()}
        print(f"Found {len(existing_ids)} existing contracts in local database.")

        inserts = []
        updates = []

        print("Processing and transforming contracts...")
        for idx, row in enumerate(rows):
            candidate = _mail_contract_case_to_candidate(row)
            contract_id = candidate["contract_id"]
            
            mapped_data = {
                "contract_id": contract_id,
                "customer_id": candidate["customer_id"],
                "contact_id": candidate["contact_id"],
                "total_money": candidate["total_money"],
                "amount_bucket": candidate["amount_bucket"],
                "product_name_all": candidate["product_name_all"],
                "business_type": candidate["business_type"],
                "contract_description": candidate["contract_description"],
                "company_name": candidate["company_name"],
                "input_time": parse_dt(row._mapping.get("InputTime")),
                "contract_time": parse_dt(row._mapping.get("ContractTime")),
                "start_time": parse_dt(row._mapping.get("StartTime")),
                "end_time": parse_dt(row._mapping.get("EndTime")),
                "business_line_inferred": candidate["business_line_inferred"],
                "language_pair_inferred": candidate["language_pair_inferred"],
                "industry_inferred": candidate["industry_inferred"],
                "quality_flags": candidate["quality_flags"],
                "mail_case_text": candidate["mail_case_text"],
                "updated_at": datetime.datetime.utcnow()
            }

            if contract_id in existing_ids:
                updates.append(mapped_data)
            else:
                mapped_data["created_at"] = datetime.datetime.utcnow()
                mapped_data["ingested_to_knowledge"] = False
                mapped_data["desensitized"] = False
                inserts.append(mapped_data)

            if (idx + 1) % 2000 == 0:
                print(f"Processed {idx + 1}/{total_fetched}...")

        print(f"Prepared {len(inserts)} inserts and {len(updates)} updates.")

        # Batch insert/update to optimize performance
        batch_size = 1000
        
        if inserts:
            print("Executing batch inserts...")
            for i in range(0, len(inserts), batch_size):
                chunk = inserts[i:i+batch_size]
                local_db.bulk_insert_mappings(MailContractCase, chunk)
                local_db.commit()
                print(f"Inserted {min(i + batch_size, len(inserts))}/{len(inserts)}...")

        if updates:
            print("Executing batch updates...")
            for i in range(0, len(updates), batch_size):
                chunk = updates[i:i+batch_size]
                local_db.bulk_update_mappings(MailContractCase, chunk)
                local_db.commit()
                print(f"Updated {min(i + batch_size, len(updates))}/{len(updates)}...")

        print("Sync complete successfully!")
        
        # Verify final count
        final_count = local_db.query(MailContractCase).count()
        print(f"Final local contract count: {final_count}")
        
    except Exception as e:
        local_db.rollback()
        print(f"Error during sync: {e}")
        raise e
    finally:
        crm_db.close()
        local_db.close()

if __name__ == "__main__":
    main()
