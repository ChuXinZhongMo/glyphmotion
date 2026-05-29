from __future__ import annotations

import os
import queue
import random
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME
from .core import (
    CHARSETS,
    AsciiAnimation,
    ConversionCancelled as ConversionCancelledError,
    ConversionError,
    ConvertOptions,
    adaptive_char_aspect,
    convert_file,
    default_char_aspect,
    find_chafa,
    find_ffmpeg,
)
from .exporters import export_many
from .formats import DEFAULT_FORMAT_NAMES, FORMAT_LABELS, FORMATS_BY_NAME, OUTPUT_FORMATS
from .presets import PRESETS, PRESETS_BY_NAME, Preset
from .theme import apply_theme

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD as _TkDnD
    _TkBase: type = _TkDnD.Tk
except Exception:
    DND_FILES = None  # type: ignore[assignment]
    _TkBase = tk.Tk


CHARSET_LABELS = {
    "default": "默认字符（推荐）",
    "long": "细节增强",
    "blocks": "块状字符",
    "minimal": "简洁字符",
    "simple": "干净字符",
    "soft": "柔和字符",
    "restore": "清晰还原字符（推荐）",
    "shader": "游戏着色器风格",
    "jiejoe": "JIEJOE 绿色随机风格",
}
CHARSET_NAMES_BY_LABEL = {label: name for name, label in CHARSET_LABELS.items()}

RENDER_MODE_LABELS = {
    "ascii": "真正 ASCII 字符（推荐）",
    "adaptive": "自适应混合字符",
    "braille": "盲文高精度",
    "fullblock": "色块像素风（非 ASCII）",
    "halfblock": "高清半块（背景会变色）",
}
RENDER_MODE_NAMES_BY_LABEL = {label: name for name, label in RENDER_MODE_LABELS.items()}

DITHER_LABELS: dict[str, str] = {
    "none": "无抖动",
    "floyd-steinberg": "Floyd-Steinberg（平滑）",
    "atkinson": "Atkinson（细节多）",
    "bayer": "Bayer（有序）",
}
DITHER_NAMES_BY_LABEL = {v: k for k, v in DITHER_LABELS.items()}

# Preset labels come from the shared preset definitions; "custom" is GUI-only
# and means "leave the manually tuned controls as they are".
CUSTOM_PRESET_LABEL = "自定义"
PRESET_COMBO_VALUES = [preset.label for preset in PRESETS] + [CUSTOM_PRESET_LABEL]
PRESET_NAME_BY_LABEL = {preset.label: preset.name for preset in PRESETS}
PRESET_LABEL_BY_NAME = {preset.name: preset.label for preset in PRESETS}


@dataclass(frozen=True)
class ConversionRequest:
    """Immutable snapshot of everything a conversion needs.

    Built on the main thread from the Tkinter variables, then handed to the
    background worker. The worker must not read any Tkinter state.
    """

    input_paths: tuple[str, ...]
    output_dir: str
    formats: tuple[str, ...]
    options: ConvertOptions
    color: bool
    ffmpeg_path: str | None
    chafa_path: str | None


@dataclass(frozen=True)
class ConversionSuccess:
    animation: AsciiAnimation
    outputs: list[Path]
    preview: str


@dataclass(frozen=True)
class ConversionFailure:
    message: str


@dataclass(frozen=True)
class ConversionProgress:
    message: str
    # 0.0–1.0 overall completion, or None to update only the status text.
    fraction: float | None = None


@dataclass(frozen=True)
class ConversionCancelled:
    """The worker stopped early because the user asked to cancel."""


# Anything the worker may place on the queue for the UI thread to consume.
ConversionMessage = (
    ConversionSuccess | ConversionFailure | ConversionProgress | ConversionCancelled
)


