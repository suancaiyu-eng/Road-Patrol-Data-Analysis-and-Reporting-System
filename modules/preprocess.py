"""
道路巡检数据分析与报告系统 - 图像预处理模块
"""
import cv2
import base64
import numpy as np


def preprocess_image(image_path: str) -> dict:
    """
    对巡检图像进行预处理
    返回原始图像和预处理后的图像的base64，以及处理步骤说明
    """
    img = _read_image(image_path)
    if img is None:
        return {'error': '无法读取图像'}

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    results = {}
    results['original'] = _img_to_base64(img)

    # 步骤1: 高斯去噪
    denoised = cv2.GaussianBlur(gray, (5, 5), 0)
    results['denoised'] = _gray_to_base64(denoised)

    # 步骤2: CLAHE对比度增强（突出裂缝纹理）
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    results['enhanced'] = _gray_to_base64(enhanced)

    # 步骤3: Canny边缘检测
    edges = cv2.Canny(enhanced, 30, 100)
    results['edges'] = _gray_to_base64(edges)

    # 步骤4: 形态学处理
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morphed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    results['morphed'] = _gray_to_base64(morphed)

    # 图像信息
    results['info'] = {
        'width': w, 'height': h,
        'channels': img.shape[2] if len(img.shape) == 3 else 1,
        'mean_brightness': round(float(np.mean(gray)), 1),
        'std_brightness': round(float(np.std(gray)), 1),
    }

    return results


def _img_to_base64(img):
    """BGR图像转base64"""
    _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer).decode('utf-8')


def _gray_to_base64(gray_img):
    """灰度图像转base64"""
    _, buffer = cv2.imencode('.jpg', gray_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer).decode('utf-8')


def _read_image(image_path: str):
    """Read images from paths containing non-ASCII characters on Windows."""
    try:
        data = np.fromfile(image_path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None
