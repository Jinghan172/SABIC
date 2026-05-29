# SABIC 上海在线寻源系统 · Python 版

基于 **Streamlit + Plotly** 的化工原材料供应商智能匹配系统。

## 快速启动（本地）

```bash
# 1. 安装依赖（使用清华镜像加速）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 启动
streamlit run app.py
# 浏览器打开 http://localhost:8501
```

## Docker 部署

```bash
# 构建
docker build -t sabic-sourcing .

# 运行
docker run -d -p 8501:8501 --name sabic-sourcing sabic-sourcing

# 访问
http://服务器IP:8501
```

## 中国地图（可选）

下载 `china.json` 放到 `data/` 目录，地图功能才会渲染：

```
https://datav.aliyun.com/portal/school/atlas/area_selector
→ 选择"中国" → 下载完整版 JSON → 保存为 data/china.json
```

## API 接入（生产环境）

接入后在 `app.py` 顶部取消注释对应 import，并在环境变量或 `.env` 中设置：

| 接口 | 环境变量 | 用途 |
|------|----------|------|
| 天眼查 | `TYC_PROXY_URL` | 企业工商信息自动回填 |
| PubChem | `PUBCHEM_ENABLED=true` | 化学品 CAS/分子式实时查询 |
| 高德地图 | `AMAP_KEY` | 精确坐标 + 公路距离 |

详见 `proxy-functions/tianyancha/DEPLOY.md`。

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | Streamlit ≥ 1.35 |
| 可视化 | Plotly 5 |
| 中文搜索 | rapidfuzz + pypinyin |
| 表格处理 | pandas |
| Excel 导出 | openpyxl |
| 部署 | Docker / 任意 Python 服务器 |

## 目录结构

```
sabic-py/
├── app.py               # 主应用入口
├── requirements.txt     # Python 依赖
├── Dockerfile           # 容器化配置
├── .streamlit/
│   └── config.toml      # Streamlit 服务器配置
├── data/
│   ├── suppliers.json   # 供应商虚拟数据（30家）
│   ├── chemicals.json   # 化学品数据（15种）
│   ├── regions.json     # 省份地理数据
│   └── china.json       # 中国地图GeoJSON（需自行下载）
├── utils/
│   ├── scorer.py        # 五维评分算法
│   ├── matcher.py       # 搜索匹配（中文/拼音/CAS）
│   └── exporter.py      # Excel 导出
└── components/
    └── charts.py        # 所有 Plotly 图表
```
