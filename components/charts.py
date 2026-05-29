"""
所有可视化图表 — 使用 Plotly 替代 ECharts
支持：雷达图、柱图、气泡图、平行坐标轴、热力矩阵、中国地图
"""
from __future__ import annotations
import json
import re
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# 品牌色系
SABIC_GREEN  = "#0E8C3A"
SABIC_DARK   = "#0a1628"
PALETTE = [
    "#0E8C3A","#3b82f6","#f59e0b","#8b5cf6","#ef4444",
    "#06b6d4","#ec4899","#14b8a6","#f97316","#6366f1",
]
BG = "rgba(0,0,0,0)"  # 透明背景

_FONT = dict(family="PingFang SC, Microsoft YaHei, sans-serif", size=12)

DIM_LABELS = ["产品匹配", "地理评分", "合作历史", "合规资质", "规模评分"]
DIM_KEYS   = ["product",  "geography","history",  "compliance","scale"]


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mid_price(value, default: float = 5000.0) -> float:
    if isinstance(value, (list, tuple)):
        nums = [_to_float(v) for v in value if _to_float(v) > 0]
    else:
        nums = [_to_float(v) for v in re.findall(r"\d+(?:\.\d+)?", str(value))]

    return sum(nums[:2]) / min(len(nums), 2) if nums else default


# ── 雷达图 ────────────────────────────────────────────────────────────
def radar_chart(suppliers: list[dict]) -> go.Figure:
    if not suppliers:
        return _empty("请选择供应商")

    cats = DIM_LABELS + [DIM_LABELS[0]]  # 首尾相连闭合

    fig = go.Figure()
    for i, s in enumerate(suppliers[:6]):
        dims = s.get("dimensions", {})
        vals = [dims.get(k, 0) for k in DIM_KEYS]
        vals_closed = vals + [vals[0]]
        name = s.get("shortName") or s.get("name", "")[:8]
        fig.add_trace(go.Scatterpolar(
            r=vals_closed,
            theta=cats,
            fill="toself",
            fillcolor=f"rgba{_hex_to_rgba(PALETTE[i % len(PALETTE)], 0.15)}",
            line=dict(color=PALETTE[i % len(PALETTE)], width=2),
            name=f"{name} ({s.get('score', 0):.1f}分)",
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=10),
                            gridcolor="#e2e8f0"),
            angularaxis=dict(tickfont=dict(size=11)),
            bgcolor="white",
        ),
        showlegend=True,
        legend=dict(font=dict(size=11), orientation="h", y=-0.15),
        font=_FONT, paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=60, r=60, t=30, b=60),
        height=340,
    )
    return fig


# ── 单项对比柱图 ──────────────────────────────────────────────────────
def bar_chart(suppliers: list[dict], metric: str = "score") -> go.Figure:
    if not suppliers:
        return _empty("请选择供应商")

    METRIC_MAP = {
        "score":    ("综合评分", lambda s: s.get("score", 0)),
        "product":  ("产品匹配", lambda s: s.get("dimensions", {}).get("product", 0)),
        "geography":("地理评分", lambda s: s.get("dimensions", {}).get("geography", 0)),
        "history":  ("合作历史", lambda s: s.get("dimensions", {}).get("history", 0)),
        "compliance":("合规资质",lambda s: s.get("dimensions", {}).get("compliance", 0)),
        "scale":    ("规模评分", lambda s: s.get("dimensions", {}).get("scale", 0)),
    }
    label, getter = METRIC_MAP.get(metric, METRIC_MAP["score"])

    names  = [s.get("shortName") or s.get("name", "")[:8] for s in suppliers[:10]]
    values = [round(getter(s), 1) for s in suppliers[:10]]
    colors = [SABIC_GREEN if v == max(values) else "#94a3b8" for v in values]

    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}" for v in values],
        textposition="outside",
        textfont=dict(size=11),
    ))
    fig.update_layout(
        title=dict(text=f"<b>{label}</b>对比", font=dict(size=13)),
        xaxis=dict(range=[0, 110], showgrid=True, gridcolor="#e2e8f0", title=label),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
        font=_FONT, paper_bgcolor=BG, plot_bgcolor="white",
        margin=dict(l=10, r=60, t=45, b=30),
        height=max(280, len(suppliers) * 38 + 80),
    )
    return fig


