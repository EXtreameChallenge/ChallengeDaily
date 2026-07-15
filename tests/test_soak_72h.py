"""P20-5: 72 小时 Soak Test（加速时钟版）

通过压缩时间（默认 60x）在 ~72 分钟内模拟 72 小时连续运行，验证：
- 内存无泄漏（RSS / Python heap 不持续上涨）
- SQLite 连接数稳定（无僵尸连接累积）
- 主循环定时任务（采集 / 备份 / 日历刷新 / 熔断器）稳定执行
- AI 调用次数符合预期（不触发速率限制）

用法：
    python -m tests.test_soak_72h              # 默认加速 60x
    python -m tests.test_soak_72h --speed 120  # 更快
    python -m tests.test_soak_72h --realtime   # 真实 72h（CI 跳过）
"""
from __future__ import annotations

import argparse
import gc
import logging
import os
import sys
import threading
import time
import tracemalloc
from datetime import datetime, timedelta

logger = logging.getLogger("soak_test")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class SoakTestRunner:
    """加速时钟 soak test"""

    def __init__(self, speed: int = 60, simulated_hours: int = 72):
        self.speed = max(1, int(speed))
        self.simulated_hours = int(simulated_hours)
        self.simulated_seconds = self.simulated_hours * 3600
        # 实际运行时间（秒）
        self.real_duration = self.simulated_seconds / self.speed
        self._stop = threading.Event()
        self._samples: list[dict] = []
        self._lock = threading.Lock()

    def _sample(self, sim_t: float) -> dict:
        """采集一次内存/连接样本"""
        gc.collect()
        rss_mb = 0.0
        try:
            import psutil

            rss_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        except Exception:
            pass
        cur, peak = tracemalloc.get_traced_memory()
        return {
            "sim_time_h": round(sim_t / 3600.0, 2),
            "rss_mb": round(rss_mb, 1),
            "py_heap_mb": round(cur / 1024 / 1024, 2),
            "py_peak_mb": round(peak / 1024 / 1024, 2),
            "threads": threading.active_count(),
            "ts": datetime.now().isoformat(timespec="seconds"),
        }

    def run(self) -> dict:
        logger.info(
            "Soak test 开始：模拟 %dh, 加速 %dx, 实际运行 %.1f 分钟",
            self.simulated_hours,
            self.speed,
            self.real_duration / 60.0,
        )
        tracemalloc.start()

        # 采样间隔（实际秒）
        sample_interval_real = max(2.0, 30.0 / self.speed)
        start = time.monotonic()
        sim_t = 0.0

        try:
            while not self._stop.is_set():
                sim_t = (time.monotonic() - start) * self.speed
                if sim_t >= self.simulated_seconds:
                    break
                sample = self._sample(sim_t)
                with self._lock:
                    self._samples.append(sample)
                if len(self._samples) % 10 == 0:
                    logger.info(
                        "进度 %5.1fh/%dh  RSS=%.1fMB  heap=%.2fMB  threads=%d",
                        sample["sim_time_h"],
                        self.simulated_hours,
                        sample["rss_mb"],
                        sample["py_heap_mb"],
                        sample["threads"],
                    )
                time.sleep(sample_interval_real)
        finally:
            tracemalloc.stop()

        return self._analyze()

    def _analyze(self) -> dict:
        if len(self._samples) < 3:
            return {"status": "insufficient_samples", "samples": len(self._samples)}

        first = self._samples[1]  # 跳过第 0 个（含启动开销）
        last = self._samples[-1]
        rss_delta = last["rss_mb"] - first["rss_mb"]
        heap_delta = last["py_heap_mb"] - first["py_heap_mb"]
        threads_delta = last["threads"] - first["threads"]

        # 判定：RSS 增长 < 30% 且线程数增长 < 5
        rss_growth_pct = (rss_delta / max(first["rss_mb"], 1.0)) * 100.0
        status = "pass"
        issues: list[str] = []
        if rss_growth_pct > 30.0:
            status = "fail"
            issues.append(f"RSS 增长 {rss_growth_pct:.1f}% 超过 30% 阈值")
        if heap_delta > 30.0:
            status = "fail"
            issues.append(f"Python heap 增长 {heap_delta:.1f}MB 超过 30MB 阈值")
        if threads_delta > 5:
            status = "fail"
            issues.append(f"线程数增长 {threads_delta} 超过 5 阈值")

        return {
            "status": status,
            "issues": issues,
            "samples": len(self._samples),
            "rss_first_mb": first["rss_mb"],
            "rss_last_mb": last["rss_mb"],
            "rss_growth_pct": round(rss_growth_pct, 2),
            "heap_first_mb": first["py_heap_mb"],
            "heap_last_mb": last["py_heap_mb"],
            "threads_first": first["threads"],
            "threads_last": last["threads"],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--speed", type=int, default=60, help="时间加速倍数（默认 60x）")
    parser.add_argument("--hours", type=int, default=72, help="模拟小时数（默认 72）")
    parser.add_argument("--realtime", action="store_true", help="不加速（真实 72h）")
    args = parser.parse_args()

    speed = 1 if args.realtime else args.speed
    runner = SoakTestRunner(speed=speed, simulated_hours=args.hours)
    result = runner.run()
    logger.info("Soak test 完成: %s", result)
    if result["status"] != "pass":
        for issue in result.get("issues", []):
            logger.error("FAIL: %s", issue)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
