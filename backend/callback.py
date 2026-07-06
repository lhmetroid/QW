import base64
import hashlib
import struct
from fastapi import APIRouter, Query, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse
from Crypto.Cipher import AES

from config import settings
import sys
import logging
import traceback

logger = logging.getLogger(__name__)
router = APIRouter()

def parse_echostr(msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
    """腾讯官方标准的 GET 回调 URL 验证解码算法"""
    # 1. 签名校验
    sort_list = [settings.TOKEN, timestamp, nonce, echostr]
    sort_list.sort()
    sha = hashlib.sha1()
    sha.update("".join(sort_list).encode('utf-8'))
    if sha.hexdigest() != msg_signature:
        raise ValueError("企业微信签名验证失败 (Signature error)")
        
    # 2. AES 解密 echostr
    aes_key = base64.b64decode(settings.ENCODING_AES_KEY + "=")
    cipher = AES.new(aes_key, AES.MODE_CBC, aes_key[:16])
    decrypted = cipher.decrypt(base64.b64decode(echostr))
    
    # 去除 PKCS7 填充
    pad = decrypted[-1]
    decrypted = decrypted[:-pad]
    
    # 剥离前缀、长度和 CorpID
    content = decrypted[16:]
    xml_len = struct.unpack("!I", content[:4])[0]
    xml_content = content[4:4+xml_len]
    from_corpid = content[4+xml_len:].decode('utf-8')
    
    if from_corpid != settings.CORP_ID:
        raise ValueError("企业微信 CorpID 不匹配")
        
    return xml_content.decode('utf-8')

@router.get("/api/wecom/callback")
async def wecom_callback_verify(
    msg_signature: str = Query(..., description="企业微信加密签名"),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(..., description="加密的随机字符串")
):
    """
    接收企微第一次在控制台点击“保存”时的握手请求
    """
    try:
        decrypted_echostr = parse_echostr(msg_signature, timestamp, nonce, echostr)
        logger.info("✅ 成功通过企微控制台回调 URL 握手验证！")
        return PlainTextResponse(content=decrypted_echostr)
    except Exception as e:
        logger.error(f"❌ 企微回调 URL 验证失败: {e}")
        return PlainTextResponse(content="error", status_code=400)

@router.post("/api/wecom/callback")
async def wecom_callback_trigger(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str | None = Query(None, description="企业微信加密签名"),
    timestamp: str | None = Query(None),
    nonce: str | None = Query(None),
):
    """
    被动接收企微有新聊天发生时的“事件通知流” (Post)
    收到事件 => 立刻去后台异步执行同步任务。这就是最高实时性的引擎。

    注意:三个参数改为可选(Query(None))。因为企微单应用唯一接收 URL 被老 C# 系统
    (SPEEDCRMWeb 的 .ashx)占用,本端点实际由老 .ashx 收到企微事件后中转(relay)触发。
    无论老 .ashx 是透传企微真签名,还是仅发裸 ping,都能稳定唤醒同步,不再因缺参 422。
    """
    if not settings.ENABLE_ARCHIVE_POLLING:
        return PlainTextResponse("success")

    logger.info(
        "📡 收到企微官方新通信事件触发信号！(Webhook Ping) sig=%s ts=%s",
        msg_signature, timestamp,
    )

    # 不阻塞 HTTP 响应，立刻利用 BackgroundTasks 启动我们的 ArchiveService 获取最新游标内容
    from archive_service import ArchiveService

    def sync_worker():
        try:
            logger.info("🚀 Webhook 唤醒：后置执行 `sync_today_data`...")
            res = ArchiveService.sync_today_data()
            logger.info(
                "✨ Webhook 唤醒数据获取完毕: status=%s 新增=%s seq=%s",
                res.get("status"), res.get("inserted_count"), res.get("current_seq"),
            )
        except Exception as e:
            logger.error(f"Webhook 唤醒失败: {e}\n{traceback.format_exc()}")

    background_tasks.add_task(sync_worker)

    # 按照企微规范，必须极速返回 "success" 字符串，以防企微重试或判定服务器挂掉
    return PlainTextResponse("success")
