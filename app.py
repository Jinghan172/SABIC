"""
SABIC 上海在线寻源系统 — Python / Streamlit 版
运行方式: streamlit run app.py
"""
from pathlib import Path as _Path
from dotenv import load_dotenv as _load
_load(_Path(__file__).parent / ".env.local", override=False)

import json
import re
from pathlib import Path
import streamlit as st
import pandas as pd

from utils.matcher import match_suppliers, get_chemical_suggestions, SUPPLIERS_RAW
from utils.scorer import DEFAULT_WEIGHTS
from utils.exporter import export_excel
from components.charts import (
    radar_chart, bar_chart, bubble_chart,
    parallel_chart, heatmap_chart, compare_dataframe, china_map,
)


def _number_value(value) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _highlight_row_max(row):
    values = [_number_value(v) for v in row.values if v not in ("—", "")]
    values = [v for v in values if v is not None]
    if not values:
        return ["" for _ in row.values]

    max_value = max(values)
    return [
        "background-color:#f0faf4;color:#0E8C3A;font-weight:bold"
        if _number_value(v) == max_value else ""
        for v in row.values
    ]


APP_DIR = Path(__file__).resolve().parent

# ── 页面配置 ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SABIC 寻源系统",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局样式注入 ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* Hero 顶部横幅 */
.sabic-hero {
    background: linear-gradient(135deg,#0a1628 0%,#0f1f38 60%,#0a1628 100%);
    border-bottom: 2px solid #0E8C3A;
    padding: 28px 32px 22px;
    border-radius: 0 0 12px 12px;
    margin: -1rem -1rem 1rem;
    position: relative;
}
.sabic-hero::before {
    content:'';
    position:absolute;inset:0;border-radius:0 0 12px 12px;
    background:repeating-linear-gradient(0deg,transparent,transparent 31px,
        rgba(255,255,255,0.02) 31px,rgba(255,255,255,0.02) 32px),
        repeating-linear-gradient(90deg,transparent,transparent 31px,
        rgba(255,255,255,0.02) 31px,rgba(255,255,255,0.02) 32px);
    pointer-events:none;
}
.hero-badge {
    display:inline-flex;align-items:center;gap:6px;
    padding:3px 12px;border-radius:20px;
    background:rgba(14,140,58,.18);border:1px solid rgba(14,140,58,.4);
    font-size:11px;font-weight:600;letter-spacing:.08em;
    text-transform:uppercase;color:#5eead4;margin-bottom:10px;
}
.hero-title {
    font-size:26px;font-weight:700;color:#fff;margin:0 0 4px;
    letter-spacing:.4px;
}
.hero-sub { font-size:13px;color:rgba(255,255,255,.45);margin-bottom:18px; }
.hero-stats { display:flex;gap:28px;border-top:1px solid rgba(255,255,255,.07);
    padding-top:16px;margin-top:4px; }
.hero-stat-val { font-size:22px;font-weight:700;color:#fff;line-height:1; }
.hero-stat-val.g { color:#27a84f; }
.hero-stat-val.b { color:#60a5fa; }
.hero-stat-val.t { color:#34d399; }
.hero-stat-lbl { font-size:10px;color:rgba(255,255,255,.38);
    text-transform:uppercase;letter-spacing:.06em;margin-top:3px; }

/* API 状态条 */
.api-bar {
    display:flex;align-items:center;gap:10px;flex-wrap:wrap;
    padding:8px 14px;background:#fff;border:1px solid #e2e8f0;
    border-radius:8px;margin-bottom:12px;font-size:12px;
}
.api-lbl { font-weight:600;text-transform:uppercase;
    letter-spacing:.06em;color:#9ba8bb;margin-right:4px; }
.api-chip {
    display:inline-flex;align-items:center;gap:5px;
    padding:3px 10px;border-radius:20px;font-size:11px;font-weight:500;
    border:1px solid;cursor:default;
}
.api-chip.demo { background:rgba(245,158,11,.08);
    border-color:rgba(245,158,11,.3);color:#d97706; }
.api-chip.off { background:rgba(156,163,175,.08);
    border-color:rgba(156,163,175,.25);color:#9ca3af; }
.dot { width:5px;height:5px;border-radius:50%;background:currentColor;
    display:inline-block; }

/* 供应商卡片 */
.sup-card {
    background:#fff;border:1px solid #e2e8f0;border-radius:10px;
    padding:12px 14px;margin-bottom:8px;cursor:pointer;
    transition:all .2s;position:relative;overflow:hidden;
}
.sup-card:hover { box-shadow:0 4px 12px rgba(0,0,0,.08);
    border-color:rgba(14,140,58,.25);transform:translateY(-1px); }
.sup-card-selected { border-color:rgba(14,140,58,.4)!important;
    background:#f0faf4!important; }
.sup-rank {
    display:inline-flex;align-items:center;justify-content:center;
    width:26px;height:26px;border-radius:6px;
    background:linear-gradient(135deg,#0E8C3A,#27a84f);
    color:#fff;font-weight:700;font-size:12px;flex-shrink:0;
}
.sup-name { font-weight:600;font-size:13px;color:#1a2233; }
.sup-meta { font-size:11px;color:#5a6780; }
.score-high { color:#059669;font-weight:700; }
.score-mid  { color:#d97706;font-weight:700; }
.score-low  { color:#dc2626;font-weight:700; }
.tier-t1 { background:rgba(14,140,58,.1);color:#0E8C3A;
    border:1px solid rgba(14,140,58,.2);padding:1px 7px;
    border-radius:4px;font-size:10px;font-weight:600; }
.tier-t2 { background:rgba(59,130,246,.1);color:#3b82f6;
    border:1px solid rgba(59,130,246,.2);padding:1px 7px;
    border-radius:4px;font-size:10px;font-weight:600; }
.tier-t3 { background:rgba(139,92,246,.1);color:#7c3aed;
    border:1px solid rgba(139,92,246,.2);padding:1px 7px;
    border-radius:4px;font-size:10px;font-weight:600; }

/* 移除 Streamlit 默认上方空白 */
.block-container { padding-top: 0.5rem !important; }

/* 页脚 */
.sabic-footer {
    text-align:center;color:#9ba8bb;font-size:11px;
    padding:16px 0 8px;border-top:1px solid #e2e8f0;margin-top:24px;
}
</style>
""", unsafe_allow_html=True)

# ── 状态初始化 ────────────────────────────────────────────────────────
def _init():
    defaults = {
        "query": "",
        "filters": {
            # ── 地域 ──────────────────────────
            "provinces":     [],        # 省份多选
            "tiers":         [],        # 圈层: [1]/[2]/[3] 或空(不限)
            # ── 企业基本信息（来自企查查）──────
            "status_active": True,      # 仅经营状态"存续/在业"
            "company_type":  "all",     # manufacturer/trader/both/all
            "min_capital":   0,         # 最低注册资本（万元）
            "est_after":     1990,      # 成立年份 ≥
            # ── 资质 ──────────────────────────
            "only_hazmat":   False,     # 仅含危化品经营资质
            # ── 关键词过滤 ────────────────────
            "scope_keyword": "",        # 经营范围额外包含词
            # ── 评分门槛 ──────────────────────
            "min_score":     0,         # 最低综合评分
        },
        "weights": dict(DEFAULT_WEIGHTS),
        "selected_ids": [],
        "active_supplier": None,
        "custom_suppliers": [],
        "use_api": False,
        "chart_tab": "radar",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()

# ── 计算匹配结果（带缓存） ────────────────────────────────────────────
all_suppliers = SUPPLIERS_RAW + st.session_state.custom_suppliers
chemical, results = match_suppliers(
    query=st.session_state.query,
    suppliers=all_suppliers,
    filters=st.session_state.filters,
    weights=st.session_state.weights,
    use_api=st.session_state.get("use_api", False),
)

sel_ids = st.session_state.selected_ids
compare_suppliers = (
    [s for s in results if s["id"] in sel_ids] if sel_ids
    else results[:5]
)

# 统计
tier1_count   = sum(1 for s in results if s.get("_tier") == 1)
partner_count = sum(1 for s in results if s.get("sabic_history", {}).get("is_partner"))
hazmat_count  = sum(1 for s in results if
    s.get("licenses", {}).get("hazardous_chemicals") or
    s.get("licenses", {}).get("hazmat_business"))
avg_score = (
    round(sum(s.get("score", 0) for s in results) / len(results), 1)
    if results else "—"
)

# ═══════════════════════════════════════════════════════════════════════
# Hero 顶部
# ═══════════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="sabic-hero">
  <div class="hero-badge">⬤&nbsp;&nbsp;SABIC Shanghai · 寻源系统</div>
  <div class="hero-title">化工原材料供应商智能匹配</div>
  <div class="hero-sub">基地：上海浦东 · 覆盖 {len(all_suppliers)} 家国内供应商 · 四维量化评分算法</div>
  <div class="hero-stats">
    <div class="hero-stat">
      <div class="hero-stat-val g">{len(results)}</div>
      <div class="hero-stat-lbl">当前匹配</div>
    </div>
    <div class="hero-stat">
      <div class="hero-stat-val b">{tier1_count}</div>
      <div class="hero-stat-lbl">华东一级</div>
    </div>
    <div class="hero-stat">
      <div class="hero-stat-val t">{partner_count}</div>
      <div class="hero-stat-lbl">SABIC 合作</div>
    </div>
    <div class="hero-stat">
      <div class="hero-stat-val">{avg_score}</div>
      <div class="hero-stat-lbl">平均评分</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════
# 侧边栏：搜索 + 筛选 + 权重
# ═══════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🔍 搜索原材料")
    query_input = st.text_input(
        "输入名称、CAS 号或拼音",
        value=st.session_state.query,
        placeholder="例：聚乙烯 / 80-05-7 / PE",
        label_visibility="collapsed",
    )
    if query_input != st.session_state.query:
        st.session_state.query = query_input
        st.session_state.selected_ids = []
        st.rerun()

    # 建议词（展示用，不阻塞）
    if query_input:
        suggestions = get_chemical_suggestions(query_input, 5)
        if suggestions:
            st.caption("💡 " + "  |  ".join(suggestions[:4]))

    # 企查查 API 模式切换
    from utils.qcc_client import is_configured as _qcc_ok
    _api_ready = _qcc_ok()
    use_api = st.toggle(
        "🔌 启用企查查实时搜索",
        value=st.session_state.get("use_api", False) and _api_ready,
        disabled=not _api_ready,
        help="已配置企查查 Key，可搜索任意产品" if _api_ready else "请在 .env.local 配置 QCC_APP_KEY 和 QCC_SECRET_KEY",
    )
    if use_api != st.session_state.get("use_api"):
        st.session_state["use_api"] = use_api
        st.rerun()

    st.divider()

    # ── 筛选器 ──────────────────────────────────────────────────────
    st.markdown("### 🔎 筛选条件")
    f = st.session_state.filters

    with open(APP_DIR / "data" / "regions.json", encoding="utf-8") as _f:
        _regions = json.load(_f)

    # ▶ 地域筛选
    with st.expander("📍 地域", expanded=True):
        tier_options = {"一级 (沪苏浙皖)": 1, "二级 (鲁粤鄂豫闽)": 2, "三级 (其余)": 3}
        sel_tier_labels = st.multiselect(
            "地理圈层", list(tier_options.keys()),
            default=[k for k, v in tier_options.items() if v in f.get("tiers", [])],
            placeholder="不限",
        )
        sel_tiers = [tier_options[l] for l in sel_tier_labels]

        tier1_p = _regions["tiers"]["tier1"]["provinces"]
        tier2_p = _regions["tiers"]["tier2"]["provinces"]
        tier3_p = _regions["tiers"].get("tier3", {}).get("provinces", [])
        if sel_tiers:
            pool = []
            if 1 in sel_tiers: pool += tier1_p
            if 2 in sel_tiers: pool += tier2_p
            if 3 in sel_tiers: pool += tier3_p
        else:
            pool = tier1_p + tier2_p + tier3_p

        sel_provinces = st.multiselect(
            "省份（支持多选）", pool,
            default=[p for p in f.get("provinces", []) if p in pool],
            placeholder="不限（全国）",
        )

    # ▶ 企业信息（来自企查查）
    with st.expander("🏢 企业信息", expanded=True):
        status_active = st.checkbox(
            "仅展示存续/在业企业",
            value=f.get("status_active", True),
            help="过滤掉注销、吊销、迁出等状态企业",
        )
        company_type = st.radio(
            "企业类型",
            options=["all", "manufacturer", "both", "trader"],
            format_func=lambda x: {
                "all": "全部",
                "manufacturer": "仅制造商",
                "both": "制造+贸易",
                "trader": "仅经销商",
            }[x],
            index=["all","manufacturer","both","trader"].index(f.get("company_type","all")),
            horizontal=True,
        )
        min_capital = st.number_input(
            "最低注册资本（万元）",
            min_value=0, max_value=100_000,
            value=int(f.get("min_capital", 0)),
            step=100,
            help="0 = 不限；来自企查查 RegistCapi 字段",
        )
        import datetime as _dt
        current_year = _dt.datetime.now().year
        est_after = st.slider(
            "成立年份 ≥",
            min_value=1980, max_value=current_year,
            value=f.get("est_after", 1990),
            help="来自企查查 StartDate 字段",
        )

    # ▶ 资质与行业
    with st.expander("📋 资质 & 关键词", expanded=False):
        only_hazmat = st.checkbox(
            "含危险化学品经营资质",
            value=f.get("only_hazmat", False),
            help="经营范围包含危险化学品关键词",
        )
        scope_keyword = st.text_input(
            "经营范围额外包含词",
            value=f.get("scope_keyword", ""),
            placeholder="例：换热器 / ISO9001 / 出口",
            help="在企查查经营范围文本中精确匹配",
        )

    # ▶ 评分门槛
    with st.expander("🎯 评分门槛", expanded=False):
        min_score = st.slider(
            "最低综合评分",
            min_value=0, max_value=90,
            value=f.get("min_score", 0),
            step=5,
            help="过滤掉低于该分数的企业",
        )

    new_filters = {
        "provinces":     sel_provinces,
        "tiers":         sel_tiers,
        "status_active": status_active,
        "company_type":  company_type,
        "min_capital":   min_capital,
        "est_after":     est_after,
        "only_hazmat":   only_hazmat,
        "scope_keyword": scope_keyword,
        "min_score":     min_score,
    }
    if new_filters != st.session_state.filters:
        st.session_state.filters = new_filters
        st.rerun()

    st.divider()

    # ── 权重调节 ─────────────────────────────────────────────────────
    st.markdown("### ⚖️ 评分权重（量化维度）")
    st.caption("四个维度全部基于企查查客观字段")
    w = st.session_state.weights
    w_geo  = st.slider("📍 地理位置（km 距离+圈层）", 0, 100, int(w.get("geography", 0.30) * 100), 5)
    w_scl  = st.slider("🏢 企业规模（资本+年限）",   0, 100, int(w.get("scale",    0.30) * 100), 5)
    w_cmp  = st.slider("✅ 合规资质（状态+角色）",   0, 100, int(w.get("compliance",0.25) * 100), 5)
    w_rel  = st.slider("🔗 经营相关度（文本匹配）",  0, 100, int(w.get("relevance", 0.15) * 100), 5)

    total_w = w_geo + w_scl + w_cmp + w_rel
    if total_w > 0:
        new_weights = {
            "geography":  w_geo  / total_w,
            "scale":      w_scl  / total_w,
            "compliance": w_cmp  / total_w,
            "relevance":  w_rel  / total_w,
            # 向后兼容旧键名
            "product":    w_rel  / total_w,
            "history":    w_cmp  / total_w,
        }
        if new_weights != st.session_state.weights:
            st.session_state.weights = new_weights
            st.rerun()
        st.caption(f"已自动归一化，合计 100%")

    if st.button("恢复默认权重", use_container_width=True):
        st.session_state.weights = dict(DEFAULT_WEIGHTS)
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════
# 主体内容
# ═══════════════════════════════════════════════════════════════════════

# API 状态条
st.markdown("""
<div class="api-bar">
  <span class="api-lbl">数据接口</span>
  <span class="api-chip demo"><span class="dot"></span>企查查 · 演示数据</span>
  <span class="api-chip demo"><span class="dot"></span>PubChem · 演示数据</span>
  <span class="api-chip demo"><span class="dot"></span>高德地图 · 演示数据</span>
  <span class="api-chip off"><span class="dot"></span>应急管理部 · 外链核验</span>
  <span style="margin-left:auto;color:#9ba8bb;font-size:11px;">当前：虚拟数据演示模式</span>
</div>
""", unsafe_allow_html=True)

# 操作行
act_col1, act_col2 = st.columns([3, 1])
with act_col1:
    if chemical:
        st.markdown(
            f"**当前查询：** "
            f"<span style='background:#f0faf4;border:1px solid rgba(14,140,58,.3);"
            f"padding:2px 10px;border-radius:4px;color:#0E8C3A;font-weight:600'>"
            f"🧪 {chemical.get('primaryName')} ({chemical.get('englishName')})</span>"
            f"&nbsp;&nbsp;<code style='font-size:12px'>CAS {chemical.get('cas')}</code>"
            f"&nbsp;&nbsp;分类：{chemical.get('category')}"
            f"&nbsp;&nbsp;&nbsp;命中 <b style='color:#0E8C3A;font-size:16px'>{len(results)}</b> 家",
            unsafe_allow_html=True,
        )
    elif st.session_state.query:
        st.markdown(
            f"关键词匹配「**{st.session_state.query}**」&nbsp;&nbsp;"
            f"命中 <b style='color:#0E8C3A'>{len(results)}</b> 家",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<span style='color:#9ba8bb'>请在左侧输入原材料名称或 CAS 号</span>"
            f"&nbsp;&nbsp;共 <b style='color:#0E8C3A'>{len(results)}</b> 家供应商",
            unsafe_allow_html=True,
        )

with act_col2:
    if results:
        excel_bytes = export_excel(
            results[:20],
            chemical["primaryName"] if chemical else "供应商对比",
        )
        st.download_button(
            "📥 导出 Excel",
            data=excel_bytes,
            file_name=f"SABIC_供应商对比{'_' + chemical['primaryName'] if chemical else ''}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

st.markdown("---")

# 两栏布局
left_col, right_col = st.columns([4, 6], gap="medium")

# ── 左栏：供应商排名列表 ─────────────────────────────────────────────
with left_col:
    n_selected = len(sel_ids)
    st.markdown(
        f"**供应商排名** "
        f"<span style='font-size:12px;color:#9ba8bb'>Top {min(len(results), 15)}</span>"
        f"{'&nbsp;&nbsp;<span style=\"background:#f0f0ff;border:1px solid #c4b5fd;padding:1px 8px;border-radius:4px;font-size:11px;color:#7c3aed\">' + str(n_selected) + ' 家已选对比</span>' if n_selected else ''}",
        unsafe_allow_html=True,
    )

    if not results:
        st.info("未找到匹配供应商，请调整搜索条件或筛选器。")
    else:
        for i, s in enumerate(results[:15]):
            sid      = s.get("id", "")
            name     = s.get("shortName") or s.get("name", "")
            score    = s.get("score", 0)
            province = s.get("province", "")
            tier     = s.get("_tier", 3)
            is_sel   = sid in sel_ids
            is_partner = s.get("sabic_history", {}).get("is_partner", False)

            tier_cls  = ["","tier-t1","tier-t2","tier-t3"][tier]
            tier_lbl  = ["","一级","二级","三级"][tier]
            score_cls = "score-high" if score >= 70 else ("score-mid" if score >= 50 else "score-low")
            star = "★ " if is_partner else ""

            # 使用 Streamlit checkbox + markdown 组合实现可点击卡片
            card_cols = st.columns([0.5, 6, 2])
            with card_cols[0]:
                checked = st.checkbox(
                    "对比", value=is_sel, key=f"sel_{sid}",
                    label_visibility="collapsed",
                )
                if checked != is_sel:
                    if checked and len(sel_ids) < 5:
                        st.session_state.selected_ids.append(sid)
                    elif not checked:
                        st.session_state.selected_ids = [x for x in sel_ids if x != sid]
                    st.rerun()

            with card_cols[1]:
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:8px;padding:6px 0'>"
                    f"  <div class='sup-rank'>{i+1}</div>"
                    f"  <div>"
                    f"    <div class='sup-name'>{star}{name}</div>"
                    f"    <div class='sup-meta'>{province} · {s.get('city','')}</div>"
                    f"  </div>"
                    f"  <span class='{tier_cls}'>{tier_lbl}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            with card_cols[2]:
                st.markdown(
                    f"<div style='text-align:right;padding:6px 0'>"
                    f"  <span class='{score_cls}' style='font-size:18px'>{score:.1f}</span>"
                    f"  <span style='font-size:10px;color:#9ba8bb'> 分</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # 维度迷你进度条
            dims = s.get("dimensions", {})
            bar_html = "".join(
                f"<div style='flex:1;text-align:center'>"
                f"  <div style='height:3px;background:#e2e8f0;border-radius:2px'>"
                f"    <div style='height:100%;width:{dims.get(k,0):.0f}%;"
                f"          background:{"#0E8C3A" if dims.get(k,0)>=70 else "#f59e0b" if dims.get(k,0)>=40 else "#ef4444"};"
                f"          border-radius:2px'></div>"
                f"  </div>"
                f"  <div style='font-size:9px;color:#9ba8bb;margin-top:2px'>{lbl}</div>"
                f"</div>"
                for k, lbl in zip(
                    ["product","geography","history","compliance","scale"],
                    ["产","地","史","规","规"]
                )
            )
            st.markdown(
                f"<div style='display:flex;gap:4px;margin-bottom:8px;padding:0 4px'>{bar_html}</div>",
                unsafe_allow_html=True,
            )

            # 点击查看详情
            if st.button(f"查看详情", key=f"detail_{sid}",
                         use_container_width=True, type="secondary"):
                st.session_state.active_supplier = s
                st.rerun()

            st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)

# ── 右栏：图表 + 统计 + 详情 ────────────────────────────────────────
with right_col:

    # 图表 Tabs
    tab_labels = ["📡 雷达图","📊 单项对比","📋 并排对比表",
                  "📈 平行坐标","🌡️ 热力矩阵","🫧 气泡图","🗺️ 中国地图"]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        bar_metric = "score"  # 雷达图固定
        fig = radar_chart(compare_suppliers)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="chart_radar")
        st.caption(f"展示 {'已选 ' + str(len(sel_ids)) + ' 家' if sel_ids else 'Top 5'} 供应商 · 勾选左侧复选框可自定义对比组合")

    with tabs[1]:
        metric_opt = st.selectbox(
            "选择指标",
            ["综合评分","产品匹配","地理评分","合作历史","合规资质","规模评分"],
            label_visibility="collapsed",
        )
        metric_map = {
            "综合评分":"score","产品匹配":"product","地理评分":"geography",
            "合作历史":"history","合规资质":"compliance","规模评分":"scale",
        }
        fig = bar_chart(compare_suppliers, metric_map[metric_opt])
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=f"chart_bar_{metric_opt}")

    with tabs[2]:
        if len(compare_suppliers) < 2:
            st.info("请在左侧勾选至少 2 家供应商进行并排对比。")
        else:
            df_cmp = compare_dataframe(compare_suppliers)
            st.dataframe(
                df_cmp.style.apply(_highlight_row_max, axis=1),
                use_container_width=True,
                height=480,
            )

    with tabs[3]:
        fig = parallel_chart(compare_suppliers)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="chart_parallel")
        st.caption("每条折线代表一家企业 · 悬停显示各维度精确分数 · 点击右侧图例可隐藏/显示某企业 · ★ 表示 SABIC 合作商")

    with tabs[4]:
        fig = heatmap_chart(results[:15])
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="chart_heatmap")

    with tabs[5]:
        fig = bubble_chart(results[:20])
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="chart_bubble")
        st.caption("X轴：均价 · Y轴：产能（对数）· 气泡大小：综合评分 · 颜色：地理圈层")

    with tabs[6]:
        fig = china_map(results)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="chart_map")
        st.caption("颜色深浅：该省供应商数量 · 气泡：供应商位置与评分 · ★：SABIC 上海基地")

    # ── 统计卡片 ───────────────────────────────────────────────────────
    st.markdown("---")
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("华东一级圈", f"{tier1_count} 家",
               delta=None, help="沪苏浙皖四省市")
    sc2.metric("SABIC 合作商", f"{partner_count} 家",
               delta=None, help="已有历史合作记录")
    sc3.metric("危化品资质", f"{hazmat_count} 家",
               delta=None, help="持有危化品经营许可证")
    sc4.metric("平均评分", f"{avg_score} 分",
               delta=None, help="当前筛选结果的评分均值")

    # ── 供应商详情 ─────────────────────────────────────────────────────
    active = st.session_state.active_supplier
    if active:
        st.markdown("---")
        source_badge = (
            '<span style="background:#eff6ff;border:1px solid #3b82f6;'
            'padding:1px 8px;border-radius:4px;font-size:11px;color:#3b82f6">'
            f'数据来源：{active.get("_source","演示数据")}</span>'
            if active.get("_source") else
            '<span style="background:#fef9c3;border:1px solid #ca8a04;'
            'padding:1px 8px;border-radius:4px;font-size:11px;color:#92400e">'
            '演示数据 · 接入企查查后替换为实时数据</span>'
        )
        st.markdown(
            f'#### 📋 {active.get("shortName") or active.get("name")} &nbsp; {source_badge}',
            unsafe_allow_html=True,
        )

        # ── 行 1：工商基本信息 + 合规资质 + 经营角色 ────────────────
        d1, d2, d3 = st.columns(3)
        with d1:
            st.markdown("**🏢 工商基本信息**")
            cap = active.get("registered_capital_wan", 0) or 0
            cap_str = f"{cap/10000:.1f} 亿元" if cap >= 10000 else f"{cap} 万元" if cap > 0 else "—"
            rows_d1 = [
                ("企业全称",  active.get("name", "—")),
                ("统一信用代码", active.get("creditCode") or active.get("credit_code") or "—（接入企查查后显示）"),
                ("法定代表人", active.get("legalPerson") or active.get("legal_person") or "—（接入企查查后显示）"),
                ("注册地址",  active.get("address", "—")[:30] + ("…" if len(active.get("address",""))>30 else "")),
                ("所在省市",  f"{active.get('province','—')} {active.get('city','')}"),
                ("注册资本",  cap_str),
                ("成立年份",  f"{active.get('established','—')} 年" if active.get('established') else "—"),
                ("经营状态",  active.get("reg_status", "存续") or "存续"),
                ("所属行业",  active.get("industry", "—（接入企查查后显示）")),
            ]
            for k, v in rows_d1:
                st.markdown(f'<div style="font-size:13px;padding:2px 0"><span style="color:#5a6780">{k}：</span>{v}</div>',
                            unsafe_allow_html=True)

        with d2:
            lic = active.get("licenses", {})
            st.markdown("**✅ 资质 & 合规**")
            def badge(ok, label, api_note=""):
                color = "#059669" if ok else "#9ca3af"
                icon  = "✓" if ok else "✗"
                note  = f' <span style="font-size:10px;color:#9ba8bb">{api_note}</span>' if api_note and not ok else ""
                return f'<div style="font-size:13px;padding:2px 0"><span style="color:{color}">{icon}</span> {label}{note}</div>'

            st.markdown(badge(
                lic.get("hazardous_chemicals") or lic.get("hazmat_business"),
                "危险化学品经营许可证",
                "→ 应急管理部核验"
            ), unsafe_allow_html=True)
            st.markdown(badge(lic.get("safety_production"), "安全生产许可证",
                              "→ 应急管理部核验"), unsafe_allow_html=True)
            st.markdown(badge(lic.get("vat_general", True), "增值税一般纳税人"), unsafe_allow_html=True)
            st.markdown(badge(lic.get("gb_certified"), "GB/T 质量体系认证",
                              "→ 认证机构核验"), unsafe_allow_html=True)
            st.markdown(badge(active.get("chemical_park"), "化工园区内企业"), unsafe_allow_html=True)

            st.markdown("<br>**🏭 企业类型（来自经营范围）**", unsafe_allow_html=True)
            role_map = {
                "manufacturer": ("🟢 制造商", "#059669"),
                "both":         ("🔵 制造+经销", "#3b82f6"),
                "trader":       ("🟡 经销商", "#d97706"),
                "unknown":      ("⚪ 未分类", "#9ca3af"),
            }
            role = active.get("_role", "unknown")
            rl, rc = role_map.get(role, ("⚪ 未分类", "#9ca3af"))
            st.markdown(f'<span style="color:{rc};font-weight:600">{rl}</span>', unsafe_allow_html=True)

        with d3:
            st.markdown("**📦 供应能力**")
            rows_d3 = [
                ("主营产品",  "、".join(active.get("products", [])[:5]) or "—（接入企查查后从经营范围提取）"),
                ("年产能",    f"{active.get('annual_capacity_ton',0):,} 吨" if active.get('annual_capacity_ton') else "—"),
                ("最小起订",  f"{active.get('min_order_ton','—')} 吨"),
                ("价格区间",  f"{active.get('price_range_per_ton',[0,0])[0]}~{active.get('price_range_per_ton',[0,0])[1]} 元/吨"
                              if active.get('price_range_per_ton') and any(active.get('price_range_per_ton',[0,0])) else "—"),
            ]
            for k, v in rows_d3:
                st.markdown(f'<div style="font-size:13px;padding:2px 0"><span style="color:#5a6780">{k}：</span>{v}</div>',
                            unsafe_allow_html=True)

            st.markdown("<br>**📋 经营范围（企查查 Scope 字段）**", unsafe_allow_html=True)
            scope = active.get("_business_scope", "")
            if scope:
                st.markdown(
                    f'<div style="font-size:12px;color:#374151;background:#f9fafb;'
                    f'border:1px solid #e5e7eb;border-radius:6px;padding:8px;'
                    f'max-height:120px;overflow-y:auto;line-height:1.6">{scope[:400]}'
                    f'{"…" if len(scope)>400 else ""}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.caption("经营范围在接入企查查 ic/baseinfoV2/2.0 接口后自动填充（Scope 字段）")

        # ── 行 2：待接入企查查高级字段 ──────────────────────────────
        st.markdown("---")
        ea1, ea2, ea3, ea4 = st.columns(4)

        with ea1:
            st.markdown("**👥 股东信息**")
            st.caption("接入企查查 ic/partners/2.0 接口后显示 股东名称 / 出资比例 / 认缴金额")
            st.markdown(
                '<div style="background:#f9fafb;border:1px dashed #d1d5db;'
                'border-radius:6px;padding:8px;font-size:12px;color:#9ca3af;text-align:center">'
                'API 待接入</div>', unsafe_allow_html=True)

        with ea2:
            st.markdown("**⚠️ 司法 & 风险**")
            st.caption("接入企查查 judicial/ktgg/2.0 接口后显示 开庭公告 / 被执行人 / 行政处罚")
            st.markdown(
                '<div style="background:#f9fafb;border:1px dashed #d1d5db;'
                'border-radius:6px;padding:8px;font-size:12px;color:#9ca3af;text-align:center">'
                'API 待接入</div>', unsafe_allow_html=True)

        with ea3:
            st.markdown("**📜 行政许可**")
            st.caption("接入企查查 admin/license/2.0 接口后显示 生产许可证 / 经营许可证 / ISO 认证")
            st.markdown(
                '<div style="background:#f9fafb;border:1px dashed #d1d5db;'
                'border-radius:6px;padding:8px;font-size:12px;color:#9ca3af;text-align:center">'
                'API 待接入</div>', unsafe_allow_html=True)

        with ea4:
            st.markdown("**🔗 核验链接**")
            name_enc = active.get("name", "").replace(" ", "+")
            credit   = active.get("creditCode", "")
            st.markdown(
                f'<a href="https://www.gsxt.gov.cn/corp-query-homepage.html" '
                f'target="_blank" style="font-size:12px;color:#3b82f6">🏛 国家企业信用信息公示</a><br>'
                f'<a href="https://www.mem.gov.cn/fw/cxfw/" '
                f'target="_blank" style="font-size:12px;color:#3b82f6">🔒 应急管理部资质核验</a><br>'
                f'<a href="https://credit.customs.gov.cn/" '
                f'target="_blank" style="font-size:12px;color:#3b82f6">🛃 海关信用企业查询</a>',
                unsafe_allow_html=True
            )
            if active.get("_fetched_at"):
                st.caption(f"数据拉取时间：{active.get('_fetched_at', '')[:10]}")

# ── 页脚 ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="sabic-footer">
  © SABIC Shanghai · 寻源系统 v1.1 Python 版 · 仅供内部使用 ·
  数据来源：虚拟演示数据（演示模式）
</div>
""", unsafe_allow_html=True)