# ── 气泡图 ────────────────────────────────────────────────────────────
def bubble_chart(suppliers: list[dict]) -> go.Figure:
    if not suppliers:
        return _empty("暂无数据")

    df = pd.DataFrame([{
        "name":  s.get("shortName") or s.get("name", "")[:8],
        "price": _mid_price(s.get("price_range_per_ton")),
        "capacity": max(_to_float(s.get("annual_capacity_ton"), 1000), 1000) / 1e4,
        "score": s.get("score", 50),
        "tier":  f"圈层{s.get('_tier', 3)}",
        "partner": "SABIC合作商" if s.get("sabic_history", {}).get("is_partner") else "普通供应商",
    } for s in suppliers[:20]])

    tier_color = {"圈层1": SABIC_GREEN, "圈层2": "#3b82f6", "圈层3": "#8b5cf6"}

    fig = px.scatter(
        df, x="price", y="capacity",
        size="score", color="tier",
        color_discrete_map=tier_color,
        hover_name="name",
        hover_data={"price": ":.0f", "capacity": ":.1f", "score": ":.1f"},
        labels={"price": "均价 (元/吨)", "capacity": "产能 (万吨/年)", "tier": "圈层"},
        size_max=40,
    )
    fig.update_layout(
        font=_FONT, paper_bgcolor=BG, plot_bgcolor="white",
        legend=dict(orientation="h", y=-0.18, font=dict(size=11)),
        xaxis=dict(showgrid=True, gridcolor="#e2e8f0"),
        yaxis=dict(showgrid=True, gridcolor="#e2e8f0", type="log",
                   title="产能 (万吨/年, 对数轴)"),
        margin=dict(l=20, r=20, t=30, b=60),
        height=360,
    )
    return fig


# ── 维度剖面图（替代平行坐标轴）───────────────────────────────────────
def parallel_chart(suppliers: list[dict]) -> go.Figure:
    """
    每家企业是一条彩色折线，X 轴为评分维度，Y 轴为 0-100 分。
    鼠标悬停显示企业名 + 各维度精确分数；点击图例可隐藏/显示某企业。
    """
    if not suppliers:
        return _empty("暂无数据")

    displayed = suppliers[:10]

    DIM_NAMES = ["综合评分", "产品匹配", "地理评分", "合作历史", "合规资质", "规模评分"]
    DIM_FETCH = [
        lambda s: s.get("score", 0),
        lambda s: s.get("dimensions", {}).get("product", 0),
        lambda s: s.get("dimensions", {}).get("geography", 0),
        lambda s: s.get("dimensions", {}).get("history", 0),
        lambda s: s.get("dimensions", {}).get("compliance", 0),
        lambda s: s.get("dimensions", {}).get("scale", 0),
    ]

    fig = go.Figure()

    for i, s in enumerate(displayed):
        name  = s.get("shortName") or s.get("name", "")[:8]
        vals  = [round(fn(s), 1) for fn in DIM_FETCH]
        color = PALETTE[i % len(PALETTE)]
        is_partner = s.get("sabic_history", {}).get("is_partner", False)
        line_width  = 2.5 if is_partner else 1.8
        line_dash   = "solid"
        marker_sym  = "star" if is_partner else "circle"

        hover_lines = [
            f"<b>{name}</b>{'  ★ SABIC合作商' if is_partner else ''}",
            "─────────────────",
        ] + [f"{dn}：{v:.1f} 分" for dn, v in zip(DIM_NAMES, vals)]

        fig.add_trace(go.Scatter(
            x=DIM_NAMES,
            y=vals,
            mode="lines+markers",
            name=name,
            line=dict(color=color, width=line_width, dash=line_dash),
            marker=dict(size=8, symbol=marker_sym, color=color,
                        line=dict(color="white", width=1.5)),
            hovertemplate="<br>".join(hover_lines) + "<extra></extra>",
        ))

    fig.update_layout(
        font=_FONT,
        paper_bgcolor=BG,
        plot_bgcolor="white",
        xaxis=dict(
            showgrid=True,
            gridcolor="#e2e8f0",
            tickfont=dict(size=12),
            title="",
        ),
        yaxis=dict(
            range=[0, 108],
            showgrid=True,
            gridcolor="#e2e8f0",
            title="得分",
            tickfont=dict(size=11),
            zeroline=False,
        ),
        legend=dict(
            orientation="v",
            x=1.01, y=1,
            font=dict(size=11),
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#e2e8f0",
            borderwidth=1,
            title=dict(text="企业名称", font=dict(size=11)),
        ),
        margin=dict(l=50, r=160, t=40, b=50),
        height=380,
        hovermode="x unified",
        # 添加参考线
        shapes=[
            dict(type="line", x0=0, x1=1, xref="paper",
                 y0=60, y1=60, yref="y",
                 line=dict(color="#94a3b8", width=1, dash="dot")),
        ],
        annotations=[
            dict(x=1.0, y=60, xref="paper", yref="y",
                 text="60分基准", showarrow=False,
                 font=dict(size=9, color="#94a3b8"),
                 xanchor="right"),
        ],
    )
    return fig


