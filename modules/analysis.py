"""
道路巡检数据分析与报告系统 - 统计分析模块
"""
import math

from config import DEFECT_TYPES, GPS_MISMATCH_THRESHOLD_METERS, SEVERITY_LEVELS


def analyze_inspection(inspection, defects_query, images_query, gps_tracks_query) -> dict:
    """
    对单次巡检进行多维度统计分析
    返回包含所有统计数据的字典，供前端图表和报告使用
    """
    defects = defects_query.all()
    images = images_query.all()
    gps_tracks = gps_tracks_query.all()

    total_images = len(images)
    total_defects = len(defects)
    processed_images = len([i for i in images if i.is_processed])

    stats = {
        'overview': {
            'total_images': total_images,
            'processed_images': processed_images,
            'total_defects': total_defects,
            'defect_density': round(total_defects / max(total_images, 1), 2),
        },
        'type_distribution': _count_by_type(defects),
        'severity_distribution': _count_by_severity(defects),
        'confidence_stats': _confidence_stats(defects),
        'defect_list': [_defect_to_item(d, images, gps_tracks) for d in defects],
        'gps_summary': _gps_summary(gps_tracks),
        'maintenance_summary': _maintenance_summary(defects),
    }

    return stats


def _count_by_type(defects) -> dict:
    """按病害类型统计"""
    type_count = {}
    for d in defects:
        name = d.defect_type or '未分类'
        type_count[name] = type_count.get(name, 0) + 1

    return {
        'labels': list(type_count.keys()),
        'values': list(type_count.values()),
        'total': sum(type_count.values()),
    }


def _count_by_severity(defects) -> dict:
    """按严重程度统计"""
    sev_count = {1: 0, 2: 0, 3: 0}
    for d in defects:
        sev_count[d.severity] = sev_count.get(d.severity, 0) + 1

    return {
        'labels': [SEVERITY_LEVELS.get(k, f'级别{k}') for k in [1, 2, 3]],
        'values': [sev_count[1], sev_count[2], sev_count[3]],
        'total': sum(sev_count.values()),
    }


def _confidence_stats(defects) -> dict:
    """置信度统计"""
    if not defects:
        return {'avg': 0, 'max': 0, 'min': 0, 'count_high': 0, 'count_low': 0}

    confs = [d.confidence or 0 for d in defects]
    return {
        'avg': round(sum(confs) / len(confs), 3),
        'max': round(max(confs), 3),
        'min': round(min(confs), 3),
        'count_high': sum(1 for c in confs if c >= 0.7),
        'count_medium': sum(1 for c in confs if 0.4 <= c < 0.7),
        'count_low': sum(1 for c in confs if c < 0.4),
    }


def _defect_to_item(defect, images, gps_tracks) -> dict:
    """病害记录转前端展示格式"""
    image = next((i for i in images if i.id == defect.image_id), None)
    gps_status = gps_error_info(defect.gps_lat, defect.gps_lng, gps_tracks)
    gps_text = f'{defect.gps_lat:.6f}, {defect.gps_lng:.6f}' if defect.gps_lat is not None and defect.gps_lng is not None else '未定位'
    return {
        'id': defect.id,
        'type': defect.defect_type,
        'severity': defect.severity,
        'severity_label': SEVERITY_LEVELS.get(defect.severity, '未知'),
        'confidence': defect.confidence,
        'image_name': image.filename if image else '未知',
        'gps': gps_text,
        'gps_error': gps_status['gps_error'],
        'gps_error_distance': gps_status['distance_meters'],
        'description': defect.description or '',
    }


def gps_error_info(lat, lng, gps_tracks) -> dict:
    if lat is None or lng is None or not gps_tracks:
        return {'gps_error': False, 'distance_meters': None}

    nearest = min(
        (_distance_meters(lat, lng, track.lat, track.lng) for track in gps_tracks),
        default=None,
    )
    if nearest is None:
        return {'gps_error': False, 'distance_meters': None}

    return {
        'gps_error': nearest > GPS_MISMATCH_THRESHOLD_METERS,
        'distance_meters': round(nearest, 1),
    }


def _distance_meters(lat1, lng1, lat2, lng2):
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _gps_summary(gps_tracks) -> dict:
    """GPS轨迹摘要"""
    if not gps_tracks:
        return {'point_count': 0, 'has_track': False}

    lats = [p.lat for p in gps_tracks]
    lngs = [p.lng for p in gps_tracks]
    speeds = [p.speed for p in gps_tracks if p.speed]

    return {
        'point_count': len(gps_tracks),
        'has_track': True,
        'center_lat': round(sum(lats) / len(lats), 6),
        'center_lng': round(sum(lngs) / len(lngs), 6),
        'bounds': {
            'min_lat': round(min(lats), 6),
            'max_lat': round(max(lats), 6),
            'min_lng': round(min(lngs), 6),
            'max_lng': round(max(lngs), 6),
        },
        'avg_speed': round(sum(speeds) / len(speeds), 1) if speeds else 0,
    }


def _maintenance_summary(defects) -> list:
    """生成养护建议摘要"""
    suggestions = {
        '轻微': [],
        '中等': [],
        '严重': [],
    }

    for d in defects:
        level = SEVERITY_LEVELS.get(d.severity, '未知')
        suggestions[level].append(d.defect_type or '未分类')

    result = []
    if suggestions['严重']:
        result.append({
            'level': '紧急处理',
            'count': len(suggestions['严重']),
            'advice': '建议立即进行修补，对严重坑洼和宽裂缝（>5mm）进行灌缝或挖补处理，'
                      '必要时设置警示标志限制通行。',
        })
    if suggestions['中等']:
        result.append({
            'level': '计划修复',
            'count': len(suggestions['中等']),
            'advice': '列入月度养护计划，对中等裂缝进行密封处理，防止雨水渗透扩大病害。',
        })
    if suggestions['轻微']:
        result.append({
            'level': '持续监测',
            'count': len(suggestions['轻微']),
            'advice': '纳入日常巡查范围，定期观察病害发展趋势，做好预防性养护。',
        })

    return result
