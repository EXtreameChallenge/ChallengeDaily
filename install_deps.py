"""
ChallengeDaily Windows 版 — 依赖安装脚本
运行: python install_deps.py
"""
import subprocess
import sys

DEPENDENCIES = [
    "mss>=9.0.0",
    "Pillow>=10.0.0",
    "openai>=1.30.0",
    "httpx>=0.27.0",
    "flask>=3.0.0",
    "waitress>=3.0.0",
    "pyyaml>=6.0",
    "pywin32>=306",
]

def main():
    print("正在安装依赖...")
    for dep in DEPENDENCIES:
        print(f"  安装 {dep}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
    print("\n所有依赖安装完成！")
    print("现在可以运行: python main.py")

if __name__ == "__main__":
    main()
