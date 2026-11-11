# 青果果 GIF 表情包 Skill

本目录是青果果专用表情包制作 skill 的源码。执行规则见 [SKILL.md](SKILL.md)。

## 源码结构

- `SKILL.md`：人物、文字样式、制作流程与交付规则。
- `assets/`：内置人物参考及文字样式示意，仅用于制作参考。
- `scripts/export_frames.py`：将连续帧图集导出为完整成品集合。

## 使用导出器

依赖 Python 3 和 Pillow。清单格式见 SKILL.md。每条清单须指定代表帧 `representative_frame`。

```sh
python3 scripts/export_frames.py /absolute/path/manifest.json --font '/System/Library/Fonts/STHeiti Medium.ttc'
```

默认输出至当前工作目录的 `outputs/成品`；重名依次使用 `成品-v2`、`成品-v3`，也可通过第二个位置参数指定输出路径。

成品包含 `GIF/`、`PNG/`、`全部动态预览.gif`、`全部静态预览.png`、`index.html` 和 `成品.zip`。HTML 支持动静态查看及明暗主题切换。PNG 直接提取对应 GIF 的代表帧，保留原文字。
