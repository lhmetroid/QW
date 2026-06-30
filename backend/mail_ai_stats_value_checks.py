# -*- coding: utf-8 -*-
"""Regression checks for mail AI reply value classification."""

from mail_ai_stats import _local_value_override


def test_referral_signal_is_valuable() -> None:
    body = (
        "Hi Angela,\n\n"
        "你提到的这些，你最好找布鲁克的业务相关人士，因为我这边已经是奥方KIELELE生产的医疗设备的销售，"
        "和你说及的业务相差很远。\n\n谢谢"
    )
    result = _local_value_override("RE: 从翻译到综合服务，助力布鲁克国际化沟通升级", body)
    assert result is not None
    assert result["is_valuable"] is True
    assert "业务相关" in result["reason"] or "转介绍" in result["reason"]


def test_find_other_people_with_mismatch_is_valuable() -> None:
    # 真实 6.29 回信: 裸"人"+"我这只是...销售...相差很远", 旧严格正则漏判。
    body = (
        "Hi Angela,\n\n你提到的这些，你最好找布鲁克纳的人交流一下，"
        "因为我这只是负责海外KIEFEL生产的医疗设备的销售，和你谈及的业务相差很远。\n\n谢谢"
    )
    result = _local_value_override("RE: 从翻译到综合服务，助力布鲁克纳国际化沟通升级", body)
    assert result is not None
    assert result["is_valuable"] is True


def test_unsubscribe_is_not_overridden() -> None:
    body = "请不要再发邮件，请取消订阅。你可以联系相关负责人。"
    assert _local_value_override("RE: test", body) is None


def test_plain_business_unrelated_without_referral_not_overridden() -> None:
    # 仅"业务无关"但没让你去找别人对接, 不应误判为有价值。
    body = "你好，我们公司目前不需要这类服务，业务不相关。"
    assert _local_value_override("RE: test", body) is None


if __name__ == "__main__":
    test_referral_signal_is_valuable()
    test_find_other_people_with_mismatch_is_valuable()
    test_unsubscribe_is_not_overridden()
    test_plain_business_unrelated_without_referral_not_overridden()
    print("mail_ai_stats_value_checks OK")