# ── 热力矩阵 ─────────────────────────────────────────────────────────
def heatmap_chart(suppliers: list[dict]) -> go.Figure:
    if not suppliers:
        return _empty("暂无数据")

    displayed = suppliers[:15]
    y_labels = [s.get("shortName") or s.get("name", "")[:8] for s in displayed]
    x_labels = DIM_LABELS + ["综合评分"]
    keys_ext = DIM_KEYS + ["score"]

    z = []
    for s in displayed:
        dims = s.get("dimensions", {})
        row = [round(dims.get(k, 0) if k != "score" else s.get("score", 0), 1)
               for k in keys_ext]
        z.append(row)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=x_labels,
        y=y_labels,
        # 红(低) → 橙 → 黄 → 绿(高)，对比度大幅提升
        colorscale=[
            [0.00, "#dc2626"],   # 0-20 分：深红
            [0.20, "#f97316"],   # 20-40 分：橙
            [0.40, "#fbbf24"],   # 40-60 分：黄
            [0.65, "#84cc16"],   # 60-80 分：黄绿
            [0.85, "#22c55e"],   # 80-95 分：绿
            [1.00, "#15803d"],   # 95-100分：深绿
        ],
        zmin=0, zmax=100,
        text=[[f"{v:.0f}" for v in row] for row in z],
        texttemplate="%{text}",
        textfont=dict(size=12, color="white"),
        hovertemplate="%{y} · %{x}: <b>%{z:.1f}</b>分<extra></extra>",
        colorbar=dict(
            title="得分",
            thickness=16,
            len=0.95,
            tickfont=dict(size=11),
            tickvals=[0, 20, 40, 60, 80, 100],
            ticktext=["0", "20<br>差", "40", "60<br>中", "80", "100<br>优"],
        ),
        xgap=3, ygap=3,
    ))
    fig.update_layout(
        font=_FONT, paper_bgcolor=BG, plot_bgcolor="white",
        xaxis=dict(side="top", tickfont=dict(size=12)),
        yaxis=dict(autorange="reversed", tickfont=dict(size=12)),
        margin=dict(l=10, r=100, t=70, b=10),
        height=max(340, len(displayed) * 40 + 100),
    )
    return fig


