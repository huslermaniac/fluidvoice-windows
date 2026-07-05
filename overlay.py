"""
overlay.py — FluidVoice Windows
Transparent floating transcription overlay window.
Equivalent of NotchOverlayManager.swift / BottomOverlayView.swift on macOS.

Shows a pill-shaped overlay at the bottom of the screen with:
  - Animated microphone indicator while recording
  - Live transcription text preview
  - Smooth fade-in / fade-out
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OVERLAY_HEIGHT = 56
OVERLAY_MIN_WIDTH = 260
OVERLAY_MAX_WIDTH = 700
PADDING_X = 24
PADDING_Y = 8
MARGIN_BOTTOM = 40

# Colors
BG_COLOR = "#1a1a1f"
BORDER_COLOR = "#3a3a4a"
TEXT_COLOR = "#f0f0f5"
DIM_TEXT_COLOR = "#888899"
ACCENT_COLOR = "#6c63ff"
RECORDING_COLOR = "#ff4d6d"
SUCCESS_COLOR = "#4ade80"

FONT_FAMILY = "Segoe UI"
FONT_SIZE = 14


# ---------------------------------------------------------------------------
# OverlayWindow
# ---------------------------------------------------------------------------

class OverlayWindow:
    """
    A frameless, always-on-top, click-through overlay window.
    Lives on the main thread via after() scheduling from other threads.
    """

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._win: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._visible = False
        self._fade_id: str | None = None
        self._current_alpha = 0.0
        self._target_alpha = 0.0
        self._dot_step = 0
        self._dot_anim_id: str | None = None

    # ------------------------------------------------------------------
    # Public API (thread-safe — delegates to main thread via after())
    # ------------------------------------------------------------------

    def show_recording(self) -> None:
        self._root.after(0, self._show_recording_impl)

    def show_transcribing(self) -> None:
        self._root.after(0, self._show_transcribing_impl)

    def show_text(self, text: str) -> None:
        self._root.after(0, lambda: self._show_text_impl(text))

    def hide(self) -> None:
        self._root.after(0, self._hide_impl)

    def update_text(self, text: str) -> None:
        self._root.after(0, lambda: self._update_text_impl(text))

    # ------------------------------------------------------------------
    # Implementation (must run on main thread)
    # ------------------------------------------------------------------

    def _ensure_window(self) -> None:
        if self._win is not None:
            return

        win = tk.Toplevel(self._root)
        win.overrideredirect(True)          # No title bar / borders
        win.attributes("-topmost", True)    # Always on top
        win.attributes("-alpha", 0.0)       # Start invisible
        win.attributes("-transparentcolor", "#000001")  # Click-through trick
        win.configure(bg="#000001")
        win.resizable(False, False)
        win.lift()

        # Position: bottom-center of primary monitor
        sw = win.winfo_screenwidth()
        x = (sw - OVERLAY_MIN_WIDTH) // 2
        y = win.winfo_screenheight() - OVERLAY_HEIGHT - MARGIN_BOTTOM
        win.geometry(f"{OVERLAY_MIN_WIDTH}x{OVERLAY_HEIGHT}+{x}+{y}")

        self._win = win
        self._rebuild_canvas(OVERLAY_MIN_WIDTH, OVERLAY_HEIGHT)

    def _rebuild_canvas(self, width: int, height: int) -> None:
        if self._canvas:
            self._canvas.destroy()

        canvas = tk.Canvas(
            self._win,
            width=width,
            height=height,
            bg="#000001",
            highlightthickness=0,
            bd=0,
        )
        canvas.pack(fill="both", expand=True)
        self._canvas = canvas

    def _update_overlay_layout(self, text: str, dot_color: str) -> None:
        self._ensure_window()
        
        # 1. Estimate layout
        max_text_width = OVERLAY_MAX_WIDTH - PADDING_X * 2 - 30
        
        # Measure text size
        try:
            f = tkfont.Font(family=FONT_FAMILY, size=FONT_SIZE)
            tw = f.measure(text)
        except Exception:
            tw = len(text) * 9

        # If it fits on one line:
        if tw <= max_text_width:
            width = max(OVERLAY_MIN_WIDTH, tw + PADDING_X * 2 + 30)
            height = OVERLAY_HEIGHT
            lines = 1
        else:
            # Multi-line: cap width at max
            width = OVERLAY_MAX_WIDTH
            # Estimate lines by character wrap count (approx 9px per char width)
            chars_per_line = max(20, max_text_width // 9)
            import textwrap
            wrapped_lines = textwrap.wrap(text, width=chars_per_line)
            lines = len(wrapped_lines)
            height = PADDING_Y * 2 + lines * 24 + 10 # dynamic height
            height = max(OVERLAY_HEIGHT, min(320, height))

        # 2. Resize and reposition the overlay window
        self._reposition(width, height)

        # 3. Draw layout on canvas
        c = self._canvas
        c.delete("all")

        # Corner radius
        r = 16 if lines > 1 else height // 2

        # Draw rounded rectangle background card
        self._draw_rounded_rect(c, 0, 0, width, height, r, fill=BG_COLOR, outline=BORDER_COLOR)

        # Draw dot indicator
        dot_x = PADDING_X
        dot_y = height // 2 if lines == 1 else PADDING_Y + 14
        c.create_oval(
            dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5,
            fill=dot_color, outline="", tags="dot"
        )

        # Draw wrapped text
        text_x = dot_x + 18
        if lines == 1:
            text_y = height // 2
            anchor = "w"
        else:
            text_y = PADDING_Y + 4
            anchor = "nw"

        c.create_text(
            text_x, text_y,
            text=text,
            fill=TEXT_COLOR,
            font=(FONT_FAMILY, FONT_SIZE),
            anchor=anchor,
            width=width - text_x - PADDING_X,
            justify="left",
            tags="label",
        )

    def _draw_rounded_rect(self, canvas: tk.Canvas, x0: int, y0: int, x1: int, y1: int, r: int, **kwargs) -> None:
        w = x1 - x0
        h = y1 - y0
        r = min(r, w // 2, h // 2)
        
        # 4 corner ovals
        canvas.create_oval(x0, y0, x0 + 2*r, y0 + 2*r, **kwargs)
        canvas.create_oval(x1 - 2*r, y0, x1, y0 + 2*r, **kwargs)
        canvas.create_oval(x0, y1 - 2*r, x0 + 2*r, y1, **kwargs)
        canvas.create_oval(x1 - 2*r, y1 - 2*r, x1, y1, **kwargs)
        
        # Intersecting fill rects
        inner_kwargs = dict(kwargs)
        inner_kwargs["outline"] = kwargs.get("fill")
        canvas.create_rectangle(x0 + r, y0, x1 - r, y1, **inner_kwargs)
        canvas.create_rectangle(x0, y0 + r, x1, y1 - r, **inner_kwargs)
        
        # Border outline lines
        outline_color = kwargs.get("outline")
        if outline_color:
            canvas.create_line(x0 + r, y0, x1 - r, y0, fill=outline_color)
            canvas.create_line(x0 + r, y1 - 1, x1 - r, y1 - 1, fill=outline_color)
            canvas.create_line(x0, y0 + r, x0, y1 - r, fill=outline_color)
            canvas.create_line(x1 - 1, y0 + r, x1 - 1, y1 - r, fill=outline_color)

    def _show_recording_impl(self) -> None:
        self._ensure_window()
        self._stop_dot_animation()
        self._update_overlay_layout("Listening…", RECORDING_COLOR)
        self._fade_to(0.92)
        # Pass current geometry width for dot anim
        width = self._win.winfo_width()
        self._start_dot_animation(RECORDING_COLOR, width)

    def _show_transcribing_impl(self) -> None:
        self._ensure_window()
        self._stop_dot_animation()
        self._update_overlay_layout("Transcribing…", ACCENT_COLOR)
        self._fade_to(0.92)

    def _show_text_impl(self, text: str) -> None:
        self._ensure_window()
        self._stop_dot_animation()
        # Allow up to 400 characters without truncating in final result
        display = (text[:395] + "…") if len(text) > 400 else text
        self._update_overlay_layout(display, SUCCESS_COLOR)
        self._fade_to(0.92)
        # Auto-hide after 2.5 s
        self._win.after(2500, self._hide_impl)

    def _update_text_impl(self, text: str) -> None:
        if not self._visible:
            return
        # Live updates: show full text progressively (will auto-wrap and auto-grow height)
        # Cap at 400 characters to prevent overflow off screen
        display = (text[:395] + "…") if len(text) > 400 else text
        self._update_overlay_layout(display, RECORDING_COLOR)

    def _hide_impl(self) -> None:
        self._stop_dot_animation()
        self._fade_to(0.0)

    def _reposition(self, width: int, height: int) -> None:
        if self._win is None:
            return
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        x = (sw - width) // 2
        y = sh - height - MARGIN_BOTTOM
        self._win.geometry(f"{width}x{height}+{x}+{y}")
        self._rebuild_canvas(width, height)

    # ------------------------------------------------------------------
    # Fade animation
    # ------------------------------------------------------------------

    def _fade_to(self, target: float) -> None:
        self._target_alpha = target
        if self._fade_id:
            self._win.after_cancel(self._fade_id)
            self._fade_id = None
        if target > 0:
            self._visible = True
            if self._win:
                self._win.deiconify()
                self._win.lift()
                self._win.attributes("-topmost", True)
        self._fade_step()

    def _fade_step(self) -> None:
        if self._win is None:
            return
        diff = self._target_alpha - self._current_alpha
        if abs(diff) < 0.02:
            self._current_alpha = self._target_alpha
            self._win.attributes("-alpha", self._current_alpha)
            if self._current_alpha == 0:
                self._visible = False
                self._win.withdraw()  # Hide completely from DWM
            return
        step = 0.06 if diff > 0 else -0.08
        self._current_alpha = max(0.0, min(1.0, self._current_alpha + step))
        self._win.attributes("-alpha", self._current_alpha)
        self._fade_id = self._win.after(16, self._fade_step)

    # ------------------------------------------------------------------
    # Dot pulse animation
    # ------------------------------------------------------------------

    def _start_dot_animation(self, color: str, width: int) -> None:
        self._dot_step = 0
        self._animate_dot(color, width)

    def _animate_dot(self, color: str, width: int) -> None:
        if self._canvas is None or not self._visible:
            return
        self._dot_step = (self._dot_step + 1) % 30
        scale = 1.0 + 0.3 * abs(self._dot_step - 15) / 15
        r = int(5 * scale)
        dot_x = PADDING_X
        dot_y = OVERLAY_HEIGHT // 2
        self._canvas.delete("dot")
        self._canvas.create_oval(
            dot_x - r, dot_y - r, dot_x + r, dot_y + r,
            fill=color, outline="", tags="dot"
        )
        self._dot_anim_id = self._win.after(50, lambda: self._animate_dot(color, width))

    def _stop_dot_animation(self) -> None:
        if self._dot_anim_id and self._win:
            try:
                self._win.after_cancel(self._dot_anim_id)
            except Exception:
                pass
            self._dot_anim_id = None
