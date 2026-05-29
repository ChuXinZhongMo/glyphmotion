"""Soft purple-and-white "anime" theme for the Tkinter GUI.

Tkinter/ttk has no native rounded corners or drop shadows, so we fake them
with PIL-generated 9-patch images used as ttk style elements (for both the
card panels and the buttons). If image theming is unavailable (e.g. headless
without Pillow's ImageTk), the look degrades gracefully to flat panels.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk


@dataclass(frozen=True)
class Theme:
    """Soft purple-and-white palette: lavender page, white rounded cards,
    gentle violet accents, cute rounded typography."""

    # Surfaces
    bg: str = "#f1ecfb"          # lavender page background
    panel: str = "#ffffff"       # white card interior
    panel_alt: str = "#ece5fb"   # button fill / hover row
    input_bg: str = "#ffffff"    # entry / spinbox / list field
    border: str = "#e3daf5"      # soft outlines
    grid: str = "#efeafb"        # subtle separators

    # Text
    fg: str = "#5d5573"          # primary text (muted plum)
    fg_dim: str = "#a99fc4"      # muted labels / units
    heading: str = "#7b5fd0"     # section titles (violet)

    # Accents
    accent: str = "#ab8eee"      # soft violet — primary
    accent_dim: str = "#8d6fe0"  # violet pressed
    accent2: str = "#f3a6cc"     # soft pink — secondary / failure
    warn: str = "#efa9d1"

    # Shadow (semi-transparent violet)
    shadow_rgba: tuple = (124, 95, 208, 70)

    # Preview "screen" — dark so the character-art colours (designed for the
    # near-black export background) stay visible.
    preview_bg: str = "#15111f"
    preview_fg: str = "#e9e3f6"

    mono_font: str = "Consolas"


THEME = Theme()

# Prefer a soft/rounded CJK-capable family for a "cute" feel.
_UI_FONT_PREFERENCES = ["幼圆", "YouYuan", "等线", "DengXian", "Microsoft YaHei UI", "Microsoft YaHei"]


def _resolve_ui_font(root: tk.Misc) -> str:
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        return "Microsoft YaHei UI"
    for name in _UI_FONT_PREFERENCES:
        if name in available:
            return name
    return "Microsoft YaHei UI"


def _keep(root: tk.Misc, image) -> None:
    """Keep a reference to a PhotoImage so it is not garbage-collected."""
    store = getattr(root, "_theme_images", None)
    if store is None:
        store = []
        root._theme_images = store  # type: ignore[attr-defined]
    store.append(image)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _install_rounded_elements(style: ttk.Style, root: tk.Misc, theme: Theme) -> bool:
    """Create image-based rounded elements for cards and buttons.

    Returns True on success, False if PIL/ImageTk is unavailable.
    """
    try:
        return _install_rounded_elements_impl(style, root, theme)
    except Exception:
        # Any imaging/Tcl failure falls back to flat panels.
        return False


def _install_rounded_elements_impl(style: ttk.Style, root: tk.Misc, theme: Theme) -> bool:
    from PIL import Image, ImageDraw, ImageFilter, ImageTk

    def card_image() -> tuple[object, int]:
        radius, margin = 18, 12
        size = 2 * (radius + margin) + 8
        base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (margin, margin + 2, size - margin, size - margin + 2),
            radius=radius,
            fill=theme.shadow_rgba,
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(margin / 2))
        base = Image.alpha_composite(base, shadow)
        ImageDraw.Draw(base).rounded_rectangle(
            (margin, margin, size - margin - 1, size - margin - 1),
            radius=radius,
            fill=(255, 255, 255, 255),
            outline=(*_hex_to_rgb(theme.border), 255),
            width=1,
        )
        photo = ImageTk.PhotoImage(base)
        _keep(root, photo)
        return photo, radius + margin

    def pill_image(fill: str, outline: str | None = None) -> tuple[object, int]:
        radius = 13
        size = 2 * radius + 10
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle(
            (1, 1, size - 2, size - 2),
            radius=radius,
            fill=(*_hex_to_rgb(fill), 255),
            outline=(*_hex_to_rgb(outline), 255) if outline else None,
            width=1 if outline else 0,
        )
        photo = ImageTk.PhotoImage(img)
        _keep(root, photo)
        return photo, radius

    # Card panel element
    card_photo, card_border = card_image()
    style.element_create("Card.bg", "image", card_photo, border=card_border, sticky="nsew")
    style.layout("Card.TFrame", [("Card.bg", {"sticky": "nsew"})])

    # Default (secondary) button — light lavender pill
    btn_normal, br = pill_image(theme.panel_alt, theme.border)
    btn_active, _ = pill_image("#ddccf8", theme.accent)
    btn_pressed, _ = pill_image("#cbb6f2", theme.accent)
    btn_disabled, _ = pill_image(theme.grid, theme.border)
    style.element_create(
        "Round.button",
        "image",
        btn_normal,
        ("pressed", btn_pressed),
        ("active", btn_active),
        ("disabled", btn_disabled),
        border=br,
        sticky="nsew",
        padding=(12, 6),
    )
    style.layout(
        "TButton",
        [("Round.button", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})],
    )

    # Primary button — violet pill
    pri_normal, pr = pill_image(theme.accent)
    pri_active, _ = pill_image(theme.accent_dim)
    pri_pressed, _ = pill_image("#7a5ed0")
    pri_disabled, _ = pill_image(theme.border)
    style.element_create(
        "RoundPrimary.button",
        "image",
        pri_normal,
        ("pressed", pri_pressed),
        ("active", pri_active),
        ("disabled", pri_disabled),
        border=pr,
        sticky="nsew",
        padding=(14, 9),
    )
    style.layout(
        "Primary.TButton",
        [("RoundPrimary.button", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})],
    )

    # Danger / cancel button — soft pink pill (shares the primary footprint so
    # it can swap in for the convert button while a conversion is running).
    dng_normal, dr = pill_image(theme.accent2)
    dng_active, _ = pill_image(theme.warn)
    dng_pressed, _ = pill_image("#e58bb8")
    dng_disabled, _ = pill_image(theme.border)
    style.element_create(
        "RoundDanger.button",
        "image",
        dng_normal,
        ("pressed", dng_pressed),
        ("active", dng_active),
        ("disabled", dng_disabled),
        border=dr,
        sticky="nsew",
        padding=(14, 9),
    )
    style.layout(
        "Danger.TButton",
        [("RoundDanger.button", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})],
    )
    return True


def apply_theme(root: tk.Misc, theme: Theme = THEME) -> Theme:
    """Apply the soft purple theme to ``root`` and return the palette."""
    root.configure(bg=theme.bg)
    ui = _resolve_ui_font(root)
    mono = theme.mono_font

    # Combobox dropdown is a classic tk Listbox; colour it via the option db.
    root.option_add("*TCombobox*Listbox.background", theme.input_bg)
    root.option_add("*TCombobox*Listbox.foreground", theme.fg)
    root.option_add("*TCombobox*Listbox.selectBackground", theme.accent)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.font", (ui, 10))

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    rounded = _install_rounded_elements(style, root, theme)

    # Page-level frames (lavender)
    style.configure("TFrame", background=theme.bg)
    style.configure("App.TFrame", background=theme.bg)
    style.configure("Header.TFrame", background=theme.bg)
    style.configure("TPanedwindow", background=theme.bg)
    style.configure("Sash", background=theme.border, sashthickness=8)

    # Card frames (white). When rounded elements failed, fall back to a flat
    # white panel with a soft border.
    if not rounded:
        style.configure(
            "Card.TFrame",
            background=theme.panel,
            bordercolor=theme.border,
            relief="solid",
            borderwidth=1,
        )
    style.configure("CardBody.TFrame", background=theme.panel)

    # Labels — default to white (they live inside cards).
    style.configure("TLabel", background=theme.panel, foreground=theme.fg, font=(ui, 10))
    style.configure("CardTitle.TLabel", background=theme.panel, foreground=theme.heading, font=(ui, 11, "bold"))
    # Flat section heading — same violet heading, but on the lavender page so
    # settings groups read as airy sections instead of boxed cards.
    style.configure("Section.TLabel", background=theme.bg, foreground=theme.heading, font=(ui, 11, "bold"))
    # Page labels sit on the lavender background.
    style.configure("Page.TLabel", background=theme.bg, foreground=theme.fg, font=(ui, 10))
    style.configure("Dim.TLabel", background=theme.bg, foreground=theme.fg_dim, font=(ui, 9))
    style.configure("Status.TLabel", background=theme.bg, foreground=theme.accent_dim, font=(ui, 10, "bold"))
    style.configure("Title.TLabel", background=theme.bg, foreground=theme.accent_dim, font=(ui, 17, "bold"))
    style.configure("Subtitle.TLabel", background=theme.bg, foreground=theme.fg_dim, font=(ui, 9))

    # Buttons
    style.configure(
        "TButton",
        background=theme.panel_alt,
        foreground=theme.fg,
        bordercolor=theme.border,
        focuscolor=theme.panel,
        relief="flat",
        padding=(12, 6),
        font=(ui, 9),
    )
    style.map(
        "TButton",
        background=[("active", "#ddccf8"), ("disabled", theme.grid)],
        foreground=[("active", theme.accent_dim), ("disabled", theme.fg_dim)],
    )
    style.configure(
        "Primary.TButton",
        background=theme.accent,
        foreground="#ffffff",
        bordercolor=theme.accent,
        relief="flat",
        padding=(14, 9),
        font=(ui, 11, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[("active", theme.accent_dim), ("disabled", theme.border)],
        foreground=[("disabled", "#ffffff")],
    )
    style.configure(
        "Danger.TButton",
        background=theme.accent2,
        foreground="#ffffff",
        bordercolor=theme.accent2,
        relief="flat",
        padding=(14, 9),
        font=(ui, 11, "bold"),
    )
    style.map(
        "Danger.TButton",
        background=[("active", theme.warn), ("disabled", theme.border)],
        foreground=[("disabled", "#ffffff")],
    )

    # Progress bar — violet fill on a soft trough.
    style.configure(
        "Glyph.Horizontal.TProgressbar",
        troughcolor=theme.grid,
        background=theme.accent,
        bordercolor=theme.border,
        lightcolor=theme.accent,
        darkcolor=theme.accent,
        thickness=10,
    )

    # Checkbuttons (inside white cards)
    style.configure("TCheckbutton", background=theme.panel, foreground=theme.fg, focuscolor=theme.panel, font=(ui, 10))
    style.map(
        "TCheckbutton",
        background=[("active", theme.panel)],
        foreground=[("active", theme.accent_dim)],
        indicatorcolor=[("selected", theme.accent), ("!selected", theme.input_bg)],
    )
    # Flat checkbuttons sit directly on the lavender page (no card behind them).
    style.configure("Flat.TCheckbutton", background=theme.bg, foreground=theme.fg, focuscolor=theme.bg, font=(ui, 10))
    style.map(
        "Flat.TCheckbutton",
        background=[("active", theme.bg)],
        foreground=[("active", theme.accent_dim)],
        indicatorcolor=[("selected", theme.accent), ("!selected", theme.input_bg)],
    )

    # Combobox
    style.configure(
        "TCombobox",
        fieldbackground=theme.input_bg,
        background=theme.panel_alt,
        foreground=theme.fg,
        arrowcolor=theme.accent_dim,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        selectbackground=theme.input_bg,
        selectforeground=theme.fg,
        padding=(7, 5),
        font=(ui, 10),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", theme.input_bg)],
        foreground=[("readonly", theme.fg)],
        arrowcolor=[("active", theme.accent)],
        bordercolor=[("focus", theme.accent), ("active", theme.accent)],
    )

    # Spinbox
    style.configure(
        "TSpinbox",
        fieldbackground=theme.input_bg,
        background=theme.panel_alt,
        foreground=theme.fg,
        arrowcolor=theme.accent_dim,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        insertcolor=theme.accent,
        padding=(5, 4),
        font=(mono, 10),
    )
    style.map("TSpinbox", bordercolor=[("focus", theme.accent)])

    # Entry
    style.configure(
        "TEntry",
        fieldbackground=theme.input_bg,
        foreground=theme.fg,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        insertcolor=theme.accent,
        padding=(7, 5),
        font=(mono, 10),
    )
    style.map("TEntry", bordercolor=[("focus", theme.accent)])

    # Notebook tabs
    style.configure("TNotebook", background=theme.bg, bordercolor=theme.bg, tabmargins=(2, 4, 2, 0))
    style.configure(
        "TNotebook.Tab",
        background=theme.grid,
        foreground=theme.fg_dim,
        bordercolor=theme.border,
        padding=(18, 8),
        font=(ui, 10, "bold"),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", theme.bg)],
        foreground=[("selected", theme.heading), ("active", theme.fg)],
        bordercolor=[("selected", theme.accent)],
    )

    # Scrollbars
    for orient in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            orient,
            troughcolor=theme.grid,
            background=theme.border,
            bordercolor=theme.bg,
            arrowcolor=theme.fg_dim,
        )
        style.map(orient, background=[("active", theme.accent)])

    return theme
