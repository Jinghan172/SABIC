"""
开放产品搜索引擎（企查查版）
突破 chemicals.json 的 15 种化学品限制，支持任意产品关键词
"""
from __future__ import annotations

import re
import time
import json
import logging
from pathlib import Path

from utils.qcc_client import (
    search_companies, get_company_detail,
    classify_role, is_relevant, is_configured,
)
from utils.scorer import score_supplier, DEFAULT_WEIGHTS

logger = logging.getLogger(__name__)

_DATA = Path(__file__).parent.parent / "data"
with open(_DATA / "regions.json", encoding="utf-8") as f:
    _REGIONS = json.load(f)

# 省份距离表
_DIST = {
    name: info.get("distance_km", 1000)
    for name, info in _REGIONS.get("provinceCoords", {}).items()
    if isinstance(info, dict)
}

# 企查查省份字段已是全称（如"上海"），直接用
_PROVINCE_FULL = {
    "京":"北京","津":"天津","沪":"上海","渝":"重庆",
    "冀":"河北","豫":"河南","云":"云南","辽":"辽宁",
    "黑":"黑龙江","湘":"湖南","皖":"安徽","鲁":"山东",
    "新":"新疆","苏":"江苏","浙":"浙江","赣":"江西",
    "鄂":"湖北","桂":"广西","甘":"甘肃","晋":"山西",
    "蒙":"内蒙古","陕":"陕西","吉":"吉林","闽":"福建",
    "贵":"贵州","粤":"广东","川":"四川","青":"青海",
    "琼":"海南","宁":"宁夏","藏":"西藏",
}


