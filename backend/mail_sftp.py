# -*- coding: utf-8 -*-
"""邮件 .eml 上传到老 SSH 服务的 SFTP(22 端口)。

口径对齐旧 C#/Python 的 uploadfiledirect：上传到 `年/月/日/<uuid>`，
返回的相对路径用反斜杠拼装(如 `2026\\06\\22\\<uuid>`)，直接写入 spQueueSend.EmlFtpPath。

注意：目标是老 SSH 服务，只提供 ssh-rsa(SHA-1) host key，需 paramiko<4 且显式启用 ssh-rsa。
"""
import io
import uuid
import datetime
import logging

import paramiko

from config import settings

logger = logging.getLogger(__name__)

# 老服务器需要启用的旧 host key 算法(paramiko 默认弱化/禁用了它们)
_LEGACY_HOST_KEYS = ["ssh-rsa", "rsa-sha2-512", "rsa-sha2-256"]


def _open_transport() -> paramiko.Transport:
    host = (settings.FTP_HOST or "").strip()
    port = int(settings.FTP_PORT or 22)
    user = (settings.FTP_USERID or "").strip()
    pwd = settings.FTP_PASSWORD or ""
    if not (host and user):
        raise RuntimeError("FTP_HOST/FTP_USERID 未配置，无法上传 .eml")
    t = paramiko.Transport((host, port))
    t.banner_timeout = 30
    # 把 ssh-rsa 等老 host key 加入首选列表(老 SSH 服务只给这些)
    try:
        cur = list(getattr(t, "_preferred_keys", ()) or ())
        t._preferred_keys = tuple(dict.fromkeys(_LEGACY_HOST_KEYS + cur))
    except Exception:
        logger.warning("MAIL_SFTP_SET_PREFERRED_KEYS_FAILED", exc_info=True)
    t.connect(username=user, password=pwd)
    return t


def upload_bytes(content: bytes) -> tuple[bool, str]:
    """把任意字节流上传到 SFTP 的 `年/月/日/<uuid>`，返回 (是否成功, 反斜杠相对路径)。

    .eml 正文与附件文件都走这个口径(与老 C# uploadfiledirect 一致)。
    """
    t = None
    sftp = None
    try:
        t = _open_transport()
        sftp = paramiko.SFTPClient.from_transport(t)
        today = datetime.datetime.now()
        y, m, d = str(today.year), f"{today.month:02d}", f"{today.day:02d}"
        cur = ""
        for part in (y, m, d):
            cur = part if not cur else cur + "/" + part
            try:
                sftp.stat(cur)
            except IOError:
                sftp.mkdir(cur)
        fid = uuid.uuid4().hex
        remote_rel = f"{y}/{m}/{d}/{fid}"
        with sftp.open(remote_rel, "wb") as f:
            f.write(content)
        # 校验大小
        st = sftp.stat(remote_rel)
        if int(st.st_size) != len(content):
            logger.error("MAIL_SFTP_SIZE_MISMATCH remote=%s expect=%s got=%s", remote_rel, len(content), st.st_size)
            return False, ""
        eml_ftp_path = remote_rel.replace("/", "\\")
        return True, eml_ftp_path
    except Exception:
        logger.exception("MAIL_SFTP_UPLOAD_FAILED")
        return False, ""
    finally:
        try:
            if sftp:
                sftp.close()
        finally:
            if t:
                t.close()


def upload_eml_bytes(content: bytes) -> tuple[bool, str]:
    """把 .eml 字节流上传到 SFTP，返回 (是否成功, EmlFtpPath 反斜杠相对路径)。"""
    return upload_bytes(content)


def download_bytes(remote_rel: str) -> bytes | None:
    """按 EmlFtpPath(反斜杠或正斜杠相对路径)下载文件字节。失败返回 None。"""
    rel = str(remote_rel or "").replace("\\", "/").strip().lstrip("/")
    if not rel:
        return None
    t = None
    sftp = None
    try:
        t = _open_transport()
        sftp = paramiko.SFTPClient.from_transport(t)
        with sftp.open(rel, "rb") as f:
            return f.read()
    except Exception:
        logger.exception("MAIL_SFTP_DOWNLOAD_FAILED rel=%s", remote_rel)
        return None
    finally:
        try:
            if sftp:
                sftp.close()
        finally:
            if t:
                t.close()


def overwrite_bytes(remote_rel: str, content: bytes) -> bool:
    """把字节写回指定相对路径(原路径覆盖)。成功并大小一致返回 True, 否则 False。"""
    rel = str(remote_rel or "").replace("\\", "/").strip().lstrip("/")
    if not rel:
        return False
    t = None
    sftp = None
    try:
        t = _open_transport()
        sftp = paramiko.SFTPClient.from_transport(t)
        with sftp.open(rel, "wb") as f:
            f.write(content)
        st = sftp.stat(rel)
        return int(st.st_size) == len(content)
    except Exception:
        logger.exception("MAIL_SFTP_OVERWRITE_FAILED rel=%s", remote_rel)
        return False
    finally:
        try:
            if sftp:
                sftp.close()
        finally:
            if t:
                t.close()


def verify_connection() -> dict:
    """只读连通性自检：登录 + 列根目录(不写文件)。"""
    t = None
    sftp = None
    try:
        t = _open_transport()
        sftp = paramiko.SFTPClient.from_transport(t)
        home = sftp.normalize(".")
        listing = sftp.listdir(".")[:15]
        return {"ok": True, "home": home, "listing": listing}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            if sftp:
                sftp.close()
        finally:
            if t:
                t.close()
