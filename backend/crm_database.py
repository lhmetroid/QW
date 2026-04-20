# -*- coding: utf-8 -*-
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus
from config import settings


_username = settings.CRM_DBUserId
_password = settings.CRM_DBPassword
_dbname = settings.CRM_DBName
_server = f"{settings.CRM_DBHost},{settings.CRM_DBPort}"
_driver = settings.CRM_ODBC_DRIVER
_encrypt = "yes" if settings.CRM_DB_ENCRYPT else "no"
_trust_server_certificate = "yes" if settings.CRM_DB_TRUST_SERVER_CERTIFICATE else "no"

_odbc_connect = (
    f"DRIVER={{{_driver}}};"
    f"SERVER={_server};"
    f"DATABASE={_dbname};"
    f"UID={_username};"
    f"PWD={_password};"
    f"Encrypt={_encrypt};"
    f"TrustServerCertificate={_trust_server_certificate};"
    f"Connection Timeout={settings.CRM_DB_CONNECTION_TIMEOUT};"
)
_db_url = f"mssql+pyodbc:///?odbc_connect={quote_plus(_odbc_connect)}"

crm_engine = create_engine(_db_url, pool_pre_ping=True, echo=False)
CRMSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=crm_engine)


def get_crm_db():
    """获取 CRM 数据库连接"""
    db = CRMSessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
