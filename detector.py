"""
道路巡检数据分析与报告系统 - 病害检测模块

支持两种检测模式：
1. YOLO ONNX 深度学习检测（优先，需模型文件）
2. OpenCV 传统图像处理检测（回退方案，霍夫线检测+轮廓分析）
"""
import os
import cv2
import numpy as np
from config import YOLO_MODEL_PATH, YOLO_CONFIDENCE_THRESHOLD, YOLO_IOU_THRESHOLD, DEFECT_TYPES


class RoadDefectDetector:
    """道路病害检测器"""

    def __init__(self):
        self.yolo_available = False
        self.session = None
        self.input_name = None
        self.output_names = None
        self._load_yolo_model()

    def _load_yolo_model(self):
        """尝试加载YOLO ONNX模型"""
        if os.path.exists(YOLO_MODEL_PATH):
            try:
                import onnxruntime as ort
                self.session = ort.InferenceSession(YOLO_MODEL_PATH)
                self.input_name = self.session.get_inputs()[0].name
                self.output_names = [o.name for o in self.session.get_outputs()]
                self.yolo_available = True
                print(f"[检测器] YOLO模型已加载: {YOLO_MODEL_PATH}")
            except Exception as e:
                print(f"[检测器] YOLO模型加载失败: {e}，回退到OpenCV模式")
        else:
            print(f"[检测器] 未找到YOLO模型文件，使用OpenCV传统检测模式")

    def detect(self, image_path: str) -> dict:
        if self.yolo_available:
            return self._detect_yolo(image_path)
        else:
            return self._detect_opencv(image_path)

    def _detect_yolo(self, image_path: str) -> dict:
        """YOLO ONNX推理"""
        import onnxruntime as ort
        img = _read_image(image_path)
        if img is None:
            return {'defects': [], 'annotated_image': None, 'method': 'yolo', 'error': '无法读取图像'}
        h, w = img.shape[:2]
        input_img = cv2.resize(img, (640, 640))
        input_img = input_img.transpose(2, 0, 1).astype(np.float32) / 255.0
        input_img = np.expand_dims(input_img, axis=0)
        outputs = self.session.run(self.output_names, {self.input_name: input_img})
        predictions = outputs[0]
        defects = []
        for pred in predictions[0]:
            x1, y1, x2, y2, conf, cls_id = pred
            if conf < YOLO_CONFIDENCE_THRESHOLD:
                continue
            x1, x2 = x1 * w / 640, x2 * w / 640
            y1, y2 = y1 * h / 640, y2 * h / 640
            bw, bh = x2 - x1, y2 - y1
            cls_id = int(cls_id)
            defect_info = DEFECT_TYPES.get(cls_id, {'name': f'未知病害_{cls_id}', 'severity_default': 1})
            defects.append({
                'type': defect_info['name'], 'type_code': defect_info.get('code', 'unknown'),
                'confidence': round(float(conf), 3),
                'bbox': {'x': round(x1), 'y': round(y1), 'w': round(bw), 'h': round(bh)},
                'severity': self._estimate_severity(bw * bh, defect_info.get('severity_default', 1)),
                'area_pixels': round(bw * bh), 'source': 'yolo',
            })
        defects = self._apply_nms(defects, YOLO_IOU_THRESHOLD)
        annotated = img.copy()
        for d in defects:
            b = d['bbox']
            color = {1: (0, 255, 0), 2: (0, 255, 255), 3: (0, 0, 255)}.get(d['severity'], (255, 0, 0))
            cv2.rectangle(annotated, (b['x'], b['y']), (b['x'] + b['w'], b['y'] + b['h']), color, 2)
            label = f"{d['type']} {d['confidence']:.2f}"
            cv2.putText(annotated, label, (b['x'], b['y'] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        annotated_b64 = self._img_to_base64(annotated)
        return {'defects': defects, 'defect_count': len(defects), 'annotated_image': annotated_b64, 'method': 'yolo'}

    def _detect_opencv(self, image_path: str) -> dict:
        """双策略检测：霍夫线检测（裂缝）+ 轮廓分析（坑洼/块状病害）"""
        img = _read_image(image_path)
        if img is None:
            return {'defects': [], 'annotated_image': None, 'method': 'opencv', 'error': '无法读取图像'}
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        annotated = img.copy()

        # 更强的去噪
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        # 中值滤波去除椒盐噪声
        denoised = cv2.medianBlur(blurred, 5)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        defects = []

        # 策略1: 霍夫线检测裂缝（高阈值，只找明显的线）
        edges_for_lines = cv2.Canny(enhanced, 30, 90)
        # 形态学去除小噪点
        kernel_clean = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        edges_clean = cv2.morphologyEx(edges_for_lines, cv2.MORPH_OPEN, kernel_clean)

        lines = cv2.HoughLinesP(edges_clean, 1, np.pi / 180, threshold=60, minLineLength=80, maxLineGap=20)
        line_clusters = self._cluster_lines(lines, w, h) if lines is not None else []

        for cluster in line_clusters:
            if cluster['total_length'] < 80:
                continue
            x, y, bw, bh = cluster['bbox']
            aspect = bw / max(bh, 1)
            if aspect > 3:
                dtype = '横向裂缝'
            elif aspect < 0.33:
                dtype = '纵向裂缝'
            elif cluster['line_count'] >= 4:
                dtype = '网状裂缝'
            else:
                dtype = '裂缝'
            sev = 3 if cluster['total_length'] > 400 else (2 if cluster['total_length'] > 150 else 1)
            defects.append({
                'type': dtype, 'type_code': 'crack_detected',
                'confidence': round(min(cluster['total_length'] / 600, 0.92), 3),
                'bbox': {'x': x, 'y': y, 'w': bw, 'h': bh},
                'severity': sev, 'area_pixels': bw * bh, 'source': 'hough',
            })
            cv2.rectangle(annotated, (x, y), (x + bw, y + bh), (255, 140, 0), 2)
            cv2.putText(annotated, dtype, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 140, 0), 1)

        # 策略2: 轮廓分析坑洼/块状病害
        edges_high = cv2.Canny(enhanced, 40, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(edges_high, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = (w * h) * 0.0008
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect_ratio = bw / max(bh, 1)
            extent = area / max(bw * bh, 1)
            if aspect_ratio > 5 or aspect_ratio < 0.2:
                continue
            overlap = False
            for d in defects:
                if self._bbox_overlap((x, y, bw, bh), d['bbox']):
                    overlap = True
                    break
            if overlap:
                continue
            dtype = '网状裂缝' if extent < 0.3 else '坑洼'
            sev = 3 if area > (w * h) * 0.06 else (2 if area > (w * h) * 0.02 else 1)
            defects.append({
                'type': dtype, 'type_code': 'opencv_detected',
                'confidence': round(min(extent * 2, 0.95), 3),
                'bbox': {'x': x, 'y': y, 'w': bw, 'h': bh},
                'severity': sev, 'area_pixels': round(area), 'source': 'contour',
            })
            color = {1: (0, 200, 0), 2: (0, 180, 180), 3: (0, 0, 255)}.get(sev, (200, 0, 0))
            cv2.rectangle(annotated, (x, y), (x + bw, y + bh), color, 2)
            cv2.putText(annotated, dtype, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # 按面积排序，取前15
        defects.sort(key=lambda d: d['area_pixels'], reverse=True)
        defects = defects[:15]

        annotated_b64 = self._img_to_base64(annotated)
        return {'defects': defects, 'defect_count': len(defects), 'annotated_image': annotated_b64, 'method': 'opencv'}

    @staticmethod
    def _cluster_lines(lines, img_w, img_h):
        """对霍夫检测的线段进行聚类"""
        if lines is None:
            return []
        clusters = []
        used = set()
        for i, line in enumerate(lines):
            if i in used:
                continue
            x1, y1, x2, y2 = line[0]
            cluster_lines = [line[0]]
            used.add(i)
            for j, line2 in enumerate(lines):
                if j in used:
                    continue
                x3, y3, x4, y4 = line2[0]
                d1 = np.sqrt((x2 - x3)**2 + (y2 - y3)**2)
                d2 = np.sqrt((x1 - x4)**2 + (y1 - y4)**2)
                if min(d1, d2) < 50:
                    cluster_lines.append(line2[0])
                    used.add(j)
            if cluster_lines:
                all_x, all_y, total_len = [], [], 0
                for l in cluster_lines:
                    all_x.extend([l[0], l[2]])
                    all_y.extend([l[1], l[3]])
                    total_len += np.sqrt((l[2]-l[0])**2 + (l[3]-l[1])**2)
                x_min = max(min(all_x) - 10, 0)
                y_min = max(min(all_y) - 10, 0)
                x_max = min(max(all_x) + 10, img_w)
                y_max = min(max(all_y) + 10, img_h)
                clusters.append({
                    'bbox': (x_min, y_min, x_max - x_min, y_max - y_min),
                    'total_length': int(total_len), 'line_count': len(cluster_lines),
                })
        return clusters

    @staticmethod
    def _bbox_overlap(b1, b2):
        """检查两个边界框是否重叠"""
        x1, y1, w1, h1 = b1
        x2, y2, w2, h2 = b2['x'], b2['y'], b2['w'], b2['h']
        if x1 + w1 < x2 or x2 + w2 < x1 or y1 + h1 < y2 or y2 + h2 < y1:
            return False
        ox = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
        oy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
        overlap = ox * oy
        area1, area2 = w1 * h1, w2 * h2
        return overlap / min(area1, area2) > 0.3 if min(area1, area2) > 0 else False

    def _estimate_severity(self, area_pixels, base_severity):
        if area_pixels > 50000:
            return 3
        elif area_pixels > 15000:
            return 2
        return base_severity

    def _apply_nms(self, defects, iou_threshold):
        if len(defects) <= 1:
            return defects
        defects.sort(key=lambda d: d['confidence'], reverse=True)
        keep = []
        for d1 in defects:
            suppressed = False
            for d2 in keep:
                if self._compute_iou(d1['bbox'], d2['bbox']) > iou_threshold:
                    suppressed = True
                    break
            if not suppressed:
                keep.append(d1)
        return keep

    @staticmethod
    def _compute_iou(b1, b2):
        x1 = max(b1['x'], b2['x'])
        y1 = max(b1['y'], b2['y'])
        x2 = min(b1['x'] + b1['w'], b2['x'] + b2['w'])
        y2 = min(b1['y'] + b1['h'], b2['y'] + b2['h'])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = b1['w'] * b1['h']
        area2 = b2['w'] * b2['h']
        union = area1 + area2 - inter
        return inter / max(union, 1)

    @staticmethod
    def _img_to_base64(img):
        import base64
        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode('utf-8')


detector = RoadDefectDetector()


def _read_image(image_path: str):
    """Read images from paths containing non-ASCII characters on Windows."""
    try:
        data = np.fromfile(image_path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None
