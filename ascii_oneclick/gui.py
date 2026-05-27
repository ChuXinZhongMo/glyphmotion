from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME
from .core import (
    CHARSETS,
    ConversionError,
    ConvertOptions,
    adaptive_char_aspect,
    convert_file,
    default_char_aspect,
    find_chafa,
    find_ffmpeg,
)
from .exporters import export_many


FORMAT_LABELS = {
    "txt": "TXT 文本",
    "html": "HTML 动画网页",
    "gif": "GIF 动图",
    "png": "PNG 首帧图片",
    "mp4": "MP4 视频",
    "dur": "Durdraw 工程 (.dur)",
    "ansi": "ANSI 终端动画",
    "asciimation": "Asciimation 文本 (.aam)",
}

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

PRESET_LABELS = {
    "restore": "清晰还原（黑白）",
    "shader_mono": "游戏着色器（黑白）",
    "shader_color": "游戏着色器（原色彩色）",
    "shader_color_hd": "游戏着色器（原色高清）",
    "adaptive_mono": "自适应混合字符（黑白）",
    "adaptive_color": "自适应混合字符（原色彩色）",
    "adaptive_vivid": "自适应混合字符（原色鲜艳）",
    "braille_mono": "盲文高精度（黑白）",
    "braille_color": "盲文高精度（彩色）",
    "shader_warm": "游戏着色器（暖色彩色）",
    "soft": "文字游戏柔和（黑白）",
    "custom": "自定义",
}
PRESET_NAMES_BY_LABEL = {label: name for name, label in PRESET_LABELS.items()}


class GlyphMotionApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x700")
        self.minsize(860, 560)
        self.work_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd() / "输出"))
        self.width_var = tk.IntVar(value=100)
        self.aspect_var = tk.DoubleVar(value=round(default_char_aspect(), 2))
        self.fps_var = tk.DoubleVar(value=12.0)
        self.max_frames_var = tk.IntVar(value=240)
        self.preset_var = tk.StringVar(value=PRESET_LABELS["restore"])
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
        self.format_vars = {
            "txt": tk.BooleanVar(value=True),
            "html": tk.BooleanVar(value=True),
            "gif": tk.BooleanVar(value=True),
            "png": tk.BooleanVar(value=True),
            "mp4": tk.BooleanVar(value=False),
            "dur": tk.BooleanVar(value=True),
            "ansi": tk.BooleanVar(value=False),
            "asciimation": tk.BooleanVar(value=True),
        }

        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self) -> None:
        self._configure_style()
        self.geometry("1180x760")
        self.minsize(1040, 640)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        shell = ttk.Frame(self, padding=12, style="App.TFrame")
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        self._build_file_panel(shell)
        body = ttk.PanedWindow(shell, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew", pady=(12, 0))

        controls = ttk.Frame(body, padding=(0, 0, 10, 0), style="App.TFrame")
        controls.columnconfigure(0, weight=1)
        preview_frame = ttk.LabelFrame(body, text="预览", padding=10)
        body.add(controls, weight=0)
        body.add(preview_frame, weight=1)

        self._build_control_panel(controls)
        self._build_preview_panel(preview_frame)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background="#f3f4f6")
        style.configure("TLabelframe", padding=8)
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(10, 6))
        style.configure("Status.TLabel", foreground="#4b5563")

    def _build_file_panel(self, parent: ttk.Frame) -> None:
        file_frame = ttk.LabelFrame(parent, text="文件", padding=10)
        file_frame.grid(row=0, column=0, sticky="ew")
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="输入").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(file_frame, textvariable=self.input_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(file_frame, text="选择文件", command=self._choose_input).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(file_frame, text="输出").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(file_frame, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(file_frame, text="选择目录", command=self._choose_output).grid(row=1, column=2, padx=(8, 0), pady=(8, 0))

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

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(
            action_frame,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=300,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        preset_frame = ttk.LabelFrame(parent, text="预设", padding=10)
        preset_frame.grid(row=0, column=0, sticky="ew")
        preset_frame.columnconfigure(1, weight=1)

        ttk.Label(preset_frame, text="效果").grid(row=0, column=0, sticky="w", padx=(0, 8))
        preset_combo = ttk.Combobox(
            preset_frame,
            values=list(PRESET_LABELS.values()),
            textvariable=self.preset_var,
            width=28,
            state="readonly",
        )
        preset_combo.grid(row=0, column=1, sticky="ew")
        self.preset_var.trace_add("write", self._on_preset_changed)

        grid_frame = ttk.LabelFrame(parent, text="尺寸与时间", padding=10)
        grid_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        grid_frame.columnconfigure(1, weight=1)
        grid_frame.columnconfigure(3, weight=1)

        self._add_spinbox(grid_frame, 0, 0, "宽度", self.width_var, 20, 1000, 10)
        self._add_spinbox(grid_frame, 0, 2, "比例", self.aspect_var, 0.35, 0.80, 0.01)
        self._add_spinbox(grid_frame, 1, 0, "帧率", self.fps_var, 1, 60, 1)
        self._add_spinbox(grid_frame, 1, 2, "帧数", self.max_frames_var, 1, 5000, 10)

        render_frame = ttk.LabelFrame(parent, text="字符与渲染", padding=10)
        render_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        render_frame.columnconfigure(1, weight=1)

        ttk.Label(render_frame, text="字符").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(
            render_frame,
            values=[CHARSET_LABELS[name] for name in CHARSETS],
            textvariable=self.charset_var,
            state="readonly",
        ).grid(row=0, column=1, sticky="ew")

        ttk.Label(render_frame, text="模式").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Combobox(
            render_frame,
            values=list(RENDER_MODE_LABELS.values()),
            textvariable=self.render_mode_var,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=(8, 0))

        options_frame = ttk.LabelFrame(parent, text="处理选项", padding=10)
        options_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for column in range(2):
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
            ttk.Checkbutton(options_frame, text=label, variable=variable).grid(
                row=index // 2,
                column=index % 2,
                sticky="w",
                pady=3,
            )

    def _build_output_tab(self, parent: ttk.Frame) -> None:
        actions = ttk.Frame(parent)
        actions.grid(row=0, column=0, sticky="ew")
        ttk.Button(actions, text="常用", command=self._select_common_formats).grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="全选", command=self._select_all_formats).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(actions, text="清空", command=self._clear_formats).grid(row=0, column=2, sticky="w", padx=(8, 0))

        formats_frame = ttk.LabelFrame(parent, text="格式", padding=10)
        formats_frame.grid(row=1, column=0, sticky="new", pady=(10, 0))
        for column in range(2):
            formats_frame.columnconfigure(column, weight=1)

        for index, (name, variable) in enumerate(self.format_vars.items()):
            ttk.Checkbutton(
                formats_frame,
                text=FORMAT_LABELS.get(name, name),
                variable=variable,
            ).grid(row=index // 2, column=index % 2, sticky="w", pady=4, padx=(0, 10))

    def _build_preview_panel(self, parent: ttk.LabelFrame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.preview = tk.Text(
            parent,
            wrap="none",
            bg="#080808",
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            selectbackground="#374151",
            relief="flat",
            borderwidth=0,
            font=("Consolas", 8),
        )
        self.preview.grid(row=0, column=0, sticky="nsew")
        ybar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.preview.yview)
        xbar = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.preview.xview)
        self.preview.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")

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
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(
            parent,
            from_=from_,
            to=to,
            increment=increment,
            textvariable=variable,
            width=9,
        ).grid(row=row, column=column + 1, sticky="ew", pady=4, padx=(0, 12))

    def _select_common_formats(self) -> None:
        common = {"txt", "html", "gif", "png", "dur", "asciimation"}
        for name, variable in self.format_vars.items():
            variable.set(name in common)

    def _select_all_formats(self) -> None:
        for variable in self.format_vars.values():
            variable.set(True)

    def _clear_formats(self) -> None:
        for variable in self.format_vars.values():
            variable.set(False)

    def _choose_input(self) -> None:
        path = filedialog.askopenfilename(
            title="选择图片、GIF 或视频",
            filetypes=[
                ("媒体文件", "*.png *.jpg *.jpeg *.gif *.webp *.bmp *.mp4 *.mov *.mkv *.avi *.wmv *.webm"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.input_var.set(path)
            self.output_var.set(str(Path(path).parent / "ASCII输出"))

    def _on_preset_changed(self, *_args: object) -> None:
        preset = PRESET_NAMES_BY_LABEL.get(self.preset_var.get(), "custom")
        if preset == "custom":
            return
        if preset == "restore":
            self._apply_render_settings(
                charset="restore",
                color=False,
                supersample=1,
                hierarchy=True,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "shader_mono":
            self._apply_render_settings(
                charset="shader",
                color=False,
                supersample=1,
                hierarchy=False,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "shader_color":
            self._apply_render_settings(
                charset="shader",
                color=True,
                color_grade="source",
                supersample=1,
                hierarchy=False,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "shader_color_hd":
            self.width_var.set(max(self.width_var.get(), 220))
            self.max_frames_var.set(min(self.max_frames_var.get(), 240))
            self._apply_render_settings(
                charset="shader",
                color=True,
                color_grade="source",
                supersample=2,
                hierarchy=False,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "adaptive_mono":
            self.width_var.set(max(self.width_var.get(), 180))
            self.aspect_var.set(round(adaptive_char_aspect(), 2))
            self._apply_render_settings(
                charset="shader",
                render_mode="adaptive",
                color=False,
                color_grade="source",
                supersample=2,
                hierarchy=True,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "adaptive_color":
            self.width_var.set(max(self.width_var.get(), 220))
            self.aspect_var.set(round(adaptive_char_aspect(), 2))
            self._apply_render_settings(
                charset="shader",
                render_mode="adaptive",
                color=True,
                color_grade="source",
                supersample=2,
                hierarchy=True,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "adaptive_vivid":
            self.width_var.set(max(self.width_var.get(), 220))
            self.aspect_var.set(round(adaptive_char_aspect(), 2))
            self._apply_render_settings(
                charset="shader",
                render_mode="adaptive",
                color=True,
                color_grade="vivid",
                supersample=2,
                hierarchy=True,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "braille_mono":
            self.width_var.set(max(self.width_var.get(), 160))
            self._apply_render_settings(
                charset="shader",
                render_mode="braille",
                color=False,
                color_grade="source",
                supersample=1,
                hierarchy=False,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "braille_color":
            self.width_var.set(max(self.width_var.get(), 160))
            self._apply_render_settings(
                charset="shader",
                render_mode="braille",
                color=True,
                color_grade="source",
                supersample=1,
                hierarchy=False,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "shader_warm":
            self._apply_render_settings(
                charset="shader",
                color=True,
                color_grade="warm",
                supersample=1,
                hierarchy=False,
                separation=False,
                detail=True,
                clean=True,
                edges=False,
            )
        elif preset == "soft":
            self._apply_render_settings(
                charset="soft",
                color=False,
                color_grade="source",
                supersample=1,
                hierarchy=True,
                separation=False,
                detail=False,
                clean=True,
                edges=False,
            )

    def _apply_render_settings(
        self,
        *,
        charset: str,
        color: bool,
        hierarchy: bool,
        separation: bool,
        detail: bool,
        clean: bool,
        edges: bool,
        render_mode: str = "ascii",
        color_grade: str = "source",
        supersample: int = 1,
    ) -> None:
        self.charset_var.set(CHARSET_LABELS[charset])
        self.render_mode_var.set(RENDER_MODE_LABELS[render_mode])
        self.color_var.set(color)
        self.color_grade = color_grade
        self.supersample = supersample
        self.hierarchy_var.set(hierarchy)
        self.separation_var.set(separation)
        self.detail_var.set(detail)
        self.clean_var.set(clean)
        self.edges_var.set(edges)

    def _choose_output(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_var.set(path)

    def _selected_formats(self) -> list[str]:
        return [name for name, variable in self.format_vars.items() if variable.get()]

    def _start_convert(self) -> None:
        if not self.input_var.get():
            messagebox.showerror("缺少输入文件", "请先选择一个图片、GIF 或视频文件。")
            return
        formats = self._selected_formats()
        if not formats:
            messagebox.showerror("缺少导出格式", "请至少选择一种导出格式。")
            return

        self.convert_button.configure(state=tk.DISABLED)
        self.status_var.set("正在转换...")
        self.preview.delete("1.0", tk.END)
        thread = threading.Thread(target=self._convert_worker, args=(formats,), daemon=True)
        thread.start()

    def _convert_worker(self, formats: list[str]) -> None:
        try:
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
            )
            ffmpeg = find_ffmpeg()
            chafa = find_chafa()
            animation = convert_file(self.input_var.get(), options, ffmpeg_path=ffmpeg)
            outputs = export_many(
                animation,
                self.output_var.get(),
                formats,
                color=use_color,
                ffmpeg_path=ffmpeg,
                chafa_path=chafa,
            )
            preview = "\n".join(animation.frames[0].lines)
            self.work_queue.put(("done", (animation, outputs, preview)))
        except (ConversionError, OSError, RuntimeError, ValueError) as exc:
            self.work_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            kind, payload = self.work_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_queue)
            return

        self.convert_button.configure(state=tk.NORMAL)
        if kind == "done":
            animation, outputs, preview = payload
            self.preview.insert("1.0", preview)
            self.status_var.set(f"完成：{len(animation.frames)} 帧，生成 {len(outputs)} 个文件")
            messagebox.showinfo("转换完成", "已生成：\n" + "\n".join(str(path) for path in outputs))
        else:
            self.status_var.set("转换失败")
            messagebox.showerror("转换失败", str(payload))
        self.after(100, self._poll_queue)


def main() -> None:
    app = GlyphMotionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
