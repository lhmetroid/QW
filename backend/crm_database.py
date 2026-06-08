# -*- coding: utf-8 -*-
import logging
from threading import Lock

import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings


logger = logging.getLogger(__name__)

_ACTIVE_CRM_CONNECTION_PROFILE: dict[str, object] = {}
_ACTIVE_CRM_CONNECTION_PROFILE_LOCK = Lock()


def _pymssql_module():
    try:
        import pymssql  # type: ignore
    except Exception:
        return None
    return pymssql


def _is_modern_sqlserver_driver(driver_name: str) -> bool:
    return driver_name.startswith("ODBC Driver ")


def _installed_sqlserver_drivers() -> list[str]:
    installed = [driver for driver in pyodbc.drivers() if "SQL Server" in driver]
    preferred_order = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server Native Client 10.0",
        "SQL Server",
    ]

    ordered: list[str] = []
    seen: set[str] = set()
    for driver in preferred_order + installed:
        if driver in installed and driver not in seen:
            ordered.append(driver)
            seen.add(driver)
    return ordered


def _driver_candidates() -> list[str]:
    configured = (settings.CRM_ODBC_DRIVER or "").strip()
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    for driver in _installed_sqlserver_drivers():
        if driver not in candidates:
            candidates.append(driver)
    return candidates


def _build_base_connection_string(driver_name: str) -> str:
    return (
        f"DRIVER={{{driver_name}}};"
        f"SERVER={settings.CRM_DBHost},{settings.CRM_DBPort};"
        f"DATABASE={settings.CRM_DBName};"
        f"UID={settings.CRM_DBUserId};"
        f"PWD={settings.CRM_DBPassword};"
        f"Connection Timeout={settings.CRM_DB_CONNECTION_TIMEOUT};"
    )


def _connection_profiles() -> list[dict[str, object]]:
    modern_profiles: list[tuple[str, bool, bool]] = [
        ("configured", settings.CRM_DB_ENCRYPT, settings.CRM_DB_TRUST_SERVER_CERTIFICATE),
        ("optional-trust", False, True),
        ("strict-trust", True, True),
        ("strict-default", True, settings.CRM_DB_TRUST_SERVER_CERTIFICATE),
    ]
    profiles: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    for driver_name in _driver_candidates():
        if _is_modern_sqlserver_driver(driver_name):
            for mode, encrypt, trust in modern_profiles:
                conn_str = (
                    _build_base_connection_string(driver_name)
                    + f"Encrypt={'yes' if encrypt else 'no'};"
                    + f"TrustServerCertificate={'yes' if trust else 'no'};"
                )
                key = (driver_name, conn_str)
                if key in seen:
                    continue
                seen.add(key)
                profiles.append(
                    {
                        "driver": driver_name,
                        "mode": mode,
                        "connection_string": conn_str,
                    }
                )
        else:
            conn_str = _build_base_connection_string(driver_name)
            key = (driver_name, conn_str)
            if key in seen:
                continue
            seen.add(key)
            profiles.append(
                {
                    "driver": driver_name,
                    "mode": "legacy-default",
                    "connection_string": conn_str,
                }
            )

    return profiles


def _set_active_profile(profile: dict[str, object], attempts: list[dict[str, str]]) -> None:
    with _ACTIVE_CRM_CONNECTION_PROFILE_LOCK:
        _ACTIVE_CRM_CONNECTION_PROFILE.clear()
        _ACTIVE_CRM_CONNECTION_PROFILE.update(
            {
                "driver": profile["driver"],
                "mode": profile["mode"],
                "attempts": attempts,
            }
        )


def get_crm_connection_debug_info() -> dict[str, object]:
    with _ACTIVE_CRM_CONNECTION_PROFILE_LOCK:
        active_profile = dict(_ACTIVE_CRM_CONNECTION_PROFILE)
    return {
        "configured_driver": (settings.CRM_ODBC_DRIVER or "").strip(),
        "installed_drivers": _installed_sqlserver_drivers(),
        "active_driver": active_profile.get("driver"),
        "active_mode": active_profile.get("mode"),
        "attempts": active_profile.get("attempts", []),
        "fallback_enabled": True,
    }


def _pymssql_profiles() -> list[dict[str, object]]:
    return [
        {
            "driver": "pymssql",
            "mode": f"tds-{tds_version}",
            "tds_version": tds_version,
        }
        for tds_version in ("7.0", "7.1", "7.2", "7.3", "7.4")
    ]


def _connect_with_pymssql_fallback():
    pymssql = _pymssql_module()
    if pymssql is None:
        raise RuntimeError("pymssql is not installed")

    attempts: list[dict[str, str]] = []
    last_error: Exception | None = None

    for profile in _pymssql_profiles():
        mode = str(profile["mode"])
        try:
            connection = pymssql.connect(
                server=settings.CRM_DBHost,
                port=int(settings.CRM_DBPort),
                user=settings.CRM_DBUserId,
                password=settings.CRM_DBPassword,
                database=settings.CRM_DBName,
                login_timeout=int(settings.CRM_DB_CONNECTION_TIMEOUT),
                timeout=int(settings.CRM_DB_CONNECTION_TIMEOUT),
                charset="UTF-8",
                tds_version=str(profile["tds_version"]),
            )
            _set_active_profile(profile, attempts)
            if attempts:
                logger.warning(
                    "CRM pymssql connection recovered after fallback; active_mode=%s previous_failures=%s",
                    mode,
                    attempts,
                )
            return connection
        except Exception as exc:  # pragma: no cover - fallback path is environment-specific
            last_error = exc
            attempts.append(
                {
                    "driver": "pymssql",
                    "mode": mode,
                    "error": str(exc),
                }
            )

    message = "CRM database connection failed after trying all pymssql TDS profiles."
    if attempts:
        logger.error("%s attempts=%s", message, attempts)
    raise RuntimeError(message) from last_error


def _connect_with_odbc_fallback():
    attempts: list[dict[str, str]] = []
    last_error: Exception | None = None

    for profile in _connection_profiles():
        driver_name = str(profile["driver"])
        mode = str(profile["mode"])
        try:
            connection = pyodbc.connect(str(profile["connection_string"]))
            _set_active_profile(profile, attempts)
            if attempts:
                logger.warning(
                    "CRM connection recovered after fallback; active_driver=%s active_mode=%s previous_failures=%s",
                    driver_name,
                    mode,
                    attempts,
                )
            return connection
        except Exception as exc:  # pragma: no cover - fallback path is environment-specific
            last_error = exc
            attempts.append(
                {
                    "driver": driver_name,
                    "mode": mode,
                    "error": str(exc),
                }
            )

    message = "CRM database connection failed after trying all ODBC profiles."
    if attempts:
        logger.error("%s attempts=%s", message, attempts)
    raise RuntimeError(message) from last_error


def _create_crm_engine():
    if _pymssql_module() is not None:
        return create_engine(
            "mssql+pymssql://",
            creator=_connect_with_pymssql_fallback,
            pool_pre_ping=True,
            echo=False,
        )
    return create_engine("mssql+pyodbc://", creator=_connect_with_odbc_fallback, pool_pre_ping=True, echo=False)


crm_engine = _create_crm_engine()
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
