"""
道路巡检数据分析与报告系统 - 数据库模型
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Inspection(db.Model):
    """巡检记录"""
    __tablename__ = 'inspections'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, comment='所属用户')
    title = db.Column(db.String(200), nullable=False, comment='巡检任务名称')
    road_section = db.Column(db.String(200), comment='巡检路段')
    inspector = db.Column(db.String(50), comment='巡检员')
    inspection_date = db.Column(db.Date, nullable=False, comment='巡检日期')
    weather = db.Column(db.String(20), comment='天气')
    notes = db.Column(db.Text, comment='备注')
    total_images = db.Column(db.Integer, default=0, comment='图像总数')
    total_defects = db.Column(db.Integer, default=0, comment='病害总数')
    created_at = db.Column(db.DateTime, default=datetime.now)

    images = db.relationship('Image', backref='inspection', lazy='dynamic',
                             cascade='all, delete-orphan')
    defects = db.relationship('Defect', backref='inspection', lazy='dynamic',
                              cascade='all, delete-orphan')
    gps_tracks = db.relationship('GPSTrack', backref='inspection', lazy='dynamic',
                                 cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'road_section': self.road_section,
            'inspector': self.inspector,
            'inspection_date': self.inspection_date.strftime('%Y-%m-%d'),
            'weather': self.weather,
            'notes': self.notes,
            'total_images': self.total_images,
            'total_defects': self.total_defects,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M'),
        }


class User(db.Model):
    """系统用户"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    inspections = db.relationship('Inspection', backref='user', lazy='dynamic')


class Image(db.Model):
    """巡检图像"""
    __tablename__ = 'images'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('inspections.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    gps_lat = db.Column(db.Float, comment='纬度')
    gps_lng = db.Column(db.Float, comment='经度')
    gps_alt = db.Column(db.Float, comment='海拔')
    captured_at = db.Column(db.DateTime, comment='拍摄时间')
    is_processed = db.Column(db.Boolean, default=False, comment='是否已检测')
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    defects = db.relationship('Defect', backref='image', lazy='dynamic',
                              cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'inspection_id': self.inspection_id,
            'filename': self.filename,
            'gps_lat': self.gps_lat,
            'gps_lng': self.gps_lng,
            'is_processed': self.is_processed,
        }


class Defect(db.Model):
    """道路病害"""
    __tablename__ = 'defects'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('inspections.id'), nullable=False)
    image_id = db.Column(db.Integer, db.ForeignKey('images.id'), nullable=False)
    defect_type = db.Column(db.String(30), comment='病害类型')
    severity = db.Column(db.Integer, default=1, comment='严重程度 1-3')
    confidence = db.Column(db.Float, comment='检测置信度')
    x = db.Column(db.Float, comment='边界框x')
    y = db.Column(db.Float, comment='边界框y')
    w = db.Column(db.Float, comment='边界框宽度')
    h = db.Column(db.Float, comment='边界框高度')
    gps_lat = db.Column(db.Float, comment='映射纬度')
    gps_lng = db.Column(db.Float, comment='映射经度')
    description = db.Column(db.String(200), comment='描述')
    maintenance_suggestion = db.Column(db.Text, comment='养护建议')
    detected_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'defect_type': self.defect_type,
            'severity': self.severity,
            'confidence': self.confidence,
            'x': self.x, 'y': self.y, 'w': self.w, 'h': self.h,
            'gps_lat': self.gps_lat, 'gps_lng': self.gps_lng,
            'description': self.description,
            'maintenance_suggestion': self.maintenance_suggestion,
        }


class GPSTrack(db.Model):
    """GPS轨迹点"""
    __tablename__ = 'gps_tracks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('inspections.id'), nullable=False)
    point_order = db.Column(db.Integer, nullable=False, comment='轨迹序号')
    lat = db.Column(db.Float, nullable=False, comment='纬度')
    lng = db.Column(db.Float, nullable=False, comment='经度')
    alt = db.Column(db.Float, comment='海拔(m)')
    speed = db.Column(db.Float, comment='速度(km/h)')
    timestamp = db.Column(db.DateTime, comment='定位时间')

    def to_dict(self):
        return {
            'id': self.id,
            'lat': self.lat,
            'lng': self.lng,
            'alt': self.alt,
            'speed': self.speed,
            'timestamp': self.timestamp.strftime('%H:%M:%S') if self.timestamp else None,
        }
