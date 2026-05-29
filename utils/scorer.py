"""
SABIC 供应商全量化评分算法  v2.0
四个维度全部基于客观可量化指标，去除主观评分（历史合作、产品匹配度）

维度（默认权重）：
  ① 地理位置      geography   30%  — 省份圈层 + km 距离（纯数字）
  ② 企业规模      scale       30%  — 注册资本 + 成立年限（纯数字）
  ③ 合规与资质    compliance  25%  — 经营状态 + 角色分类 + 资质标志（布尔）
  ④ 经营相关度    relevance   15%  — 经营范围文本与查询词的匹配得分（算法）

字段来源：全部来自企查查 API 或可从工商信息推导，无主观填写
"""
from __future__ import annotations
import re
import json
from pathlib import Path
from datetime import datetime

_DATA = Path(__file__).parent.parent / "data"
with open(_DATA / "regions.json", encoding="utf-8") as f:
    REGIONS = json.load(f)

TIERS          = REGIONS["tiers"]
PROVINCE_COORDS = REGIONS.get("provinceCoords", {})  # {省名: {lng,lat,distance_km}}

DEFAULT_WEIGHTS = {
    "geography":  0.30,
    "scale":      0.30,
    "compliance": 0.25,
    "relevance":  0.15,
}

# 同义词表：从 data/synonyms.json 动态加载（由 categories.json 生成）
try:
    with open(_DATA / "synonyms.json", encoding="utf-8") as _sf:
        _SYNONYMS: dict[str, list[str]] = json.load(_sf)
except Exception:
    _SYNONYMS = {}  # 文件不存在时降级


# ════════════════════════════════════════════════════════════════════
# ① 地理位置评分  (0-100)  ← 纯量化
# ════════════════════════════════════════════════════════════════════
def score_geography(supplier: dict) -> float:
    """
    来源字段：province（企查查 Province 字段）
    计算方式：省份圈层基础分 + 距离上海 km 奖励分，全部数字计算
    """
    province = supplier.get("province", "")
    tier1 = TIERS.get("tier1", {}).get("provinces", [])
    tier2 = TIERS.get("tier2", {}).get("provinces", [])

    # 圈层基础分（70% 权重）
    if province in tier1:
        tier_score = 100.0  # 沪苏浙皖
    elif province in tier2:
        tier_score = 55.0   # 鲁粤鄂豫闽等
    else:
        tier_score = 20.0   # 其余

    # 距离奖励（30% 权重）— km 数越小奖励越高
    distance = (
        supplier.get("logistics", {}).get("distance_km_to_shanghai")
        or PROVINCE_COORDS.get(province, {}).get("distance_km", 9999)
    )
    if distance < 100:
        dist_score = 100.0
    elif distance < 300:
        dist_score = 80.0
    elif distance < 600:
        dist_score = 60.0
    elif distance < 1000:
        dist_score = 35.0
    else:
        dist_score = 10.0

    return round(0.70 * tier_score + 0.30 * dist_score, 1)


# ════════════════════════════════════════════════════════════════════
# ② 企业规模评分  (0-100)  ← 纯量化
# ════════════════════════════════════════════════════════════════════
def score_scale(supplier: dict) -> float:
    """
    来源字段：
      registered_capital_wan — 企查查 RegistCapi 解析（万元）
      established            — 企查查 StartDate 解析（年份）
    计算方式：注册资本分 × 65% + 成立年限分 × 35%
    """
    cap  = supplier.get("registered_capital_wan", 0) or 0
    year = supplier.get("established", 0) or 0
    age  = max(0, datetime.now().year - year) if year else 0

    # 注册资本分（对数尺度）
    if cap >= 100_000:    # ≥10亿
        cap_score = 100.0
    elif cap >= 50_000:   # ≥5亿
        cap_score = 90.0
    elif cap >= 10_000:   # ≥1亿
        cap_score = 78.0
    elif cap >= 5_000:    # ≥5000万
        cap_score = 64.0
    elif cap >= 1_000:    # ≥1000万
        cap_score = 50.0
    elif cap >= 200:      # ≥200万
        cap_score = 36.0
    elif cap > 0:
        cap_score = 22.0
    else:
        cap_score = 30.0  # 未知 → 中性

    # 成立年限分
    if age >= 20:
        age_score = 100.0
    elif age >= 15:
        age_score = 85.0
    elif age >= 10:
        age_score = 70.0
    elif age >= 5:
        age_score = 50.0
    elif age >= 2:
        age_score = 30.0
    elif age > 0:
        age_score = 10.0
    else:
        age_score = 30.0  # 未知 → 中性

    return round(0.65 * cap_score + 0.35 * age_score, 1)


