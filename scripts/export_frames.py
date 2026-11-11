#!/usr/bin/env python3
"""Export actual animation keyframes from sprite sheets; see frame-manifest.md."""
import argparse
import html
import json
from pathlib import Path
import re
import math
from urllib.parse import quote
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image, ImageDraw, ImageFont, ImageSequence

SIZE = 320

def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', s)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', nargs='?', type=Path, default=Path('outputs/成品'))
    parser.add_argument('--font', required=True)
    args = parser.parse_args()
    m = json.loads(args.manifest.read_text(encoding='utf-8'))
    entries = m['entries']
    if not entries or len({e['text'] for e in entries}) != len(entries):
        raise ValueError('Entries must be nonempty and captions unique')
    base = args.output
    version = 2
    while args.output.exists():
        args.output = base.with_name(base.name + f"-v{version}")
        version += 1
    args.output.mkdir(parents=True, exist_ok=False)
    pngs = args.output / "PNG"; pngs.mkdir()
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
    # Decode finished GIFs so static exports exactly preserve their captions and palette.
    animations = []
    stills = []
    for entry, path in zip(entries, paths):
        with Image.open(path) as gif:
            frames = [frame.convert('RGBA') for frame in ImageSequence.Iterator(gif)]
            times = []
            for i in range(gif.n_frames):
                gif.seek(i); times.append(gif.info.get('duration', 100))
        index = entry['representative_frame']
        if not isinstance(index, int) or not 0 <= index < len(frames):
            raise ValueError('Invalid representative_frame: ' + entry['text'])
        frames[index].save(pngs / (path.stem + '.png'))
        stills.append(frames[index])
        animations.append((frames, times))
    columns = min(4, math.ceil(math.sqrt(len(paths))))
    rows = math.ceil(len(paths) / columns)
    def grid(frames):
        canvas = Image.new('RGB', (columns*344+24, rows*344+24), '#eee5da')
        for i, frame in enumerate(frames):
            canvas.paste(frame, (24+(i%columns)*344, 24+(i//columns)*344), frame)
        return canvas
    grid(stills).save(args.output/'全部静态预览.png')
    # A bounded shared timeline accommodates differing loop durations.
    step = 100
    period = min(12000, max(sum(times) for _, times in animations)*2)
    overview = []
    for t in range(0, period, step):
        current = []
        for frames, times in animations:
            phase = t % sum(times)
            index = 0
            while phase >= times[index] and index < len(times)-1:
                phase -= times[index]; index += 1
            current.append(frames[index])
        overview.append(grid(current))
    overview[0].save(args.output/'全部动态预览.gif', save_all=True,
                     append_images=overview[1:], duration=step, loop=0)
    cards = []
    for entry, path in zip(entries, paths):
        gif_url = quote('GIF/'+path.name)
        png_url = quote('PNG/'+path.stem+'.png')
        cards.append(f'<figure><img src="{gif_url}" data-gif="{gif_url}" data-png="{png_url}" alt="{html.escape(entry["text"], quote=True)}"><figcaption>{html.escape(entry["text"])}</figcaption></figure>')
    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>青果果表情包</title>
<style>:root{color-scheme:light;--bg:#faf6ef;--fg:#473426;--card:#eee5da}body.dark{color-scheme:dark;--bg:#211e1c;--fg:#fff0d1;--card:#37312c}*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);color:var(--fg);font-family:system-ui;transition:background .25s,color .25s}header{max-width:1400px;margin:auto}button{padding:10px 18px;margin:4px;border-radius:12px;cursor:pointer}main{max-width:1400px;margin:20px auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr));gap:20px}figure{margin:0;padding:12px;border-radius:20px;background:var(--card);text-align:center;transition:background .25s}img{width:100%;max-width:320px;aspect-ratio:1;object-fit:contain}figcaption{padding:8px}</style>
<header><h1>青果果表情包</h1><button id="theme" aria-pressed="false">切换明暗主题</button><button id="mode" aria-pressed="false">查看静态 PNG</button></header><main>""" + ''.join(cards) + """</main><script>
document.querySelector('#theme').onclick=function(){let dark=document.body.classList.toggle('dark');this.setAttribute('aria-pressed',dark)};
document.querySelector('#mode').onclick=function(){let still=this.getAttribute('aria-pressed')!=='true';this.setAttribute('aria-pressed',still);this.textContent=still?'查看动态 GIF':'查看静态 PNG';document.querySelectorAll('img').forEach(img=>img.src=still?img.dataset.png:img.dataset.gif)};
</script></html>"""
    (args.output/'index.html').write_text(page, encoding='utf-8')
    archive = args.output/'成品.zip'
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for path in sorted(args.output.rglob('*')):
            if path.is_file() and path != archive: z.write(path, path.relative_to(args.output))
    with ZipFile(archive) as z:
        if z.testzip() is not None: raise ValueError('Invalid ZIP')
    print(json.dumps({'count':len(paths),'output':str(args.output.resolve())},ensure_ascii=False))

if __name__=='__main__': main()
