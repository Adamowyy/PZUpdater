"""Generuje ikonę PZ Updater: ciemny zaokrąglony kwadrat + literowy 'PZ'."""
import sys, os
sys.path.insert(0, r"C:\Users\adamo\AppData\Local\hermes\skills\creative\icon-design\scripts")
from generate_ico import make_ico_file
from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Tło — ciemny granat (spójny z motywem aplikacji)
margin = 40
radius = 220
draw.rounded_rectangle([margin, margin, SIZE - margin, SIZE - margin],
                       radius=radius, fill=(21, 26, 42, 255))  # #151a2a

# Font (Segoe UI Bold)
font_path = r"C:\Windows\Fonts\segoeuib.ttf"
if not os.path.exists(font_path):
    font_path = r"C:\Windows\Fonts\segoeui.ttf"

WHITE = (255, 255, 255, 255)
BLUE = (59, 130, 246, 255)  # #3b82f6 — akcent aplikacji

# Największy rozmiar czcionki mieszczący się w ~72% szerokości
font = None
for fs in range(640, 200, -10):
    f = ImageFont.truetype(font_path, fs)
    b = draw.textbbox((0, 0), "PZ", font=f)
    if b[2] - b[0] <= int(SIZE * 0.72):
        font = f
        break

gap = int(0.05 * SIZE)

def metrics(ch):
    b = draw.textbbox((0, 0), ch, font=font)
    return b[0], b[2] - b[0]  # lewy bearing, szerokość "atramentu"

lbP, wP = metrics("P")
lbZ, wZ = metrics("Z")
total = wP + gap + wZ
xP = (SIZE - total) // 2 - lbP
xZ = xP + wP + gap - lbZ

# Wyśrodkowanie pionowe po wspólnym bbox obu liter
bfull = draw.textbbox((0, 0), "PZ", font=font)
cap = bfull[3] - bfull[1]
y = (SIZE - cap) // 2 - bfull[1]

draw.text((xP, y), "P", font=font, fill=WHITE)
draw.text((xZ, y), "Z", font=font, fill=BLUE)

img.save("icon.png")
make_ico_file(img, "icon.ico")
print("OK: icon.png + icon.ico")
