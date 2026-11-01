"""Fabrique les jaquettes 600x900 des jeux navigateur (Chess.com, PokéRogue).

Usage : python -I tools/make_web_covers.py <dossier des images sources> <dossier covers>
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

src, out = Path(sys.argv[1]), Path(sys.argv[2])
W, H = 600, 900
FONTS = Path('C:/Windows/Fonts')


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def title(img, text, y, size=64, fill='white'):
    d = ImageDraw.Draw(img)
    f = font('seguibl.ttf', size)
    w = d.textlength(text, font=f)
    shadow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text(((W - w) / 2, y + 4), text, font=f, fill=(0, 0, 0, 170))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)))
    d.text(((W - w) / 2, y), text, font=f, fill=fill)


# --- PokéRogue : l'art pixel carré, ciel prolongé en haut et en bas
logo = Image.open(src / 'pokerogue_logo.png').convert('RGBA')
art = logo.resize((W, W), Image.NEAREST)
img = Image.new('RGBA', (W, H))
top = logo.crop((0, 0, logo.width, 1)).resize((W, 150), Image.NEAREST)
bottom = logo.crop((0, logo.height - 1, logo.width, logo.height)).resize((W, H - 150 - W), Image.NEAREST)
img.paste(top, (0, 0)); img.paste(art, (0, 150)); img.paste(bottom, (0, 150 + W))
title(img, 'PokéRogue', 772, 70)
img.convert('RGB').save(out / 'pokerogue.jpg', quality=92)

# --- Chess.com : fond sombre, échiquier en perspective douce, pion vert
img = Image.new('RGBA', (W, H), '#262421')
d = ImageDraw.Draw(img)
for y in range(H):
    t = y / H
    d.line([(0, y), (W, y)], fill=(int(49 - 15 * t), int(46 - 14 * t), int(43 - 13 * t)))
board = Image.new('RGBA', (W, 360), (0, 0, 0, 0))
bd = ImageDraw.Draw(board)
cell = W // 8
for r in range(6):
    for c in range(8):
        if (r + c) % 2:
            bd.rectangle([c * cell, r * cell, (c + 1) * cell, (r + 1) * cell], fill=(129, 182, 76, 70))
        else:
            bd.rectangle([c * cell, r * cell, (c + 1) * cell, (r + 1) * cell], fill=(235, 236, 208, 28))
board = board.transform((W, 360), Image.PERSPECTIVE, (1.6, .55, -330, 0, 1.6, 0, 0, .0016, 1), Image.BICUBIC)
img.alpha_composite(board, (0, H - 360))
glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse([110, 170, 490, 570], fill=(129, 182, 76, 90))
img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(60)))
pawn = font('seguisym.ttf', 340)
pw = d.textlength('♟', font=pawn)
d.text(((W - pw) / 2, 150), '♟', font=pawn, fill='#81b64c')
title(img, 'Chess.com', 610, 76)
img.convert('RGB').save(out / 'chess.jpg', quality=92)
print('ok')