# ════════════════════════════════════════════════════════════════════
# ③ 合规与资质评分  (0-100)  ← 布尔 + 分类标志
# ════════════════════════════════════════════════════════════════════
def score_compliance(supplier: dict) -> float:
    """
    来源字段（全部可从企查查获取或推导）：
      reg_status            — 企查查 Status（存续/注销/吊销）
      _role                 — 经营范围文本分类（manufacturer/trader/both）
      licenses.hazardous_chemicals — 经营范围含"危险化学品"关键词
      licenses.vat_general  — 注册资本>500万一般可认定；精确需单独接口
      chemical_park         — 地址含"化工区/化工园/化工园区"
    得分构成：
      经营状态有效  40 分
      经营角色      0-25 分（制造商25 / 制造+贸易20 / 贸易5 / 未知15）
      危化品资质    20 分
      增值税纳税人  10 分
      化工园区       5 分
    """
    score = 0.0

    # 经营状态（40分）
    status = supplier.get("reg_status", "存续") or "存续"
    if status in ("存续", "在业", ""):
        score += 40

    # 企业角色分类（25分）
    role = supplier.get("_role", "unknown")
    role_map = {"manufacturer": 25, "both": 20, "trader": 5, "unknown": 15}
    score += role_map.get(role, 15)

    # 危险化学品资质（20分）— 来自经营范围关键词或许可证字段
    lic = supplier.get("licenses", {})
    if lic.get("hazardous_chemicals") or lic.get("hazmat_business"):
        score += 20

    # 增值税一般纳税人（10分）
    if lic.get("vat_general"):
        score += 10

    # 化工园区（5分）
    if supplier.get("chemical_park"):
        score += 5

    return min(score, 100.0)


# ════════════════════════════════════════════════════════════════════
# ④ 经营相关度评分  (0-100)  ← 文本算法
# ════════════════════════════════════════════════════════════════════
def score_relevance(supplier: dict, query: str = "") -> float:
    """
    来源字段：
      _business_scope — 企查查 Scope 字段（经营范围全文）
      products        — 本地演示数据的产品列表
    计算方式：
      关键词在经营范围中的出现次数 → 基础分
      同义词命中 → 加分
      制造商角色 → 加分
      产品列表匹配 → 加分
    完全算法化，无主观判断
    """
    if not query:
        return 50.0  # 无查询词时给中性分

    scope = (
        supplier.get("_business_scope", "")
        or " ".join(supplier.get("products", []))
        or " ".join(supplier.get("main_categories", []))
    )

    if not scope:
        # 无经营范围文本时，只能靠产品列表
        prods = supplier.get("products", [])
        cats  = supplier.get("main_categories", [])
        if query in prods or query in cats:
            return 65.0
        if any(query in p for p in prods + cats):
            return 45.0
        return 20.0

    # ── 主词命中次数 ───────────────────────────────────────────────
    count = scope.count(query)

    # ── 同义词命中 ─────────────────────────────────────────────────
    syn_hits = 0
    for syn in _SYNONYMS.get(query, []):
        syn_hits += scope.count(syn)

    total_hits = count + syn_hits * 0.5  # 同义词权重 50%

    if total_hits >= 4:
        base = 92.0
    elif total_hits >= 3:
        base = 82.0
    elif total_hits >= 2:
        base = 70.0
    elif total_hits >= 1:
        base = 58.0
    else:
        # 字符级部分匹配（经营范围包含查询词子串）
        if any(char in scope for char in query if len(query) >= 2):
            base = 25.0
        else:
            base = 8.0

    # ── 制造商加成 ─────────────────────────────────────────────────
    role   = supplier.get("_role", "unknown")
    bonus  = {"manufacturer": 8, "both": 5, "trader": 0, "unknown": 3}.get(role, 3)

    return min(base + bonus, 100.0)


# ════════════════════════════════════════════════════════════════════
# 总分计算
# ════════════════════════════════════════════════════════════════════
def score_supplier(
    supplier: dict,
    chemical: dict | None = None,  # 保留参数兼容性
    weights: dict | None = None,
    query: str = "",
) -> dict:
    """
    计算供应商综合得分。
    所有维度均为客观量化指标，公式透明可解释。
    chemical 参数保留供演示模式兼容；实际用 query 字符串计算相关度。
    """
    w = weights or DEFAULT_WEIGHTS

    # 如果调用方传了 chemical 对象，提取其名称用于相关度计算
    if chemical and not query:
        query = chemical.get("primaryName", "") or ""

    dims = {
        "geography":  score_geography(supplier),
        "scale":      score_scale(supplier),
        "compliance": score_compliance(supplier),
        "relevance":  score_relevance(supplier, query),
    }

    # 兼容旧版五维格式（UI 里可能还引用 product/history）
    dims["product"]  = dims["relevance"]   # 向后兼容
    dims["history"]  = dims["compliance"]  # 向后兼容

    total = sum(dims[k] * w.get(k, 0) for k in ["geography", "scale", "compliance", "relevance"])

    # 圈层标签
    province = supplier.get("province", "")
    tier1 = TIERS.get("tier1", {}).get("provinces", [])
    tier2 = TIERS.get("tier2", {}).get("provinces", [])
    tier  = 1 if province in tier1 else (2 if province in tier2 else 3)

    return {
        **supplier,
        "score":      round(total, 1),
        "dimensions": dims,
        "_tier":      tier,
    }


def get_tier_label(province: str) -> str:
    t1 = TIERS.get("tier1", {}).get("provinces", [])
    t2 = TIERS.get("tier2", {}).get("provinces", [])
    if province in t1:
        return "一级(华东)"
    if province in t2:
        return "二级"
    return "三级"