def _norm_province(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    # 企查查直接返回省份全称
    if len(raw) >= 2:
        return _PROVINCE_FULL.get(raw[:1], raw)
    return raw


def _parse_capital(s: str) -> float:
    if not s:
        return 0.0
    m = re.search(r"([\d.]+)\s*([万亿]?)", s)
    if not m:
        return 0.0
    val = float(m.group(1))
    return val * 10000 if m.group(2) == "亿" else val


def _parse_year(date_str: str) -> int:
    """'2010-01-01' -> 2010"""
    if not date_str:
        return 2010
    try:
        return int(str(date_str)[:4])
    except Exception:
        return 2010


# ══════════════════════════════════════════════════════════════════════
# 企查查字段 → 系统 Supplier 格式
# ══════════════════════════════════════════════════════════════════════

def qcc_to_supplier(detail: dict, query: str = "") -> dict:
    """
    企查查 ECIV4/GetBasicDetailsByName 或 FuzzySearch/GetList 返回字段
    映射成系统 Supplier 对象，可直接传入 score_supplier()。

    企查查关键字段：
      Name          企业全称
      OperName      法定代表人
      Status        经营状态（存续/注销等）
      Province      所在省份
      Address       注册地址
      StartDate     成立日期  "2010-01-01"
      RegistCapi    注册资本  "1000万人民币"
      No / CreditCode  统一社会信用代码
      Scope         经营范围（详情接口）
      BusinessScope 经营范围（搜索结果字段，部分版本）
    """
    # 兼容搜索结果和详情两种格式
    scope    = detail.get("Scope") or detail.get("BusinessScope") or ""
    province = _norm_province(detail.get("Province", ""))
    role     = classify_role(scope)

    # 从经营范围粗提产品列表（仅用于 UI 展示）
    products = _extract_products(scope, query)

    return {
        "id":          f"QCC-{detail.get('KeyNo') or detail.get('No', str(time.time()))}",
        "name":        detail.get("Name", ""),
        "shortName":   detail.get("Name", "")[:8],
        "creditCode":  detail.get("No") or detail.get("CreditCode", ""),
        "province":    province,
        "city":        "",
        "address":     detail.get("Address", ""),
        "established": _parse_year(detail.get("StartDate", "")),
        "employees":   0,
        "reg_status":  detail.get("Status", ""),

        # 供应能力（企查查不提供，留默认）
        "products":            products,
        "main_categories":     [query] if query else [],
        "annual_capacity_ton": 0,
        "min_order_ton":       1,
        "price_range_per_ton": [0, 0],
        "chemical_park":       False,

        "registered_capital_wan": _parse_capital(detail.get("RegistCapi", "")),

        # 资质（企查查基础接口不直接返回许可证）
        "licenses": {
            "hazardous_chemicals": "危险化学品" in scope or "危化品" in scope,
            "safety_production":   False,
            "vat_general":         True,
            "gb_certified":        False,
        },

        "logistics": {
            "distance_km_to_shanghai": _DIST.get(province, 1000),
            "own_fleet":        False,
            "hazmat_transport": False,
        },

        "sabic_history": {
            "is_partner": False,
            "years":      0,
            "rating":     "",
        },

        # 元数据
        "_source":         "qichacha",
        "_role":           role,
        "_business_scope": scope,
        "_fetched_at":     time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _extract_products(scope: str, query: str) -> list[str]:
    """从经营范围简单提取产品列表"""
    if not scope:
        return [query] if query else []
    parts = re.split(r"[；;，,。\n]", scope)
    result = []
    for p in parts:
        p = p.strip()
        if 2 <= len(p) <= 20 and not any(p.startswith(w) for w in ["销售","经营","从事","提供"]):
            result.append(p)
    out = result[:6]
    if query and query not in out:
        out.insert(0, query)
    return out


# ══════════════════════════════════════════════════════════════════════
# 开放搜索主入口
# ══════════════════════════════════════════════════════════════════════

def open_search(
    query: str,
    filters: dict | None = None,
    weights: dict | None = None,
    page: int = 1,
    include_traders: bool = False,
) -> dict:
    """
    开放产品搜索：输入任意产品关键词，返回评分排序的供应商列表。

    返回：
    {
        "total":     int,    企查查总命中数
        "displayed": int,    本次实际返回数量
        "suppliers": list,   已评分排序的供应商
        "source":    str,    "qichacha"
    }
    """
    if not query:
        return {"total": 0, "displayed": 0, "suppliers": [], "source": "demo"}

    f = filters or {}
    w = weights or DEFAULT_WEIGHTS

    # 搜索关键词：短词追加"制造"提高精准度
    search_kw = f"{query}制造" if len(query) <= 6 else query
    raw = search_companies(search_kw, page=page, page_size=5)

    # 降级：搜不到则去掉"制造"重试
    if not raw["items"]:
        raw = search_companies(query, page=page, page_size=5)

    total      = raw["total"]
    candidates = raw["items"]

    # ── 快速过滤（用搜索结果字段，不消耗详情额度）─────────────────────
    filtered = []
    for c in candidates:
        scope = c.get("Scope") or c.get("BusinessScope") or ""

        # 经营范围包含查询词（宽松：没有 scope 的直接通过，详情里再判断）
        if scope and not is_relevant(scope, query):
            continue

        # 仅制造商（默认）
        role = classify_role(scope)
        if not include_traders and role == "trader":
            continue

        # 经营状态
        status = c.get("Status", "")
        if status and status not in ("存续", "在业", ""):
            continue

        # 省份筛选
        if f.get("provinces"):
            prov = _norm_province(c.get("Province", ""))
            if prov not in f["provinces"]:
                continue

        filtered.append(c)

    if not filtered:
        return {"total": total, "displayed": 0, "suppliers": [], "source": "qichacha"}

    # ── 批量获取详情（缓存命中不消耗额度）────────────────────────────
    suppliers = []
    for c in filtered:
        name   = c.get("Name", "")
        detail = get_company_detail(name) if name else None
        if not detail:
            detail = c  # 降级：用搜索结果字段
        suppliers.append(qcc_to_supplier(detail, query))

    # ── 评分排序 ─────────────────────────────────────────────────────
    virtual_chem = {"id": query, "category": query, "primaryName": query}
    scored = []
    for s in suppliers:
        s["main_categories"] = list(set(s.get("main_categories", []) + [query]))
        if query in " ".join(s.get("products", [])):
            s["products"] = list(set(s.get("products", []) + [query]))
        scored.append(score_supplier(s, virtual_chem, w))

    scored.sort(key=lambda x: x["score"], reverse=True)

    return {
        "total":     total,
        "displayed": len(scored),
        "suppliers": scored,
        "source":    "qichacha",
    }
