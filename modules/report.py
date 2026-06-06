"""
道路巡检数据分析与报告系统 - 报告生成模块
"""
import os
from datetime import datetime
from config import REPORT_FOLDER, SEVERITY_LEVELS


def generate_report(inspection, stats: dict) -> str:
    """
    生成巡检报告HTML
    返回报告HTML字符串，可直接保存为文件或在前端渲染
    """
    os.makedirs(REPORT_FOLDER, exist_ok=True)

    ov = stats.get('overview', {})
    td = stats.get('type_distribution', {})
    sd = stats.get('severity_distribution', {})
    gps = stats.get('gps_summary', {})
    ms = stats.get('maintenance_summary', [])
    dl = stats.get('defect_list', [])

    # 生成病害明细表格行
    defect_rows = ''
    for i, d in enumerate(dl[:50], 1):  # 最多显示50条
        sev_class = {1: 'sev-light', 2: 'sev-medium', 3: 'sev-serious'}.get(d['severity'], '')
        gps_text = d.get('gps', '未定位')
        if d.get('gps_error'):
            distance = d.get('gps_error_distance')
            suffix = f'（偏离轨迹 {distance} m）' if distance else ''
            gps_text = f'{gps_text} <span class="gps-error">GPS有误{suffix}</span>'
        defect_rows += f'''
        <tr class="{sev_class}">
            <td>{i}</td>
            <td>{d['type']}</td>
            <td><span class="badge badge-{sev_class}">{d['severity_label']}</span></td>
            <td>{d['confidence']:.0%}</td>
            <td class="text-truncate" style="max-width:200px">{d['image_name']}</td>
            <td>{gps_text}</td>
        </tr>'''

    # 生成养护建议
    maintenance_html = ''
    for m in ms:
        icon = {'紧急处理': '🔴', '计划修复': '🟡', '持续监测': '🟢'}.get(m['level'], '⚪')
        maintenance_html += f'''
        <div class="maintenance-item">
            <h4>{icon} {m['level']} <span class="badge">{m['count']}处</span></h4>
            <p>{m['advice']}</p>
        </div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>道路巡检报告 - {inspection.title}</title>
<style>
    :root {{ color-scheme: light; }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: "Microsoft YaHei", "SimHei", sans-serif; color: #333; background: #fff; padding: 0; }}
    .report {{ max-width: 210mm; margin: 0 auto; padding: 20px 30px; }}
    .header {{ text-align: center; border-bottom: 2px solid #1a73e8; padding-bottom: 16px; margin-bottom: 20px; }}
    .header h1 {{ font-size: 22px; color: #1a73e8; }}
    .header .subtitle {{ font-size: 13px; color: #666; margin-top: 4px; }}
    .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; margin-bottom: 20px; font-size: 13px; }}
    .info-grid div {{ padding: 2px 0; }}
    .info-grid .label {{ color: #666; }}
    .info-grid .value {{ font-weight: bold; }}
    .section {{ margin-bottom: 18px; }}
    .section h2 {{ font-size: 15px; color: #1a73e8; border-left: 3px solid #1a73e8; padding-left: 8px; margin-bottom: 8px; }}
    .stats-cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 16px; }}
    .stat-card {{ background: #f8f9fa; border: 1px solid #e8e8e8; border-radius: 6px; padding: 12px; text-align: center; }}
    .stat-card .number {{ font-size: 28px; font-weight: bold; color: #1a73e8; }}
    .stat-card .label {{ font-size: 11px; color: #666; margin-top: 2px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
    th {{ background: #f0f5ff; color: #1a73e8; font-weight: 600; }}
    .sev-light {{ background: #f0fff0; }}
    .sev-medium {{ background: #fffdf0; }}
    .sev-serious {{ background: #fff0f0; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: bold; }}
    .badge-sev-light {{ background: #d4edda; color: #155724; }}
    .badge-sev-medium {{ background: #fff3cd; color: #856404; }}
    .badge-sev-serious {{ background: #f8d7da; color: #721c24; }}
    .gps-error {{ display: inline-block; margin-left: 4px; padding: 2px 6px; border-radius: 8px; background: #dc3545; color: #fff; font-size: 10px; font-weight: bold; }}
    .maintenance-item {{ background: #f8f9fa; border: 1px solid #e8e8e8; border-radius: 6px; padding: 12px; margin-bottom: 8px; }}
    .maintenance-item h4 {{ font-size: 13px; margin-bottom: 4px; }}
    .maintenance-item p {{ font-size: 12px; color: #555; line-height: 1.6; }}
    .footer {{ border-top: 1px solid #ddd; margin-top: 24px; padding-top: 8px; font-size: 11px; color: #999; text-align: center; }}
    .text-truncate {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    @media print {{
        body {{ print-color-adjust: exact; }}
        .report {{ padding: 0; }}
    }}
</style>
</head>
<body>
<div class="report">

    <!-- 报告头 -->
    <div class="header">
        <h1>道路巡检数据分析报告</h1>
        <div class="subtitle">基于无人机的道路巡检系统 | 报告编号: RPT-{inspection.id:04d} | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
    </div>

    <!-- 基本信息 -->
    <div class="section">
        <h2>一、巡检基本信息</h2>
        <div class="info-grid">
            <div><span class="label">巡检任务：</span><span class="value">{inspection.title}</span></div>
            <div><span class="label">巡检日期：</span><span class="value">{inspection.inspection_date}</span></div>
            <div><span class="label">巡检路段：</span><span class="value">{inspection.road_section or '未指定'}</span></div>
            <div><span class="label">巡检员：</span><span class="value">{inspection.inspector or '未指定'}</span></div>
            <div><span class="label">天气：</span><span class="value">{inspection.weather or '未记录'}</span></div>
            <div><span class="label">备注：</span><span class="value">{inspection.notes or '无'}</span></div>
        </div>
    </div>

    <!-- 巡检概览 -->
    <div class="section">
        <h2>二、巡检数据概览</h2>
        <div class="stats-cards">
            <div class="stat-card">
                <div class="number">{ov.get('total_images', 0)}</div>
                <div class="label">采集图像</div>
            </div>
            <div class="stat-card">
                <div class="number">{ov.get('total_defects', 0)}</div>
                <div class="label">检测病害</div>
            </div>
            <div class="stat-card">
                <div class="number">{ov.get('defect_density', 0)}</div>
                <div class="label">病害密度(处/张)</div>
            </div>
            <div class="stat-card">
                <div class="number">{gps.get('point_count', 0)}</div>
                <div class="label">GPS轨迹点</div>
            </div>
        </div>
    </div>

    <!-- 病害统计 -->
    <div class="section">
        <h2>三、病害统计分析</h2>
        <h3 style="font-size:13px; color:#555; margin-bottom:4px;">3.1 病害类型分布</h3>
        <table>
            <tr><th>病害类型</th><th>数量</th><th>占比</th></tr>'''
    for i, label in enumerate(td.get('labels', [])):
        val = td.get('values', [])[i] if i < len(td.get('values', [])) else 0
        total = td.get('total', 1)
        html += f'<tr><td>{label}</td><td>{val}</td><td>{val/max(total,1)*100:.1f}%</td></tr>'
    html += f'''
        </table>

        <h3 style="font-size:13px; color:#555; margin-bottom:4px;">3.2 严重程度分布</h3>
        <table>
            <tr><th>严重程度</th><th>数量</th><th>占比</th></tr>'''
    for i, label in enumerate(sd.get('labels', [])):
        val = sd.get('values', [])[i] if i < len(sd.get('values', [])) else 0
        total = sd.get('total', 1)
        html += f'<tr><td>{label}</td><td>{val}</td><td>{val/max(total,1)*100:.1f}%</td></tr>'
    html += '''
        </table>
    </div>

    <!-- 病害明细 -->
    <div class="section">
        <h2>四、病害明细表</h2>
        <table>
            <tr><th>序号</th><th>病害类型</th><th>严重程度</th><th>置信度</th><th>来源图像</th><th>GPS位置</th></tr>'''
    html += defect_rows
    html += '''
        </table>
    </div>

    <!-- 养护建议 -->
    <div class="section">
        <h2>五、养护建议</h2>'''
    html += maintenance_html
    if not maintenance_html:
        html += '<p style="color:#666;">未检测到明显病害，建议保持日常巡查频率。</p>'
    html += '''
    </div>

    <!-- GPS轨迹摘要 -->
    <div class="section">
        <h2>六、GPS轨迹摘要</h2>'''
    if gps.get('has_track'):
        html += f'''
        <div class="info-grid">
            <div><span class="label">轨迹点数：</span><span class="value">{gps.get('point_count', 0)}</span></div>
            <div><span class="label">平均速度：</span><span class="value">{gps.get('avg_speed', 0)} km/h</span></div>
            <div><span class="label">中心纬度：</span><span class="value">{gps.get('center_lat', '-')}</span></div>
            <div><span class="label">中心经度：</span><span class="value">{gps.get('center_lng', '-')}</span></div>
        </div>'''
    else:
        html += '<p style="color:#666;">本次巡检未记录GPS轨迹数据。</p>'
    html += '''
    </div>

    <!-- 页脚 -->
    <div class="footer">
        <p>本报告由「基于无人机的道路巡检系统」自动生成</p>
        <p>桂林电子科技大学 · 电子工程与自动化学院 © 2025-2027</p>
    </div>

</div>
</body>
</html>'''

    return html


def save_report(html_content: str, inspection_id: int) -> str:
    """保存报告为HTML文件，返回文件路径"""
    filename = f'report_inspection_{inspection_id:04d}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
    filepath = os.path.join(REPORT_FOLDER, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)
    return filepath
