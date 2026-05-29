"""
搜索与匹配核心 v2.0
演示模式：chemicals.json + suppliers.json（本地虚拟数据）
API 模式：企查查开放搜索（任意产品关键词）

筛选字段对照企查查字段：
  provinces     ← Province
  tiers         ← Province 推算
  status_active ← Status
  company_type  ← _role（经营范围分类）
  min_capital   ← registered_capital_wan（RegistCapi 解析）
  est_after     ← established（StartDate 解析）
  only_hazmat   ← _business_scope 含"危险化学品"
  scope_keyword ← _business_scope 文本匹配
  min_score     ← 计算后过滤
"""
from __future__ import annotations
import re
import json
from pathlib import Path
from pypinyin import lazy_pinyin, Style
from rapidfuzz import fuzz, process

from utils.scorer import score_supplier, DEFAULT_WEIGHTS, TIERS

_DATA = Path(__file__).parent.parent / "data"

with open(_DATA / "chemicals.json", encoding="utf-8") as f:
    CHEMICALS_RAW = json.load(f)["chemicals"]

with open(_DATA / "suppliers.json", encoding="utf-8") as f:
    SUPPLIERS_RAW = json.load(f)["suppliers"]

CAS_PATTERN = re.compile(r"^\d{2,7}-\d{2}-\d$")
TIER1 = TIERS.get("tier1", {}).get("provinces", [])
TIER2 = TIERS.get("tier2", {}).get("provinces", [])
TIER3 = TIERS.get("tier3", {}).get("provinces", [])


def _py(text):  return "".join(lazy_pinyin(text, style=Style.NORMAL))
def _pf(text):  return "".join(lazy_pinyin(text, style=Style.FIRST_LETTER))


CHEMICALS_INDEX = [
    {**c,
     "_s": " ".join(filter(None, [
         c.get("primaryName",""), c.get("englishName",""),
         c.get("cas",""), c.get("formula",""),
         _py(c.get("primaryName","")), _pf(c.get("primaryName","")),
         *c.get("aliases",[]),
     ]))}
    for c in CHEMICALS_RAW
]


def search_chemical(query: str) -> dict | None:
    q = (query or "").strip()
    if not q:
        return None
    if CAS_PATTERN.match(q):
        for c in CHEMICALS_RAW:
            if c.get("cas") == q:
                return c
        return None
    ql = q.lower()
    for c in CHEMICALS_INDEX:
        name = c.get("primaryName","").lower()
        eng  = c.get("englishName","").lower()
        if ql in (name, eng) or name.startswith(ql) or eng.startswith(ql):
            return c
    targets = [c["_s"] for c in CHEMICALS_INDEX]
    res = process.extract(q, targets, scorer=fuzz.WRatio, limit=3)
    if res and res[0][1] >= 65:
        return CHEMICALS_RAW[targets.index(res[0][0])]
    return None


def get_chemical_suggestions(query: str, limit: int = 6) -> list[str]:
    q = (query or "").strip()
    if len(q) < 1:
        return []
    targets = [c["_s"] for c in CHEMICALS_INDEX]
    res = process.extract(q, targets, scorer=fuzz.WRatio, limit=limit)
    return [
        CHEMICALS_RAW[targets.index(m)]["primaryName"]
        for m, score, _ in res if score >= 40
    ]


def _province_tier(province: str) -> int:
    if province in TIER1: return 1
    if province in TIER2: return 2
    return 3


def _apply_filters(supplier: dict, filters: dict, score: float = 0) -> bool:
    """返回 True 表示保留该供应商。所有条件取 AND。"""
    f = filters or {}
    province = supplier.get("province", "")

    # 省份筛选
    if f.get("provinces") and province not in f["provinces"]:
        return False

    # 圈层筛选（来自企查查 Province 推算）
    if f.get("tiers"):
        if _province_tier(province) not in f["tiers"]:
            return False

    # 经营状态（来自企查查 Status）
    if f.get("status_active"):
        status = supplier.get("reg_status", "存续") or "存续"
        if status not in ("存续", "在业", ""):
            return False

    # 企业类型（来自经营范围分类）
    ctype = f.get("company_type", "all")
    if ctype != "all":
        role = supplier.get("_role", "unknown")
        if role != ctype:
            # "manufacturer" 也接受 "both"
            if not (ctype == "manufacturer" and role == "both"):
                return False

    # 最低注册资本（来自企查查 RegistCapi）
    min_cap = f.get("min_capital", 0) or 0
    if min_cap > 0:
        cap = supplier.get("registered_capital_wan", 0) or 0
        if cap < min_cap:
            return False

    # 成立年份（来自企查查 StartDate）
    est_after = f.get("est_after", 1980) or 1980
    est = supplier.get("established", 0) or 0
    if est_after > 1980 and est > 0 and est < est_after:
        return False

    # 危化品资质（来自经营范围关键词）
    if f.get("only_hazmat"):
        lic = supplier.get("licenses", {})
        scope = supplier.get("_business_scope", "")
        if not (lic.get("hazardous_chemicals") or lic.get("hazmat_business")
                or "危险化学品" in scope):
            return False

    # 经营范围额外关键词（来自企查查 Scope 文本）
    kw = (f.get("scope_keyword") or "").strip()
    if kw:
        scope = supplier.get("_business_scope", "") or " ".join(supplier.get("products", []))
        if kw not in scope:
            return False

    # 最低评分门槛（计算后过滤）
    min_score = f.get("min_score", 0) or 0
    if min_score > 0 and score < min_score:
        return False

    return True


def match_suppliers(
    query: str = "",
    suppliers: list[dict] | None = None,
    filters: dict | None = None,
    weights: dict | None = None,
    use_api: bool | None = None,
) -> tuple[dict | None, list[dict]]:
    """
    主匹配入口。
    use_api=None  → 自动判断（配置了企查查 Key 就用 API）
    use_api=True  → 强制 API 模式
    use_api=False → 强制演示数据
    """
    if use_api is None:
        from utils.qcc_client import is_configured
        use_api = is_configured()

    if use_api and query:
        from utils.open_search import open_search
        result = open_search(query=query, filters=filters, weights=weights)
        # API 结果也要过筛选器（open_search 已做基础过滤，这里做精细过滤）
        final = [s for s in result["suppliers"] if _apply_filters(s, filters, s.get("score", 0))]
        return None, final

    # ── 演示模式 ──────────────────────────────────────────────────────
    src = suppliers if suppliers is not None else SUPPLIERS_RAW
    w   = weights or DEFAULT_WEIGHTS
    f   = filters or {}

    chemical = search_chemical(query) if query else None

    # 先评分再过滤（因为 min_score 需要评分结果）
    scored = []
    for s in src:
        scored_s = score_supplier(s, chemical, w, query=query)
        if _apply_filters(scored_s, f, scored_s.get("score", 0)):
            scored.append(scored_s)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return chemical, scored
