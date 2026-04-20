#!/usr/bin/env python
# -*- coding: utf-8 -*-

import base64
import string
import random
import hashlib
import time
import struct
from Crypto.Cipher import AES
import xml.etree.cElementTree as ET
import sys


from .ierror import *

"""
关于Crypto.Cipher模块，需要安装 pycryptodome
"""

class PKCS7Encoder():
    """内容补位"""
    def __init__(self, k=32):
        self.k = k

    def encode(self, text):
        l = len(text)
        amount_to_pad = self.k - (l % self.k)
        if amount_to_pad == 0:
            amount_to_pad = self.k
        pad = chr(amount_to_pad)
        return text + (pad * amount_to_pad).encode('utf-8')

    def decode(self, decrypted):
        pad = decrypted[-1]
        if pad < 1 or pad > 32:
            pad = 0
        return decrypted[:-pad]


class Prpcrypt(object):
    """提供接收和推送给企业微信消息的加解密接口"""
    def __init__(self, key):
        self.key = key
        self.mode = AES.MODE_CBC

    def encrypt(self, text, receiveid):
        """对明文进行加密"""
        # 16位随机字符串
        text_bytes = text.encode('utf-8')
        random_str = ''.join(random.sample(string.ascii_letters + string.digits, 16)).encode('utf-8')
        # 网络字节序
        length_bytes = struct.pack("I", socket.htonl(len(text_bytes)))
        receiveid_bytes = receiveid.encode('utf-8')
        
        # 拼接: random(16) + length(4) + text + receiveid
        full_text = random_str + length_bytes + text_bytes + receiveid_bytes
        
        # PKCS7补位
        pkcs7 = PKCS7Encoder()
        full_text = pkcs7.encode(full_text)
        
        # AES加密
        cryptor = AES.new(self.key, self.mode, self.key[:16])
        try:
            ciphertext = cryptor.encrypt(full_text)
            return WXBizMsgCrypt_OK, base64.b64encode(ciphertext).decode('utf-8')
        except Exception as e:
            return WXBizMsgCrypt_EncryptAES_Error, None

    def decrypt(self, ciphertext, receiveid):
        """对解密后的明文进行补位删除"""
        try:
            cryptor = AES.new(self.key, self.mode, self.key[:16])
            plain_text = cryptor.decrypt(base64.b64decode(ciphertext))
        except Exception as e:
            return WXBizMsgCrypt_DecryptAES_Error, None
        
        try:
            # 去掉补位
            pkcs7 = PKCS7Encoder()
            plain_text = pkcs7.decode(plain_text)
            # 解析: random(16) + length(4) + text + receiveid
            content = plain_text[16:]
            xml_len = socket.ntohl(struct.unpack("I", content[:4])[0])
            xml_content = content[4 : xml_len + 4].decode('utf-8')
            from_receiveid = content[xml_len + 4 :].decode('utf-8')
        except Exception as e:
            return WXBizMsgCrypt_IllegalBuffer, None
            
        if from_receiveid != receiveid:
            return WXBizMsgCrypt_ValidateCorpid_Error, None
        return WXBizMsgCrypt_OK, xml_content


class WXBizMsgCrypt(object):
    """主接口类"""
    def __init__(self, sToken, sEncodingAESKey, sReceiveId):
        try:
            self.key = base64.b64decode(sEncodingAESKey + "=")
            assert len(self.key) == 32
        except:
            raise Exception("EncodingAESKey Error")
        self.m_sToken = sToken
        self.m_sReceiveId = sReceiveId

    def VerifyURL(self, sMsgSignature, sTimeStamp, sNonce, sEchoStr):
        """验证URL回调"""
        sha1 = hashlib.sha1()
        try:
            list_params = [self.m_sToken, sTimeStamp, sNonce, sEchoStr]
            list_params.sort()
            sha1.update("".join(list_params).encode('utf-8'))
            hashcode = sha1.hexdigest()
        except Exception as e:
            return WXBizMsgCrypt_ComputeSignature_Error, None
            
        if hashcode != sMsgSignature:
            return WXBizMsgCrypt_ValidateSignature_Error, None
        
        pc = Prpcrypt(self.key)
        ret, sReplyEchoStr = pc.decrypt(sEchoStr, self.m_sReceiveId)
        return ret, sReplyEchoStr

    def DecryptMsg(self, sPostData, sMsgSignature, sTimeStamp, sNonce):
        """解密Post过来的消息"""
        # 解析XML中的加密内容
        try:
            root = ET.fromstring(sPostData)
            encrypt_str = root.find("Encrypt").text
        except Exception as e:
            return WXBizMsgCrypt_ParseXml_Error, None
        
        # 验证签名
        sha1 = hashlib.sha1()
        try:
            list_params = [self.m_sToken, sTimeStamp, sNonce, encrypt_str]
            list_params.sort()
            sha1.update("".join(list_params).encode('utf-8'))
            hashcode = sha1.hexdigest()
        except Exception as e:
            return WXBizMsgCrypt_ComputeSignature_Error, None
            
        if hashcode != sMsgSignature:
            return WXBizMsgCrypt_ValidateSignature_Error, None
            
        pc = Prpcrypt(self.key)
        ret, xml_content = pc.decrypt(encrypt_str, self.m_sReceiveId)
        return ret, xml_content

import socket
