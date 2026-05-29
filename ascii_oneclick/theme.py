"""Dark "HUD / tech" theme for the Tkinter GUI.

Centralizes the colour palette and all ttk style configuration so the look can
be tuned in one place. Chinese text stays in a UI font for readability; a
monospace font is used for the title, preview and file list to give the
console / telemetry feel of the reference design.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk


@dataclass(frozen=True)
class Theme:
    """Soft purple-and-white "anime" palette: light lavender surfaces, gentle
    violet accents, rounded calm contrast."""

    # Surfaces
    bg: str = "#f5f2fc"          # soft lavender white (window / base)
    panel: str = "#ffffff"       # raised panels / buttons
    panel_alt: str = "#ece5fb"   # hover / selected row
    input_bg: str = "#ffffff"    # entry / spinbox / list field
    border: str = "#e0d6f3"      # thin soft outlines
    grid: str = "#efeafb"        # subtle separators

    # Text
    fg: str = "#5b5470"          # primary text (muted plum)
    fg_dim: str = "#a79ec2"      # muted labels / units
    heading: str = "#7b5fd0"     # section titles (violet)

    # Accents
    accent: str = "#a98eea"      # soft violet — primary
    accent_dim: str = "#8d6fe0"  # violet pressed
    accent2: str = "#f3a6cc"     # soft pink — secondary
    warn: str = "#efa9d1"        # pink — warnings / failure

    # Fonts
    ui_font: str = "Microsoft YaHei UI"
    mono_font: str = "Consolas"


THEME = Theme()


def apply_theme(root: tk.Misc, theme: Theme = THEME) -> Theme:
    """Apply the dark HUD theme to ``root`` and return the palette."""
    root.configure(bg=theme.bg)

    # Combobox dropdown is a classic tk Listbox; colour it via the option db.
    root.option_add("*TCombobox*Listbox.background", theme.input_bg)
    root.option_add("*TCombobox*Listbox.foreground", theme.fg)
    root.option_add("*TCombobox*Listbox.selectBackground", theme.accent)
    root.option_add("*TCombobox*Listbox.selectForeground", theme.bg)
    root.option_add("*TCombobox*Listbox.font", (theme.ui_font, 9))

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    ui = theme.ui_font
    mono = theme.mono_font

    # Frames / panes
    style.configure("TFrame", background=theme.bg)
    style.configure("App.TFrame", background=theme.bg)
    style.configure("Header.TFrame", background=theme.bg)
    style.configure("TPanedwindow", background=theme.bg)
    style.configure("Sash", background=theme.border, bordercolor=theme.border, sashthickness=6)

    # Labels
    style.configure("TLabel", background=theme.bg, foreground=theme.fg, font=(ui, 9))
    style.configure("Dim.TLabel", background=theme.bg, foreground=theme.fg_dim, font=(ui, 9))
    style.configure("Status.TLabel", background=theme.bg, foreground=theme.accent, font=(mono, 9))
    style.configure(
        "Title.TLabel", background=theme.bg, foreground=theme.accent, font=(mono, 16, "bold")
    )
    style.configure(
        "Subtitle.TLabel", background=theme.bg, foreground=theme.fg_dim, font=(mono, 9)
    )

    # Label frames (section cards)
    style.configure(
        "TLabelframe",
        background=theme.bg,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "TLabelframe.Label",
        background=theme.bg,
        foreground=theme.heading,
        font=(ui, 10, "bold"),
    )

    # Buttons
    style.configure(
        "TButton",
        background=theme.panel,
        foreground=theme.fg,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        focuscolor=theme.bg,
        relief="flat",
        padding=(10, 5),
        font=(ui, 9),
    )
    style.map(
        "TButton",
        background=[("active", theme.panel_alt), ("disabled", theme.bg)],
        foreground=[("active", theme.accent), ("disabled", theme.fg_dim)],
        bordercolor=[("active", theme.accent)],
    )

    style.configure(
        "Primary.TButton",
        background=theme.accent,
        foreground="#ffffff",
        bordercolor=theme.accent,
        lightcolor=theme.accent,
        darkcolor=theme.accent,
        relief="flat",
        padding=(12, 8),
        font=(ui, 10, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[("active", theme.accent_dim), ("disabled", theme.border)],
        foreground=[("disabled", theme.fg_dim)],
    )

    # Checkbuttons
    style.configure(
        "TCheckbutton",
        background=theme.bg,
        foreground=theme.fg,
        focuscolor=theme.bg,
        font=(ui, 9),
    )
    style.map(
        "TCheckbutton",
        background=[("active", theme.bg)],
        foreground=[("active", theme.accent)],
        indicatorcolor=[("selected", theme.accent), ("!selected", theme.input_bg)],
    )

    # Combobox
    style.configure(
        "TCombobox",
        fieldbackground=theme.input_bg,
        background=theme.panel,
        foreground=theme.fg,
        arrowcolor=theme.accent,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        selectbackground=theme.input_bg,
        selectforeground=theme.fg,
        padding=(6, 4),
        font=(ui, 9),
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
        background=theme.panel,
        foreground=theme.fg,
        arrowcolor=theme.accent,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        insertcolor=theme.accent,
        padding=(4, 3),
        font=(mono, 9),
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
        padding=(6, 4),
        font=(mono, 9),
    )
    style.map("TEntry", bordercolor=[("focus", theme.accent)])

    # Notebook tabs
    style.configure("TNotebook", background=theme.bg, bordercolor=theme.border, tabmargins=(2, 4, 2, 0))
    style.configure(
        "TNotebook.Tab",
        background=theme.grid,
        foreground=theme.fg_dim,
        bordercolor=theme.border,
        padding=(16, 7),
        font=(ui, 9, "bold"),
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
            troughcolor=theme.panel,
            background=theme.border,
            bordercolor=theme.bg,
            arrowcolor=theme.fg_dim,
        )
        style.map(orient, background=[("active", theme.accent_dim)])

    return theme
