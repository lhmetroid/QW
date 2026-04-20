import requests
import json
import logging
from typing import Optional
from config import settings
from qywx_crypt.WXBizMsgCrypt import WXBizMsgCrypt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QYWXUtils:
    """企业微信API工具类"""
    
    _access_token = None
    
    @classmethod
    def get_access_token(cls):
        """获取 access_token"""
        if cls._access_token:
            return cls._access_token
            
        if not hasattr(settings, 'CORP_SECRET') or not settings.CORP_SECRET or "填写" in settings.CORP_SECRET:
            logger.warning("未配置企微 CORP_SECRET，跳过触达发送机制（仅在系统UI展示 V2 建议）")
            return None
        
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={settings.CORP_ID}&corpsecret={settings.CORP_SECRET}"
        try:
            response = requests.get(url)
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