class GlyphMotionApp(_TkBase):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x700")
        self.minsize(860, 560)
        self.work_queue: queue.Queue[ConversionMessage] = queue.Queue()
        self._conversion_running = False
        self._cancel_event: threading.Event | None = None
        self.last_outputs: list[Path] = []
        self.last_output_dir: Path | None = None

        # Preview state. Conversion shows a random frame to spot-check the
        # effect; prev/next/random let the user inspect other frames. There is
        # deliberately no auto-playback.
        self._preview_animation: AsciiAnimation | None = None
        self._preview_index = 0
        self._preview_tags: dict[tuple, str] = {}
        self._preview_font_sizes = (8, 11, 14)
        self._preview_zoom = 0

        self._input_files: list[str] = []
        self.output_var = tk.StringVar(value=str(Path.cwd() / "输出"))
        self.width_var = tk.IntVar(value=100)
        self.aspect_var = tk.DoubleVar(value=round(default_char_aspect(), 2))
        self.fps_var = tk.DoubleVar(value=12.0)
        self.max_frames_var = tk.IntVar(value=240)
        self.preset_var = tk.StringVar(value=PRESET_LABEL_BY_NAME["restore"])
        self.charset_var = tk.StringVar(value=CHARSET_LABELS["restore"])
        self.render_mode_var = tk.StringVar(value=RENDER_MODE_LABELS["ascii"])
        self.color_var = tk.BooleanVar(value=False)
        self.invert_var = tk.BooleanVar(value=False)
        self.autocontrast_var = tk.BooleanVar(value=True)
        self.clean_var = tk.BooleanVar(value=True)
        self.edges_var = tk.BooleanVar(value=False)
        self.hierarchy_var = tk.BooleanVar(value=True)
        self.separation_var = tk.BooleanVar(value=False)
        self.detail_var = tk.BooleanVar(value=True)
        self.color_grade = "source"
        self.supersample = 1
        self.vibrance = 0.0
        self.dither_var = tk.StringVar(value=DITHER_LABELS["none"])
        self.format_vars = {
            fmt.name: tk.BooleanVar(value=fmt.default) for fmt in OUTPUT_FORMATS
        }

        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self) -> None:
        self.theme = apply_theme(self)
        self.geometry("1240x900")
        self.minsize(1160, 860)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        shell = ttk.Frame(self, padding=12, style="App.TFrame")
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        self._build_header(shell)
        self._build_file_panel(shell)
        body = ttk.PanedWindow(shell, orient=tk.HORIZONTAL)
        body.grid(row=2, column=0, sticky="nsew", pady=(12, 0))

        controls = ttk.Frame(body, padding=(0, 0, 10, 0), style="App.TFrame")
        controls.columnconfigure(0, weight=1)

        right = ttk.Frame(body, style="App.TFrame")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        preview_section = self._make_section(right, "预览 / PREVIEW", indent=0)
        preview_section.grid(row=0, column=0, sticky="nsew")

        body.add(controls, weight=0)
        body.add(right, weight=1)

        self._build_control_panel(controls)
        self._build_preview_panel(preview_section.content)
        self._build_results_area(right)

    def _build_header(self, parent: ttk.Frame) -> None:
        # Standalone brand header that floats on the lavender page — no box or
        # full-width rule, so the title reads as the app's identity rather than
        # as a panel wrapping the content below.
        header = ttk.Frame(parent, style="Header.TFrame", padding=(2, 2, 2, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        title_box = ttk.Frame(header, style="Header.TFrame")
        title_box.grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, text="◆ GLYPHMOTION", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        # Short accent underline hugging just the title — a brand flourish, not
        # a divider across the whole window.
        underline = tk.Frame(
            title_box, height=3, bg=self.theme.accent, bd=0, highlightthickness=0
        )
        underline.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        ttk.Label(
            header,
            text="字影工坊 · CHARACTER ANIMATION STUDIO",
            style="Subtitle.TLabel",
        ).grid(row=0, column=1, sticky="se", pady=(0, 2))

    def _make_section(self, parent: tk.Misc, title: str, *, indent: int = 12) -> ttk.Frame:
        """A flat section: an accented heading on the lavender page with a
        content frame below — no card, no shadow. Exposed as ``section.content``.

        ``indent`` left-pads the content so small control groups read as
        belonging to their heading; pass ``0`` for full-width panels (preview,
        file list) where indentation would only create an asymmetric gap.
        """
        section = ttk.Frame(parent, style="App.TFrame")
        section.columnconfigure(0, weight=1)
        section.rowconfigure(1, weight=1)
        ttk.Label(section, text=title, style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        content = ttk.Frame(section, style="App.TFrame", padding=(indent, 0, 0, 0))
        content.grid(row=1, column=0, sticky="nsew")
        # Callers configure their own column weights (e.g. the field column for
        # label/field rows, or column 0 for a full-width preview/list).
        section.content = content  # type: ignore[attr-defined]
        return section

    def _build_file_panel(self, parent: ttk.Frame) -> None:
        section = self._make_section(parent, "文件 / SOURCE", indent=0)
        section.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        file_frame = section.content
        file_frame.columnconfigure(0, weight=1)

        # --- input list ---
        list_frame = ttk.Frame(file_frame, style="App.TFrame")
        list_frame.grid(row=0, column=0, columnspan=3, sticky="ew")
        list_frame.columnconfigure(0, weight=1)
        ttk.Label(list_frame, text="输入", style="Page.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        self.file_listbox = tk.Listbox(
            list_frame,
            height=4,
            activestyle="none",
            bg=self.theme.input_bg,
            fg=self.theme.fg,
            selectbackground=self.theme.accent,
            selectforeground="#ffffff",
            highlightthickness=1,
            highlightbackground=self.theme.border,
            highlightcolor=self.theme.accent,
            borderwidth=0,
            relief="flat",
            font=(self.theme.mono_font, 9),
        )
        self.file_listbox.grid(row=1, column=0, sticky="ew")
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=sb.set)
        sb.grid(row=1, column=1, sticky="ns")

        if DND_FILES:
            self.file_listbox.drop_target_register(DND_FILES)
            self.file_listbox.dnd_bind("<<Drop>>", self._on_drop)
            hint = "支持拖拽"
        else:
            hint = ""

        btn_row = ttk.Frame(list_frame, style="App.TFrame")
        btn_row.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(btn_row, text="+ 添加文件", command=self._choose_input).grid(row=0, column=0)
        ttk.Button(btn_row, text="移除所选", command=self._remove_input_file).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(btn_row, text="清空", command=self._clear_input_files).grid(row=0, column=2, padx=(8, 0))
        if hint:
            ttk.Label(btn_row, text=hint, style="Page.TLabel").grid(row=0, column=3, padx=(12, 0))

        # --- output dir ---
        out_row = ttk.Frame(file_frame, style="App.TFrame")
        out_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        out_row.columnconfigure(1, weight=1)
        ttk.Label(out_row, text="输出", style="Page.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(out_row, textvariable=self.output_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(out_row, text="选择目录", command=self._choose_output).grid(row=0, column=2, padx=(8, 0))

    def _build_control_panel(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")
        parent.rowconfigure(0, weight=1)

        settings_tab = ttk.Frame(notebook, padding=10)
        output_tab = ttk.Frame(notebook, padding=10)
        notebook.add(settings_tab, text="转换参数")
        notebook.add(output_tab, text="导出格式")
        settings_tab.columnconfigure(0, weight=1)
        output_tab.columnconfigure(0, weight=1)

        self._build_settings_tab(settings_tab)
        self._build_output_tab(output_tab)

        action_frame = ttk.Frame(parent, padding=(0, 12, 0, 0), style="App.TFrame")
        action_frame.grid(row=1, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=1)

        self.convert_button = ttk.Button(
            action_frame,
            text="开始转换",
            style="Primary.TButton",
            command=self._start_convert,
        )
        self.convert_button.grid(row=0, column=0, sticky="ew")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            action_frame,
            orient=tk.HORIZONTAL,
            mode="determinate",
            maximum=100.0,
            variable=self.progress_var,
            style="Glyph.Horizontal.TProgressbar",
        )
        # Created hidden; shown only while a conversion is running.
        self._progress_pady = (8, 0)

        self.status_var = tk.StringVar(value="● 就绪 / READY")
        self.status_label = ttk.Label(
            action_frame,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=300,
        )
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(8, 0))

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.configure(foreground=self.theme.accent2 if error else self.theme.accent)
        self.status_var.set(text)

    def _build_results_area(self, parent: ttk.Frame) -> None:
        section = self._make_section(parent, "输出文件 / OUTPUT", indent=0)
        section.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        results = section.content
        results.columnconfigure(0, weight=1)

        self.output_list = tk.Listbox(
            results,
            height=4,
            activestyle="none",
            bg=self.theme.input_bg,
            fg=self.theme.fg,
            selectbackground=self.theme.accent,
            selectforeground="#ffffff",
            highlightthickness=1,
            highlightbackground=self.theme.border,
            highlightcolor=self.theme.border,
            borderwidth=0,
            relief="flat",
            font=(self.theme.mono_font, 9),
        )
        self.output_list.grid(row=0, column=0, sticky="ew")
        list_scroll = ttk.Scrollbar(results, orient=tk.VERTICAL, command=self.output_list.yview)
        self.output_list.configure(yscrollcommand=list_scroll.set)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.output_list.bind("<Double-Button-1>", lambda _event: self._open_selected_output())

        buttons = ttk.Frame(results)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.open_dir_button = ttk.Button(
            buttons, text="打开输出目录", command=self._open_output_dir, state=tk.DISABLED
        )
        self.open_dir_button.grid(row=0, column=0, sticky="w")
        self.open_file_button = ttk.Button(
            buttons, text="打开所选文件", command=self._open_selected_output, state=tk.DISABLED
        )
        self.open_file_button.grid(row=0, column=1, sticky="w", padx=(8, 0))

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        # Subtle rule under the tab strip so sections read as one airy column.
        rule = tk.Frame(parent, height=1, bg=self.theme.border, bd=0, highlightthickness=0)
        rule.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        preset = self._make_section(parent, "预设 / PRESET")
        preset.grid(row=1, column=0, sticky="ew")
        preset_frame = preset.content
        preset_frame.columnconfigure(1, weight=1)

        ttk.Label(preset_frame, text="效果", style="Page.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        preset_combo = ttk.Combobox(
            preset_frame,
            values=PRESET_COMBO_VALUES,
            textvariable=self.preset_var,
            width=28,
            state="readonly",
        )
        preset_combo.grid(row=0, column=1, sticky="ew")
        self.preset_var.trace_add("write", self._on_preset_changed)

        grid_section = self._make_section(parent, "尺寸与时间 / GEOMETRY")
        grid_section.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        grid_frame = grid_section.content
        grid_frame.columnconfigure(1, weight=1)
        grid_frame.columnconfigure(3, weight=1)

        self._add_spinbox(grid_frame, 0, 0, "宽度", self.width_var, 20, 1000, 10)
        self._add_spinbox(grid_frame, 0, 2, "比例", self.aspect_var, 0.35, 0.80, 0.01)
        self._add_spinbox(grid_frame, 1, 0, "帧率", self.fps_var, 1, 60, 1)
        self._add_spinbox(grid_frame, 1, 2, "帧数", self.max_frames_var, 1, 5000, 10)

        render_section = self._make_section(parent, "字符与渲染 / RENDER")
        render_section.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        render_frame = render_section.content
        render_frame.columnconfigure(1, weight=1)

        ttk.Label(render_frame, text="字符", style="Page.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(
            render_frame,
            values=[CHARSET_LABELS[name] for name in CHARSETS],
            textvariable=self.charset_var,
            state="readonly",
        ).grid(row=0, column=1, sticky="ew")

        ttk.Label(render_frame, text="模式", style="Page.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Combobox(
            render_frame,
            values=list(RENDER_MODE_LABELS.values()),
            textvariable=self.render_mode_var,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(render_frame, text="抖动", style="Page.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Combobox(
            render_frame,
            values=list(DITHER_LABELS.values()),
            textvariable=self.dither_var,
            state="readonly",
            width=28,
        ).grid(row=2, column=1, sticky="ew", pady=(8, 0))

        options_section = self._make_section(parent, "处理选项 / OPTIONS")
        options_section.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        options_frame = options_section.content
        columns = 2
        for column in range(columns):
            options_frame.columnconfigure(column, weight=1)

        checks = [
            ("保留颜色", self.color_var),
            ("反转明暗", self.invert_var),
            ("增强对比", self.autocontrast_var),
            ("干净模式", self.clean_var),
            ("主体层次", self.hierarchy_var),
            ("区域分离", self.separation_var),
            ("细节还原", self.detail_var),
            ("硬轮廓线", self.edges_var),
        ]
        for index, (label, variable) in enumerate(checks):
            ttk.Checkbutton(options_frame, text=label, variable=variable, style="Flat.TCheckbutton").grid(
                row=index // columns,
                column=index % columns,
                sticky="w",
                padx=(0, 12),
                pady=3,
            )

    def _build_output_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        # Subtle rule under the tab strip to match the settings tab.
        rule = tk.Frame(parent, height=1, bg=self.theme.border, bd=0, highlightthickness=0)
        rule.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        actions = ttk.Frame(parent, style="App.TFrame")
        actions.grid(row=1, column=0, sticky="ew")
        ttk.Button(actions, text="常用", command=self._select_common_formats).grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="全选", command=self._select_all_formats).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(actions, text="清空", command=self._clear_formats).grid(row=0, column=2, sticky="w", padx=(8, 0))

        formats_section = self._make_section(parent, "格式 / FORMATS")
        formats_section.grid(row=2, column=0, sticky="new", pady=(16, 0))
        formats_frame = formats_section.content
        for column in range(2):
            formats_frame.columnconfigure(column, weight=1)

        # Detect external tools once so MP4/ANSI can show their dependency.
        tool_available = {"ffmpeg": find_ffmpeg() is not None, "chafa": find_chafa() is not None}
        for index, (name, variable) in enumerate(self.format_vars.items()):
            ttk.Checkbutton(
                formats_frame,
                text=self._format_checkbox_label(name, tool_available),
                variable=variable,
                style="Flat.TCheckbutton",
            ).grid(row=index // 2, column=index % 2, sticky="w", pady=4, padx=(0, 10))

    @staticmethod
    def _format_checkbox_label(name: str, tool_available: dict[str, bool]) -> str:
        fmt = FORMATS_BY_NAME.get(name)
        if fmt is None:
            return FORMAT_LABELS.get(name, name)
        if not fmt.requires_tool:
            return fmt.label
        tool_display = {"ffmpeg": "FFmpeg", "chafa": "Chafa"}[fmt.requires_tool]
        available = tool_available.get(fmt.requires_tool, False)
        if fmt.tool_optional:
            note = f"建议 {tool_display}" if available else f"{tool_display} 未检测到，将用内置降级"
        else:
            note = f"需 {tool_display}" if available else f"需 {tool_display}，未检测到"
        return f"{fmt.label}（{note}）"

    def _build_preview_panel(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        screen = tk.Frame(
            parent,
            bg=self.theme.preview_bg,
            bd=0,
            highlightthickness=1,
            highlightbackground=self.theme.border,
            highlightcolor=self.theme.border,
        )
        screen.grid(row=0, column=0, sticky="nsew")
        screen.rowconfigure(0, weight=1)
        screen.columnconfigure(0, weight=1)

        self.preview = tk.Text(
            screen,
            wrap="none",
            bg=self.theme.preview_bg,
            fg=self.theme.preview_fg,
            insertbackground=self.theme.accent,
            selectbackground=self.theme.accent,
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=(self.theme.mono_font, self._preview_font_sizes[self._preview_zoom]),
            cursor="arrow",
        )
        self.preview.grid(row=0, column=0, sticky="nsew")
        ybar = ttk.Scrollbar(screen, orient=tk.VERTICAL, command=self.preview.yview)
        xbar = ttk.Scrollbar(screen, orient=tk.HORIZONTAL, command=self.preview.xview)
        self.preview.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")

        toolbar = ttk.Frame(parent, style="App.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        toolbar.columnconfigure(4, weight=1)

        self.prev_button = ttk.Button(toolbar, text="◀ 上一帧", command=self._preview_prev, state=tk.DISABLED)
        self.prev_button.grid(row=0, column=0)
        self.random_button = ttk.Button(toolbar, text="🎲 随机一帧", command=self._preview_random, state=tk.DISABLED)
        self.random_button.grid(row=0, column=1, padx=(8, 0))
        self.next_button = ttk.Button(toolbar, text="下一帧 ▶", command=self._preview_next, state=tk.DISABLED)
        self.next_button.grid(row=0, column=2, padx=(8, 0))

        self.preview_meta_var = tk.StringVar(value="帧 0 / 0")
        ttk.Label(toolbar, textvariable=self.preview_meta_var, style="Page.TLabel").grid(row=0, column=3, padx=(12, 0))

        ttk.Button(toolbar, text="A－", width=4, command=lambda: self._zoom_preview(-1)).grid(row=0, column=5)
        ttk.Button(toolbar, text="A＋", width=4, command=lambda: self._zoom_preview(1)).grid(row=0, column=6, padx=(8, 0))

    # ----- colored preview rendering -------------------------------------

    def _clear_preview(self) -> None:
        self._preview_animation = None
        self.preview.configure(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.configure(state=tk.DISABLED)
        self.preview_meta_var.set("帧 0 / 0")
        for button in (self.prev_button, self.random_button, self.next_button):
            button.configure(state=tk.DISABLED)

    def _set_preview_animation(self, animation: AsciiAnimation) -> None:
        self._preview_animation = animation
        # Spot-check the result on a random frame rather than always frame 0,
        # so a single glance is more representative of the whole clip.
        index = random.randrange(len(animation.frames)) if animation.frames else 0
        self._render_preview_frame(index)
        multi = len(animation.frames) > 1
        state = tk.NORMAL if multi else tk.DISABLED
        for button in (self.prev_button, self.random_button, self.next_button):
            button.configure(state=state)

    def _preview_prev(self) -> None:
        animation = self._preview_animation
        if not animation:
            return
        self._render_preview_frame((self._preview_index - 1) % len(animation.frames))

    def _preview_next(self) -> None:
        animation = self._preview_animation
        if not animation:
            return
        self._render_preview_frame((self._preview_index + 1) % len(animation.frames))

    def _preview_random(self) -> None:
        animation = self._preview_animation
        if not animation or len(animation.frames) <= 1:
            return
        # Jump to a different frame than the one already shown.
        choices = [i for i in range(len(animation.frames)) if i != self._preview_index]
        self._render_preview_frame(random.choice(choices))

    def _zoom_preview(self, delta: int) -> None:
        self._preview_zoom = max(0, min(len(self._preview_font_sizes) - 1, self._preview_zoom + delta))
        self.preview.configure(font=(self.theme.mono_font, self._preview_font_sizes[self._preview_zoom]))

    def _render_preview_frame(self, index: int) -> None:
        animation = self._preview_animation
        if not animation or not animation.frames:
            return
        index = max(0, min(index, len(animation.frames) - 1))
        self._preview_index = index
        frame = animation.frames[index]
        text = self.preview
        text.configure(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        try:
            self._insert_colored_frame(frame)
        except Exception:
            # Colour rendering must never block the user from seeing output.
            text.delete("1.0", tk.END)
            text.insert("1.0", "\n".join(frame.lines))
        text.configure(state=tk.DISABLED)
        self.preview_meta_var.set(f"帧 {index + 1} / {len(animation.frames)}")

    def _insert_colored_frame(self, frame) -> None:
        """Insert one frame, colouring runs of same-coloured characters."""
        text = self.preview
        colors = frame.colors
        bg_colors = frame.bg_colors
        for y, line in enumerate(frame.lines):
            row_fg = colors[y]
            row_bg = bg_colors[y] if bg_colors else None
            width = len(line)
            x = 0
            while x < width:
                fg = row_fg[x]
                bg = row_bg[x] if row_bg else None
                end = x + 1
                while end < width and row_fg[end] == fg and (row_bg[end] if row_bg else None) == bg:
                    end += 1
                text.insert(tk.END, line[x:end], self._preview_tag(fg, bg))
                x = end
            text.insert(tk.END, "\n")

    def _preview_tag(self, fg: tuple, bg: tuple | None) -> str:
        key = (fg, bg)
        tag = self._preview_tags.get(key)
        if tag is None:
            tag = f"pc{len(self._preview_tags)}"
            options = {"foreground": "#%02x%02x%02x" % tuple(fg)}
            if bg is not None:
                options["background"] = "#%02x%02x%02x" % tuple(bg)
            self.preview.tag_configure(tag, **options)
            self._preview_tags[key] = tag
        return tag

    def _add_spinbox(
        self,
        parent: ttk.Frame,
        row: int,
        column: int,
        label: str,
        variable: tk.Variable,
        from_: float,
        to: float,
        increment: float,
    ) -> None:
        ttk.Label(parent, text=label, style="Page.TLabel").grid(row=row, column=column, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(
            parent,
            from_=from_,
            to=to,
            increment=increment,
            textvariable=variable,
            width=9,
        ).grid(row=row, column=column + 1, sticky="ew", pady=4, padx=(0, 12))

    def _select_common_formats(self) -> None:
        common = set(DEFAULT_FORMAT_NAMES)
        for name, variable in self.format_vars.items():
            variable.set(name in common)

    def _select_all_formats(self) -> None:
        for variable in self.format_vars.values():
            variable.set(True)

    def _clear_formats(self) -> None:
        for variable in self.format_vars.values():
            variable.set(False)

    def _choose_input(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择图片、GIF 或视频",
            filetypes=[
                ("媒体文件", "*.png *.jpg *.jpeg *.gif *.webp *.bmp *.mp4 *.mov *.mkv *.avi *.wmv *.webm"),
                ("所有文件", "*.*"),
            ],
        )
        if paths:
            self._add_input_files(list(paths))

    def _add_input_files(self, paths: list[str]) -> None:
        existing = set(self._input_files)
        for p in paths:
            if p not in existing:
                self._input_files.append(p)
                existing.add(p)
                self.file_listbox.insert(tk.END, Path(p).name)
        if self._input_files and not self.output_var.get().strip():
            self.output_var.set(str(Path(self._input_files[0]).parent / "ASCII输出"))

    def _remove_input_file(self) -> None:
        sel = list(self.file_listbox.curselection())
        for idx in reversed(sel):
            self.file_listbox.delete(idx)
            del self._input_files[idx]

    def _clear_input_files(self) -> None:
        self._input_files.clear()
        self.file_listbox.delete(0, tk.END)

    def _on_drop(self, event: object) -> None:
        raw = getattr(event, "data", "")
        try:
            paths = self.tk.splitlist(raw)
        except Exception:
            paths = [raw]
        media_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
                      ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm"}
        valid = [p for p in paths if Path(p).suffix.lower() in media_exts]
        if valid:
            self._add_input_files(valid)

    def _on_preset_changed(self, *_args: object) -> None:
        name = PRESET_NAME_BY_LABEL.get(self.preset_var.get())
        if name is None:  # "custom" or an unknown label: keep manual settings.
            return
        self._apply_preset(PRESETS_BY_NAME[name])

    def _apply_preset(self, preset: Preset) -> None:
        """Apply a shared Preset to the GUI controls.

        Core render fields come from ``preset.options_patch`` (the same patch
        the CLI applies), so the two front-ends stay in sync. ``recommended_*``
        and ``use_adaptive_aspect`` are GUI-only sizing hints.
        """
        patch = preset.options_patch
        self.charset_var.set(CHARSET_LABELS[patch["charset_name"]])
        self.render_mode_var.set(RENDER_MODE_LABELS[patch["render_mode"]])
        self.color_var.set(patch["color"])
        self.color_grade = patch["color_grade"]
        self.supersample = patch["supersample"]
        self.vibrance = patch.get("vibrance", 0.0)
        self.hierarchy_var.set(patch["hierarchy"])
        self.separation_var.set(patch["separation"])
        self.detail_var.set(patch["detail"])
        self.clean_var.set(patch["clean"])
        self.edges_var.set(patch["edges"])

        if preset.recommended_width:
            self.width_var.set(max(self.width_var.get(), preset.recommended_width))
        if preset.recommended_max_frames:
            self.max_frames_var.set(min(self.max_frames_var.get(), preset.recommended_max_frames))
        if preset.use_adaptive_aspect:
            self.aspect_var.set(round(adaptive_char_aspect(), 2))

    def _choose_output(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_var.set(path)

    def _selected_formats(self) -> list[str]:
        return [name for name, variable in self.format_vars.items() if variable.get()]

    def _start_convert(self) -> None:
        if self._conversion_running:
            # Guard against a second conversion while one is in flight.
            return
        if not self._input_files:
            messagebox.showerror("缺少输入文件", "请先添加至少一个图片、GIF 或视频文件。")
            return
        formats = self._selected_formats()
        if not formats:
            messagebox.showerror("缺少导出格式", "请至少选择一种导出格式。")
            return

        request = self._build_request(formats)

        self._conversion_running = True
        self._cancel_event = threading.Event()
        # The convert button doubles as a cancel button while work is running.
        self.convert_button.configure(
            text="取消转换 / CANCEL",
            style="Danger.TButton",
            command=self._cancel_convert,
            state=tk.NORMAL,
        )
        self._show_progress()
        self._set_status("● 正在转换 / RUNNING…")
        self._clear_preview()
        thread = threading.Thread(
            target=self._convert_worker, args=(request, self._cancel_event), daemon=True
        )
        thread.start()

    def _cancel_convert(self) -> None:
        if not self._conversion_running or self._cancel_event is None:
            return
        self._cancel_event.set()
        # Disable until the worker acknowledges, so it can't be clicked twice.
        self.convert_button.configure(state=tk.DISABLED)
        self._set_status("● 正在取消 / CANCELLING…")

    def _show_progress(self) -> None:
        self.progress_var.set(0.0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=self._progress_pady)

    def _hide_progress(self) -> None:
        self.progress_bar.grid_remove()

    def _build_request(self, formats: list[str]) -> ConversionRequest:
        """Read every Tkinter variable on the main thread into a snapshot."""
        charset_name = CHARSET_NAMES_BY_LABEL.get(self.charset_var.get(), "default")
        use_color = self.color_var.get()
        options = ConvertOptions(
            columns=self.width_var.get(),
            fps=self.fps_var.get(),
            charset_name=charset_name,
            render_mode=RENDER_MODE_NAMES_BY_LABEL.get(self.render_mode_var.get(), "ascii"),
            invert=self.invert_var.get(),
            color=use_color,
            max_frames=self.max_frames_var.get(),
            char_aspect=self.aspect_var.get(),
            autocontrast=self.autocontrast_var.get(),
            clean=self.clean_var.get(),
            edges=self.edges_var.get(),
            hierarchy=self.hierarchy_var.get(),
            separation=self.separation_var.get(),
            detail=self.detail_var.get(),
            color_grade=self.color_grade,
            supersample=self.supersample,
            vibrance=self.vibrance,
            dither=DITHER_NAMES_BY_LABEL.get(self.dither_var.get(), "none"),
        )
        return ConversionRequest(
            input_paths=tuple(self._input_files),
            output_dir=self.output_var.get(),
            formats=tuple(formats),
            options=options,
            color=use_color,
            ffmpeg_path=find_ffmpeg(),
            chafa_path=find_chafa(),
        )

    def _convert_worker(self, request: ConversionRequest, cancel_event: threading.Event) -> None:
        """Run the conversion off the main thread using only the snapshot.

        Progress and cancellation cross the thread boundary through the work
        queue / the shared ``cancel_event``; the worker never touches Tkinter.
        Frame rendering takes the bulk of the time, so it owns most of the
        progress range (5–78%) and export fills the rest.
        """

        def should_cancel() -> bool:
            return cancel_event.is_set()

        def on_frame(done: int, total: int) -> None:
            fraction = 0.05 + 0.73 * (done / max(1, total))
            self.work_queue.put(
                ConversionProgress(f"● 渲染帧 / FRAMES {done}/{total}", fraction)
            )

        def on_export(done: int, total: int, name: str) -> None:
            fraction = 0.78 + 0.22 * (done / max(1, total))
            self.work_queue.put(
                ConversionProgress(f"● 导出 / EXPORT {name.upper()} {done}/{total}", fraction)
            )

        try:
            n_files = len(request.input_paths)
            all_outputs: list[Path] = []
            last_animation = None

            for file_idx, input_path in enumerate(request.input_paths):
                file_base = file_idx / n_files
                file_span = 1.0 / n_files
                fname = Path(input_path).name

                def on_frame(done: int, total: int, _b: float = file_base, _s: float = file_span) -> None:
                    frac = _b + _s * (0.05 + 0.73 * (done / max(1, total)))
                    self.work_queue.put(ConversionProgress(
                        f"● [{file_idx + 1}/{n_files}] {fname} — 渲染帧 {done}/{total}", frac))

                def on_export(done: int, total: int, name: str,
                              _b: float = file_base, _s: float = file_span) -> None:
                    frac = _b + _s * (0.78 + 0.22 * (done / max(1, total)))
                    self.work_queue.put(ConversionProgress(
                        f"● [{file_idx + 1}/{n_files}] {fname} — 导出 {name.upper()} {done}/{total}", frac))

                self.work_queue.put(ConversionProgress(
                    f"● [{file_idx + 1}/{n_files}] {fname} — 解码中…", file_base + file_span * 0.02))

                animation = convert_file(
                    input_path,
                    request.options,
                    ffmpeg_path=request.ffmpeg_path,
                    progress=on_frame,
                    should_cancel=should_cancel,
                )
                outputs = export_many(
                    animation,
                    request.output_dir,
                    list(request.formats),
                    color=request.color,
                    ffmpeg_path=request.ffmpeg_path,
                    chafa_path=request.chafa_path,
                    progress=on_export,
                    should_cancel=should_cancel,
                )
                all_outputs.extend(outputs)
                last_animation = animation

            preview = "\n".join(last_animation.frames[0].lines) if last_animation else ""
            self.work_queue.put(ConversionSuccess(
                animation=last_animation, outputs=all_outputs, preview=preview))
        except ConversionCancelledError:
            self.work_queue.put(ConversionCancelled())
        except (ConversionError, OSError, RuntimeError, ValueError) as exc:
            self.work_queue.put(ConversionFailure(message=str(exc)))

    def _poll_queue(self) -> None:
        try:
            message = self.work_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_queue)
            return

        if isinstance(message, ConversionProgress):
            self._set_status(message.message)
            if message.fraction is not None:
                self.progress_var.set(max(0.0, min(100.0, message.fraction * 100)))
        elif isinstance(message, ConversionSuccess):
            self.progress_var.set(100.0)
            self._finish_conversion()
            self._set_preview_animation(message.animation)
            self._set_outputs(message.outputs)
            self._set_status(
                f"● 完成 / DONE — {len(message.animation.frames)} 帧，{len(message.outputs)} 个文件"
            )
        elif isinstance(message, ConversionCancelled):
            self._finish_conversion()
            self._set_status("● 已取消 / CANCELLED")
        elif isinstance(message, ConversionFailure):
            self._finish_conversion()
            self._set_status("● 转换失败 / FAILED", error=True)
            messagebox.showerror("转换失败", message.message)
        self.after(100, self._poll_queue)

    def _finish_conversion(self) -> None:
        self._conversion_running = False
        self._cancel_event = None
        self._hide_progress()
        self.convert_button.configure(
            text="开始转换",
            style="Primary.TButton",
            command=self._start_convert,
            state=tk.NORMAL,
        )

    def _set_outputs(self, outputs: list[Path]) -> None:
        self.last_outputs = list(outputs)
        self.last_output_dir = outputs[0].parent if outputs else None
        self.output_list.delete(0, tk.END)
        for path in self.last_outputs:
            self.output_list.insert(tk.END, path.name)
        has_outputs = bool(self.last_outputs)
        self.open_dir_button.configure(state=tk.NORMAL if self.last_output_dir else tk.DISABLED)
        self.open_file_button.configure(state=tk.NORMAL if has_outputs else tk.DISABLED)
        if has_outputs:
            self.output_list.selection_clear(0, tk.END)
            self.output_list.selection_set(0)

    def _open_output_dir(self) -> None:
        if self.last_output_dir and self.last_output_dir.exists():
            self._open_path(self.last_output_dir)
        else:
            messagebox.showinfo("没有输出目录", "请先完成一次转换。")

    def _open_selected_output(self) -> None:
        selection = self.output_list.curselection()
        if not selection or not self.last_outputs:
            return
        target = self.last_outputs[selection[0]]
        if target.exists():
            self._open_path(target)
        else:
            messagebox.showinfo("文件不存在", f"未找到文件：{target}")

    def _open_path(self, target: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(target)], check=False)
            else:
                subprocess.run(["xdg-open", str(target)], check=False)
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc))


def main() -> None:
    app = GlyphMotionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
