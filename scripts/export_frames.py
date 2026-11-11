#!/usr/bin/env python3
"""Export actual animation keyframes from sprite sheets; see frame-manifest.md."""
import argparse
import html
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image, ImageDraw, ImageFont, ImageSequence

SIZE = 320

def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', s)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path, help='New output directory')
    parser.add_argument('--font', required=True)
    args = parser.parse_args()
    m = json.loads(args.manifest.read_text(encoding='utf-8'))
    entries = m['entries']
    if not entries or len({e['text'] for e in entries}) != len(entries):
        raise ValueError('Entries must be nonempty and captions unique')
    args.output.mkdir(parents=True, exist_ok=False)
    gifs = args.output / 'GIF'; gifs.mkdir()
    styles = {'A': ('#FFF0D1','#573A25','#FFF5E2'),
              'B': ('#61412B','#FFF0D1','#61412B'),
              'C': ('#A05B2A','#FFF4DE','#65412B'),
              'D': ('#62422F','#FFF0D4','#62422F')}
    style = m.get('style','A').upper()
    if style not in styles: raise ValueError('Unknown text style: '+style)
    fill, edge, outer = styles[style]
    paths = []
    for n, e in enumerate(entries, 1):
        sheet = Image.open(args.manifest.parent / e['sheet']).convert('RGBA')
        cols, rows = e['grid']
        order = e['frames']; durations = e['durations_ms']
        if len(order) < 2 or len(order) != len(durations) or min(durations) < 10:
            raise ValueError('Each frame requires a duration >= 10ms')
        images = []
        for col, row in order:
            if not (0 <= col < cols and 0 <= row < rows):
                raise ValueError('Frame cell out of range')
            box = (round(col*sheet.width/cols), round(row*sheet.height/rows), round((col+1)*sheet.width/cols), round((row+1)*sheet.height/rows))
            tile = sheet.crop(box)
            tile.thumbnail((300, 255), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (SIZE,SIZE), (255,255,255,0) if m.get('transparent',False) else 'white')
            canvas.alpha_composite(tile, ((SIZE-tile.width)//2, 0))
            draw = ImageDraw.Draw(canvas)
            fs = 42 if len(e['text']) < 6 else 39
            while True:
                font = ImageFont.truetype(args.font, fs)
                bounds = draw.textbbox((160,274), e['text'], font=font, anchor='mt')
                if bounds[2]-bounds[0] <= 280 and bounds[3] <= 311: break
                fs -= 1
                if fs < 12: raise ValueError('Caption too long')
            if style == 'D':
                draw.rounded_rectangle((bounds[0]-12,bounds[1]-8,bounds[2]+12,bounds[3]+9),radius=15,fill=edge,outline=outer,width=2)
                draw.text((160,274),e['text'],font=font,anchor='mt',fill=fill,stroke_width=1,stroke_fill=fill)
            else:
                for width,color in [(6,outer),(4,edge),(1,fill)]:
                    draw.text((160,274),e['text'],font=font,anchor='mt',fill=fill,stroke_width=width,stroke_fill=color)
            images.append(canvas)
        if len({i.tobytes() for i in images}) < 2:
            raise ValueError('No distinct images: ' + e['text'])
        path = gifs / f'{n:02d}-{safe_name(e["text"])}.gif'
        # Shared palette on a white matte; transparency index reserved for alpha<128.
        palette_img = Image.new('RGB', (SIZE*len(images),SIZE), 'white')
        for j, im in enumerate(images): palette_img.paste(im, (SIZE*j,0), im.getchannel('A'))
        palette = palette_img.quantize(colors=255)
        indexed = []
        for im in images:
            matte = Image.new('RGB', im.size, 'white'); matte.paste(im, mask=im.getchannel('A'))
            ind = matte.quantize(palette=palette, dither=Image.Dither.NONE)
            if m.get('transparent',False): ind.paste(255, mask=im.getchannel('A').point(lambda a: 255 if a < 128 else 0))
            indexed.append(ind)
        kw = dict(save_all=True, append_images=indexed[1:], duration=durations, loop=0, disposal=2, optimize=False)
        if m.get('transparent',False): kw['transparency']=255
        indexed[0].save(path, **kw)
        with Image.open(path) as check:
            if check.n_frames < 2 or check.size != (SIZE,SIZE): raise ValueError('Invalid output: '+str(path))
        paths.append(path)
    with ZipFile(args.output/'动态表情合集.zip','w',ZIP_DEFLATED) as z:
        for p in paths: z.write(p, p.relative_to(args.output))
    with ZipFile(args.output/'动态表情合集.zip') as z:
        if z.testzip() is not None: raise ValueError('Invalid ZIP')
    print(json.dumps({'count':len(paths),'output':str(args.output.resolve())},ensure_ascii=False))

if __name__=='__main__': main()
