from sqlalchemy import text
from database import engine

def fix_schema():
    print("--- 正在执行数据库热修复: 迁移 is_mock 字段 ---")
    with engine.connect() as conn:
        try:
            # 尝试添加 is_mock 列，如果已存在则会跳过（使用 PostgreSQL 的异常处理或先检查）
            conn.execute(text("ALTER TABLE message_logs ADD COLUMN IF NOT EXISTS is_mock BOOLEAN DEFAULT FALSE;"))
            conn.commit()
            print("✅ message_logs 表补丁执行成功：is_mock 字段已就绪")
        except Exception as e:
            print(f"❌ 补丁执行失败或已存在: {e}")

if __name__ == "__main__":
    fix_schema()
