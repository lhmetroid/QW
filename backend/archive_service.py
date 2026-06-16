import ctypes
import os
import json
import logging
import base64
import hashlib
import threading
import time
import re
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
    # 新消息落库后的回调钩子(供 SSE 推送等订阅)。在工作线程中触发,
    # 监听方需自行保证线程安全(如用 loop.call_soon_threadsafe 投递到 asyncio 队列)。
    _new_message_hooks: list = []
    _sdk_error_messages = {
        10000: "参数错误，请检查 SDK 初始化与调用参数",
        10001: "网络错误，腾讯会话存档接口请求失败",
        10002: "数据解析失败",
        10003: "系统失败",
        10004: "密钥对版本或私钥解析失败",
        10005: "fileid 错误",
        10006: "拉取媒体数据失败",
        10007: "找不到消息加密版本，需确认私钥是否已更新",
        10008: "encrypt_key 错误",
        10009: "IP 不合法",
        10010: "数据过期或不可用",
    }

    @classmethod
    def register_new_message_hook(cls, fn) -> None:
        """注册新消息回调。fn(messages: list[dict]) 在每批新消息落库提交后被调用。"""
        if fn not in cls._new_message_hooks:
            cls._new_message_hooks.append(fn)

    @classmethod
    def _emit_new_messages(cls, messages: list) -> None:
        if not messages or not cls._new_message_hooks:
            return
        for hook in list(cls._new_message_hooks):
            try:
                hook(messages)
            except Exception as exc:  # 钩子异常绝不能影响主同步链路
                logger.warning("新消息钩子触发失败: %s", exc)

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
    def _log_file_path(cls) -> str:
        return os.path.join(os.path.dirname(__file__), "logs", "app.log")

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
    def _format_sdk_error(cls, code: int) -> str:
        return cls._sdk_error_messages.get(int(code), f"未知 SDK 错误码 {code}")

    @staticmethod
    def _format_dt(ts: float | None) -> str | None:
        if ts is None:
            return None
        try:
            return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    @classmethod
    def _read_seq_cursor_info(cls) -> dict:
        path = cls._seq_file_path()
        info = {
            "path": path,
            "exists": os.path.exists(path),
            "value": None,
            "updated_at": None,
        }
        if not info["exists"]:
            return info
        try:
            with open(path, "r", encoding="utf-8") as sf:
                info["value"] = sf.read().strip() or None
        except Exception as exc:
            info["read_error"] = str(exc)
        try:
            info["updated_at"] = cls._format_dt(os.path.getmtime(path))
        except OSError:
            pass
        return info

    @classmethod
    def _read_lock_info(cls) -> dict:
        path = cls._sync_lock_path()
        info = {
            "path": path,
            "exists": os.path.exists(path),
            "pid_text": None,
            "updated_at": None,
            "age_seconds": None,
            "stale_hint": False,
        }
        if not info["exists"]:
            return info
        try:
            with open(path, "r", encoding="utf-8") as lf:
                info["pid_text"] = lf.read().strip() or None
        except Exception as exc:
            info["read_error"] = str(exc)
        try:
            mtime = os.path.getmtime(path)
            info["updated_at"] = cls._format_dt(mtime)
            info["age_seconds"] = round(max(0.0, time.time() - mtime), 2)
            info["stale_hint"] = info["age_seconds"] > 120
        except OSError:
            pass
        return info

    @classmethod
    def _tail_archive_sync_events(cls, limit: int = 5) -> list[dict]:
        path = cls._log_file_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except Exception:
            return []

        matched: list[dict] = []
        pattern = re.compile(r"ARCHIVE_SYNC_(SUCCESS|ERROR|SKIPPED)\s+(.+)$")
        event_labels = {
            "SUCCESS": "同步成功",
            "ERROR": "同步失败",
            "SKIPPED": "同步跳过",
        }

        for raw_line in reversed(lines):
            line = raw_line.strip()
            if "ARCHIVE_SYNC_" not in line:
                continue
            match = pattern.search(line)
            if not match:
                continue
            event = match.group(1)
            payload_raw = match.group(2)
            payload = {}
            try:
                payload = json.loads(payload_raw)
            except Exception:
                payload = {"raw_payload": payload_raw}
            timestamp = line.split(" | ", 1)[0].strip() if " | " in line else ""
            matched.append({
                "timestamp": timestamp,
                "event": event,
                "event_label": event_labels.get(event, event),
                "payload": payload,
                "raw_line": line,
            })
            if len(matched) >= limit:
                break
        return list(reversed(matched))

    @classmethod
    def get_runtime_diagnostics(cls) -> dict:
        config = cls.config_status()
        seq_cursor = cls._read_seq_cursor_info()
        process_lock = cls._read_lock_info()
        recent_events = cls._tail_archive_sync_events(limit=5)
        last_event = recent_events[-1] if recent_events else None
        last_payload = (last_event or {}).get("payload") or {}

        suggestions: list[str] = []
        if not config.get("ready"):
            suggestions.append("请先补齐企微会话存档所需配置，再重试同步。")
        sdk_error_code = last_payload.get("sdk_error_code")
        if sdk_error_code == 10001:
            suggestions.append("腾讯会话存档接口网络失败：请检查服务器出网、代理、防火墙、DNS 与腾讯侧 IP 白名单。")
        elif sdk_error_code == 10009:
            suggestions.append("腾讯侧返回 IP 不合法：请把当前服务器公网 IP 加入企业微信会话存档白名单。")
        elif sdk_error_code == 10007:
            suggestions.append("私钥版本不匹配：请重新下载并替换企业微信会话存档私钥。")
        if process_lock.get("stale_hint"):
            suggestions.append("发现同步锁文件长时间未更新，建议检查是否存在卡死进程，必要时重启服务后重试。")
        if not recent_events:
            suggestions.append("尚未发现最近同步日志，请先点击一次“同步今日真实记录”生成链路日志。")

        overall = "ok"
        summary = "企微会话存档链路看起来正常。"
        if not config.get("ready"):
            overall = "error"
            summary = "企微会话存档基础配置不完整，当前无法正常同步。"
        elif last_event and last_event.get("event") == "ERROR":
            overall = "error"
            summary = "最近一次企微会话存档同步失败，请根据错误码和建议继续排查。"
        elif process_lock.get("exists"):
            overall = "warning"
            summary = "检测到同步锁文件存在，若持续不消失，可能有并发同步或残留锁。"

        return {
            "status": overall,
            "summary": summary,
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "archive_sdk": config,
            "seq_cursor": seq_cursor,
            "process_lock": process_lock,
            "last_sync_event": last_event,
            "recent_sync_events": recent_events,
            "suggestions": suggestions,
        }

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
            emitted_messages: list[dict] = []  # 本次新增消息,提交后用于 SSE 等推送
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
                    timings_ms["total_ms"] = round((time.perf_counter() - total_started) * 1000, 2)
                    result = {
                        "status": "error",
                        "msg": f"腾讯会话存档拉取失败: {cls._format_sdk_error(ret_get)}",
                        "sdk_error_code": int(ret_get),
                        "current_seq": current_seq,
                        "timings_ms": timings_ms,
                    }
                    cls._log_sync_result("ERROR", {"session_id_filter": session_id_filter, **result})
                    return result

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
                                emitted_messages.append({
                                    "session_id": session_id,
                                    "content": content,
                                    "sender_type": sender_type,
                                    "timestamp": datetime.fromtimestamp(ts).isoformat(),
                                    "archive_msg_id": archive_msg_id,
                                })
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
            # 落库提交成功后再触发新消息钩子,保证订阅方读到的是已持久化数据
            cls._emit_new_messages(emitted_messages)
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
