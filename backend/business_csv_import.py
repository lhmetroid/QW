from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import uuid
from decimal import Decimal
from typing import Any

from config import settings
from database import KnowledgeChunk, KnowledgeDocument
from embedding_service import EmbeddingService
from knowledge_governance import infer_library_type, infer_scenario_intent, merge_tags, score_content_governance

logger = logging.getLogger(__name__)

DEFAULT_BUSINESS_CSV_FILENAME = "业务知识、业务流程、话术、案例.csv"
DEFAULT_SOURCE_TYPE = "business_csv"
DEFAULT_OWNER = "business_csv_import"
DEFAULT_ROW_START = 1
DEFAULT_ROW_END = 50
DEFAULT_ROW_LIMIT = DEFAULT_ROW_END - DEFAULT_ROW_START + 1
DEFAULT_SKIP_ROWS = {
    29: "too_short_generic",
    48: "too_short_generic",
    69: "too_short_generic",
    74: "too_short_generic",
    75: "too_short_generic",
    76: "too_short_generic",
    79: "too_short_generic",
    97: "too_short_generic",
    116: "pure_phone_low_increment",
    117: "pure_phone_low_increment",
    118: "pure_phone_low_increment",
    122: "pure_phone_low_increment",
    147: "too_vague_low_value",
    148: "too_short_generic",
    151: "too_short_generic",
    152: "pure_phone_low_increment",
    169: "duplicate_low_increment",
    170: "duplicate_low_increment",
    178: "too_short_generic",
    188: "duplicate_low_increment",
    196: "duplicate_low_increment",
    202: "too_generic_low_value",
    214: "duplicate_low_increment",
    215: "risk_of_miscalculation",
    221: "pure_phone_low_increment",
    224: "too_unclear_low_value",
    226: "too_generic_low_value",
    228: "too_generic_low_value",
    233: "duplicate_low_increment",
    234: "duplicate_low_increment",
    237: "duplicate_low_increment",
    238: "too_generic_low_value",
    244: "too_generic_low_value",
    247: "too_generic_low_value",
    248: "duplicate_low_increment",
    256: "too_generic_low_value",
    258: "too_generic_low_value",
    260: "too_generic_low_value",
    264: "pure_phone_low_increment",
    267: "too_generic_low_value",
    281: "risk_of_miscalculation",
    286: "risk_of_miscalculation",
    293: "pure_phone_low_increment",
    295: "too_uncertain_low_value",
    297: "too_unclear_low_value",
    302: "too_case_specific_low_value",
    303: "too_generic_low_value",
    304: "too_case_specific_low_value",
    305: "risk_of_miscalculation",
    315: "duplicate_low_increment",
    317: "duplicate_low_increment",
    324: "duplicate_low_increment",
    331: "duplicate_low_increment",
    337: "duplicate_low_increment",
    338: "duplicate_low_increment",
    368: "risk_of_miscalculation",
    369: "too_case_specific_low_value",
    382: "duplicate_low_increment",
    407: "duplicate_low_increment",
    419: "duplicate_low_increment",
    421: "duplicate_low_increment",
    402: "duplicate_low_increment",
    404: "duplicate_low_increment",
    428: "duplicate_low_increment",
    433: "time_sensitive_low_value",
    438: "duplicate_low_increment",
    442: "too_case_specific_low_value",
    458: "duplicate_low_increment",
    478: "duplicate_low_increment",
    499: "too_unclear_low_value",
    519: "too_case_specific_low_value",
    521: "pure_phone_low_increment",
    551: "duplicate_low_increment",
    554: "time_sensitive_low_value",
    586: "duplicate_low_increment",
    598: "duplicate_low_increment",
    594: "too_case_specific_low_value",
    597: "too_case_specific_low_value",
    605: "too_case_specific_low_value",
    606: "too_case_specific_low_value",
    608: "too_case_specific_low_value",
    612: "too_case_specific_low_value",
    624: "too_case_specific_low_value",
    625: "duplicate_low_increment",
    678: "pure_phone_low_increment",
    712: "too_short_generic",
}


def _optional_embedding_for_import(text: str, *, context: str) -> list[float] | None:
    try:
        embedding = EmbeddingService.embed(text)
    except Exception as exc:
        logger.warning("业务 CSV embedding 调用失败，继续按无向量模式入库。 context=%s error=%s", context, exc)
        return None
    if not embedding:
        logger.warning("业务 CSV embedding 未返回向量，继续按无向量模式入库。 context=%s", context)
        return None
    return embedding
TITLE_NORMALIZATION_OVERRIDES = {
    24: "推荐本人全业务",
    25: "推荐本人同传业务",
    26: "推荐本人印刷业务",
    27: "推荐本人视频业务",
    520: "首次合作如何确定预付款与账期条件？",
}

