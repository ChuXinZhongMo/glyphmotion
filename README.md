# 字影工坊 GlyphMotion

一键将图片、GIF、视频转换为字符动画的本地工具。GlyphMotion 不只处理严格 ASCII，也支持彩色字符、盲文点阵、Unicode 块字符、shader 风格字符和多格式导出。

## 功能

- 输入：PNG、JPG、GIF、WEBP、BMP、MP4、MOV、MKV、AVI、WMV、WEBM，以及 FFmpeg 可读取的视频格式。
- 输出：TXT、HTML 动画、GIF、PNG、MP4、ANSI、Durdraw `.dur`、Asciimation `.aam`。
- 界面：中文 Tkinter 桌面 GUI，转换完成后在窗口内列出生成的文件，可一键打开输出目录或所选文件；MP4/ANSI 会标注所需的外部工具（FFmpeg/Chafa）及其检测状态。
- 命令行：适合批量转换和脚本调用。
- 预设：清晰还原、游戏着色器、原色鲜艳、自适应混合字符、盲文高精度、文字游戏柔和。
- 颜色：源色采样、HSV 原色增强、暖色调、黑白灰度。

## 快速开始

### 1. 安装依赖

需要 Python 3.12+。视频输入和 MP4 导出需要 FFmpeg。

```powershell
Set-Location E:\ASCII动画
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Windows 上可以用 WinGet 安装 FFmpeg：

```powershell
winget install --id Gyan.FFmpeg --source winget
```

### 2. 启动 GUI

```powershell
Set-Location E:\ASCII动画
.\run_gui.cmd
```

### 3. 命令行转换

```powershell
Set-Location E:\ASCII动画
.\convert.cmd "C:\path\to\input.gif" --output-dir output --formats "txt,html,gif,png,dur,asciimation" --width 100 --fps 12
```

视频转 GIF/MP4/HTML：

```powershell
.\convert.cmd "C:\path\to\input.mp4" --output-dir output --formats "html,gif,mp4,dur" --width 160 --fps 12 --max-frames 240
```

## 常用预设

```powershell
.\convert.cmd "C:\path\to\input.mp4" --output-dir output --formats "html,gif,mp4" --preset restore --width 160
.\convert.cmd "C:\path\to\input.mp4" --output-dir output --formats "html,gif,mp4" --preset shader-color --width 160
.\convert.cmd "C:\path\to\input.mp4" --output-dir output --formats "html,gif,mp4" --preset shader-color-hd --width 220
.\convert.cmd "C:\path\to\input.mp4" --output-dir output --formats "html,gif,mp4" --preset adaptive-color --width 220
.\convert.cmd "C:\path\to\input.mp4" --output-dir output --formats "html,gif,mp4" --preset adaptive-vivid --width 220
.\convert.cmd "C:\path\to\input.mp4" --output-dir output --formats "html,gif,mp4" --preset braille-color --width 160
```

## 预设说明

- `restore`：清晰还原黑白字符，适合先判断主体是否可读。
- `shader-color`：游戏后处理风格，使用源色和彩色字符。
- `shader-color-hd`：高清 shader 风格，启用 2x 超采样，速度更慢。
- `adaptive-color`：自适应混合字符，按局部区域混合普通字符、shader 字符和少量盲文细节。
- `adaptive-vivid`：保留自适应布局和原素材色相，轻微增强已有饱和度和主体亮度。
- `braille-color`：盲文点阵高精度字符，细节多但可能更像点阵画。
- `soft`：文字游戏柔和黑白风格。

## 输出格式

- `txt`：纯文本帧。
- `html`：可播放的本地 HTML 动画。
- `gif`：GIF 动图。
- `png`：首帧图片。
- `mp4`：MP4 视频，需要 FFmpeg。
- `ansi`：终端彩色动画，检测到 Chafa 时可借助 Chafa 输出。
- `dur`：Durdraw 兼容工程文件。
- `asciimation`：简单 Asciimation 文本格式。

## Windows 安装包

项目可以打包为一个当前用户安装的 MSI，不需要管理员权限。安装后会在开始菜单创建 `字影工坊 GlyphMotion` 快捷方式。

构建脚本会自动定位 FFmpeg；找不到时会优先通过 WinGet 安装 `Gyan.FFmpeg`，然后把 `ffmpeg.exe` 打进 GUI 程序。这样安装包装完后可以直接处理视频输入和 MP4 导出，不需要用户再单独配置 FFmpeg。

打包依赖：

- Python 3.12+ 和项目 `.venv`。
- PyInstaller：`.\.venv\Scripts\python.exe -m pip install pyinstaller`
- WiX Toolset CLI：`winget install --id WiXToolset.WiXCLI --source winget`
- FFmpeg：构建脚本会自动查找或安装。

构建：

```powershell
Set-Location E:\ASCII动画
.\build_msi.cmd
```

产物：

- `dist/windows/GlyphMotion.exe`
- `dist/windows/GlyphMotion-0.1.0-win64.msi`

发布带 FFmpeg 的安装包时，请保留 `LICENSE`、`NOTICE` 和 `THIRD_PARTY_NOTICES.md`。FFmpeg 是独立第三方程序，不按 GlyphMotion 的 PolyForm Noncommercial License 1.0.0 重新授权。

## 开发

```powershell
Set-Location E:\ASCII动画
.\.venv\Scripts\python.exe -m compileall ascii_oneclick tests
.\.venv\Scripts\python.exe tests\run_tests.py
```

`tests\run_tests.py` 会运行冒烟测试和全部 `test_*.py`。也可以单独运行某个文件，例如：

```powershell
.\.venv\Scripts\python.exe tests\smoke.py
.\.venv\Scripts\python.exe tests\test_cli.py
```

查看检测到的外部工具（不需要传入文件）：

```powershell
.\.venv\Scripts\python.exe -m ascii_oneclick.cli --tools
```

项目结构：

- `ascii_oneclick/core.py`：媒体读取、帧采样、字符映射、颜色处理。
- `ascii_oneclick/exporters.py`：TXT/HTML/GIF/PNG/MP4/DUR/ANSI/AAM 导出。
- `ascii_oneclick/presets.py`：CLI 与 GUI 共用的预设定义和 `apply_preset()`。
- `ascii_oneclick/formats.py`：导出格式定义、中文标签、默认选择、工具依赖。
- `ascii_oneclick/gui.py`：中文桌面 GUI。
- `ascii_oneclick/cli.py`：命令行入口。
- `tests/`：`smoke.py` 冒烟测试与 `test_*.py` 回归测试，`run_tests.py` 统一入口。

## 参考与兼容

GlyphMotion 的导出格式和效果方向参考了 Durdraw、Asciimation、Asciiville、PyAsciiFilm 以及一些网页 ASCII animation 实验。仓库不包含这些项目的源码副本；本地研究资料放在 `reference/`，默认不会进入 Git 提交。

## 使用许可

本项目使用 PolyForm Noncommercial License 1.0.0。见 [LICENSE](LICENSE)。

简单说：你可以在非商业目的下使用、研究、修改和分发 GlyphMotion；商业使用、商业打包、商业售卖、商业 SaaS 托管、付费再分发或商业产品集成都需要单独获得书面授权。

本项目是 source-available noncommercial software，不是 OSI 定义下的标准开源软件。
