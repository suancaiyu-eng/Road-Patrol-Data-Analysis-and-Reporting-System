"""
道路巡检数据分析与报告系统 - Flask 主应用
"""
import os
import csv
import re
import uuid
from datetime import datetime
from io import StringIO

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_from_directory, abort)
from werkzeug.utils import secure_filename

from config import (BASE_DIR, DATABASE_URI, UPLOAD_FOLDER, REPORT_FOLDER,
                    SECRET_KEY, DEBUG, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_GPS_EXTENSIONS)
from models import db, Inspection, Image, Defect, GPSTrack
from detector import detector
from modules.preprocess import preprocess_image
from modules.analysis import analyze_inspection, gps_error_info
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


def _save_detection_result(inspection, image, result):
    error = result.get('error')
    if error:
        return {'success': False, 'error': error, 'method': result.get('method')}

    defects = result.get('defects', [])
    if result.get('annotated_image') is None:
        return {'success': False, 'error': '检测未返回标注图像', 'method': result.get('method')}

    for d in defects:
        bbox = d.get('bbox', {})
        defect = Defect(
            inspection_id=inspection.id,
            image_id=image.id,
            defect_type=d.get('type', '未知'),
            severity=d.get('severity', 1),
            confidence=d.get('confidence', 0),
            x=bbox.get('x', 0), y=bbox.get('y', 0),
            w=bbox.get('w', 0), h=bbox.get('h', 0),
            gps_lat=image.gps_lat,
            gps_lng=image.gps_lng,
        )
        db.session.add(defect)

    image.is_processed = True
    inspection.total_defects = Defect.query.filter_by(inspection_id=inspection.id).count()

    return {
        'success': True,
        'defect_count': len(defects),
        'annotated_image': result.get('annotated_image'),
        'method': result.get('method'),
        'defects': defects,
    }


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
        uploaded_images = []
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
                        captured_at=_extract_image_capture_time(filepath),
                    )
                    db.session.add(image)
                    uploaded_images.append(image)
                    image_count += 1

        # 处理GPS数据上传
        gps_file = request.files.get('gps_file')
        gps_count = 0
        gps_mapped = 0
        gps_mapped = _apply_photo_gps_to_images(uploaded_images)

        if gps_file and gps_file.filename:
            ext = gps_file.filename.rsplit('.', 1)[-1].lower() if '.' in gps_file.filename else ''
            if ext in ALLOWED_GPS_EXTENSIONS:
                gps_count, _gps_points = _import_gps_csv(gps_file, inspection.id)
        else:
            gps_count = _create_gps_tracks_from_images(inspection.id, uploaded_images)

        inspection.total_images = image_count
        db.session.commit()

        flash(f'导入成功！图像 {image_count} 张，GPS轨迹点 {gps_count} 个，照片GPS定位 {gps_mapped} 张', 'success')
        return redirect(url_for('inspection_detail', inspection_id=inspection.id))

    return render_template('import_data.html')


def _import_gps_csv(file_obj, inspection_id):
    """解析GPS CSV文件，导入轨迹点"""
    count = 0
    gps_points = []
    try:
        content = file_obj.read().decode('utf-8')
        reader = csv.DictReader(StringIO(content))
        for i, row in enumerate(reader):
            lat = float(row.get('lat', row.get('latitude', 0)))
            lng = float(row.get('lng', row.get('lon', row.get('longitude', 0))))
            alt = float(row.get('alt', row.get('altitude', 0)) or 0)
            speed = float(row.get('speed', 0) or 0)
            ts_str = row.get('timestamp', row.get('time', ''))
            image_name = _gps_row_image_name(row)

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
            gps_points.append({
                'lat': lat,
                'lng': lng,
                'alt': alt,
                'speed': speed,
                'timestamp': ts,
                'image_name': image_name,
            })
            count += 1
    except Exception as e:
        print(f"GPS导入错误: {e}")

    return count, gps_points


def _gps_row_image_name(row):
    for key in ['filename', 'image', 'image_name', 'photo', 'photo_name', 'file']:
        value = row.get(key)
        if value:
            return os.path.basename(value.strip()).lower()
    return None


def _extract_gps_from_image(image_path):
    return _extract_exif_gps(image_path) or _extract_overlay_gps(image_path)


def _extract_image_capture_time(image_path):
    try:
        from PIL import Image as PILImage
    except Exception:
        return None

    try:
        with PILImage.open(image_path) as img:
            exif = img.getexif()
            return _extract_exif_datetime(exif) if exif else None
    except Exception:
        return None


