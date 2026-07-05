"""临时启动脚本 — 验证后端 + token"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from server import start_server
start_server()
