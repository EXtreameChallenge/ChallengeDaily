"""ChallengeDaily Web Tracker — 图标生成脚本

生成 16x16 / 48x48 / 128x128 紫色圆角方形 PNG 图标（带橙色时钟指针图案）。
优先使用 PIL（Pillow）；若未安装则回退到纯 Python（zlib + struct）的 PNG 编码器，
确保无第三方依赖也能生成可用图标。

用法：
    python generate_icons.py
图标输出到同级 icons/ 目录。
"""
import os
import struct
import zlib

# ChallengeDaily 品牌色
BG_COLOR = (109, 74, 255)      # 紫色 #6d4aff
ACCENT_COLOR = (255, 138, 61)  # 橙色 #ff8a3d
SIZES = [16, 48, 128]


def _in_rounded_rect(x, y, size, radius):
    """判断点 (x,y) 是否在圆角方形内（中心为 size/2）。"""
    if radius <= 0:
        return 0 <= x < size and 0 <= y < size
    cx = cy = size / 2.0
    # 把点变换到最近圆角的局部坐标
    dx = abs(x - cx) - (size / 2.0 - radius)
    dy = abs(y - cy) - (size / 2.0 - radius)
    if dx <= 0 or dy <= 0:
        return 0 <= x < size and 0 <= y < size
    return (dx * dx + dy * dy) <= radius * radius


def _in_clock_hand(px, py, size):
    """绘制一个简化的时钟指针图案（12点指向的指针），返回是否命中。"""
    cx = cy = size / 2.0
    # 表盘半径
    r = size * 0.30
    # 距离中心
    dx = px - cx
    dy = py - cy
    dist = (dx * dx + dy * dy) ** 0.5
    if dist > r:
        return False
    # 指针：从中心向上一条粗线（12点方向）+ 向右一条短线（3点方向）
    # 用矩形区域近似
    half_w = max(1.0, size * 0.05)
    # 垂直指针（向上）：x 在中心 ± half_w，y 从中心向上到 -r*0.7
    if abs(dx) <= half_w and (-r * 0.75) <= dy <= 0:
        return True
    # 水平指针（向右）：y 在中心 ± half_w，x 从 0 到 r*0.6
    if abs(dy) <= half_w and 0 <= dx <= r * 0.6:
        return True
    return False


def _render_pixel_clean(size, x, y):
    """更清晰的像素渲染：圆角紫底 + 橙色圆环 + 橙色指针。"""
    radius = size * 0.22
    if not _in_rounded_rect(x, y, size, radius):
        return (0, 0, 0, 0)

    cx = cy = size / 2.0
    dx = x - cx
    dy = y - cy
    dist = (dx * dx + dy * dy) ** 0.5
    ring_outer = size * 0.30
    ring_inner = size * 0.245

    # 橙色圆环
    if ring_inner <= dist <= ring_outer:
        return (ACCENT_COLOR[0], ACCENT_COLOR[1], ACCENT_COLOR[2], 255)

    # 橙色时钟指针
    if _in_clock_hand(x, y, size):
        return (ACCENT_COLOR[0], ACCENT_COLOR[1], ACCENT_COLOR[2], 255)

    # 紫色背景
    return (BG_COLOR[0], BG_COLOR[1], BG_COLOR[2], 255)


# ── 纯 Python PNG 编码器（无依赖回退方案）──

def _write_png(path, width, height, pixels):
    """pixels: list of rows, each row is list of (r,g,b,a) tuples."""
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0 (None) per scanline
        for (r, g, b, a) in row:
            raw.append(r)
            raw.append(g)
            raw.append(b)
            raw.append(a)

    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    idat = zlib.compress(bytes(raw), 9)
    with open(path, "wb") as f:
        f.write(sig)
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", idat))
        f.write(chunk(b"IEND", b""))


def generate_with_pure_python(out_dir):
    """无 PIL 回退：逐像素生成圆角紫色图标 + 橙色时钟图案。"""
    for size in SIZES:
        pixels = []
        for y in range(size):
            row = []
            for x in range(size):
                row.append(_render_pixel_clean(size, x, y))
            pixels.append(row)
        path = os.path.join(out_dir, f"icon{size}.png")
        _write_png(path, size, size, pixels)
        print(f"[pure-python] 已生成 {path}")


def generate_with_pil(out_dir):
    """优先路径：用 Pillow 绘制更平滑的图标。"""
    from PIL import Image, ImageDraw

    for size in SIZES:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        radius = max(2, int(size * 0.22))

        # 圆角紫色方形背景
        draw.rounded_rectangle(
            [(0, 0), (size - 1, size - 1)],
            radius=radius,
            fill=BG_COLOR + (255,),
        )

        cx = cy = size / 2.0
        ring_outer = size * 0.30
        ring_inner = size * 0.245

        # 橙色圆环（表盘外圈）：用椭圆差集近似
        ring_box_outer = [
            cx - ring_outer, cy - ring_outer,
            cx + ring_outer, cy + ring_outer,
        ]
        draw.ellipse(ring_box_outer, outline=ACCENT_COLOR + (255,),
                     width=max(1, int(size * 0.05)))

        # 橙色时针（向上）与分针（向右）
        w = max(1, int(size * 0.06))
        # 时针：中心 -> 上
        draw.line([(cx, cy), (cx, cy - size * 0.20)],
                  fill=ACCENT_COLOR + (255,), width=w)
        # 分针：中心 -> 右
        draw.line([(cx, cy), (cx + size * 0.15, cy)],
                  fill=ACCENT_COLOR + (255,), width=w)
        # 中心点
        draw.ellipse(
            [cx - w * 0.6, cy - w * 0.6, cx + w * 0.6, cy + w * 0.6],
            fill=ACCENT_COLOR + (255,),
        )

        path = os.path.join(out_dir, f"icon{size}.png")
        img.save(path, "PNG")
        print(f"[PIL] 已生成 {path}")


def main():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
    os.makedirs(out_dir, exist_ok=True)
    try:
        import PIL  # noqa: F401
        generate_with_pil(out_dir)
    except ImportError:
        print("未检测到 Pillow，使用纯 Python PNG 编码器生成图标...")
        generate_with_pure_python(out_dir)
    print(f"图标已生成到: {out_dir}")


if __name__ == "__main__":
    main()
