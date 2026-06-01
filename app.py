"""
道路巡检数据分析与报告系统 - Flask 主应用
"""
import os
import csv
import uuid
from datetime import datetime
from io import StringIO

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_from_directory)
from werkzeug.utils import secure_filename

from config import (BASE_DIR, DATABASE_URI, UPLOAD_FOLDER, REPORT_FOLDER,
                    SECRET_KEY, DEBUG, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_GPS_EXTENSIONS)
from models import db, Inspection, Image, Defect, GPSTrack
from detector import detector
from modules.preprocess import preprocess_image
from modules.analysis import analyze_inspection
from modules.report import generate_report, save_report


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    db.init_app(app)

    # 创建必要目录
    for folder in [UPLOAD_FOLDER, REPORT_FOLDER]:
        os.makedirs(folder, exist_ok=True)

    with app.app_context():
        db.create_all()

    return app


app = create_app()


# ============================================================
# 首页 - 仪表盘
# ============================================================
@app.route('/')
def index():
    inspections = Inspection.query.order_by(Inspection.created_at.desc()).limit(10).all()
    total_inspections = Inspection.query.count()
    total_defects = Defect.query.count()
    total_images = Image.query.count()
    avg_defects = round(total_defects / max(total_inspections, 1), 1)

    # 最近巡检统计
    recent_stats = []
    for insp in Inspection.query.order_by(Inspection.inspection_date.desc()).limit(7).all():
        recent_stats.append({
            'date': str(insp.inspection_date),
            'defects': insp.total_defects,
            'images': insp.total_images,
        })

    # 病害类型汇总
    defect_summary = {}
    for d in Defect.query.all():
        name = d.defect_type or '未分类'
        defect_summary[name] = defect_summary.get(name, 0) + 1

    return render_template('index.html',
                           inspections=inspections,
                           total_inspections=total_inspections,
                           total_defects=total_defects,
                           total_images=total_images,
                           avg_defects=avg_defects,
                           recent_stats=recent_stats,
                           defect_summary=defect_summary)


# ============================================================
# 数据导入
# ============================================================
@app.route('/import', methods=['GET', 'POST'])
def import_data():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        road_section = request.form.get('road_section', '').strip()
        inspector = request.form.get('inspector', '').strip()
        inspection_date = request.form.get('inspection_date', '')
        weather = request.form.get('weather', '').strip()
        notes = request.form.get('notes', '').strip()

        if not title or not inspection_date:
            flash('巡检任务名称和日期不能为空', 'danger')
            return redirect(url_for('import_data'))

        try:
            insp_date = datetime.strptime(inspection_date, '%Y-%m-%d').date()
        except ValueError:
            flash('日期格式错误', 'danger')
            return redirect(url_for('import_data'))

        inspection = Inspection(
            title=title,
            road_section=road_section,
            inspector=inspector,
            inspection_date=insp_date,
            weather=weather,
            notes=notes,
        )
        db.session.add(inspection)
        db.session.flush()  # 获取 inspection.id

        # 处理图像上传
        images = request.files.getlist('images')
        image_count = 0
        for img_file in images:
            if img_file and img_file.filename:
                ext = img_file.filename.rsplit('.', 1)[-1].lower() if '.' in img_file.filename else ''
                if ext in ALLOWED_IMAGE_EXTENSIONS:
                    filename = secure_filename(f"{uuid.uuid4().hex[:8]}_{img_file.filename}")
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    img_file.save(filepath)

                    image = Image(
                        inspection_id=inspection.id,
                        filename=img_file.filename,
                        filepath=filepath,
                    )
                    db.session.add(image)
                    image_count += 1

        # 处理GPS数据上传
        gps_file = request.files.get('gps_file')
        gps_count = 0
        if gps_file and gps_file.filename:
            ext = gps_file.filename.rsplit('.', 1)[-1].lower() if '.' in gps_file.filename else ''
            if ext in ALLOWED_GPS_EXTENSIONS:
                gps_count = _import_gps_csv(gps_file, inspection.id)

        inspection.total_images = image_count
        db.session.commit()

        flash(f'导入成功！图像 {image_count} 张，GPS轨迹点 {gps_count} 个', 'success')
        return redirect(url_for('inspection_detail', inspection_id=inspection.id))

    return render_template('import_data.html')