# ── 并排对比表（DataFrame） ───────────────────────────────────────────
def compare_dataframe(suppliers: list[dict]) -> pd.DataFrame:
    """返回用于 st.dataframe 展示的 DataFrame。"""
    if not suppliers:
        return pd.DataFrame()

    rows = []
    metric_labels = [
        "综合评分", "产品匹配", "地理评分", "合作历史", "合规资质", "规模评分",
        "所在省份", "圈层", "成立年份", "注册资本(万)",
        "危化品资质", "安全生产证", "SABIC合作商", "合作年限",
        "最小起订(吨)", "化工园区",
    ]
    for label in metric_labels:
        row = {"指标": label}
        for s in suppliers:
            name = s.get("shortName") or s.get("name", "")[:8]
            dims = s.get("dimensions", {})
            lic  = s.get("licenses", {})
            hist = s.get("sabic_history", {})
            tier = s.get("_tier", 3)
            tier_label = ["", "一级(华东)", "二级", "三级"][tier]

            val_map = {
                "综合评分":    f"{s.get('score', 0):.1f}",
                "产品匹配":    f"{dims.get('product', 0):.1f}",
                "地理评分":    f"{dims.get('geography', 0):.1f}",
                "合作历史":    f"{dims.get('history', 0):.1f}",
                "合规资质":    f"{dims.get('compliance', 0):.1f}",
                "规模评分":    f"{dims.get('scale', 0):.1f}",
                "所在省份":    s.get("province", "—"),
                "圈层":        tier_label,
                "成立年份":    str(s.get("established", "—")),
                "注册资本(万)": str(s.get("registered_capital_wan", "—")),
                "危化品资质":  "✓" if (lic.get("hazardous_chemicals") or lic.get("hazmat_business")) else "—",
                "安全生产证":  "✓" if lic.get("safety_production") else "—",
                "SABIC合作商": "★" if hist.get("is_partner") else "—",
                "合作年限":    f"{hist.get('years', 0)} 年" if hist.get("is_partner") else "—",
                "最小起订(吨)": f"{s.get('min_order_ton', '—')}",
                "化工园区":    "✓" if s.get("chemical_park") else "—",
            }
            row[name] = val_map.get(label, "—")
        rows.append(row)

    return pd.DataFrame(rows).set_index("指标")