ROW_OVERRIDES = {
    1: {"knowledge_class": "process", "business_line": "printing", "service_scope": "printing_general"},
    2: {"knowledge_class": "process", "business_line": "translation", "service_scope": "translation_general"},
    3: {"knowledge_class": "process", "business_line": "interpretation", "service_scope": "simultaneous_interpretation"},
    4: {"knowledge_class": "faq", "business_line": "general", "service_scope": "general"},
    5: {"knowledge_class": "faq", "business_line": "general", "service_scope": "general"},
    6: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    7: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    8: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    9: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    10: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "technical_translation"},
    11: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    12: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "translation_general"},
    13: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    14: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    15: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    16: {"knowledge_class": "faq", "business_line": "general", "service_scope": "general"},
    17: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    18: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    19: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    20: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    21: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    22: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    23: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    24: {"knowledge_class": "script", "business_line": "general", "service_scope": "cross_sell"},
    25: {"knowledge_class": "script", "business_line": "interpretation", "service_scope": "cross_sell"},
    26: {"knowledge_class": "script", "business_line": "printing", "service_scope": "cross_sell"},
    27: {"knowledge_class": "script", "business_line": "multimedia", "service_scope": "cross_sell"},
    28: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    30: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    31: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    32: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_refresh"},
    33: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    34: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    35: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    36: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    37: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    38: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    39: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    40: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    41: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    42: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    43: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    44: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    45: {"knowledge_class": "faq", "business_line": "general", "service_scope": "company_background"},
    46: {"knowledge_class": "script", "business_line": "general", "service_scope": "procurement_path"},
    47: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    49: {"knowledge_class": "script", "business_line": "general", "service_scope": "security_response"},
    50: {"knowledge_class": "script", "business_line": "general", "service_scope": "cross_sell"},
    51: {"knowledge_class": "script", "business_line": "general", "service_scope": "cross_sell"},
    52: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    53: {"knowledge_class": "script", "business_line": "general", "service_scope": "procurement_path"},
    54: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    55: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    56: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    57: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    58: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    59: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    60: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    61: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    62: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    63: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    64: {"knowledge_class": "script", "business_line": "general", "service_scope": "account_reactivation"},
    65: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    66: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    67: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    68: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    70: {"knowledge_class": "script", "business_line": "general", "service_scope": "account_transfer"},
    71: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    72: {"knowledge_class": "faq", "business_line": "general", "service_scope": "company_background"},
    73: {"knowledge_class": "faq", "business_line": "general", "service_scope": "company_background"},
    77: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    78: {"knowledge_class": "script", "business_line": "general", "service_scope": "supplier_assessment"},
    80: {"knowledge_class": "script", "business_line": "general", "service_scope": "supplier_assessment"},
    81: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    82: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    83: {"knowledge_class": "capability", "business_line": "general", "service_scope": "general"},
    84: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    85: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    86: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    87: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    88: {"knowledge_class": "script", "business_line": "general", "service_scope": "supplier_assessment"},
    89: {"knowledge_class": "script", "business_line": "general", "service_scope": "objection_handling"},
    90: {"knowledge_class": "script", "business_line": "general", "service_scope": "cross_sell"},
    91: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    92: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    93: {"knowledge_class": "example", "business_line": "general", "service_scope": "cold_customer"},
    94: {"knowledge_class": "process", "business_line": "general", "service_scope": "industry_development"},
    95: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    96: {"knowledge_class": "process", "business_line": "general", "service_scope": "pricing_objection"},
    98: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    99: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    100: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_etiquette"},
    101: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    102: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    103: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    104: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    105: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    106: {"knowledge_class": "process", "business_line": "general", "service_scope": "pre_call_preparation"},
    107: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    108: {"knowledge_class": "process", "business_line": "general", "service_scope": "account_reactivation"},
    109: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    110: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    111: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    112: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    113: {"knowledge_class": "process", "business_line": "general", "service_scope": "rapport_building"},
    114: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    115: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    116: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    117: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    118: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    119: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    120: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    121: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    122: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    123: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    124: {"knowledge_class": "script", "business_line": "interpretation", "service_scope": "townhall_follow_up"},
    125: {"knowledge_class": "process", "business_line": "interpretation", "service_scope": "townhall_follow_up"},
    126: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    127: {"knowledge_class": "process", "business_line": "general", "service_scope": "rapport_building"},
    128: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    129: {"knowledge_class": "process", "business_line": "gifts", "service_scope": "cross_sell"},
    130: {"knowledge_class": "process", "business_line": "gifts", "service_scope": "objection_handling"},
    131: {"knowledge_class": "process", "business_line": "translation", "service_scope": "demand_probe"},
    132: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    133: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    134: {"knowledge_class": "process", "business_line": "general", "service_scope": "research"},
    135: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_rediscovery"},
    136: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_rediscovery"},
    137: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_rediscovery"},
    138: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_rediscovery"},
    139: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_rediscovery"},
    140: {"knowledge_class": "process", "business_line": "general", "service_scope": "account_transfer"},
    141: {"knowledge_class": "process", "business_line": "general", "service_scope": "visit_preparation"},
    142: {"knowledge_class": "process", "business_line": "general", "service_scope": "visit_goal"},
    143: {"knowledge_class": "process", "business_line": "general", "service_scope": "visit_execution"},
    144: {"knowledge_class": "process", "business_line": "general", "service_scope": "visit_scheduling"},
    145: {"knowledge_class": "process", "business_line": "general", "service_scope": "visit_execution"},
    146: {"knowledge_class": "process", "business_line": "general", "service_scope": "relationship_maintenance"},
    149: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    150: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    153: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_qualification"},
    154: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_qualification"},
    155: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_qualification"},
    156: {"knowledge_class": "example", "business_line": "translation", "service_scope": "translation_requirement"},
    157: {"knowledge_class": "example", "business_line": "translation", "service_scope": "project_scope"},
    158: {"knowledge_class": "process", "business_line": "translation", "service_scope": "translation_revision"},
    159: {"knowledge_class": "process", "business_line": "translation", "service_scope": "compliance_editing"},
    160: {"knowledge_class": "process", "business_line": "general", "service_scope": "payment_terms"},
    161: {"knowledge_class": "process", "business_line": "translation", "service_scope": "translation_requirement"},
    162: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "service_options"},
    163: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    164: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "translator_qualification"},
    165: {"knowledge_class": "process", "business_line": "translation", "service_scope": "translation_revision"},
    166: {"knowledge_class": "process", "business_line": "translation", "service_scope": "compliance_editing"},
    167: {"knowledge_class": "example", "business_line": "translation", "service_scope": "translation_requirement"},
    168: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "translation_requirement"},
    171: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "localization_quality"},
    172: {"knowledge_class": "process", "business_line": "general", "service_scope": "payment_follow_up"},
    173: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quality_issue"},
    174: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quality_issue"},
    175: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quality_issue"},
    176: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "certified_translation"},
    177: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "certified_translation"},
    179: {"knowledge_class": "example", "business_line": "translation", "service_scope": "file_format"},
    180: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    181: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    182: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    183: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    184: {"knowledge_class": "example", "business_line": "translation", "service_scope": "cooperation_history"},
    185: {"knowledge_class": "process", "business_line": "general", "service_scope": "service_response"},
    186: {"knowledge_class": "capability", "business_line": "general", "service_scope": "service_response"},
    187: {"knowledge_class": "process", "business_line": "translation", "service_scope": "case_request"},
    189: {"knowledge_class": "process", "business_line": "general", "service_scope": "contract_approval"},
    190: {"knowledge_class": "process", "business_line": "general", "service_scope": "contract_approval"},
    191: {"knowledge_class": "process", "business_line": "translation", "service_scope": "project_timeline"},
    192: {"knowledge_class": "process", "business_line": "translation", "service_scope": "project_timeline"},
    193: {"knowledge_class": "process", "business_line": "translation", "service_scope": "pricing_objection"},
    194: {"knowledge_class": "process", "business_line": "general", "service_scope": "quote_update"},
    195: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_onboarding"},
    197: {"knowledge_class": "faq", "business_line": "general", "service_scope": "nda"},
    198: {"knowledge_class": "process", "business_line": "general", "service_scope": "nda"},
    199: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quotation"},
    200: {"knowledge_class": "faq", "business_line": "general", "service_scope": "payment_terms"},
    201: {"knowledge_class": "process", "business_line": "general", "service_scope": "payment_terms"},
    203: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "language_pair"},
    204: {"knowledge_class": "example", "business_line": "translation", "service_scope": "translation_requirement"},
    205: {"knowledge_class": "example", "business_line": "translation", "service_scope": "project_timeline"},
    206: {"knowledge_class": "faq", "business_line": "general", "service_scope": "invoicing"},
    207: {"knowledge_class": "example", "business_line": "general", "service_scope": "email_follow_up"},
    208: {"knowledge_class": "example", "business_line": "translation", "service_scope": "project_priority"},
    209: {"knowledge_class": "example", "business_line": "general", "service_scope": "file_receipt"},
    210: {"knowledge_class": "example", "business_line": "translation", "service_scope": "project_scope"},
    211: {"knowledge_class": "example", "business_line": "translation", "service_scope": "project_timeline"},
    212: {"knowledge_class": "process", "business_line": "translation", "service_scope": "translation_revision"},
    213: {"knowledge_class": "process", "business_line": "translation", "service_scope": "text_conversion"},
    217: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quotation"},
    218: {"knowledge_class": "process", "business_line": "translation", "service_scope": "project_start"},
    219: {"knowledge_class": "script", "business_line": "general", "service_scope": "trust_building"},
    220: {"knowledge_class": "example", "business_line": "translation", "service_scope": "translation_requirement"},
    222: {"knowledge_class": "example", "business_line": "general", "service_scope": "contact_role"},
    223: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    225: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    227: {"knowledge_class": "process", "business_line": "general", "service_scope": "objection_handling"},
    229: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "word_count"},
    230: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "word_count"},
    231: {"knowledge_class": "process", "business_line": "translation", "service_scope": "word_count"},
    232: {"knowledge_class": "process", "business_line": "translation", "service_scope": "word_count"},
    235: {"knowledge_class": "process", "business_line": "translation", "service_scope": "word_count"},
    236: {"knowledge_class": "process", "business_line": "translation", "service_scope": "word_count"},
    239: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_onboarding"},
    240: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_onboarding"},
    241: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    242: {"knowledge_class": "process", "business_line": "translation", "service_scope": "demand_probe"},
    243: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    245: {"knowledge_class": "example", "business_line": "translation", "service_scope": "cooperation_history"},
    246: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    249: {"knowledge_class": "example", "business_line": "general", "service_scope": "payment_follow_up"},
    250: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    251: {"knowledge_class": "example", "business_line": "general", "service_scope": "payment_follow_up"},
    252: {"knowledge_class": "process", "business_line": "translation", "service_scope": "feedback_follow_up"},
    253: {"knowledge_class": "process", "business_line": "translation", "service_scope": "feedback_follow_up"},
    254: {"knowledge_class": "process", "business_line": "general", "service_scope": "payment_follow_up"},
    255: {"knowledge_class": "example", "business_line": "general", "service_scope": "payment_follow_up"},
    257: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    259: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "ai_translation"},
    261: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    262: {"knowledge_class": "process", "business_line": "translation", "service_scope": "supplier_selection"},
    263: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    265: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    266: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    268: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    269: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    270: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    271: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "technical_translation"},
    272: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "localization_quality"},
    273: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    274: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    275: {"knowledge_class": "process", "business_line": "translation", "service_scope": "pricing_objection"},
    276: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "trial_translation"},
    277: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "turnaround_time"},
    278: {"knowledge_class": "capability", "business_line": "general", "service_scope": "service_scope"},
    279: {"knowledge_class": "example", "business_line": "translation", "service_scope": "technical_translation"},
    280: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "local_vendor"},
    281: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    282: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "layout_fee"},
    283: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "turnaround_time"},
    284: {"knowledge_class": "process", "business_line": "translation", "service_scope": "file_submission"},
    285: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "quality_management"},
    286: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    287: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    288: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    289: {"knowledge_class": "process", "business_line": "multimedia", "service_scope": "audio_translation"},
    290: {"knowledge_class": "process", "business_line": "translation", "service_scope": "layout_handoff"},
    291: {"knowledge_class": "example", "business_line": "translation", "service_scope": "deliverable_format"},
    292: {"knowledge_class": "process", "business_line": "general", "service_scope": "cross_sell"},
    294: {"knowledge_class": "example", "business_line": "general", "service_scope": "account_balance"},
    296: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    298: {"knowledge_class": "example", "business_line": "general", "service_scope": "discount_policy"},
    299: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quality_feedback"},
    300: {"knowledge_class": "capability", "business_line": "general", "service_scope": "case_showcase"},
    301: {"knowledge_class": "process", "business_line": "translation", "service_scope": "online_order_system"},
    302: {"knowledge_class": "example", "business_line": "general", "service_scope": "payment_terms"},
    305: {"knowledge_class": "example", "business_line": "translation", "service_scope": "quotation"},
    306: {"knowledge_class": "capability", "business_line": "general", "service_scope": "service_scope"},
    307: {"knowledge_class": "capability", "business_line": "general", "service_scope": "case_showcase"},
    308: {"knowledge_class": "example", "business_line": "translation", "service_scope": "objection_handling"},
    309: {"knowledge_class": "example", "business_line": "general", "service_scope": "demand_probe"},
    310: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    311: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_follow_up"},
    312: {"knowledge_class": "process", "business_line": "general", "service_scope": "trust_building"},
    313: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    314: {"knowledge_class": "example", "business_line": "general", "service_scope": "identity_confirmation"},
    316: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    317: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    318: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    319: {"knowledge_class": "capability", "business_line": "general", "service_scope": "quality_management"},
    320: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    321: {"knowledge_class": "example", "business_line": "general", "service_scope": "supplier_selection"},
    322: {"knowledge_class": "faq", "business_line": "general", "service_scope": "contract_signing"},
    323: {"knowledge_class": "process", "business_line": "general", "service_scope": "file_delivery"},
    325: {"knowledge_class": "script", "business_line": "general", "service_scope": "demand_probe"},
    326: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    327: {"knowledge_class": "script", "business_line": "general", "service_scope": "trust_building"},
    328: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_etiquette"},
    329: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    330: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    332: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    333: {"knowledge_class": "example", "business_line": "general", "service_scope": "referral_source"},
    334: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    335: {"knowledge_class": "process", "business_line": "general", "service_scope": "case_request"},
    336: {"knowledge_class": "process", "business_line": "translation", "service_scope": "pricing_objection"},
    339: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quality_assurance"},
    340: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_selection"},
    341: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    342: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    343: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    344: {"knowledge_class": "example", "business_line": "general", "service_scope": "cooperation_history"},
    345: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_onboarding"},
    346: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "certified_translation"},
    347: {"knowledge_class": "process", "business_line": "translation", "service_scope": "project_timeline"},
    348: {"knowledge_class": "example", "business_line": "translation", "service_scope": "pricing_objection"},
    349: {"knowledge_class": "example", "business_line": "translation", "service_scope": "quotation"},
    350: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "certified_translation"},
    351: {"knowledge_class": "process", "business_line": "translation", "service_scope": "certified_translation"},
    352: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    353: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "certified_translation"},
    354: {"knowledge_class": "example", "business_line": "translation", "service_scope": "certified_translation"},
    355: {"knowledge_class": "capability", "business_line": "general", "service_scope": "service_scope"},
    356: {"knowledge_class": "script", "business_line": "general", "service_scope": "trust_building"},
    357: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    358: {"knowledge_class": "example", "business_line": "translation", "service_scope": "pricing_rule"},
    359: {"knowledge_class": "example", "business_line": "general", "service_scope": "cooperation_history"},
    360: {"knowledge_class": "example", "business_line": "general", "service_scope": "cross_sell"},
    361: {"knowledge_class": "process", "business_line": "translation", "service_scope": "ai_translation"},
    362: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    363: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    364: {"knowledge_class": "process", "business_line": "translation", "service_scope": "supplier_selection"},
    365: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    366: {"knowledge_class": "script", "business_line": "translation", "service_scope": "quality_assurance"},
    367: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    368: {"knowledge_class": "example", "business_line": "translation", "service_scope": "quotation"},
    369: {"knowledge_class": "example", "business_line": "general", "service_scope": "payment_terms"},
    370: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quality_feedback"},
    371: {"knowledge_class": "process", "business_line": "translation", "service_scope": "pricing_rule"},
    372: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    373: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "language_pair"},
    374: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    375: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    376: {"knowledge_class": "script", "business_line": "general", "service_scope": "identity_confirmation"},
    377: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    378: {"knowledge_class": "process", "business_line": "translation", "service_scope": "objection_handling"},
    379: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    380: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    381: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    382: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "quality_management"},
    383: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    384: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    385: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    386: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "language_pair"},
    387: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    388: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "service_scope"},
    389: {"knowledge_class": "example", "business_line": "general", "service_scope": "demand_status"},
    390: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    391: {"knowledge_class": "example", "business_line": "general", "service_scope": "cooperation_history"},
    392: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    393: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    394: {"knowledge_class": "capability", "business_line": "general", "service_scope": "case_showcase"},
    395: {"knowledge_class": "process", "business_line": "translation", "service_scope": "service_process"},
    396: {"knowledge_class": "example", "business_line": "general", "service_scope": "cooperation_history"},
    397: {"knowledge_class": "process", "business_line": "translation", "service_scope": "case_request"},
    398: {"knowledge_class": "script", "business_line": "general", "service_scope": "identity_confirmation"},
    399: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    400: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    401: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    403: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    405: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    406: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    408: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "quality_management"},
    409: {"knowledge_class": "example", "business_line": "translation", "service_scope": "case_showcase"},
    410: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    411: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    412: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    413: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    414: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "translation_requirement"},
    415: {"knowledge_class": "process", "business_line": "translation", "service_scope": "translation_requirement"},
    416: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    417: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    418: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    419: {"knowledge_class": "process", "business_line": "general", "service_scope": "objection_handling"},
    420: {"knowledge_class": "process", "business_line": "general", "service_scope": "account_transfer"},
    421: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    422: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    423: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_etiquette"},
    424: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    425: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    426: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    427: {"knowledge_class": "example", "business_line": "general", "service_scope": "project_department_status"},
    429: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    430: {"knowledge_class": "process", "business_line": "translation", "service_scope": "objection_handling"},
    431: {"knowledge_class": "capability", "business_line": "general", "service_scope": "service_scope"},
    432: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    434: {"knowledge_class": "faq", "business_line": "general", "service_scope": "tender_information"},
    435: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    436: {"knowledge_class": "process", "business_line": "translation", "service_scope": "demand_probe"},
    437: {"knowledge_class": "script", "business_line": "translation", "service_scope": "contact_follow_up"},
    439: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_onboarding"},
    440: {"knowledge_class": "process", "business_line": "translation", "service_scope": "objection_handling"},
    441: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    443: {"knowledge_class": "example", "business_line": "translation", "service_scope": "service_scope"},
    444: {"knowledge_class": "process", "business_line": "translation", "service_scope": "objection_handling"},
    445: {"knowledge_class": "example", "business_line": "general", "service_scope": "project_department_status"},
    446: {"knowledge_class": "example", "business_line": "general", "service_scope": "project_department_status"},
    447: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    448: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    449: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "ai_translation"},
    450: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    451: {"knowledge_class": "example", "business_line": "translation", "service_scope": "quality_feedback"},
    452: {"knowledge_class": "capability", "business_line": "general", "service_scope": "case_showcase"},
    453: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    454: {"knowledge_class": "script", "business_line": "general", "service_scope": "long_term_cooperation"},
    455: {"knowledge_class": "process", "business_line": "general", "service_scope": "objection_handling"},
    456: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    457: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    458: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    459: {"knowledge_class": "script", "business_line": "general", "service_scope": "identity_confirmation"},
    460: {"knowledge_class": "example", "business_line": "translation", "service_scope": "project_timeline"},
    461: {"knowledge_class": "example", "business_line": "translation", "service_scope": "quality_feedback"},
    462: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    463: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    464: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    465: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "quality_management"},
    466: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    467: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    468: {"knowledge_class": "faq", "business_line": "general", "service_scope": "security_response"},
    469: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    470: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    471: {"knowledge_class": "example", "business_line": "general", "service_scope": "contact_role"},
    472: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "translation_scope"},
    473: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "language_pair"},
    474: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    475: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    476: {"knowledge_class": "process", "business_line": "translation", "service_scope": "demand_probe"},
    477: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    479: {"knowledge_class": "example", "business_line": "translation", "service_scope": "ai_translation"},
    480: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    481: {"knowledge_class": "process", "business_line": "translation", "service_scope": "supplier_selection"},
    482: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "domain_knowledge"},
    483: {"knowledge_class": "example", "business_line": "general", "service_scope": "supplier_assessment"},
    484: {"knowledge_class": "capability", "business_line": "general", "service_scope": "service_scope"},
    485: {"knowledge_class": "script", "business_line": "general", "service_scope": "identity_confirmation"},
    486: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    487: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    488: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    489: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    490: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "ai_translation"},
    491: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    492: {"knowledge_class": "example", "business_line": "general", "service_scope": "cooperation_history"},
    493: {"knowledge_class": "example", "business_line": "general", "service_scope": "account_transfer"},
    494: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    495: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    496: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "certified_translation"},
    497: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "domain_knowledge"},
    498: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "domain_knowledge"},
    500: {"knowledge_class": "process", "business_line": "translation", "service_scope": "case_request"},
    501: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "pricing_rule"},
    502: {"knowledge_class": "process", "business_line": "general", "service_scope": "cross_sell"},
    503: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_prioritization"},
    504: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    505: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_coaching"},
    506: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    507: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    508: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    509: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_coaching"},
    510: {"knowledge_class": "process", "business_line": "general", "service_scope": "account_transfer"},
    511: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    512: {"knowledge_class": "script", "business_line": "translation", "service_scope": "contact_discovery"},
    513: {"knowledge_class": "example", "business_line": "general", "service_scope": "supplier_selection"},
    514: {"knowledge_class": "example", "business_line": "general", "service_scope": "budget_control"},
    515: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "ai_translation"},
    516: {"knowledge_class": "example", "business_line": "general", "service_scope": "contact_follow_up"},
    517: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    518: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "ai_translation"},
    520: {"knowledge_class": "process", "business_line": "translation", "service_scope": "payment_terms"},
    521: {"knowledge_class": "process", "business_line": "general", "service_scope": "identity_confirmation"},
    522: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_resolution_internal"},
    523: {"knowledge_class": "example", "business_line": "general", "service_scope": "budget_control"},
    524: {"knowledge_class": "script", "business_line": "general", "service_scope": "identity_confirmation"},
    525: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    526: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    527: {"knowledge_class": "process", "business_line": "translation", "service_scope": "pricing_rule"},
    528: {"knowledge_class": "process", "business_line": "general", "service_scope": "account_transfer"},
    529: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    530: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_follow_up"},
    531: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    532: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_coaching"},
    533: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    534: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "ai_translation"},
    535: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    536: {"knowledge_class": "process", "business_line": "general", "service_scope": "referral_source"},
    537: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    538: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    539: {"knowledge_class": "example", "business_line": "general", "service_scope": "cooperation_history"},
    540: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_onboarding"},
    541: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    542: {"knowledge_class": "process", "business_line": "translation", "service_scope": "project_timeline"},
    543: {"knowledge_class": "process", "business_line": "general", "service_scope": "objection_handling"},
    544: {"knowledge_class": "script", "business_line": "general", "service_scope": "cooperation_history"},
    545: {"knowledge_class": "example", "business_line": "translation", "service_scope": "demand_status"},
    546: {"knowledge_class": "process", "business_line": "translation", "service_scope": "file_submission"},
    547: {"knowledge_class": "process", "business_line": "general", "service_scope": "payment_follow_up"},
    548: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    549: {"knowledge_class": "process", "business_line": "translation", "service_scope": "demand_probe"},
    550: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "translation_requirement"},
    552: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "quality_requirements"},
    553: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    555: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "certified_translation"},
    556: {"knowledge_class": "process", "business_line": "general", "service_scope": "payment_terms"},
    557: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_management"},
    558: {"knowledge_class": "process", "business_line": "general", "service_scope": "customer_segmentation"},
    559: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_management"},
    560: {"knowledge_class": "process", "business_line": "general", "service_scope": "system_usage"},
    561: {"knowledge_class": "process", "business_line": "general", "service_scope": "account_planning"},
    562: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_qualification"},
    563: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    564: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    565: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_management"},
    566: {"knowledge_class": "process", "business_line": "general", "service_scope": "opportunity_management"},
    567: {"knowledge_class": "process", "business_line": "translation", "service_scope": "demand_probe"},
    568: {"knowledge_class": "process", "business_line": "general", "service_scope": "trust_building"},
    569: {"knowledge_class": "process", "business_line": "general", "service_scope": "customer_strategy"},
    570: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    571: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    572: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    573: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    574: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    575: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "language_pair"},
    576: {"knowledge_class": "process", "business_line": "general", "service_scope": "objection_handling"},
    577: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    578: {"knowledge_class": "capability", "business_line": "general", "service_scope": "service_scope"},
    579: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "quality_management"},
    580: {"knowledge_class": "capability", "business_line": "general", "service_scope": "case_showcase"},
    581: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    582: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "translation_requirement"},
    583: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_selection"},
    584: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    585: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "language_pair"},
    587: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_selection"},
    588: {"knowledge_class": "process", "business_line": "general", "service_scope": "long_term_cooperation"},
    589: {"knowledge_class": "process", "business_line": "translation", "service_scope": "ai_translation"},
    590: {"knowledge_class": "script", "business_line": "general", "service_scope": "trust_building"},
    591: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quality_assurance"},
    592: {"knowledge_class": "process", "business_line": "general", "service_scope": "cross_sell"},
    593: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_etiquette"},
    595: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    596: {"knowledge_class": "process", "business_line": "translation", "service_scope": "demand_probe"},
    598: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    599: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    600: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    601: {"knowledge_class": "process", "business_line": "general", "service_scope": "supplier_selection"},
    602: {"knowledge_class": "process", "business_line": "general", "service_scope": "lead_generation"},
    603: {"knowledge_class": "process", "business_line": "general", "service_scope": "system_usage"},
    604: {"knowledge_class": "process", "business_line": "general", "service_scope": "project_management"},
    607: {"knowledge_class": "process", "business_line": "general", "service_scope": "cross_sell"},
    609: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    610: {"knowledge_class": "process", "business_line": "general", "service_scope": "system_usage"},
    611: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    613: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_etiquette"},
    614: {"knowledge_class": "process", "business_line": "general", "service_scope": "objection_handling"},
    615: {"knowledge_class": "process", "business_line": "general", "service_scope": "objection_handling"},
    616: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_management"},
    617: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    618: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    619: {"knowledge_class": "process", "business_line": "translation", "service_scope": "demand_probe"},
    620: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    621: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_etiquette"},
    622: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    623: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    625: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    626: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    627: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "terminology"},
    628: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "quality_assurance"},
    629: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "file_delivery"},
    630: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "terminology"},
    631: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "quality_assurance"},
    632: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "quality_assurance"},
    633: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "quality_assurance"},
    634: {"knowledge_class": "example", "business_line": "translation", "service_scope": "quality_feedback"},
    635: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "quality_assurance"},
    636: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "terminology"},
    637: {"knowledge_class": "faq", "business_line": "multimedia", "service_scope": "quality_assurance"},
    638: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "layout_handoff"},
    639: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "quality_assurance"},
    640: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "localization_quality"},
    641: {"knowledge_class": "faq", "business_line": "multimedia", "service_scope": "quality_assurance"},
    642: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "localization_quality"},
    643: {"knowledge_class": "faq", "business_line": "translation", "service_scope": "quality_assurance"},
    644: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_outreach"},
    645: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    646: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_management"},
    647: {"knowledge_class": "process", "business_line": "translation", "service_scope": "demand_probe"},
    648: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    649: {"knowledge_class": "process", "business_line": "general", "service_scope": "follow_up_strategy"},
    650: {"knowledge_class": "process", "business_line": "general", "service_scope": "procurement_path"},
    651: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    652: {"knowledge_class": "process", "business_line": "general", "service_scope": "demand_probe"},
    653: {"knowledge_class": "process", "business_line": "general", "service_scope": "system_usage"},
    654: {"knowledge_class": "process", "business_line": "general", "service_scope": "pre_call_preparation"},
    655: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    656: {"knowledge_class": "process", "business_line": "general", "service_scope": "system_usage"},
    657: {"knowledge_class": "process", "business_line": "general", "service_scope": "system_usage"},
    658: {"knowledge_class": "process", "business_line": "general", "service_scope": "email_handling"},
    659: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_management"},
    660: {"knowledge_class": "process", "business_line": "general", "service_scope": "system_usage"},
    661: {"knowledge_class": "process", "business_line": "general", "service_scope": "contact_discovery"},
    662: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_outreach"},
    663: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    664: {"knowledge_class": "script", "business_line": "general", "service_scope": "sales_outreach"},
    665: {"knowledge_class": "script", "business_line": "translation", "service_scope": "sales_outreach"},
    666: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    667: {"knowledge_class": "capability", "business_line": "general", "service_scope": "case_showcase"},
    668: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    669: {"knowledge_class": "capability", "business_line": "general", "service_scope": "case_showcase"},
    670: {"knowledge_class": "script", "business_line": "general", "service_scope": "cross_sell"},
    671: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    672: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_discovery"},
    673: {"knowledge_class": "script", "business_line": "general", "service_scope": "procurement_path"},
    674: {"knowledge_class": "script", "business_line": "translation", "service_scope": "contact_discovery"},
    675: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_follow_up"},
    676: {"knowledge_class": "script", "business_line": "general", "service_scope": "supplier_selection"},
    677: {"knowledge_class": "process", "business_line": "translation", "service_scope": "quality_feedback"},
    678: {"knowledge_class": "script", "business_line": "general", "service_scope": "competitive_advantage"},
    679: {"knowledge_class": "script", "business_line": "general", "service_scope": "contact_rediscovery"},
    680: {"knowledge_class": "script", "business_line": "translation", "service_scope": "pricing_objection"},
    681: {"knowledge_class": "script", "business_line": "translation", "service_scope": "objection_handling"},
    682: {"knowledge_class": "capability", "business_line": "general", "service_scope": "competitive_advantage"},
    683: {"knowledge_class": "process", "business_line": "general", "service_scope": "sales_outreach"},
    684: {"knowledge_class": "example", "business_line": "interpretation", "service_scope": "simultaneous_interpretation"},
    685: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    686: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    687: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    688: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    689: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    690: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    691: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    692: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    693: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    694: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    695: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    696: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    697: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    698: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    699: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    700: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    701: {"knowledge_class": "capability", "business_line": "general", "service_scope": "case_showcase"},
    702: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    703: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "partner_network"},
    704: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    705: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    706: {"knowledge_class": "capability", "business_line": "general", "service_scope": "case_showcase"},
    707: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    708: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "case_showcase"},
    709: {"knowledge_class": "capability", "business_line": "exhibition", "service_scope": "event_marketing"},
    710: {"knowledge_class": "capability", "business_line": "gifts", "service_scope": "promotional_gifts"},
    711: {"knowledge_class": "capability", "business_line": "translation", "service_scope": "technical_translation"},
}


