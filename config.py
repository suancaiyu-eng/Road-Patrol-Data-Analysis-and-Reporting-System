"""
道路巡检数据分析与报告系统 - 配置模块
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 数据库
DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "inspection.db")}'

# 上传文件
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
REPORT_FOLDER = os.path.join(BASE_DIR, 'reports')
MODEL_FOLDER = os.path.join(BASE_DIR, 'models')
SAMPLE_FOLDER = os.path.join(BASE_DIR, 'sample_data')

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'tiff'}
ALLOWED_GPS_EXTENSIONS = {'csv', 'gpx', 'json'}
GPS_MISMATCH_THRESHOLD_METERS = 100

# YOLO模型配置
YOLO_MODEL_PATH = os.path.join(MODEL_FOLDER, 'road_defect.onnx')
YOLO_CONFIDENCE_THRESHOLD = 0.4
YOLO_IOU_THRESHOLD = 0.45

# 病害类型映射
DEFECT_TYPES = {
    0: {'name': '横向裂缝', 'code': 'crack_h', 'severity_default': 1},
    1: {'name': '纵向裂缝', 'code': 'crack_v', 'severity_default': 1},
    2: {'name': '网状裂缝', 'code': 'net_crack', 'severity_default': 2},
    3: {'name': '坑洼', 'code': 'pothole', 'severity_default': 2},
    4: {'name': '路面沉降', 'code': 'settlement', 'severity_default': 3},
}

SEVERITY_LEVELS = {1: '轻微', 2: '中等', 3: '严重'}

# 报告模板
REPORT_TEMPLATE = 'report_template.html'

# Flask
SECRET_KEY = 'road-inspection-secret-key-2025'
DEBUG = True