def _import_gps_csv(file_obj, inspection_id) -> int:
    """解析GPS CSV文件，导入轨迹点"""
    count = 0
    try:
        content = file_obj.read().decode('utf-8')
        reader = csv.DictReader(StringIO(content))
        for i, row in enumerate(reader):
            lat = float(row.get('lat', row.get('latitude', 0)))
            lng = float(row.get('lng', row.get('lon', row.get('longitude', 0))))
            alt = float(row.get('alt', row.get('altitude', 0)) or 0)
            speed = float(row.get('speed', 0) or 0)
            ts_str = row.get('timestamp', row.get('time', ''))

            ts = None
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                except ValueError:
                    pass

            track = GPSTrack(
                inspection_id=inspection_id,
                point_order=i,
                lat=lat, lng=lng, alt=alt, speed=speed, timestamp=ts,
            )
            db.session.add(track)
            count += 1
    except Exception as e:
        print(f"GPS导入错误: {e}")

    return count


# ============================================================
# 巡检记录列表
# ============================================================
@app.route('/inspections')
def inspection_list():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    pagination = Inspection.query.order_by(Inspection.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return render_template('inspection_list.html', inspections=pagination.items, pagination=pagination)


# ============================================================
# 巡检详情
# ============================================================
@app.route('/inspection/<int:inspection_id>')
def inspection_detail(inspection_id):
    inspection = Inspection.query.get_or_404(inspection_id)

    # 统计分析
    stats = analyze_inspection(
        inspection,
        Defect.query.filter_by(inspection_id=inspection_id),
        Image.query.filter_by(inspection_id=inspection_id),
        GPSTrack.query.filter_by(inspection_id=inspection_id),
    )

    images = Image.query.filter_by(inspection_id=inspection_id).all()
    has_gps = GPSTrack.query.filter_by(inspection_id=inspection_id).first() is not None

    return render_template('inspection_detail.html',
                           inspection=inspection,
                           stats=stats,
                           images=images,
                           has_gps=has_gps)


# ============================================================
# 病害检测
# ============================================================
@app.route('/detect/<int:inspection_id>', methods=['GET', 'POST'])
def detect_defects(inspection_id):
    inspection = Inspection.query.get_or_404(inspection_id)
    images = Image.query.filter_by(inspection_id=inspection_id).all()

    if request.method == 'POST':
        image_id = request.form.get('image_id', type=int)
        image = Image.query.get_or_404(image_id)

        # 执行检测
        result = detector.detect(image.filepath)
        defects = result.get('defects', [])

        # 保存检测结果
        for d in defects:
            bbox = d.get('bbox', {})
            defect = Defect(
                inspection_id=inspection_id,
                image_id=image.id,
                defect_type=d.get('type', '未知'),
                severity=d.get('severity', 1),
                confidence=d.get('confidence', 0),
                x=bbox.get('x', 0), y=bbox.get('y', 0),
                w=bbox.get('w', 0), h=bbox.get('h', 0),
            )
            db.session.add(defect)

        image.is_processed = True
        inspection.total_defects = Defect.query.filter_by(inspection_id=inspection_id).count()
        db.session.commit()

        return jsonify({
            'success': True,
            'defect_count': len(defects),
            'annotated_image': result.get('annotated_image'),
            'method': result.get('method'),
            'defects': defects,
        })

    return render_template('detect.html', inspection=inspection, images=images, detector=detector)


@app.route('/detect/<int:inspection_id>/batch', methods=['POST'])
def detect_batch(inspection_id):
    """批量检测所有未处理图像"""
    images = Image.query.filter_by(inspection_id=inspection_id, is_processed=False).all()
    total_defects = 0

    for image in images:
        result = detector.detect(image.filepath)
        for d in result.get('defects', []):
            bbox = d.get('bbox', {})
            defect = Defect(
                inspection_id=inspection_id,
                image_id=image.id,
                defect_type=d.get('type', '未知'),
                severity=d.get('severity', 1),
                confidence=d.get('confidence', 0),
                x=bbox.get('x', 0), y=bbox.get('y', 0),
                w=bbox.get('w', 0), h=bbox.get('h', 0),
            )
            db.session.add(defect)
            total_defects += 1

        image.is_processed = True

    inspection = Inspection.query.get(inspection_id)
    inspection.total_defects = Defect.query.filter_by(inspection_id=inspection_id).count()
    db.session.commit()

    return jsonify({'success': True, 'processed': len(images), 'total_defects': total_defects})


# ============================================================
# 图像预处理
# ============================================================
@app.route('/preprocess/<int:image_id>')
def preprocess_view(image_id):
    image = Image.query.get_or_404(image_id)
    result = preprocess_image(image.filepath)
    return jsonify(result)


# ============================================================
# 统计分析
# ============================================================
@app.route('/analysis/<int:inspection_id>')
def analysis_view(inspection_id):
    inspection = Inspection.query.get_or_404(inspection_id)
    stats = analyze_inspection(
        inspection,
        Defect.query.filter_by(inspection_id=inspection_id),
        Image.query.filter_by(inspection_id=inspection_id),
        GPSTrack.query.filter_by(inspection_id=inspection_id),
    )
    return render_template('analysis.html', inspection=inspection, stats=stats)


# ============================================================
# 地图视图
# ============================================================
@app.route('/map/<int:inspection_id>')
def map_view(inspection_id):
    inspection = Inspection.query.get_or_404(inspection_id)
    tracks = GPSTrack.query.filter_by(inspection_id=inspection_id).order_by(GPSTrack.point_order).all()
    defects = Defect.query.filter_by(inspection_id=inspection_id).all()

    track_points = [t.to_dict() for t in tracks]
    defect_points = [d.to_dict() for d in defects if d.gps_lat and d.gps_lng]

    return render_template('map_view.html',
                           inspection=inspection,
                           track_points=track_points,
                           defect_points=defect_points)


# ============================================================
# 报告生成
# ============================================================
@app.route('/report/<int:inspection_id>')
def report_view(inspection_id):
    inspection = Inspection.query.get_or_404(inspection_id)
    stats = analyze_inspection(
        inspection,
        Defect.query.filter_by(inspection_id=inspection_id),
        Image.query.filter_by(inspection_id=inspection_id),
        GPSTrack.query.filter_by(inspection_id=inspection_id),
    )
    report_html = generate_report(inspection, stats)
    return report_html


@app.route('/report/<int:inspection_id>/download')
def report_download(inspection_id):
    """下载报告HTML文件"""
    inspection = Inspection.query.get_or_404(inspection_id)
    stats = analyze_inspection(
        inspection,
        Defect.query.filter_by(inspection_id=inspection_id),
        Image.query.filter_by(inspection_id=inspection_id),
        GPSTrack.query.filter_by(inspection_id=inspection_id),
    )
    report_html = generate_report(inspection, stats)
    filepath = save_report(report_html, inspection_id)

    filename = os.path.basename(filepath)
    return send_from_directory(REPORT_FOLDER, filename, as_attachment=True)


# ============================================================
# 预览上传的图像
# ============================================================
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ============================================================
# 删除
# ============================================================
@app.route('/inspection/<int:inspection_id>/delete', methods=['POST'])
def delete_inspection(inspection_id):
    inspection = Inspection.query.get_or_404(inspection_id)
    db.session.delete(inspection)
    db.session.commit()
    flash('巡检记录已删除', 'success')
    return redirect(url_for('inspection_list'))


# ============================================================
# API: 获取统计数据JSON
# ============================================================
@app.route('/api/stats/<int:inspection_id>')
def api_stats(inspection_id):
    inspection = Inspection.query.get_or_404(inspection_id)
    stats = analyze_inspection(
        inspection,
        Defect.query.filter_by(inspection_id=inspection_id),
        Image.query.filter_by(inspection_id=inspection_id),
        GPSTrack.query.filter_by(inspection_id=inspection_id),
    )
    return jsonify(stats)


if __name__ == '__main__':
    app.run(debug=DEBUG, host='0.0.0.0', port=5000)