def normalize_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^\s*```+\s*$", "", text, flags=re.M)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_source_title(row_no: int, title: str) -> str:
    cleaned = normalize_text(title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([，。！？；：,.!?;:])", r"\1", cleaned)
    if row_no in TITLE_NORMALIZATION_OVERRIDES:
        return TITLE_NORMALIZATION_OVERRIDES[row_no]
    return cleaned


def normalized_fingerprint(title: str, content: str) -> str:
    raw = re.sub(r"\s+", "", f"{title}|{content}")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def title_for_row(row_no: int, title: str) -> str:
    return f"业务资料{row_no:02d}·{title[:120]}"


def infer_business_line(title: str, content: str) -> str:
    text = f"{title}\n{content}"
    if any(word in text for word in ["印刷", "样本", "骑马钉", "胶装", "纸张", "打样"]):
        return "printing"
    if any(word in text for word in ["同传", "交传", "口译", "耳机", "彩排", "会议"]):
        return "interpretation"
    if any(word in text for word in ["视频", "字幕", "配音", "听写"]):
        return "multimedia"
    if any(word in text for word in ["展会", "展台", "易拉宝"]):
        return "exhibition"
    if any(word in text for word in ["礼品", "台历", "笔记本"]):
        return "gifts"
    if any(word in text for word in ["翻译", "译员", "语种", "译审", "笔译"]):
        return "translation"
    return "general"


def infer_service_scope(title: str, content: str, business_line: str) -> str | None:
    text = f"{title}\n{content}"
    if business_line == "printing":
        if "样本" in text:
            return "marketing_material"
        return "printing_general"
    if business_line == "interpretation":
        if "同传" in text:
            return "simultaneous_interpretation"
        return "interpretation_general"
    if business_line == "multimedia":
        return "video_localization"
    if business_line == "exhibition":
        return "event_marketing"
    if business_line == "gifts":
        return "promotional_gifts"
    if business_line == "translation":
        if "技术资料" in text:
            return "technical_translation"
        return "translation_general"
    return "general"


def infer_knowledge_class(row_no: int, title: str, content: str) -> str:
    override = ROW_OVERRIDES.get(row_no, {})
    if override.get("knowledge_class"):
        return override["knowledge_class"]
    if "流程" in title or "流程" in content:
        return "process"
    if title.endswith("？") or "何时成立" in title or "有哪些" in title:
        return "faq"
    return "faq"


def infer_chunk_type(knowledge_class: str) -> tuple[str, str]:
    mapping = {
        "process": ("process", "rule"),
        "capability": ("capability", "rule"),
        "example": ("faq", "example"),
        "script": ("faq", "template"),
        "faq": ("faq", "faq"),
    }
    return mapping.get(knowledge_class, ("faq", "faq"))


def risk_level_for_row(row_no: int, title: str, content: str, knowledge_class: str) -> str:
    text = f"{title}\n{content}"
    if knowledge_class == "script" and any(word in text for word in ["保密", "供应商系统", "合同", "签单"]):
        return "high"
    if any(word in text for word in ["第一", "市场份额", "最大", "95%", "70%", "100多名", "30名"]):
        return "medium"
    return "medium"


def format_row_scope(row_start: int, row_end: int) -> str:
    return f"{row_start}-{row_end}"


def build_import_batch_name(row_start: int, row_end: int) -> str:
    if row_start == 1:
        return f"business_csv_first{row_end}_{uuid.uuid4().hex[:12]}"
    return f"business_csv_rows{row_start}_{row_end}_{uuid.uuid4().hex[:12]}"


def build_tags(
    *,
    source_filename: str,
    row_no: int,
    row_start: int,
    row_end: int,
    title: str,
    knowledge_class: str,
    business_line: str,
    service_scope: str | None,
) -> dict:
    scenario_label, intent_label, language_style = infer_scenario_intent(
        title=title,
        content=title,
        tags={
            "knowledge_class": knowledge_class,
            "scenario_label": "process" if knowledge_class == "process" else None,
            "intent_label": "script" if knowledge_class == "script" else None,
            "language_style": "spoken_sales" if knowledge_class == "script" else None,
        },
    )
    return {
        "knowledge_class": knowledge_class,
        "source_filename": source_filename,
        "source_row": row_no,
        "row_scope": format_row_scope(row_start, row_end),
        "dataset_kind": "business_knowledge_csv",
        "business_line_hint": business_line,
        "service_scope_hint": service_scope,
        "scenario_label": scenario_label,
        "intent_label": intent_label,
        "language_style": language_style,
    }


def strip_leading_list_marker(text: str) -> str:
    return re.sub(r"^\s*(?:\d+|[一二三四五六七八九十]+)[\.\)）．、]\s*", "", str(text or "").strip())


def split_numbered_sections(content: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in lines:
        marker = re.match(r"^(\d+[\.\)）]|[一二三四五六七八九十]+[、.])\s*(.*)$", line)
        if marker:
            if current_lines:
                sections.append((current_title or current_lines[0][:40], current_lines))
            first_line = marker.group(2).strip() or strip_leading_list_marker(line) or line
            current_title = first_line
            current_lines = [first_line]
            continue
        current_lines.append(line)
    if current_lines:
        sections.append((current_title or current_lines[0][:40], current_lines))
    result: list[tuple[str, str]] = []
    for section_title, section_lines in sections:
        block = "\n".join(section_lines).strip()
        if block:
            result.append((section_title[:80], block))
    return result


def split_numbered_points(
    content: str,
    *,
    title_map: dict[int, str] | None = None,
    default_title_prefix: str = "要点",
    include_intro_in_first: bool = False,
) -> list[tuple[str, str]]:
    text = content.strip()
    text = re.sub(r"[；;]\s*((?:\d+|[一二三四五六七八九十]+)[\.\)）．、])", r"\n\1", text)
    matches = list(re.finditer(
        r"(?:^|\n)\s*((?:\d+|[一二三四五六七八九十]+)[\.\)）．、])\s*(.*?)(?=(?:\n\s*(?:\d+|[一二三四五六七八九十]+)[\.\)）．、])|\Z)",
        text,
        flags=re.S,
    ))
    chunks: list[tuple[str, str]] = []
    intro = ""
    if include_intro_in_first and matches:
        intro = text[:matches[0].start()].strip()
    for idx, match in enumerate(matches, start=1):
        body = match.group(2)
        block = strip_leading_list_marker(body)
        if idx == 1 and intro:
            block = f"{intro}\n{block}" if block else intro
        if not block:
            continue
        title = (title_map or {}).get(idx, f"{default_title_prefix}{idx}")
        chunks.append((title, block))
    return chunks


def split_formula_example(content: str) -> list[tuple[str, str]]:
    parts = re.split(r"话术示例[:：]", content, maxsplit=1)
    if len(parts) == 2:
        formula = re.sub(r"^公式[:：]\s*", "", parts[0].strip())
        sample = parts[1].strip()
        chunks: list[tuple[str, str]] = []
        if formula:
            chunks.append(("话术公式", formula))
        if sample:
            chunks.append(("话术示例", sample))
        return chunks
    return [("话术内容", content.strip())]


def split_security_points(content: str) -> list[tuple[str, str]]:
    return split_numbered_points(
        content,
        title_map={
            1: "保密协议与长期合作承诺",
            2: "ERP 权限隔离说明",
            3: "译员与员工保密约束",
            4: "长期外企客户与零事故记录",
            5: "客户仍担心时可补签保密协议",
        },
        default_title_prefix="保密回复要点",
    ) or [("保密回复", content.strip())]


def split_capability_points(row_no: int, content: str) -> list[tuple[str, str]]:
    title_map_by_row = {
        8: {
            1: "长期合作客户背书",
            2: "可提供的一体化业务范围",
        },
        11: {
            1: "ERP 自研与长期建设",
            2: "海量语料与术语资源积累",
        },
    }
    return split_numbered_points(
        content,
        title_map=title_map_by_row.get(row_no),
        default_title_prefix="能力要点",
    )


def split_advantage_points(content: str) -> list[tuple[str, str]]:
    points = split_numbered_points(content, default_title_prefix="优势要点")
    result: list[tuple[str, str]] = []
    for idx, (_, block) in enumerate(points, start=1):
        first_line = normalize_text(block.split("\n", 1)[0])
        heading = re.split(r"[:：]", first_line, maxsplit=1)[0].strip(" \t-—:：")
        title = heading[:80] if heading else f"优势要点{idx}"
        result.append((title, block))
    return result


def split_follow_up_points(row_no: int, content: str) -> list[tuple[str, str]]:
    if row_no == 41:
        points = split_numbered_points(
            content,
            title_map={
                1: "KP 基础身份信息",
                2: "需求情况确认",
            },
            default_title_prefix="跟进要点",
        )
        if len(points) >= 2 and len(points[1][1]) < 12:
            merged = f"{points[0][1]}，并同步确认{points[1][1].rstrip('。；;，,')}"
            return [("KP 基础信息与需求情况确认", merged)]
        return points
    title_map_by_row = {
        23: {
            1: "企微邀请留档",
            2: "邮件资料与转介绍请求",
        },
        42: {
            1: "未来需求探询",
            2: "过往需求回溯",
        },
    }
    return split_numbered_points(
        content,
        title_map=title_map_by_row.get(row_no),
        default_title_prefix="跟进要点",
    )


def split_customer_service_issue_points(content: str) -> list[tuple[str, str]]:
    text = normalize_text(content)
    quality_marker = "（若客户说是质量不满意）"
    service_marker = "（若客户说是服务质量差）"
    quality_pos = text.find(quality_marker)
    service_pos = text.find(service_marker)
    if quality_pos == -1 or service_pos == -1 or quality_pos >= service_pos:
        return [("供应商不满意回复", text)]
    intro = text[:quality_pos].strip().lstrip("*")
    quality_block = text[quality_pos + len(quality_marker):service_pos].strip().lstrip("*")
    service_block = text[service_pos + len(service_marker):].strip().lstrip("*")
    chunks: list[tuple[str, str]] = []
    if intro:
        chunks.append(("先问不满意点", intro))
    if quality_block:
        chunks.append(("若客户反馈质量不满", quality_block))
    if service_block:
        chunks.append(("若客户反馈服务不满", service_block))
    return chunks


def split_front_desk_examples(content: str) -> list[tuple[str, str]]:
    text = normalize_text(content)
    note = ""
    note_split = re.split(r"\n\s*\*{3,}\s*", text, maxsplit=1)
    if len(note_split) == 2:
        text, note = note_split
        note = note.strip(" *\n")
    chunks = split_numbered_points(
        text,
        title_map={
            1: "打不通时请前台查人",
            2: "按同事介绍线索请求转接",
            3: "电话断线后请求续接",
            4: "未接到回电时请求转接",
        },
        default_title_prefix="前台协助话术",
    )
    if note:
        chunks.append(("前台追问身份时的补充回答", note))
    return chunks


def split_townhall_follow_up(content: str) -> list[tuple[str, str]]:
    return split_numbered_points(
        content,
        title_map={
            1: "先强调同传案例与经验",
            2: "追问会议频次与形式",
            3: "追问负责部门与联系人",
        },
        default_title_prefix="Townhall 跟进要点",
    )


def split_second_batch_points(row_no: int, content: str) -> list[tuple[str, str]]:
    if row_no == 82:
        return split_customer_service_issue_points(content)
    if row_no == 111:
        return split_front_desk_examples(content)
    if row_no == 124:
        return split_townhall_follow_up(content)
    title_map_by_row = {
        56: {
            1: "确认现有对接销售",
            2: "说明来电目的是重启合作",
            3: "追问最近合作业务",
        },
        57: {
            1: "询问接替者或需求部门",
            2: "请求推荐仍在职同事",
        },
        59: {
            1: "确认当前公司与行业",
            2: "追问当前需求解决方式",
        },
        60: {
            1: "先征求一分钟沟通时间",
            2: "改发邮件供客户后看",
            3: "转微信维持联系",
            4: "确认更合适的回拨时间",
            5: "礼貌结束并稍后再联",
        },
        61: {
            1: "说明介绍来源与长期合作",
            2: "承诺合作后再公开介绍人",
        },
        62: {
            1: "确认原联系人何时在岗",
            2: "说明回访背景与公司能力",
            3: "向新人留资料与邮箱",
            4: "确认原联系人近期需求",
        },
        64: {
            1: "表达感谢",
            2: "询问满意度",
            3: "确认近期需求",
            4: "强调专属团队与词汇积累",
            5: "再次致谢并争取续单",
        },
        66: {
            1: "询问哪个业务部门需求更多",
            2: "确认原联系人并索取新联系人",
        },
        67: {
            1: "询问哪些部门有需求",
            2: "追问市场部具体负责人",
        },
        68: {
            1: "说明双方人员变动并重启联系",
            2: "追问之前未继续合作原因",
        },
        70: {
            1: "说明原销售仍在职",
            2: "解释增派销售的原因",
            3: "明确后续由我负责",
            4: "再次确认原销售并安抚客户",
        },
        72: {
            1: "客户常用简称",
            2: "正式公司名称",
            3: "交大背景与独立发展",
        },
        80: {
            1: "询问对现有供应商的满意度",
            2: "强调我们可替代并做到更好",
            3: "强调 ERP 质量管理优势",
        },
        81: {
            1: "多家供应商属于正常配置",
            2: "我们性价比更高",
            3: "长期客户证明我们的稳定性",
            4: "多一家便于比较与筛选",
            5: "紧急项目时更稳妥",
            6: "一体化服务可覆盖更多需求",
            7: "500 强客户也会配置多家供应商",
            8: "质量与交付会让客户更多选择我们",
        },
        84: {
            1: "强调市场地位与长期客户背书",
            2: "说明历史合作基础可重启",
        },
        86: {
            1: "发邮件补合作项目并拉回印象",
            2: "了解进入供应商备选的方式",
        },
        89: {
            1: "正面回应并列出我们的优势",
            2: "追问现有合作量级与要求",
            3: "追问公关公司线索",
        },
        92: {
            1: "先判断客户为什么反感频繁跟进",
            2: "在方式与时间上做差异化",
            3: "每次切换不同话题",
            4: "必要时从周边联系人切入",
        },
        93: {
            1: "先建立强势第一印象",
            2: "直接说明来意推动客户表态",
            3: "用案例启发并逐步问到人",
        },
        94: {
            1: "向销助补行业案例",
            2: "查航空公司官网",
            3: "向其他翻译公司侧面取样",
            4: "补充航空技术用语",
        },
        96: {
            1: "用同行失败案例提醒客户",
            2: "鼓励客户适度降低质量等级",
            3: "评估我们是否要迎合价格要求",
        },
        99: {
            1: "先加企微或核对邮箱",
            2: "联系其他人找到决策人或部门",
        },
        100: {
            1: "放慢语速继续中文沟通",
            2: "确认完全听不懂时可结束通话",
            3: "系统标记为老外联系人",
        },
    }
    prefix_by_row = {
        56: "跟进要点",
        57: "离职联系人处理要点",
        59: "跟进要点",
        60: "挂断应对要点",
        61: "介绍人话术要点",
        62: "前台转接跟进要点",
        64: "老客户再开发要点",
        66: "联系人拓展要点",
        67: "需求探询要点",
        68: "项目追问要点",
        70: "交接说明要点",
        72: "公司名称说明要点",
        80: "供应商评估要点",
        81: "多供应商优势要点",
        84: "供应商过饱和应对要点",
        86: "推进步骤",
        89: "跟进要点",
        92: "跟进策略要点",
        93: "案例要点",
        94: "开发做法",
        96: "价格异议应对要点",
        99: "跟进步骤",
        100: "处理要点",
    }
    return split_numbered_points(
        content,
        title_map=title_map_by_row.get(row_no),
        default_title_prefix=prefix_by_row.get(row_no, "要点"),
        include_intro_in_first=row_no in {57, 84, 93},
    )


def build_chunks(
    *,
    source_filename: str,
    row_start: int,
    row_end: int,
    row_no: int,
    title: str,
    content: str,
    knowledge_class: str,
) -> list[dict[str, Any]]:
    override = ROW_OVERRIDES.get(row_no, {})
    business_line = override.get("business_line") or infer_business_line(title, content)
    service_scope = override.get("service_scope") or infer_service_scope(title, content, business_line)
    risk_level = risk_level_for_row(row_no, title, content, knowledge_class)
    tags = build_tags(
        source_filename=source_filename,
        row_no=row_no,
        row_start=row_start,
        row_end=row_end,
        title=title,
        knowledge_class=knowledge_class,
        business_line=business_line,
        service_scope=service_scope,
    )
    knowledge_type, chunk_type = infer_chunk_type(knowledge_class)

    raw_chunks: list[tuple[str, str]] = []
    custom_points = split_second_batch_points(row_no, content) if 51 <= row_no <= 150 else []
    if custom_points:
        raw_chunks = custom_points
    elif knowledge_class == "process":
        raw_chunks = split_numbered_sections(content)
    elif row_no in {8, 11}:
        raw_chunks = split_capability_points(row_no, content)
    elif row_no in {24, 25, 26, 27}:
        raw_chunks = split_formula_example(content)
    elif row_no == 49:
        raw_chunks = split_security_points(content)
    elif row_no == 682:
        raw_chunks = split_advantage_points(content)
    elif row_no in {23, 41, 42}:
        raw_chunks = split_follow_up_points(row_no, content)
    else:
        raw_chunks = [(title, content)]

    chunks: list[dict[str, Any]] = []
    for idx, (chunk_title, chunk_content) in enumerate(raw_chunks, start=1):
        chunk_content = normalize_text(chunk_content)
        if len(raw_chunks) > 1:
            min_chunk_length = 2 if knowledge_class == "process" else 4
        else:
            min_chunk_length = 12
        if len(raw_chunks) == 1 and knowledge_class in {"faq", "capability"} and re.search(r"[\d%％]", chunk_content):
            min_chunk_length = 4
        if len(chunk_content) < min_chunk_length:
            continue
        chunk_tags = merge_tags(tags, chunk_index=idx)
        chunks.append(
            {
                "title": f"{title[:80]} · {chunk_title[:80]}" if len(raw_chunks) > 1 else title,
                "content": chunk_content,
                "knowledge_type": knowledge_type,
                "chunk_type": chunk_type,
                "knowledge_class": knowledge_class,
                "business_line": business_line,
                "service_scope": service_scope,
                "risk_level": risk_level,
                "priority": 78 if knowledge_class == "script" else 72 if knowledge_class == "process" else 68,
                "tags": chunk_tags,
            }
        )
    return chunks


def purge_existing(db, *, source_type: str, source_filename: str, row_start: int, row_end: int) -> dict[str, int]:
    doc_count = 0
    chunk_count = 0
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.source_type == source_type).all()
    for doc in docs:
        meta = dict(doc.source_meta or {})
        row_no = meta.get("source_row") or meta.get("row")
        filename = str(meta.get("source_filename") or meta.get("filename") or "").strip()
        if filename == source_filename and isinstance(row_no, int) and row_start <= row_no <= row_end:
            chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.document_id).all()
            for chunk in chunks:
                db.delete(chunk)
                chunk_count += 1
            db.delete(doc)
            doc_count += 1
    db.flush()
    return {"deleted_documents": doc_count, "deleted_chunks": chunk_count}


def apply_chunk_governance(chunk: KnowledgeChunk, *, source_type: str, source_ref: str) -> dict[str, Any]:
    tags = dict(chunk.structured_tags or {})
    quality = score_content_governance(
        title=chunk.title,
        content=chunk.content,
        knowledge_type=chunk.knowledge_type,
        chunk_type=chunk.chunk_type,
        source_type=source_type,
        tags=tags,
        has_source_ref=bool(source_ref),
        metadata={
            "business_line": chunk.business_line,
            "service_scope": chunk.service_scope,
            "customer_tier": chunk.customer_tier,
            "language_pair": chunk.language_pair,
        },
    )
    chunk.library_type = quality["library_type"]
    chunk.allowed_for_generation = bool(quality["allowed_for_generation"])
    chunk.usable_for_reply = bool(quality["usable_for_reply"])
    chunk.publishable = bool(quality["publishable"])
    chunk.topic_clarity_score = Decimal(str(quality["topic_clarity_score"]))
    chunk.completeness_score = Decimal(str(quality["completeness_score"]))
    chunk.reusability_score = Decimal(str(quality["reusability_score"]))
    chunk.evidence_reliability_score = Decimal(str(quality["evidence_reliability_score"]))
    chunk.useful_score = Decimal(str(quality["useful_score"]))
    return quality


def create_document(
    db,
    *,
    source_filename: str,
    source_type: str,
    owner: str,
    import_batch: str,
    row_start: int,
    row_end: int,
    row_no: int,
    title: str,
    original_title: str,
    content: str,
    chunks_payload: list[dict[str, Any]],
) -> tuple[KnowledgeDocument, list[KnowledgeChunk]]:
    primary = chunks_payload[0]
    source_ref = f"{source_filename}:row:{row_no}"
    doc_tags = merge_tags(
        primary["tags"],
        chunk_count=len(chunks_payload),
        source_ref=source_ref,
    )
    document = KnowledgeDocument(
        title=title_for_row(row_no, title),
        knowledge_type=primary["knowledge_type"],
        business_line=primary["business_line"],
        sub_service=None,
        source_type=source_type,
        source_ref=source_ref,
        source_meta={
            "source_filename": source_filename,
            "source_row": row_no,
            "original_title": original_title,
            "normalized_title": title,
            "original_content_length": len(content),
            "row_start": row_start,
            "row_end": row_end,
            "row_limit": row_end - row_start + 1,
            "row_scope": format_row_scope(row_start, row_end),
            "chunk_count": len(chunks_payload),
        },
        status="review",
        owner=owner,
        import_batch=import_batch,
        risk_level=primary["risk_level"],
        review_required=True,
        review_status="in_review",
        library_type=infer_library_type(
            source_type=source_type,
            knowledge_type=primary["knowledge_type"],
            chunk_type=primary["chunk_type"],
            tags=doc_tags,
        ),
        tags=doc_tags,
    )
    db.add(document)
    db.flush()

    chunks: list[KnowledgeChunk] = []
    for idx, payload in enumerate(chunks_payload, start=1):
        retrieval_text = f"{payload['title']}\n{payload['content']}"
        embedding = _optional_embedding_for_import(
            retrieval_text,
            context=f"row={row_no} chunk={idx} title={payload['title']}",
        )
        chunk = KnowledgeChunk(
            document_id=document.document_id,
            chunk_no=idx,
            chunk_type=payload["chunk_type"],
            title=payload["title"][:255],
            content=payload["content"],
            keyword_text=retrieval_text,
            embedding=embedding,
            embedding_provider=settings.EMBEDDING_PROVIDER if embedding else None,
            embedding_model=settings.EMBEDDING_MODEL if embedding else None,
            embedding_dim=len(embedding) if embedding else None,
            priority=payload["priority"],
            retrieval_weight=Decimal("1.000"),
            business_line=payload["business_line"],
            sub_service=None,
            knowledge_type=payload["knowledge_type"],
            language_pair=None,
            service_scope=payload["service_scope"],
            region=None,
            customer_tier=None,
            structured_tags=payload["tags"],
            status="review",
        )
        db.add(chunk)
        db.flush()
        quality = apply_chunk_governance(chunk, source_type=source_type, source_ref=source_ref)
        document.library_type = chunk.library_type
        document.tags = merge_tags(document.tags, library_type=document.library_type)
        if quality["function_fragment"]:
            chunk.structured_tags = merge_tags(chunk.structured_tags, function_fragment=quality["function_fragment"])
        chunks.append(chunk)
    return document, chunks


def run_business_csv_import(
    db,
    *,
    raw: bytes,
    filename: str = DEFAULT_BUSINESS_CSV_FILENAME,
    row_limit: int | None = None,
    start_row: int = DEFAULT_ROW_START,
    end_row: int | None = None,
    source_type: str = DEFAULT_SOURCE_TYPE,
    owner: str = DEFAULT_OWNER,
    import_batch: str | None = None,
    skip_rows: dict[int, str] | None = None,
) -> dict[str, Any]:
    source_filename = str(filename or DEFAULT_BUSINESS_CSV_FILENAME).strip() or DEFAULT_BUSINESS_CSV_FILENAME
    if end_row is None:
        end_row = row_limit if row_limit is not None else DEFAULT_ROW_END
    if start_row < 1 or end_row < start_row:
        raise ValueError(f"invalid_row_range {start_row}-{end_row}")
    import_batch = import_batch or build_import_batch_name(start_row, end_row)
    skip_rows = dict(DEFAULT_SKIP_ROWS if skip_rows is None else skip_rows)
    created_documents = 0
    created_chunks = 0
    skipped: list[dict[str, Any]] = []
    imported: list[dict[str, Any]] = []

    text = raw.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    first_seen_by_fingerprint: dict[str, int] = {}
    for row_no, row in enumerate(rows, start=1):
        title = normalize_text(row[0] if len(row) > 0 else "")
        content = normalize_text(row[1] if len(row) > 1 else "")
        if not title or not content:
            continue
        fingerprint = normalized_fingerprint(title, content)
        first_seen_by_fingerprint.setdefault(fingerprint, row_no)
    purged = purge_existing(
        db,
        source_type=source_type,
        source_filename=source_filename,
        row_start=start_row,
        row_end=end_row,
    )

    for row_no, row in enumerate(rows, start=1):
        if row_no < start_row:
            continue
        if row_no > end_row:
            break
        original_title = normalize_text(row[0] if len(row) > 0 else "")
        content = normalize_text(row[1] if len(row) > 1 else "")
        title = normalize_source_title(row_no, original_title)
        if row_no in skip_rows:
            skipped.append({"row": row_no, "title": original_title, "reason": skip_rows[row_no]})
            continue
        if not title or not content:
            skipped.append({"row": row_no, "title": original_title, "reason": "empty_title_or_content"})
            continue
        fingerprint = normalized_fingerprint(original_title, content)
        first_seen_row = first_seen_by_fingerprint.get(fingerprint, row_no)
        if first_seen_row != row_no:
            skipped.append({"row": row_no, "title": original_title, "reason": f"duplicate_of_row_{first_seen_row}"})
            continue
        knowledge_class = infer_knowledge_class(row_no, title, content)
        chunks_payload = build_chunks(
            source_filename=source_filename,
            row_start=start_row,
            row_end=end_row,
            row_no=row_no,
            title=title,
            content=content,
            knowledge_class=knowledge_class,
        )
        if not chunks_payload:
            skipped.append({"row": row_no, "title": title, "reason": "no_valid_chunks"})
            continue
        document, chunks = create_document(
            db,
            source_filename=source_filename,
            source_type=source_type,
            owner=owner,
            import_batch=import_batch,
            row_start=start_row,
            row_end=end_row,
            row_no=row_no,
            title=title,
            original_title=original_title,
            content=content,
            chunks_payload=chunks_payload,
        )
        created_documents += 1
        created_chunks += len(chunks)
        imported.append(
            {
                "row": row_no,
                "title": title,
                "document_id": str(document.document_id),
                "knowledge_class": knowledge_class,
                "business_line": chunks_payload[0]["business_line"],
                "chunk_count": len(chunks),
            }
        )

    db.commit()
    return {
        "status": "success",
        "source_file": source_filename,
        "import_batch": import_batch,
        "start_row": start_row,
        "end_row": end_row,
        "created_documents": created_documents,
        "created_chunks": created_chunks,
        "skipped_count": len(skipped),
        "purged": purged,
        "imported": imported,
        "skipped": skipped,
    }


def dump_business_csv_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
