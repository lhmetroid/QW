# backend/crm_database.py
# -*- coding: utf-8 -*-
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus
from config import CONFIG

# 从配置文件读取MSSQL CRM数据库配置
_username = quote_plus(CONFIG.get("CRM_DBUserId", ""))
_password = quote_plus(CONFIG.get("CRM_DBPassword", ""))
_dbname = CONFIG.get("CRM_DBName", "")
_host = CONFIG.get("CRM_DBHost", "")
_port = CONFIG.get("CRM_DBPort", "1433")

# 构建MSSQL连接字符串
# 使用 mssql+pyodbc 方言，需要安装 pyodbc
# 如果服务器配置了命名实例，可以修改连接字符串
_db_url = f"mssql+pyodbc://{_username}:{_password}@{_host}:{_port}/{_dbname}?driver=ODBC+Driver+18+for+SQL+Server"

try:
    crm_engine = create_engine(_db_url, pool_pre_ping=True, echo=False)
    CRMSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=crm_engine)
except Exception as e:
    raise Exception(f"无法创建MSSQL CRM数据库连接: {str(e)}")


def get_crm_db():
    """获取CRM数据库连接"""
    db = CRMSessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
