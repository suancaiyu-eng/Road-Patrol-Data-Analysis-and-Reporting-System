# Road Patrol Data Analysis and Reporting System

基于 Flask 和 OpenCV 的道路巡检数据分析与报告生成系统，支持巡检数据导入、道路病害检测、统计分析、地图展示和 HTML 报告生成。

## 功能特性

- 账号注册、登录和退出
- 不同账号的数据相互隔离
- 创建巡检任务并上传道路图像和 GPS CSV 数据
- OpenCV 传统图像处理病害检测
- YOLO ONNX 模型检测预留接口
- 病害类型、严重程度、置信度和 GPS 轨迹统计
- 地图轨迹展示
- HTML 巡检报告在线预览和下载
- 兼容 Windows 中文路径下的图片读取

## 技术栈

- Python 3
- Flask
- Flask-SQLAlchemy
- SQLite
- OpenCV
- NumPy
- Bootstrap 5
- Leaflet
- Chart.js

## 快速启动

安装依赖：

```bash
pip install -r requirements.txt
```

启动服务：

```bash
python app.py
```

浏览器访问：

```text
http://127.0.0.1:5000
```

首次进入系统需要先注册账号。系统会自动创建本地 SQLite 数据库 `inspection.db`。

## 账号与数据隔离

系统使用登录会话识别当前用户。每个账号只能查看和操作自己创建的巡检记录，包括：

- 巡检列表
- 巡检详情
- 上传图片
- 病害检测结果
- 统计分析
- 地图视图
- 报告生成

访问其他账号的数据会返回 404。

## 目录结构

```text
.
├── app.py                  # Flask 主应用和路由
├── config.py               # 项目配置
├── detector.py             # 病害检测逻辑
├── models.py               # 数据库模型
├── modules/
│   ├── analysis.py         # 统计分析
│   ├── preprocess.py       # 图像预处理
│   └── report.py           # 报告生成
├── templates/              # 页面模板
├── uploads/                # 上传图片目录，运行时生成
├── reports/                # 报告输出目录，运行时生成
└── requirements.txt        # Python 依赖
```

## 检测模式

默认情况下，如果未提供 `models/road_defect.onnx`，系统会使用 OpenCV 传统检测模式。

如果需要启用 YOLO ONNX 检测：

1. 创建 `models` 目录。
2. 放入模型文件 `models/road_defect.onnx`。
3. 确认已安装 `onnxruntime`。

```bash
pip install onnxruntime
```

## 使用流程

1. 注册并登录账号。
2. 进入“数据导入”，创建巡检任务。
3. 上传道路图片，可选上传 GPS CSV。
4. 进入巡检详情，查看图像和基础信息。
5. 点击“病害检测”执行单张或批量检测。
6. 查看统计分析、地图视图和巡检报告。

## GPS CSV 格式

支持字段名：

```csv
lat,lng,alt,speed,timestamp
31.1,121.1,5,30,2026-06-01T10:00:00
31.2,121.2,5,35,2026-06-01T10:01:00
```

经纬度字段也兼容：

- `lat` 或 `latitude`
- `lng`、`lon` 或 `longitude`
- `alt` 或 `altitude`
- `timestamp` 或 `time`

## 注意事项

- `inspection.db`、`uploads/` 和 `reports/` 是运行时数据，不建议提交到 Git。
- 默认 Flask `SECRET_KEY` 仅适合本地开发，生产环境请改为安全随机值。
- Flask 内置开发服务器不适合生产部署。