def _extract_exif_gps(image_path):
    try:
        from PIL import Image as PILImage, ExifTags
    except Exception:
        return None

    try:
        with PILImage.open(image_path) as img:
            exif = img.getexif()
            if not exif:
                return None

            gps_tag = next((k for k, v in ExifTags.TAGS.items() if v == 'GPSInfo'), None)
            gps_info = exif.get_ifd(gps_tag) if gps_tag else None
            if not gps_info:
                return None

            gps_names = ExifTags.GPSTAGS
            decoded = {gps_names.get(k, k): v for k, v in gps_info.items()}
            lat = _dms_to_decimal(decoded.get('GPSLatitude'), decoded.get('GPSLatitudeRef'))
            lng = _dms_to_decimal(decoded.get('GPSLongitude'), decoded.get('GPSLongitudeRef'))
            if lat is None or lng is None:
                return None

            return {
                'lat': lat,
                'lng': lng,
                'alt': _rational_to_float(decoded.get('GPSAltitude')),
                'timestamp': _extract_exif_datetime(exif),
            }
    except Exception:
        return None


def _extract_exif_datetime(exif):
    try:
        from PIL import ExifTags
    except Exception:
        return None

    tag_by_name = {name: key for key, name in ExifTags.TAGS.items()}
    for name in ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']:
        value = exif.get(tag_by_name.get(name))
        if value:
            try:
                return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
            except ValueError:
                pass
    return None


def _dms_to_decimal(value, ref):
    if not value:
        return None

    degrees = _rational_to_float(value[0])
    minutes = _rational_to_float(value[1])
    seconds = _rational_to_float(value[2])
    if degrees is None or minutes is None or seconds is None:
        return None

    decimal = degrees + minutes / 60 + seconds / 3600
    if ref in ['S', 'W']:
        decimal = -decimal
    return round(decimal, 8)


def _rational_to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except TypeError:
        numerator, denominator = value
        return numerator / denominator if denominator else None


def _extract_overlay_gps(image_path):
    text = _read_top_right_text(image_path)
    if not text:
        return None
    return _parse_gps_text(text)


def _read_top_right_text(image_path):
    try:
        from PIL import Image as PILImage, ImageOps, ImageEnhance
        import pytesseract
    except Exception:
        return None

    try:
        with PILImage.open(image_path) as img:
            width, height = img.size
            crop = img.crop((int(width * 0.45), 0, width, int(height * 0.28)))
            crop = ImageOps.grayscale(crop)
            crop = ImageEnhance.Contrast(crop).enhance(2.0)
            return pytesseract.image_to_string(crop, config='--psm 6')
    except Exception:
        return None


def _parse_gps_text(text):
    normalized = text.replace('，', ',').replace('：', ':')

    lat_match = re.search(r'(?:lat|latitude|纬度)\s*[:=]?\s*(-?\d+(?:\.\d+)?)', normalized, re.I)
    lng_match = re.search(r'(?:lng|lon|longitude|经度)\s*[:=]?\s*(-?\d+(?:\.\d+)?)', normalized, re.I)
    if lat_match and lng_match:
        lat, lng = float(lat_match.group(1)), float(lng_match.group(1))
        if _valid_lat_lng(lat, lng):
            return {'lat': lat, 'lng': lng, 'alt': None, 'timestamp': None}

    numbers = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', normalized)]
    for i in range(len(numbers) - 1):
        lat, lng = numbers[i], numbers[i + 1]
        if _valid_lat_lng(lat, lng):
            return {'lat': lat, 'lng': lng, 'alt': None, 'timestamp': None}

    return None


def _valid_lat_lng(lat, lng):
    return -90 <= lat <= 90 and -180 <= lng <= 180


def _apply_gps_to_image(image, point):
    image.gps_lat = point['lat']
    image.gps_lng = point['lng']
    image.gps_alt = point.get('alt')
    if point.get('timestamp'):
        image.captured_at = point['timestamp']

    for defect in Defect.query.filter_by(image_id=image.id).all():
        defect.gps_lat = image.gps_lat
        defect.gps_lng = image.gps_lng


def _apply_photo_gps_to_images(images):
    mapped = 0
    for image in images:
        point = _extract_gps_from_image(image.filepath)
        if point:
            _apply_gps_to_image(image, point)
            mapped += 1
    return mapped


def _create_gps_tracks_from_images(inspection_id, images=None):
    """Use photo GPS as a track when photos are the GPS source."""
    if GPSTrack.query.filter_by(inspection_id=inspection_id).first():
        return 0

    images = images or Image.query.filter_by(inspection_id=inspection_id).order_by(Image.id).all()
    count = 0
    for image in images:
        point = None
        if image.gps_lat is None or image.gps_lng is None:
            point = _extract_gps_from_image(image.filepath)
            if point:
                _apply_gps_to_image(image, point)

        lat = image.gps_lat
        lng = image.gps_lng
        if lat is None or lng is None:
            continue

        track = GPSTrack(
            inspection_id=inspection_id,
            point_order=count,
            lat=lat,
            lng=lng,
            alt=image.gps_alt if image.gps_alt is not None else (point or {}).get('alt'),
            speed=0,
            timestamp=image.captured_at or (point or {}).get('timestamp'),
        )
        db.session.add(track)
        count += 1

    return count


