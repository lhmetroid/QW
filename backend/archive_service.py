import ctypes
import os
import json
import logging
import base64
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)

# 定义 SDK V3 的内存片结构体
class FinanceSlice(ctypes.Structure):
    _fields_ = [("buf", ctypes.c_char_p), ("len", ctypes.c_int)]

class ArchiveService:
    """企业微信会话内容存档适配器 (基于官方 C-SDK V3)"""
    
    _sdk = None

    @classmethod
    def _load_sdk(cls):
        if cls._sdk:
            return cls._sdk
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        dll_path = os.path.join(current_dir, "WeWorkFinanceSdk.dll")
        
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
    def sync_today_data(cls):
        """全量增量拉取、分布式解密并展示明文 (V1.4.26)"""
        from database import SessionLocal, MessageLog
        from Crypto.PublicKey import RSA
        from Crypto.Cipher import PKCS1_v1_5
        from datetime import datetime
        import json

        sdk = cls._load_sdk()
        if not sdk: return {"status": "error", "msg": "SDK加载失败"}
        
        try:
            # 1. 准备本地私钥
            with open(settings.PRIVATE_KEY_PATH, "rb") as f:
                private_key = RSA.import_key(f.read())
            cipher_rsa = PKCS1_v1_5.new(private_key)

            # 2. 强力初始化 SDK
            sdk.NewSdk.restype = ctypes.c_void_p
            client_ptr = sdk.NewSdk()
            sdk.Init(ctypes.c_void_p(client_ptr), settings.CORP_ID.encode(), settings.CHATDATA_SECRET.encode())
            
            # 3. 拉取加密流 (引入 Seq 游标实现增量追捕)
            seq_file = os.path.join(os.path.dirname(__file__), "seq_cursor.txt")
            current_seq = 0
            if os.path.exists(seq_file):
                try:
                    with open(seq_file, "r") as sf:
                        current_seq = int(sf.read().strip())
                except: pass

            sdk.NewSlice.restype = ctypes.c_void_p
            chat_data_slice = sdk.NewSlice()
            db = SessionLocal()
            count = 0
            
            while True:
                ret_get = sdk.GetChatData(ctypes.c_void_p(client_ptr), ctypes.c_uint64(current_seq), ctypes.c_uint32(100), b"", b"", 10, ctypes.c_void_p(chat_data_slice))
                if ret_get != 0: break

                p_slice = ctypes.cast(ctypes.c_void_p(chat_data_slice), ctypes.POINTER(FinanceSlice))
                raw_json_bytes = ctypes.string_at(p_slice.contents.buf, p_slice.contents.len)
                data_list = json.loads(raw_json_bytes.decode('utf-8', 'ignore')).get("chatdata", [])
                
                if not data_list: break

                for item in data_list:
                    current_seq = item.get("seq", current_seq)
                    try:
                        enc_key = item.get("encrypt_random_key")
                        if not enc_key: continue
                        random_key = cipher_rsa.decrypt(base64.b64decode(enc_key), None)
                        
                        msg_slice = sdk.NewSlice()
                        res_dec = sdk.DecryptData(random_key, item.get("encrypt_chat_msg").encode(), ctypes.c_void_p(msg_slice))
                        
                        if res_dec == 0:
                            dec_p_slice = ctypes.cast(ctypes.c_void_p(msg_slice), ctypes.POINTER(FinanceSlice))
                            dec_json_bytes = ctypes.string_at(dec_p_slice.contents.buf, dec_p_slice.contents.len)
                            dec_obj = json.loads(dec_json_bytes.decode('utf-8', 'ignore'))
                            
                            msg_type = dec_obj.get("msgtype", "")
                            content = "[未知格式报文]"
                            if msg_type == "text" and isinstance(dec_obj.get("text"), dict):
                                content = dec_obj["text"].get("content", "")
                            elif msg_type == "image": content = "[图片消息]"
                            elif msg_type == "voice": content = "[语音消息]"
                            elif msg_type == "video": content = "[视频消息]"
                            elif msg_type == "file": content = f"[文件消息] {dec_obj.get('file', {}).get('filename', '')}"
                            elif msg_type == "emotion": content = "[表情包]"
                            elif msg_type == "revoke": content = "[撤回了一条消息]"
                            else: content = f"[{msg_type}类型报文]"
                            
                            sender = dec_obj.get("from", "")
                            tolist = dec_obj.get("tolist", [])
                            roomid = dec_obj.get("roomid", "")
                            
                            sender_type = "customer" if sender.startswith(("wm", "wo", "wb", "ex")) else "sales"
                            if roomid:
                                session_id = f"group_{roomid}"
                            else:
                                participants = sorted([sender] + (tolist if isinstance(tolist, list) else []))
                                session_id = f"single_{'_'.join(participants)}"
                            
                            # 防止超过 VARCHAR(50)
                            if len(session_id) > 50:
                                session_id = session_id[:50]
                                
                            ts = float(dec_obj.get("msgtime", 0))
                            ts = ts / 1000.0 if ts > 9999999999 else ts
                            now_ts = datetime.now().timestamp()
                            ts = ts if ts <= now_ts else now_ts
                            
                            db.add(MessageLog(
                                user_id=session_id,
                                content=content,
                                sender_type=sender_type,
                                is_mock=False,
                                timestamp=datetime.fromtimestamp(ts)
                            ))
                            count += 1
                        sdk.FreeSlice(ctypes.c_void_p(msg_slice))
                    except Exception as e:
                        continue
                
                # 更新游标
                with open(seq_file, "w") as sf:
                    sf.write(str(current_seq))
                    
                if len(data_list) < 100:
                    break

            db.commit()
            db.close()

            sdk.FreeSlice(ctypes.c_void_p(chat_data_slice))
            sdk.DestroySdk(ctypes.c_void_p(client_ptr))
            
            return {"status": "success", "msg": f"同步成功！已成功解密并展示 {count} 条真实中文对话。"}
        except Exception as e:
            logger.error(f"全链路解析故障: {e}")
            return {"status": "error", "msg": f"全链路解析故障: {str(e)}"}

    @classmethod
    def get_token_status(cls):
        """仅做连通性测试"""
        return {
            "is_sdk_present": os.path.exists(os.path.join(os.path.dirname(__file__), "WeWorkFinanceSdk.dll")),
            "private_key_present": os.path.exists(settings.PRIVATE_KEY_PATH)
        }
