import ctypes
import os
import json
import logging
import base64
import hashlib
import threading
import time
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)

# 定义 SDK V3 的内存片结构体
class FinanceSlice(ctypes.Structure):
    _fields_ = [("buf", ctypes.c_char_p), ("len", ctypes.c_int)]

class ArchiveService:
    """企业微信会话内容存档适配器 (基于官方 C-SDK V3)"""
    
    _sdk = None
    _sync_lock = threading.Lock()

    @staticmethod
    def _is_placeholder(value: object) -> bool:
        text = str(value or "").strip()
        return not text or text.startswith("your-")

    @staticmethod
    def _project_root() -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @classmethod
    def _seq_file_path(cls) -> str:
        return os.path.join(os.path.dirname(__file__), "seq_cursor.txt")

    @classmethod
    def _sync_lock_path(cls) -> str:
        return os.path.join(os.path.dirname(__file__), "archive_sync.lock")

    @classmethod
    def _resolve_private_key_path(cls) -> str:
        configured = settings.PRIVATE_KEY_PATH
        if os.path.isabs(configured):
            return configured
        root_candidate = os.path.join(cls._project_root(), configured)
        if os.path.exists(root_candidate):
            return root_candidate
        return os.path.abspath(configured)

    @classmethod
    def config_status(cls) -> dict:
        sdk_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WeWorkFinanceSdk.dll")
        private_key_path = cls._resolve_private_key_path()
        checks = {
            "sdk_present": os.path.exists(sdk_path),
            "private_key_present": os.path.exists(private_key_path),
            "corp_id_configured": not cls._is_placeholder(settings.CORP_ID),
            "chatdata_secret_configured": not cls._is_placeholder(settings.CHATDATA_SECRET),
        }
        missing = []
        if not checks["sdk_present"]:
            missing.append("backend/WeWorkFinanceSdk.dll")
        if not checks["private_key_present"]:
            missing.append(f"PRIVATE_KEY_PATH={settings.PRIVATE_KEY_PATH}")
        if not checks["corp_id_configured"]:
            missing.append("CORP_ID")
        if not checks["chatdata_secret_configured"]:
            missing.append("CHATDATA_SECRET")
        return {
            **checks,
            "ready": not missing,
            "missing": missing,
            "sdk_path": sdk_path,
            "private_key_path": private_key_path,
            "archive_polling_enabled": bool(settings.ENABLE_ARCHIVE_POLLING),
        }

    @classmethod
    def _load_sdk(cls):
        if cls._sdk:
            return cls._sdk
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        dll_path = os.path.join(current_dir, "WeWorkFinanceSdk.dll")
        if not os.path.exists(dll_path):
            logger.warning("企微会话存档 SDK 未配置: %s", dll_path)
            return None
        
        if hasattr(os, "add_dll_directory"):
            try: os.add_dll_directory(current_dir)
            except: pass
        
        try:
            cls._sdk = ctypes.WinDLL(dll_path)
            
            def safe_map(attr, argtypes=None, restype=None):
                try:
                    func = getattr(cls._sdk, attr)
                    if argtypes: func.argtypes = argtypes
                    if restype: func.restype = restype
                    return True
                except AttributeError: return False

            safe_map("NewSdk", restype=ctypes.c_void_p)
            safe_map("Init", argtypes=[ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p], restype=ctypes.c_int)
            safe_map("GetChatData", argtypes=[ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p], restype=ctypes.c_int)
            safe_map("FreeSlice", argtypes=[ctypes.c_void_p])
            
            logger.info("企微 SDK V3 接口映射与内存模型初始化完成")
            return cls._sdk
        except Exception as e:
            logger.error(f"SDK 加载异常: {e}")
            return None

    @classmethod
    def _acquire_process_lock(cls, stale_seconds: int = 120):
        lock_path = cls._sync_lock_path()
        now_ts = time.time()
        try:
            if os.path.exists(lock_path):
                try:
                    age_seconds = now_ts - os.path.getmtime(lock_path)
                except OSError:
                    age_seconds = 0
                if age_seconds > stale_seconds:
                    os.remove(lock_path)
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            return fd
        except FileExistsError:
            return None

    @classmethod
    def _release_process_lock(cls, lock_fd) -> None:
        if lock_fd is None:
            return
        try:
            os.close(lock_fd)
        except OSError:
            pass
        try:
            os.remove(cls._sync_lock_path())
        except OSError:
            pass

    @staticmethod
    def _build_session_id(sender: str, tolist: list[str] | None, roomid: str) -> str:
        if roomid:
            return f"group_{roomid}"
        participants = sorted([sender] + (tolist if isinstance(tolist, list) else []))
        return f"single_{'_'.join(participants)}"

    @staticmethod
    def _extract_message_content(dec_obj: dict) -> str:
        msg_type = dec_obj.get("msgtype", "")
        if msg_type == "text" and isinstance(dec_obj.get("text"), dict):
            return dec_obj["text"].get("content", "")
        if msg_type == "image":
            return "[图片消息]"
        if msg_type == "voice":
            return "[语音消息]"
        if msg_type == "video":
            return "[视频消息]"
        if msg_type == "file":
            return f"[文件消息] {dec_obj.get('file', {}).get('filename', '')}"
        if msg_type == "emotion":
            return "[表情包]"
        if msg_type == "revoke":
            return "[撤回了一条消息]"
        return f"[{msg_type}类型报文]" if msg_type else "[未知格式报文]"

    @classmethod
    def _build_archive_msg_id(cls, item: dict, dec_obj: dict, content: str) -> str:
        raw_msg_id = str(
            dec_obj.get("msgid")
            or dec_obj.get("sdkfileid")
            or item.get("msgid")
            or ""
        ).strip()
        if raw_msg_id:
            return raw_msg_id[:120]
        fingerprint = {
            "seq": item.get("seq"),
            "from": dec_obj.get("from"),
            "tolist": dec_obj.get("tolist"),
            "roomid": dec_obj.get("roomid"),
            "msgtime": dec_obj.get("msgtime"),
            "msgtype": dec_obj.get("msgtype"),
            "content": content,
        }
        payload = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _accumulate_timing(timings_ms: dict[str, float], name: str, started_at: float) -> None:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        timings_ms[name] = round(timings_ms.get(name, 0.0) + elapsed_ms, 2)

    @staticmethod
    def _log_sync_result(event: str, payload: dict) -> None:
        logger.info(
            "ARCHIVE_SYNC_%s %s",
            event,
            json.dumps(payload, ensure_ascii=False, default=str),
        )

    @classmethod
    def sync_today_data(cls, session_id_filter: str | None = None):
        """全量增量拉取企微会话；支持按会话过滤返回结果，已落库消息不会重复写入。"""
        from database import SessionLocal, MessageLog
        from Crypto.PublicKey import RSA
        from Crypto.Cipher import PKCS1_v1_5

        total_started = time.perf_counter()
        timings_ms: dict[str, float] = {}

        status = cls.config_status()
        if not status["ready"]:
            result = {
                "status": "error",
                "msg": "企微会话存档未完整配置: " + ", ".join(status["missing"]),
                "config": status,
                "timings_ms": {"total_ms": round((time.perf_counter() - total_started) * 1000, 2)},
            }
            cls._log_sync_result("ERROR", {"session_id_filter": session_id_filter, **result})
            return result

        sdk = cls._load_sdk()
        if not sdk:
            result = {
                "status": "error",
                "msg": "SDK加载失败",
                "timings_ms": {"total_ms": round((time.perf_counter() - total_started) * 1000, 2)},
            }
            cls._log_sync_result("ERROR", {"session_id_filter": session_id_filter, **result})
            return result

        if not cls._sync_lock.acquire(blocking=False):
            result = {
                "status": "skipped",
                "msg": "已有企微会话存档同步任务在当前进程执行中",
                "timings_ms": {"total_ms": round((time.perf_counter() - total_started) * 1000, 2)},
            }
            cls._log_sync_result("SKIPPED", {"session_id_filter": session_id_filter, **result})
            return result

        process_lock_fd = cls._acquire_process_lock()
        if process_lock_fd is None:
            cls._sync_lock.release()
            result = {
                "status": "skipped",
                "msg": "已有企微会话存档同步任务在其他进程执行中",
                "timings_ms": {"total_ms": round((time.perf_counter() - total_started) * 1000, 2)},
            }
            cls._log_sync_result("SKIPPED", {"session_id_filter": session_id_filter, **result})
            return result
        
        db = None
        chat_data_slice = None
        client_ptr = None
        try:
            # 1. 准备本地私钥
            stage_started = time.perf_counter()
            with open(status["private_key_path"], "rb") as f:
                private_key = RSA.import_key(f.read())
            cipher_rsa = PKCS1_v1_5.new(private_key)
            cls._accumulate_timing(timings_ms, "load_private_key_ms", stage_started)

            # 2. 强力初始化 SDK
            stage_started = time.perf_counter()
            sdk.NewSdk.restype = ctypes.c_void_p
            client_ptr = sdk.NewSdk()
            sdk.Init(ctypes.c_void_p(client_ptr), settings.CORP_ID.encode(), settings.CHATDATA_SECRET.encode())
            cls._accumulate_timing(timings_ms, "sdk_init_ms", stage_started)
            
            # 3. 拉取加密流 (引入 Seq 游标实现增量追捕)
            stage_started = time.perf_counter()
            seq_file = cls._seq_file_path()
            current_seq = 0
            if os.path.exists(seq_file):
                try:
                    with open(seq_file, "r") as sf:
                        current_seq = int(sf.read().strip())
                except Exception:
                    pass
            cls._accumulate_timing(timings_ms, "load_seq_cursor_ms", stage_started)

            sdk.NewSlice.restype = ctypes.c_void_p
            chat_data_slice = sdk.NewSlice()
            db = SessionLocal()
            inserted_count = 0
            duplicate_count = 0
            parse_failed_count = 0
            fetched_count = 0
            batch_count = 0
            matched_session_new_count = 0
            matched_session_total_count = 0
            
            while True:
                fetch_started = time.perf_counter()
                ret_get = sdk.GetChatData(ctypes.c_void_p(client_ptr), ctypes.c_uint64(current_seq), ctypes.c_uint32(100), b"", b"", 10, ctypes.c_void_p(chat_data_slice))
                cls._accumulate_timing(timings_ms, "fetch_chat_data_ms", fetch_started)
                if ret_get != 0:
                    break

                p_slice = ctypes.cast(ctypes.c_void_p(chat_data_slice), ctypes.POINTER(FinanceSlice))
                raw_json_bytes = ctypes.string_at(p_slice.contents.buf, p_slice.contents.len)
                data_list = json.loads(raw_json_bytes.decode('utf-8', 'ignore')).get("chatdata", [])
                
                if not data_list:
                    break

                batch_count += 1
                fetched_count += len(data_list)

                for item in data_list:
                    process_started = time.perf_counter()
                    current_seq = item.get("seq", current_seq)
                    try:
                        enc_key = item.get("encrypt_random_key")
                        if not enc_key:
                            cls._accumulate_timing(timings_ms, "process_messages_ms", process_started)
                            continue
                        random_key = cipher_rsa.decrypt(base64.b64decode(enc_key), None)
                        
                        msg_slice = sdk.NewSlice()
                        try:
                            res_dec = sdk.DecryptData(random_key, item.get("encrypt_chat_msg").encode(), ctypes.c_void_p(msg_slice))
                            
                            if res_dec == 0:
                                dec_p_slice = ctypes.cast(ctypes.c_void_p(msg_slice), ctypes.POINTER(FinanceSlice))
                                dec_json_bytes = ctypes.string_at(dec_p_slice.contents.buf, dec_p_slice.contents.len)
                                dec_obj = json.loads(dec_json_bytes.decode('utf-8', 'ignore'))

                                sender = dec_obj.get("from", "")
                                tolist = dec_obj.get("tolist", [])
                                roomid = dec_obj.get("roomid", "")
                                session_id = cls._build_session_id(sender, tolist, roomid)
                                content = cls._extract_message_content(dec_obj)
                                archive_msg_id = cls._build_archive_msg_id(item, dec_obj, content)

                                if session_id_filter and session_id == session_id_filter:
                                    matched_session_total_count += 1

                                existing = None
                                if archive_msg_id:
                                    existing = db.query(MessageLog.id).filter(MessageLog.archive_msg_id == archive_msg_id).first()
                                if existing:
                                    duplicate_count += 1
                                    continue

                                sender_type = "customer" if sender.startswith(("wm", "wo", "wb", "ex")) else "sales"
                                ts = float(dec_obj.get("msgtime", 0))
                                ts = ts / 1000.0 if ts > 9999999999 else ts
                                now_ts = datetime.now().timestamp()
                                ts = ts if ts <= now_ts else now_ts

                                db.add(MessageLog(
                                    user_id=session_id,
                                    content=content,
                                    sender_type=sender_type,
                                    is_mock=False,
                                    timestamp=datetime.fromtimestamp(ts),
                                    archive_msg_id=archive_msg_id,
                                    archive_seq=str(item.get("seq", ""))[:40] or None,
                                ))
                                inserted_count += 1
                                if session_id_filter and session_id == session_id_filter:
                                    matched_session_new_count += 1
                        finally:
                            sdk.FreeSlice(ctypes.c_void_p(msg_slice))
                    except Exception as e:
                        parse_failed_count += 1
                        logger.warning("企微会话存档单条消息解析失败 seq=%s err=%s", item.get("seq"), e)
                    finally:
                        cls._accumulate_timing(timings_ms, "process_messages_ms", process_started)
                
                # 更新游标
                cursor_started = time.perf_counter()
                with open(seq_file, "w") as sf:
                    sf.write(str(current_seq))
                cls._accumulate_timing(timings_ms, "save_seq_cursor_ms", cursor_started)
                    
                if len(data_list) < 100:
                    break

            commit_started = time.perf_counter()
            db.commit()
            cls._accumulate_timing(timings_ms, "commit_ms", commit_started)
            timings_ms["total_ms"] = round((time.perf_counter() - total_started) * 1000, 2)
            
            result = {
                "status": "success",
                "msg": f"同步成功：新增 {inserted_count} 条，跳过重复 {duplicate_count} 条。",
                "inserted_count": inserted_count,
                "duplicate_count": duplicate_count,
                "parse_failed_count": parse_failed_count,
                "fetched_count": fetched_count,
                "batch_count": batch_count,
                "current_seq": current_seq,
                "timings_ms": timings_ms,
            }
            if session_id_filter:
                result["session_id"] = session_id_filter
                result["matched_session_new_count"] = matched_session_new_count
                result["matched_session_total_count"] = matched_session_total_count
            cls._log_sync_result("SUCCESS", {"session_id_filter": session_id_filter, **result})
            return result
        except Exception as e:
            logger.error(f"全链路解析故障: {e}")
            if db is not None:
                db.rollback()
            timings_ms["total_ms"] = round((time.perf_counter() - total_started) * 1000, 2)
            result = {
                "status": "error",
                "msg": f"全链路解析故障: {str(e)}",
                "timings_ms": timings_ms,
            }
            cls._log_sync_result("ERROR", {"session_id_filter": session_id_filter, **result})
            return result
        finally:
            if db is not None:
                db.close()
            if chat_data_slice:
                try:
                    sdk.FreeSlice(ctypes.c_void_p(chat_data_slice))
                except Exception:
                    pass
            if client_ptr and hasattr(sdk, "DestroySdk"):
                try:
                    sdk.DestroySdk(ctypes.c_void_p(client_ptr))
                except Exception:
                    pass
            cls._release_process_lock(process_lock_fd)
            cls._sync_lock.release()

    @classmethod
    def get_token_status(cls):
        """仅做连通性测试"""
        return cls.config_status()