def _assign_gps_to_images(inspection_id, images=None, gps_points=None):
    images = images or Image.query.filter_by(inspection_id=inspection_id).order_by(Image.id).all()
    if not images:
        return 0

    mapped = 0
    gps_points = gps_points if gps_points is not None else [
        {
            'lat': t.lat,
            'lng': t.lng,
            'alt': t.alt,
            'speed': t.speed,
            'timestamp': t.timestamp,
            'image_name': None,
        }
        for t in GPSTrack.query.filter_by(inspection_id=inspection_id).order_by(GPSTrack.point_order).all()
    ]
    if not gps_points:
        return 0

    points_by_name = {p['image_name']: p for p in gps_points if p.get('image_name')}
    if points_by_name:
        for image in images:
            point = points_by_name.get(os.path.basename(image.filename).lower())
            if point:
                _apply_gps_to_image(image, point)
                mapped += 1

    if mapped:
        return mapped

    timed_points = [p for p in gps_points if p.get('timestamp')]
    timed_images = [image for image in images if image.captured_at]
    if timed_points and timed_images:
        for image in timed_images:
            point = min(timed_points, key=lambda p: abs((p['timestamp'] - image.captured_at).total_seconds()))
            _apply_gps_to_image(image, point)
            mapped += 1

    return mapped


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
    for image in images:
        image.url = url_for('uploaded_file', filename=os.path.basename(image.filepath))
    has_gps = GPSTrack.query.filter_by(inspection_id=inspection_id).first() is not None
    has_image_gps = any(image.gps_lat is not None and image.gps_lng is not None for image in images)

    return render_template('inspection_detail.html',
                           inspection=inspection,
                           stats=stats,
                           images=images,
                           has_gps=has_gps,
                           has_image_gps=has_image_gps)


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
        if image.inspection_id != inspection.id:
            abort(404)

        # 执行检测
        result = detector.detect(image.filepath)
        response = _save_detection_result(inspection, image, result)
        db.session.commit()

        status_code = 200 if response['success'] else 422
        return jsonify(response), status_code

    return render_template('detect.html', inspection=inspection, images=images, detector=detector)


@app.route('/detect/<int:inspection_id>/batch', methods=['POST'])
def detect_batch(inspection_id):
    """批量检测所有未处理图像"""
    inspection = Inspection.query.get_or_404(inspection_id)
    images = Image.query.filter_by(inspection_id=inspection_id, is_processed=False).all()
    total_defects = 0
    failed = []
    processed = 0

    for image in images:
        result = detector.detect(image.filepath)
        response = _save_detection_result(inspection, image, result)
        if response['success']:
            processed += 1
            total_defects += response['defect_count']
        else:
            failed.append({'image_id': image.id, 'filename': image.filename, 'error': response['error']})

    inspection.total_defects = Defect.query.filter_by(inspection_id=inspection_id).count()
    db.session.commit()

    return jsonify({
        'success': len(failed) == 0,
        'processed': processed,
        'failed': failed,
        'total_defects': total_defects,
    }), 200 if not failed else 207


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
    defect_points = []
    for defect in defects:
        if defect.gps_lat is None or defect.gps_lng is None:
            continue
        item = defect.to_dict()
        item.update(gps_error_info(defect.gps_lat, defect.gps_lng, tracks))
        defect_points.append(item)

    return render_template('map_view.html',
                           inspection=inspection,
                           track_points=track_points,
                           defect_points=defect_points)


@app.route('/inspection/<int:inspection_id>/assign-gps', methods=['POST'])
def assign_gps_view(inspection_id):
    inspection = Inspection.query.get_or_404(inspection_id)
    images = Image.query.filter_by(inspection_id=inspection.id).order_by(Image.id).all()
    mapped = _apply_photo_gps_to_images(images)
    track_count = _create_gps_tracks_from_images(inspection.id)
    db.session.commit()
    if mapped or track_count:
        flash(f'已为 {mapped} 张图像匹配GPS定位，补充GPS轨迹点 {track_count} 个', 'success')
    else:
        flash('未找到可匹配的GPS定位或已有轨迹无需重复生成', 'warning')
    return redirect(url_for('inspection_detail', inspection_id=inspection.id))


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
