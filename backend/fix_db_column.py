from sqlalchemy import text
from database import engine

def fix_schema():
    print("--- 正在执行数据库热修复: 迁移 is_mock 字段 ---")
    with engine.connect() as conn:
        try:
            # 尝试添加 is_mock 列，如果已存在则会跳过
            conn.execute(text("ALTER TABLE message_logs ADD COLUMN IF NOT EXISTS is_mock BOOLEAN DEFAULT FALSE;"))
            # 尝试添加 turn_id & turn_no 列到 case_iteration_result
            conn.execute(text("ALTER TABLE case_iteration_result ADD COLUMN IF NOT EXISTS turn_id UUID;"))
            conn.execute(text("ALTER TABLE case_iteration_result ADD COLUMN IF NOT EXISTS turn_no INTEGER;"))
            conn.commit()
            print("✅ 数据库补丁执行成功：is_mock & turn_id & turn_no 字段已就绪")
        except Exception as e:
            print(f"❌ 补丁执行失败: {e}")

if __name__ == "__main__":
    fix_schema()