# ── 中国地图 ─────────────────────────────────────────────────────────
def china_map(suppliers: list[dict]) -> go.Figure:
    _geojson_path = Path(__file__).parent.parent / "data" / "china.json"
    if not _geojson_path.exists():
        return _empty("china.json 未找到\n请下载放到 data/ 目录", height=400)

    with open(_geojson_path, encoding="utf-8") as f:
        geojson = json.load(f)

    # 省份热力数据
    province_count: dict[str, int] = {}
    for s in suppliers:
        p = s.get("province", "")
        if p:
            province_count[p] = province_count.get(p, 0) + 1

    df_map = pd.DataFrame([
        {"province": p, "count": c} for p, c in province_count.items()
    ])

    if df_map.empty:
        df_map = pd.DataFrame({"province": [], "count": []})

    fig = go.Figure()

    # 省份底图
    fig.add_trace(go.Choropleth(
        geojson=geojson,
        locations=df_map["province"] if not df_map.empty else [],
        z=df_map["count"] if not df_map.empty else [],
        featureidkey="properties.name",
        colorscale=[[0,"#e2e8f0"],[1, SABIC_GREEN]],
        zmin=0, zmax=max(df_map["count"].max() if not df_map.empty else 1, 1),
        showscale=True,
        colorbar=dict(title="供应商数", thickness=12, len=0.6,
                      tickfont=dict(size=10)),
        marker_line_color="white",
        marker_line_width=0.5,
        hovertemplate="%{location}: %{z} 家<extra></extra>",
    ))

    # 供应商散点（用省会坐标 + 微抖动）
    _DATA = Path(__file__).parent.parent / "data"
    with open(_DATA / "regions.json", encoding="utf-8") as f:
        regions = json.load(f)
    # provinceCoords 是 {省名: {lng, lat, distance_km}} 的 dict，直接用
    coord_map = regions.get("provinceCoords", {})

    import random
    scatter_lats, scatter_lons, scatter_texts, scatter_sizes, scatter_colors = [], [], [], [], []
    for s in suppliers:
        prov = s.get("province", "")
        coord = coord_map.get(prov)
        if not coord:
            continue
        seed = hash(s.get("id", "")) % 1000
        r = random.Random(seed)
        lat = coord.get("lat", 30) + r.uniform(-0.6, 0.6)
        lon = coord.get("lng", 120) + r.uniform(-0.8, 0.8)
        score = s.get("score", 50)
        name  = s.get("shortName") or s.get("name", "")[:10]
        dims  = s.get("dimensions", {})
        scatter_lats.append(lat)
        scatter_lons.append(lon)
        scatter_colors.append(score)
        scatter_sizes.append(max(8, score * 0.22))
        scatter_texts.append(
            f"<b>{name}</b><br>"
            f"综合：{score:.1f}分<br>"
            f"地理：{dims.get('geography',0):.0f} · "
            f"规模：{dims.get('scale',0):.0f} · "
            f"合规：{dims.get('compliance',0):.0f} · "
            f"相关：{dims.get('relevance',0):.0f}"
        )

    if scatter_lats:
        fig.add_trace(go.Scattergeo(
            lat=scatter_lats, lon=scatter_lons,
            text=scatter_texts,
            mode="markers",
            marker=dict(
                size=scatter_sizes,
                color=scatter_colors,   # ← 修复：与 scatter_lats 等长
                colorscale=[[0,"#f59e0b"],[0.5,"#3b82f6"],[1, SABIC_GREEN]],
                cmin=0, cmax=100,
                line=dict(color="white", width=0.8),
                opacity=0.88,
            ),
            hovertemplate="%{text}<extra></extra>",
            name="供应商",
        ))

    # SABIC 上海基地标注
    fig.add_trace(go.Scattergeo(
        lat=[31.2222], lon=[121.5447],
        mode="markers+text",
        marker=dict(size=16, color=SABIC_GREEN, symbol="star",
                    line=dict(color="white", width=1.5)),
        text=["SABIC 上海"], textposition="top center",
        textfont=dict(size=10, color=SABIC_DARK),
        name="SABIC 基地",
        hovertemplate="SABIC 上海基地<extra></extra>",
    ))

    fig.update_geos(
        visible=False,               # 关掉默认底图，用我们自己的 GeoJSON
        resolution=50,
        scope="asia",
        showland=True,   landcolor="#f0f4f8",
        showocean=True,  oceancolor="#dbeafe",
        showlakes=True,  lakecolor="#dbeafe",
        showcountries=True, countrycolor="#94a3b8", countrywidth=0.5,
        showcoastlines=True, coastlinecolor="#94a3b8", coastlinewidth=0.5,
        center=dict(lat=36, lon=104),
        projection_type="mercator",
        lonaxis=dict(range=[72, 136]),
        lataxis=dict(range=[17, 54]),
    )
    fig.update_layout(
        font=_FONT, paper_bgcolor=BG,
        margin=dict(l=0, r=0, t=10, b=0),
        height=440,
        legend=dict(
            font=dict(size=11), x=0.01, y=0.98,
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#e2e8f0", borderwidth=1,
        ),
    )
    return fig


# ── 工具函数 ──────────────────────────────────────────────────────────
def _empty(msg: str, height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=msg, showarrow=False,
        xref="paper", yref="paper", x=0.5, y=0.5,
        font=dict(size=14, color="#9ba8bb"),
    )
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor="white",
        height=height,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"({r},{g},{b},{alpha})"
