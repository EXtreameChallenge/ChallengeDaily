"""
生成 ChallengeDaily 应用图标（256x256 PNG + 多尺寸 ICO）
风格：深色圆形背景 + 紫色/金色原子轨道
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT_PNG = ROOT / "client" / "public" / "icon.png"
OUT_ICO = ROOT / "client" / "public" / "icon.ico"

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

cx, cy = SIZE // 2, SIZE // 2
radius = SIZE // 2 - 8

# 深色圆形背景
bg_color = (30, 30, 35, 255)
draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=bg_color)

# 原子轨道参数
orbit_color = (123, 104, 238, 220)  # 紫色 #7B68EE
accent_color = (240, 192, 64, 255)  # 金色 #F0C040
core_color = (240, 240, 255, 255)


def draw_ellipse(draw, bbox, outline, width, start=0, end=360):
    """PIL ImageDraw.ellipse 不支持宽度，这里手动绘制"""
    # 使用弧线的弦模拟椭圆
    for w in range(width):
        draw.arc(bbox, start=start, end=end, fill=outline, width=1)
        bbox = (bbox[0] + 1, bbox[1] + 1, bbox[2] - 1, bbox[3] - 1)


# 绘制三条倾斜的椭圆轨道
orbit_width = 6
orbits = [
    # (rx, ry, 旋转角度)
    (90, 28, 0),
    (90, 28, 60),
    (90, 28, 120),
]

import math


def ellipse_points(rx, ry, angle_deg, cx, cy, t):
    """参数方程返回椭圆上一点，再绕中心旋转 angle_deg"""
    angle = math.radians(angle_deg)
    x = rx * math.cos(t)
    y = ry * math.sin(t)
    xr = x * math.cos(angle) - y * math.sin(angle)
    yr = x * math.sin(angle) + y * math.cos(angle)
    return cx + xr, cy + yr


for i, (rx, ry, rot) in enumerate(orbits):
    # 用密集线段绘制椭圆，比 arc 更可控
    points = []
    steps = 120
    color = accent_color if i == 0 else orbit_color
    for j in range(steps + 1):
        t = 2 * math.pi * j / steps
        points.append(ellipse_points(rx, ry, rot, cx, cy, t))
    # 描边
    for j in range(len(points) - 1):
        draw.line([points[j], points[j + 1]], fill=color, width=orbit_width)

# 中心金色圆点
core_radius = 18
draw.ellipse([cx - core_radius, cy - core_radius, cx + core_radius, cy + core_radius], fill=accent_color)
# 中心高光
highlight_r = 6
draw.ellipse([cx - 4 - highlight_r, cy - 4 - highlight_r, cx - 4 + highlight_r, cy - 4 + highlight_r], fill=(255, 255, 255, 160))

# 保存 PNG
img.save(OUT_PNG, "PNG")

# 保存多尺寸 ICO：electron-builder 要求至少 256x256，因此把 256 放在第一位
sizes = [256, 128, 48, 32, 16]
ico_images = []
for s in sizes:
    ico = img.resize((s, s), Image.LANCZOS)
    # ICO 在某些场景下 alpha 表现不一致，转换为 RGB 并保留透明背景
    # 但 electron-builder 解析 ICO 尺寸时只读取目录头，与模式无关
    ico_images.append(ico)

ico_images[0].save(
    OUT_ICO,
    format="ICO",
    sizes=[(s, s) for s in sizes],
    append_images=ico_images[1:],
)

print(f"Generated: {OUT_PNG} ({SIZE}x{SIZE})")
print(f"Generated: {OUT_ICO} with sizes {sizes}")
