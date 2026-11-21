"""每日定时自动生成日报（默认18:00触发）"""
import threading
import logging
import time
from datetime import datetime, date

logger = logging.getLogger(__name__)

_scheduler_thread = None
_scheduler_stop = threading.Event()


def init_auto_report_scheduler():
    """初始化自动日报生成调度器"""
    _scheduler_stop.clear()
    t = threading.Thread(target=_report_loop, daemon=True, name="AutoReportScheduler")
    t.start()
    logger.info("自动日报调度器已启动")


def stop_auto_report_scheduler():
    """停止调度器"""
    _scheduler_stop.set()


def _report_loop():
    """日报生成循环：在设定时间自动生成日报"""
    while not _scheduler_stop.is_set():
        try:
            from config import load_settings
            settings = load_settings()

            if not settings.get("auto_daily_report", False):
                # 功能关闭，每分钟检查一次是否重新开启
                _scheduler_stop.wait(60)
                continue

            target_hour = settings.get("auto_daily_report_hour", 18)
            now = datetime.now()

            # 计算到今天目标时间的秒数
            target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            if target_time <= now:
                # 已过今天的目标时间，等明天
                import datetime as dt
                target_time = target_time + dt.timedelta(days=1)

            wait_sec = (target_time - now).total_seconds()
            # 最长等1小时，周期性检查设置变更和stop信号
            wait_sec = min(wait_sec, 3600)

            if _scheduler_stop.wait(wait_sec):
                break

            # 检查是否到了目标时间（允许5分钟误差）
            now = datetime.now()
            if now.hour == target_hour and abs(now.minute) < 5:
                _generate_auto_report(settings)

        except Exception as e:
            logger.error(f"自动日报调度异常: {e}")
            _scheduler_stop.wait(300)  # 出错后等5分钟再试


def _generate_auto_report(settings: dict):
    """执行自动日报生成"""
    try:
        from report import generate_daily_report
        template = settings.get("auto_daily_report_template", "standard")
        today = date.today().isoformat()

        # 检查今天是否已生成
        from db import get_report
        existing = get_report(today)
        if existing:
            logger.info(f"今日日报已存在，跳过自动生成")
            return

        logger.info(f"开始自动生成日报，模板: {template}")
        result = generate_daily_report(today, template=template)
        if result:
            logger.info(f"自动日报生成成功")
        else:
            logger.warning(f"自动日报生成返回空结果")
    except Exception as e:
        logger.error(f"自动日报生成失败: {e}")
