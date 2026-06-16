import requests
import json
import time
import hashlib
import logging
from typing import Optional
from config import settings
from qywx_crypt.WXBizMsgCrypt import WXBizMsgCrypt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QYWXUtils:
    """企业微信API工具类"""

    _access_token = None
    # JSSDK 票据缓存(带过期时间)。企微 ticket 有效期 7200s,提前 200s 失效以留余量。
    _jsapi_ticket = None          # 企业身份 ticket(用于 wx.config)
    _jsapi_ticket_expire_at = 0
    _agent_ticket = None          # 应用身份 ticket(用于 wx.agentConfig, getCurExternalContact 必需)
    _agent_ticket_expire_at = 0

    @classmethod
    def get_access_token(cls, force_refresh: bool = False):
        """获取 access_token; force_refresh=True 时强制重取(用于票据过期 42001 重试)。"""
        if cls._access_token and not force_refresh:
            return cls._access_token

        if not hasattr(settings, 'CORP_SECRET') or not settings.CORP_SECRET or "填写" in settings.CORP_SECRET:
            logger.warning("未配置企微 CORP_SECRET，跳过触达发送机制（仅在系统UI展示 V2 建议）")
            return None

        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={settings.CORP_ID}&corpsecret={settings.CORP_SECRET}"
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            if data.get("errcode") == 0:
                cls._access_token = data.get("access_token")
                return cls._access_token
            else:
                logger.error(f"获取access_token失败: {data}")
        except Exception as e:
            logger.error(f"获取access_token异常: {e}")
        return None

    @classmethod
    def _fetch_ticket(cls, params: dict, label: str):
        """通用 ticket 拉取,token 过期(42001/40014)时强制刷新 token 重试一次。"""
        for attempt in range(2):
            token = cls.get_access_token(force_refresh=(attempt == 1))
            if not token:
                return None, 0
            url = "https://qyapi.weixin.qq.com/cgi-bin/ticket/get" if "type" in params \
                else "https://qyapi.weixin.qq.com/cgi-bin/get_jsapi_ticket"
            try:
                resp = requests.get(url, params={"access_token": token, **params}, timeout=10)
                data = resp.json()
            except Exception as e:
                logger.error(f"获取{label}异常: {e}")
                return None, 0
            errcode = data.get("errcode")
            if errcode == 0:
                ttl = int(data.get("expires_in", 7200))
                return data.get("ticket"), time.time() + max(60, ttl - 200)
            if errcode in (42001, 40014) and attempt == 0:
                logger.warning(f"{label} token 过期({errcode}),强制刷新后重试")
                continue
            logger.error(f"获取{label}失败: {data}")
            return None, 0
        return None, 0

    @classmethod
    def get_jsapi_ticket(cls):
        """企业身份 jsapi_ticket(用于 wx.config)。"""
        if cls._jsapi_ticket and time.time() < cls._jsapi_ticket_expire_at:
            return cls._jsapi_ticket
        ticket, expire_at = cls._fetch_ticket({}, "jsapi_ticket")
        if ticket:
            cls._jsapi_ticket = ticket
            cls._jsapi_ticket_expire_at = expire_at
        return ticket

    @classmethod
    def get_agent_ticket(cls):
        """应用身份 ticket(type=agent_config,用于 wx.agentConfig)。"""
        if cls._agent_ticket and time.time() < cls._agent_ticket_expire_at:
            return cls._agent_ticket
        ticket, expire_at = cls._fetch_ticket({"type": "agent_config"}, "agent_ticket")
        if ticket:
            cls._agent_ticket = ticket
            cls._agent_ticket_expire_at = expire_at
        return ticket

    @staticmethod
    def build_jssdk_signature(ticket: str, url: str, noncestr: str, timestamp: str) -> str:
        """企微 JSSDK 签名: sha1(jsapi_ticket + noncestr + timestamp + url) 按字典序拼接。"""
        raw = "&".join([
            f"jsapi_ticket={ticket}",
            f"noncestr={noncestr}",
            f"timestamp={timestamp}",
            f"url={url}",
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @classmethod
    def send_text_card(cls, to_user: str, title: str, description: str, url: str = "#"):
        """发送文本卡片消息"""
        token = cls.get_access_token()
        if not token:
            return False
        
        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        payload = {
            "touser": to_user,
            "msgtype": "textcard",
            "agentid": settings.AGENT_ID,
            "textcard": {
                "title": title,
                "description": description,
                "url": url,
                "btntxt": "查看详情"
            },
            "safe": 0,
            "enable_id_trans": 0,
            "enable_duplicate_check": 0
        }
        
        try:
            response = requests.post(send_url, json=payload)
            res_data = response.json()
            if res_data.get("errcode") == 0:
                logger.info(f"成功向用户 {to_user} 发送提醒卡片")
                return True
            else:
                logger.error(f"发送提醒失败: {res_data}")
        except Exception as e:
            logger.error(f"发送提醒请求异常: {e}")
        return False

    @staticmethod
    def decrypt_message(msg_signature, timestamp, nonce, echostr_or_data, is_verify=True):
        """
        验证/解密企微消息
        :param is_verify: 为 True 时处理 URL 验证请求，为 False 时处理 POST 内容解密
        """
        wxcpt = WXBizMsgCrypt(settings.TOKEN, settings.ENCODING_AES_KEY, settings.CORP_ID)
        if is_verify:
            ret, sReplyEchoStr = wxcpt.VerifyURL(msg_signature, timestamp, nonce, echostr_or_data)
        else:
            ret, sReplyEchoStr = wxcpt.DecryptMsg(echostr_or_data, msg_signature, timestamp, nonce)
        
        if ret != 0:
            logger.error(f"企微消息解密失败, 错误码: {ret}")
            return None
        return sReplyEchoStr
