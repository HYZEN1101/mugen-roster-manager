"""
launcher.py - MUGEN Smart Roster Manager
Full GUI application built with tkinter.

Requirements: Python 3.7+ (tkinter is included)
"""
import os
import sys
import json
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from os.path import join, exists, dirname, basename, abspath

# Make sure local modules are importable
sys.path.insert(0, dirname(abspath(__file__)))

from core.scanner import scan_characters, scan_stages, save_cache, load_cache
from core.roster import RosterManager, RosterProfile
from core.mugen_runner import MugenLauncher
from core.config_manager import load_config, save_config
from core.sff_reader import get_portrait, find_sff_path

# ─── Logging ────────────────────────────────────────────────────────────────
_log_fmt = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s')
_file_handler = logging.FileHandler("roster_manager.log", encoding='utf-8')
_file_handler.setFormatter(_log_fmt)
# On Windows, stdout may be cp1252 which can't encode Japanese/Chinese folder names
import io as _io
_stream_handler = logging.StreamHandler(
    _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stdout, 'buffer') else sys.stdout
)
_stream_handler.setFormatter(_log_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _stream_handler])
logger = logging.getLogger("launcher")

# PIL ImageTk for portrait rendering (optional — graceful fallback if missing)
try:
    from PIL import Image, ImageTk
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# ─── Color Theme ────────────────────────────────────────────────────────────
THEME = {
    'bg':           '#1a1a2e',
    'bg2':          '#16213e',
    'bg3':          '#0f3460',
    'accent':       '#e94560',
    'accent2':      '#533483',
    'fg':           '#eaeaea',
    'fg_dim':       '#8888aa',
    'selected_bg':  '#e94560',
    'selected_fg':  '#ffffff',
    'entry_bg':     '#0f3460',
    'entry_fg':     '#eaeaea',
    'btn_bg':       '#533483',
    'btn_fg':       '#ffffff',
    'btn_hover':    '#6a45a8',
    'green':        '#00e676',
    'red':          '#ff5252',
    'yellow':       '#ffeb3b',
    'border':       '#2a2a4a',
}

PROFILES_DIR = "profiles"
CACHE_FILE = "char_stage_cache.json"


# ─── Styled Widgets ──────────────────────────────────────────────────────────

class StyledButton(tk.Button):
    def __init__(self, parent, text, command=None, color=None, **kwargs):
        bg = color or THEME['btn_bg']
        super().__init__(
            parent, text=text, command=command,
            bg=bg, fg=THEME['btn_fg'],
            activebackground=THEME['btn_hover'],
            activeforeground=THEME['btn_fg'],
            relief='flat', bd=0, padx=12, pady=6,
            font=('Segoe UI', 9, 'bold'), cursor='hand2',
            **kwargs
        )
        self.default_bg = bg
        self.bind('<Enter>', lambda e: self.config(bg=THEME['btn_hover']))
        self.bind('<Leave>', lambda e: self.config(bg=self.default_bg))


class SearchEntry(tk.Entry):
    def __init__(self, parent, placeholder="Search...", **kwargs):
        super().__init__(
            parent,
            bg=THEME['entry_bg'], fg=THEME['fg_dim'],
            insertbackground=THEME['fg'],
            relief='flat', bd=0,
            font=('Segoe UI', 10),
            **kwargs
        )
        self.placeholder = placeholder
        self._has_focus = False
        self.insert(0, placeholder)
        self.bind('<FocusIn>', self._on_focus_in)
        self.bind('<FocusOut>', self._on_focus_out)

    def _on_focus_in(self, e):
        if not self._has_focus:
            self._has_focus = True
            if self.get() == self.placeholder:
                self.delete(0, tk.END)
                self.config(fg=THEME['fg'])

    def _on_focus_out(self, e):
        if not self.get():
            self._has_focus = False
            self.insert(0, self.placeholder)
            self.config(fg=THEME['fg_dim'])

    def get_value(self):
        val = self.get()
        return '' if val == self.placeholder else val


# ─── Settings Dialog ─────────────────────────────────────────────────────────

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.title("Settings — MUGEN Path Configuration")
        self.configure(bg=THEME['bg'])
        self.resizable(False, False)
        self.result = None
        self.cfg = dict(cfg)

        self._build(cfg)
        self.grab_set()
        self.wait_window(self)

    def _build(self, cfg):
        pad = {'padx': 16, 'pady': 6}

        tk.Label(self, text="⚙  Settings", bg=THEME['bg'], fg=THEME['accent'],
                 font=('Segoe UI', 13, 'bold')).pack(**pad, anchor='w')

        self._make_path_row("MUGEN Root Folder:", 'mugen_root', cfg, is_dir=True)
        self._make_path_row("mugen.exe name:", 'mugen_exe', cfg, is_dir=False, browse=False)
        self._make_path_row("Characters subfolder:", 'chars_subdir', cfg, is_dir=False, browse=False)
        self._make_path_row("Stages subfolder:", 'stages_subdir', cfg, is_dir=False, browse=False)

        # Auto-restore toggle
        self.restore_var = tk.BooleanVar(value=cfg.get('auto_restore_select_def', True))
        fr = tk.Frame(self, bg=THEME['bg'])
        fr.pack(fill='x', **pad)
        tk.Checkbutton(
            fr, text="Auto-restore original select.def after MUGEN exits",
            variable=self.restore_var,
            bg=THEME['bg'], fg=THEME['fg'],
            activebackground=THEME['bg'], activeforeground=THEME['fg'],
            selectcolor=THEME['bg3'],
            font=('Segoe UI', 9)
        ).pack(side='left')

        # Buttons
        btn_fr = tk.Frame(self, bg=THEME['bg'])
        btn_fr.pack(fill='x', padx=16, pady=12)
        StyledButton(btn_fr, "Save", command=self._save,
                     color=THEME['accent']).pack(side='right', padx=4)
        StyledButton(btn_fr, "Cancel", command=self.destroy).pack(side='right', padx=4)

    def _make_path_row(self, label, key, cfg, is_dir=True, browse=True):
        fr = tk.Frame(self, bg=THEME['bg'])
        fr.pack(fill='x', padx=16, pady=4)
        tk.Label(fr, text=label, bg=THEME['bg'], fg=THEME['fg_dim'],
                 font=('Segoe UI', 9), width=28, anchor='w').pack(side='left')
        var = tk.StringVar(value=cfg.get(key, ''))
        entry = tk.Entry(fr, textvariable=var, bg=THEME['entry_bg'],
                         fg=THEME['fg'], insertbackground=THEME['fg'],
                         relief='flat', font=('Segoe UI', 9), width=38)
        entry.pack(side='left', padx=(4, 4))
        setattr(self, f'_var_{key}', var)

        if browse:
            def _browse(v=var, d=is_dir):
                if d:
                    path = filedialog.askdirectory()
                else:
                    path = filedialog.askopenfilename()
                if path:
                    v.set(path)
            StyledButton(fr, "Browse", command=_browse).pack(side='left')

    def _save(self):
        keys = ['mugen_root', 'mugen_exe', 'chars_subdir', 'stages_subdir']
        for key in keys:
            var = getattr(self, f'_var_{key}', None)
            if var:
                self.cfg[key] = var.get().strip()
        self.cfg['auto_restore_select_def'] = self.restore_var.get()
        self.result = self.cfg
        self.destroy()


# ─── Main Application ─────────────────────────────────────────────────────────

class RosterManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MUGEN Smart Roster Manager")
        self.configure(bg=THEME['bg'])
        self.minsize(1100, 650)

        # State
        self.cfg = load_config()
        self.all_characters = []
        self.all_stages = []
        self.current_profile = None
        self.selected_chars = set()   # set of def_path strings
        self.selected_stages = set()
        self._mugen_running = False
        self._portrait_cache = {}       # def_path -> PhotoImage or 'NONE'
        self._portrait_load_thread = None
        self._current_hover_char = None

        self.roster_manager = RosterManager(PROFILES_DIR)
        self._build_launcher()

        self._build_ui()
        self._restore_geometry()

        # Auto-load cache or prompt setup
        self.after(100, self._startup)

    def _build_launcher(self):
        self.launcher = MugenLauncher(
            mugen_root=self.cfg.get('mugen_root', ''),
            mugen_exe=self.cfg.get('mugen_exe', 'mugen.exe'),
            auto_restore=self.cfg.get('auto_restore_select_def', True)
        )
        self.launcher.set_callbacks(
            on_launch=self._on_mugen_launch,
            on_exit=self._on_mugen_exit
        )

    # ──────────────────────────────────────────────────────────────────────────
    #  UI BUILD
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──
        topbar = tk.Frame(self, bg=THEME['bg3'], height=52)
        topbar.pack(fill='x', side='top')
        topbar.pack_propagate(False)

        tk.Label(topbar, text="⚡ MUGEN Smart Roster Manager",
                 bg=THEME['bg3'], fg=THEME['fg'],
                 font=('Segoe UI', 13, 'bold')).pack(side='left', padx=16)

        self._status_label = tk.Label(topbar, text="Not configured",
                                      bg=THEME['bg3'], fg=THEME['yellow'],
                                      font=('Segoe UI', 9))
        self._status_label.pack(side='left', padx=12)

        StyledButton(topbar, "⚙ Settings", command=self._open_settings,
                     color=THEME['bg2']).pack(side='right', padx=8, pady=10)
        StyledButton(topbar, "🔄 Rescan", command=self._rescan,
                     color=THEME['bg2']).pack(side='right', padx=4, pady=10)

        # ── Main content ──
        main = tk.Frame(self, bg=THEME['bg'])
        main.pack(fill='both', expand=True)

        # Left: profile panel
        self._build_profile_panel(main)

        # Center: character library
        self._build_char_panel(main)

        # Right: stage panel
        self._build_stage_panel(main)

        # ── Bottom bar ──
        self._build_bottom_bar()

    def _build_profile_panel(self, parent):
        """Portrait preview panel — shows 9000,1 sprite for highlighted character."""
        PORTRAIT_W = 120
        PORTRAIT_H = 140

        frame = tk.Frame(parent, bg=THEME['bg2'], width=220)
        frame.pack(side='left', fill='y', padx=0)
        frame.pack_propagate(False)

        tk.Label(frame, text="CHARACTER INFO", bg=THEME['bg2'], fg=THEME['accent'],
                 font=('Segoe UI', 10, 'bold')).pack(pady=(14, 8), padx=12, anchor='w')

        # ── Portrait box ──────────────────────────────────────────────────────
        portrait_outer = tk.Frame(frame, bg=THEME['bg2'])
        portrait_outer.pack(padx=12, pady=(0, 8), anchor='w')

        # The canvas is the portrait display — fixed size
        self._portrait_canvas = tk.Canvas(
            portrait_outer,
            width=PORTRAIT_W, height=PORTRAIT_H,
            bg=THEME['bg'], highlightthickness=1,
            highlightbackground=THEME['border']
        )
        self._portrait_canvas.pack()

        # Placeholder silhouette text shown when no portrait loaded
        self._portrait_canvas.create_text(
            PORTRAIT_W // 2, PORTRAIT_H // 2,
            text="?", fill=THEME['fg_dim'],
            font=('Segoe UI', 32), tags='placeholder'
        )
        self._portrait_photo = None  # keep reference to avoid GC
        self._portrait_canvas_W = PORTRAIT_W
        self._portrait_canvas_H = PORTRAIT_H

        # ── Name & Author labels ──────────────────────────────────────────────
        info_frame = tk.Frame(frame, bg=THEME['bg2'])
        info_frame.pack(fill='x', padx=12, pady=(0, 6))

        self._info_name = tk.Label(
            info_frame, text="",
            bg=THEME['bg2'], fg=THEME['fg'],
            font=('Segoe UI', 10, 'bold'),
            wraplength=196, justify='left', anchor='w'
        )
        self._info_name.pack(fill='x', pady=(0, 2))

        self._info_author = tk.Label(
            info_frame, text="",
            bg=THEME['bg2'], fg=THEME['fg_dim'],
            font=('Segoe UI', 8),
            wraplength=196, justify='left', anchor='w'
        )
        self._info_author.pack(fill='x')

        # ── Separator + profile section below ────────────────────────────────
        tk.Frame(frame, bg=THEME['border'], height=1).pack(fill='x', padx=12, pady=8)

        tk.Label(frame, text="PROFILES", bg=THEME['bg2'], fg=THEME['accent'],
                 font=('Segoe UI', 10, 'bold')).pack(pady=(0, 4), padx=12, anchor='w')

        lb_frame = tk.Frame(frame, bg=THEME['bg2'])
        lb_frame.pack(fill='both', expand=True, padx=8)

        self.profile_listbox = tk.Listbox(
            lb_frame,
            bg=THEME['bg'], fg=THEME['fg'],
            selectbackground=THEME['accent'],
            selectforeground=THEME['fg'],
            relief='flat', bd=0,
            font=('Segoe UI', 9),
            activestyle='none',
            highlightthickness=0
        )
        self.profile_listbox.pack(fill='both', expand=True)
        self.profile_listbox.bind('<<ListboxSelect>>', self._on_profile_select)

        btn_grid = tk.Frame(frame, bg=THEME['bg2'])
        btn_grid.pack(fill='x', padx=8, pady=6)
        StyledButton(btn_grid, "+ New", command=self._new_profile).grid(
            row=0, column=0, sticky='ew', padx=2, pady=2)
        StyledButton(btn_grid, "💾 Save", command=self._save_profile).grid(
            row=0, column=1, sticky='ew', padx=2, pady=2)
        StyledButton(btn_grid, "✏ Rename", command=self._rename_profile).grid(
            row=1, column=0, sticky='ew', padx=2, pady=2)
        StyledButton(btn_grid, "🗑 Delete", command=self._delete_profile,
                     color='#7a1a1a').grid(row=1, column=1, sticky='ew', padx=2, pady=2)
        btn_grid.columnconfigure(0, weight=1)
        btn_grid.columnconfigure(1, weight=1)

        self.profile_stats = tk.Label(
            frame, text="No profile loaded",
            bg=THEME['bg2'], fg=THEME['fg_dim'],
            font=('Segoe UI', 8), wraplength=190, justify='left'
        )
        self.profile_stats.pack(padx=12, pady=(0, 6), anchor='w')

        self._refresh_profile_list()

    # ── Portrait loading ──────────────────────────────────────────────────────

    def _on_char_hover(self, event=None):
        """Called on mouse motion over char_listbox — show portrait for item under cursor."""
        idx = self.char_listbox.nearest(event.y)
        if idx < 0 or idx >= len(self._displayed_chars):
            return
        char = self._displayed_chars[idx]
        if char.get('def_path') == self._current_hover_char:
            return  # same char, no update needed
        self._current_hover_char = char.get('def_path')
        self._show_char_info(char)

    def _on_char_leave(self, event=None):
        """Mouse left the listbox — clear portrait."""
        self._current_hover_char = None

    def _show_char_info(self, char):
        """Update the portrait canvas and name/author labels for a character."""
        # Update text immediately
        display = char.get('displayname') or char.get('name') or char.get('folder', '')
        author = char.get('author', '')
        self._info_name.config(text=display)
        self._info_author.config(text=f"by {author}" if author else "")

        def_path = char.get('def_path', '')
        abs_path = char.get('abs_path', '')

        # No PIL = no portrait support
        if not _PIL_AVAILABLE:
            return

        # Check cache
        cached = self._portrait_cache.get(def_path)
        if cached is not None:
            if cached == 'NONE':
                self._draw_no_portrait()
            else:
                self._draw_portrait(cached)
            return

        # Show loading state
        self._draw_loading()

        # Load in background thread
        def load_portrait():
            try:
                sff_path = find_sff_path(abs_path)
                if not sff_path:
                    self._portrait_cache[def_path] = 'NONE'
                    self.after(0, self._draw_no_portrait)
                    return
                pil_img = get_portrait(sff_path)
                if pil_img is None:
                    self._portrait_cache[def_path] = 'NONE'
                    self.after(0, self._draw_no_portrait)
                    return
                # Scale to fit 120x140, anchored bottom
                photo = self._scale_portrait(pil_img)
                self._portrait_cache[def_path] = photo
                # Only draw if still the same char
                if self._current_hover_char == def_path:
                    self.after(0, lambda p=photo: self._draw_portrait(p))
            except Exception as e:
                logger.debug(f"Portrait load error: {e}")
                self._portrait_cache[def_path] = 'NONE'
                self.after(0, self._draw_no_portrait)

        t = threading.Thread(target=load_portrait, daemon=True)
        t.start()

    def _scale_portrait(self, pil_img):
        """
        Scale PIL image to fit within 120x140, anchored to bottom.
        Returns a tk.PhotoImage.
        """
        from PIL import Image, ImageTk
        W, H = self._portrait_canvas_W, self._portrait_canvas_H
        iw, ih = pil_img.size
        if iw == 0 or ih == 0:
            return None

        # Scale to fit within box, preserving aspect ratio
        scale = min(W / iw, H / ih)
        new_w = max(1, int(iw * scale))
        new_h = max(1, int(ih * scale))
        resized = pil_img.resize((new_w, new_h), Image.LANCZOS)

        # Compose onto transparent canvas (WxH), bottom-aligned
        canvas_img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        paste_x = (W - new_w) // 2           # center horizontally
        paste_y = H - new_h                  # anchor to bottom
        canvas_img.paste(resized, (paste_x, paste_y), resized if resized.mode == 'RGBA' else None)

        return ImageTk.PhotoImage(canvas_img)

    def _draw_portrait(self, photo):
        """Render a portrait PhotoImage onto the canvas."""
        c = self._portrait_canvas
        c.delete('all')
        if photo is None:
            self._draw_no_portrait()
            return
        self._portrait_photo = photo  # keep GC reference
        W, H = self._portrait_canvas_W, self._portrait_canvas_H
        c.create_image(0, 0, image=photo, anchor='nw', tags='portrait')

    def _draw_no_portrait(self):
        """Show the 'no portrait' placeholder."""
        c = self._portrait_canvas
        c.delete('all')
        W, H = self._portrait_canvas_W, self._portrait_canvas_H
        c.create_text(W // 2, H // 2, text="no portrait",
                      fill=THEME['fg_dim'], font=('Segoe UI', 8),
                      tags='placeholder')

    def _draw_loading(self):
        """Show loading indicator."""
        c = self._portrait_canvas
        c.delete('all')
        W, H = self._portrait_canvas_W, self._portrait_canvas_H
        c.create_text(W // 2, H // 2, text="...",
                      fill=THEME['fg_dim'], font=('Segoe UI', 14),
                      tags='loading')

    def _build_char_panel(self, parent):
        frame = tk.Frame(parent, bg=THEME['bg'])
        frame.pack(side='left', fill='both', expand=True, padx=0)

        # Header
        hdr = tk.Frame(frame, bg=THEME['bg'])
        hdr.pack(fill='x', padx=12, pady=(10, 4))
        tk.Label(hdr, text="CHARACTER LIBRARY", bg=THEME['bg'], fg=THEME['accent'],
                 font=('Segoe UI', 10, 'bold')).pack(side='left')
        self._char_count_label = tk.Label(hdr, text="(0)", bg=THEME['bg'],
                                          fg=THEME['fg_dim'], font=('Segoe UI', 9))
        self._char_count_label.pack(side='left', padx=6)

        # Search + filter
        search_fr = tk.Frame(frame, bg=THEME['bg'])
        search_fr.pack(fill='x', padx=12, pady=(0, 6))
        self._char_search = SearchEntry(search_fr, placeholder="Search characters...", width=28)
        self._char_search.pack(side='left', ipady=6, padx=(0, 8))
        self._char_search.bind('<KeyRelease>', lambda e: self._filter_chars())

        # Group filter
        tk.Label(search_fr, text="Group:", bg=THEME['bg'], fg=THEME['fg_dim'],
                 font=('Segoe UI', 9)).pack(side='left')
        self._group_var = tk.StringVar(value='All')
        self._group_combo = ttk.Combobox(search_fr, textvariable=self._group_var,
                                         state='readonly', width=16,
                                         font=('Segoe UI', 9))
        self._group_combo.pack(side='left', padx=6)
        self._group_combo.bind('<<ComboboxSelected>>', lambda e: self._filter_chars())

        # Select all / none
        StyledButton(search_fr, "✓ All", command=self._select_all_filtered,
                     color=THEME['bg3']).pack(side='right', padx=2)
        StyledButton(search_fr, "✗ None", command=self._deselect_all_filtered,
                     color=THEME['bg3']).pack(side='right', padx=2)

        # Character list with scrollbar
        list_fr = tk.Frame(frame, bg=THEME['bg'])
        list_fr.pack(fill='both', expand=True, padx=12, pady=(0, 8))

        scroll = tk.Scrollbar(list_fr, bg=THEME['bg2'], troughcolor=THEME['bg2'],
                              relief='flat', bd=0)
        scroll.pack(side='right', fill='y')

        self.char_listbox = tk.Listbox(
            list_fr,
            bg=THEME['bg'], fg=THEME['fg'],
            selectbackground=THEME['accent'],
            selectforeground=THEME['fg'],
            relief='flat', bd=0,
            font=('Segoe UI', 9),
            activestyle='none',
            highlightthickness=0,
            selectmode=tk.EXTENDED,
            yscrollcommand=scroll.set
        )
        self.char_listbox.pack(side='left', fill='both', expand=True)
        scroll.config(command=self.char_listbox.yview)
        self.char_listbox.bind('<space>', self._toggle_char_selection)
        self.char_listbox.bind('<Double-Button-1>', self._toggle_char_selection)
        self.char_listbox.bind('<Motion>', self._on_char_hover)
        self.char_listbox.bind('<Leave>', self._on_char_leave)
        # Also show portrait on keyboard navigation
        self.char_listbox.bind('<<ListboxSelect>>', self._on_char_listbox_select)

        # Bottom: selected count
        self._char_sel_label = tk.Label(frame, text="0 characters selected",
                                        bg=THEME['bg'], fg=THEME['fg_dim'],
                                        font=('Segoe UI', 8))
        self._char_sel_label.pack(padx=12, anchor='w')

        # Internal list of currently displayed chars (filtered)
        self._displayed_chars = []

    def _build_stage_panel(self, parent):
        frame = tk.Frame(parent, bg=THEME['bg2'], width=260)
        frame.pack(side='right', fill='y', padx=0)
        frame.pack_propagate(False)

        tk.Label(frame, text="STAGES", bg=THEME['bg2'], fg=THEME['accent'],
                 font=('Segoe UI', 10, 'bold')).pack(pady=(14, 4), padx=12, anchor='w')

        # Search
        search_fr = tk.Frame(frame, bg=THEME['bg2'])
        search_fr.pack(fill='x', padx=8, pady=(0, 4))
        self._stage_search = SearchEntry(search_fr, placeholder="Search stages...", width=24)
        self._stage_search.pack(fill='x', ipady=5)
        self._stage_search.bind('<KeyRelease>', lambda e: self._filter_stages())

        # Stage listbox
        list_fr = tk.Frame(frame, bg=THEME['bg2'])
        list_fr.pack(fill='both', expand=True, padx=8)
        scroll = tk.Scrollbar(list_fr, bg=THEME['bg'], troughcolor=THEME['bg'],
                              relief='flat', bd=0)
        scroll.pack(side='right', fill='y')

        self.stage_listbox = tk.Listbox(
            list_fr,
            bg=THEME['bg'], fg=THEME['fg'],
            selectbackground=THEME['accent2'],
            selectforeground=THEME['fg'],
            relief='flat', bd=0,
            font=('Segoe UI', 9),
            activestyle='none',
            highlightthickness=0,
            selectmode=tk.EXTENDED,
            yscrollcommand=scroll.set
        )
        self.stage_listbox.pack(side='left', fill='both', expand=True)
        scroll.config(command=self.stage_listbox.yview)
        self.stage_listbox.bind('<space>', self._toggle_stage_selection)
        self.stage_listbox.bind('<Double-Button-1>', self._toggle_stage_selection)

        # Stage all/none
        btn_fr = tk.Frame(frame, bg=THEME['bg2'])
        btn_fr.pack(fill='x', padx=8, pady=4)
        StyledButton(btn_fr, "✓ All Stages",
                     command=lambda: self._select_all_stages(),
                     color=THEME['bg3']).pack(side='left', padx=2)
        StyledButton(btn_fr, "✗ None",
                     command=lambda: self._deselect_all_stages(),
                     color=THEME['bg3']).pack(side='left', padx=2)

        self._stage_sel_label = tk.Label(frame, text="0 stages selected",
                                         bg=THEME['bg2'], fg=THEME['fg_dim'],
                                         font=('Segoe UI', 8))
        self._stage_sel_label.pack(padx=12, pady=(0, 4), anchor='w')

        self._displayed_stages = []

    def _build_bottom_bar(self):
        bar = tk.Frame(self, bg=THEME['bg3'], height=58)
        bar.pack(fill='x', side='bottom')
        bar.pack_propagate(False)

        self._launch_btn = StyledButton(
            bar, "▶  LAUNCH MUGEN",
            command=self._launch_mugen,
            color=THEME['accent']
        )
        self._launch_btn.config(font=('Segoe UI', 11, 'bold'), padx=24, pady=10)
        self._launch_btn.pack(side='right', padx=16, pady=8)

        StyledButton(bar, "💾 Apply Only\n(no launch)",
                     command=self._apply_only,
                     color=THEME['accent2']).pack(side='right', padx=4, pady=8)

        self._launch_status = tk.Label(bar, text="",
                                       bg=THEME['bg3'], fg=THEME['green'],
                                       font=('Segoe UI', 9, 'bold'))
        self._launch_status.pack(side='left', padx=16)

    # ──────────────────────────────────────────────────────────────────────────
    #  STARTUP & SCAN
    # ──────────────────────────────────────────────────────────────────────────

    def _startup(self):
        if not self.cfg.get('mugen_root'):
            messagebox.showinfo(
                "Welcome!",
                "Welcome to MUGEN Smart Roster Manager!\n\n"
                "Please configure your MUGEN root folder first via ⚙ Settings."
            )
            self._open_settings()
            return

        # Try loading cache first
        chars, stages = load_cache(CACHE_FILE)
        if chars is not None:
            self.all_characters = chars
            self.all_stages = stages
            self._populate_chars()
            self._populate_stages()
            self._set_status(f"Loaded {len(chars)} chars, {len(stages)} stages from cache", THEME['green'])
        else:
            self._rescan()

        # Restore last profile
        last = self.cfg.get('last_profile', '')
        if last:
            self._load_profile_by_name(last)

    def _rescan(self):
        """Scan chars and stages directories."""
        root = self.cfg.get('mugen_root', '')
        if not root:
            messagebox.showerror("Error", "MUGEN root not set. Go to ⚙ Settings.")
            return

        chars_dir = join(root, self.cfg.get('chars_subdir', 'chars'))
        stages_dir = join(root, self.cfg.get('stages_subdir', 'stages'))

        self._set_status("Scanning characters and stages...", THEME['yellow'])
        self.update()

        def do_scan():
            chars = scan_characters(chars_dir)
            stages = scan_stages(stages_dir)
            save_cache(chars, stages, CACHE_FILE)
            self.all_characters = chars
            self.all_stages = stages
            self.after(0, self._on_scan_complete)

        threading.Thread(target=do_scan, daemon=True).start()

    def _on_scan_complete(self):
        self._populate_chars()
        self._populate_stages()
        n_c = len(self.all_characters)
        n_s = len(self.all_stages)
        self._set_status(f"Scanned: {n_c} characters, {n_s} stages", THEME['green'])

        # Re-apply current profile selection markers
        if self.current_profile:
            self._mark_selections()

    # ──────────────────────────────────────────────────────────────────────────
    #  CHARACTER LIST
    # ──────────────────────────────────────────────────────────────────────────

    def _populate_chars(self):
        # Build group list
        groups = sorted(set(c['group'] for c in self.all_characters))
        self._group_combo['values'] = ['All'] + groups
        if self._group_var.get() not in ['All'] + groups:
            self._group_var.set('All')

        self._filter_chars()
        self._char_count_label.config(text=f"({len(self.all_characters)} total)")

    def _filter_chars(self):
        query = self._char_search.get_value().lower()
        group_filter = self._group_var.get()

        self._displayed_chars = [
            c for c in self.all_characters
            if (not query or query in (c['name'] or '').lower() or
                query in (c.get('displayname') or '').lower() or
                query in c['folder'].lower())
            and (group_filter == 'All' or c['group'] == group_filter)
        ]

        self.char_listbox.delete(0, tk.END)
        for c in self._displayed_chars:
            marker = "✓ " if c['def_path'] in self.selected_chars else "  "
            display = c.get('displayname') or c['name'] or c['folder']
            self.char_listbox.insert(tk.END, f"{marker}{display}")
            # Color selected rows
            idx = self.char_listbox.size() - 1
            if c['def_path'] in self.selected_chars:
                self.char_listbox.itemconfig(idx, fg=THEME['green'])

        self._update_char_count()

    def _toggle_char_selection(self, event=None):
        indices = self.char_listbox.curselection()
        if not indices:
            return
        for i in indices:
            if i >= len(self._displayed_chars):
                continue
            char = self._displayed_chars[i]
            if char['def_path'] in self.selected_chars:
                self.selected_chars.discard(char['def_path'])
            else:
                self.selected_chars.add(char['def_path'])
        self._filter_chars()
        self._update_char_count()

    def _select_all_filtered(self):
        for c in self._displayed_chars:
            self.selected_chars.add(c['def_path'])
        self._filter_chars()

    def _deselect_all_filtered(self):
        for c in self._displayed_chars:
            self.selected_chars.discard(c['def_path'])
        self._filter_chars()

    def _on_char_listbox_select(self, event=None):
        """Keyboard navigation — show portrait for selected item."""
        sel = self.char_listbox.curselection()
        if not sel:
            return
        idx = sel[-1]
        if idx < len(self._displayed_chars):
            char = self._displayed_chars[idx]
            if char.get('def_path') != self._current_hover_char:
                self._current_hover_char = char.get('def_path')
                self._show_char_info(char)

    def _update_char_count(self):
        n = len(self.selected_chars)
        self._char_sel_label.config(text=f"{n} character{'s' if n != 1 else ''} selected")
        self._update_profile_stats()

    # ──────────────────────────────────────────────────────────────────────────
    #  STAGE LIST
    # ──────────────────────────────────────────────────────────────────────────

    def _populate_stages(self):
        self._filter_stages()

    def _filter_stages(self):
        query = self._stage_search.get_value().lower()
        self._displayed_stages = [
            s for s in self.all_stages
            if not query or query in s['name'].lower() or query in s['filename'].lower()
        ]

        self.stage_listbox.delete(0, tk.END)
        for s in self._displayed_stages:
            marker = "✓ " if s['def_path'] in self.selected_stages else "  "
            self.stage_listbox.insert(tk.END, f"{marker}{s['name']}")
            idx = self.stage_listbox.size() - 1
            if s['def_path'] in self.selected_stages:
                self.stage_listbox.itemconfig(idx, fg=THEME['accent2'])

        n = len(self.selected_stages)
        self._stage_sel_label.config(text=f"{n} stage{'s' if n != 1 else ''} selected")

    def _toggle_stage_selection(self, event=None):
        indices = self.stage_listbox.curselection()
        for i in indices:
            if i >= len(self._displayed_stages):
                continue
            stage = self._displayed_stages[i]
            if stage['def_path'] in self.selected_stages:
                self.selected_stages.discard(stage['def_path'])
            else:
                self.selected_stages.add(stage['def_path'])
        self._filter_stages()

    def _select_all_stages(self):
        for s in self._displayed_stages:
            self.selected_stages.add(s['def_path'])
        self._filter_stages()

    def _deselect_all_stages(self):
        for s in self._displayed_stages:
            self.selected_stages.discard(s['def_path'])
        self._filter_stages()

    # ──────────────────────────────────────────────────────────────────────────
    #  PROFILE MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────

    def _refresh_profile_list(self):
        self.profile_listbox.delete(0, tk.END)
        for name in self.roster_manager.list_profiles():
            self.profile_listbox.insert(tk.END, f" {name}")
        if self.current_profile:
            names = self.roster_manager.list_profiles()
            if self.current_profile.name in names:
                idx = names.index(self.current_profile.name)
                self.profile_listbox.selection_set(idx)

    def _on_profile_select(self, event=None):
        sel = self.profile_listbox.curselection()
        if not sel:
            return
        name = self.profile_listbox.get(sel[0]).strip()
        self._load_profile_by_name(name)

    def _load_profile_by_name(self, name):
        profile = self.roster_manager.load_profile(name)
        if not profile:
            return
        self.current_profile = profile
        self.selected_chars = set(profile.characters)
        self.selected_stages = set(profile.stages)
        self._mark_selections()
        self._update_char_count()
        self._set_status(f"Loaded profile: '{name}'", THEME['green'])
        self.cfg['last_profile'] = name
        save_config(self.cfg)

    def _mark_selections(self):
        """Refresh both lists to show selections from loaded profile."""
        self._filter_chars()
        self._filter_stages()

    def _new_profile(self):
        name = simpledialog.askstring("New Profile", "Enter profile name:",
                                      parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        profile = RosterProfile(name=name)
        self.roster_manager.save_profile(profile)
        self.current_profile = profile
        self.selected_chars = set()
        self.selected_stages = set()
        self._filter_chars()
        self._filter_stages()
        self._refresh_profile_list()
        self._set_status(f"Created profile: '{name}'", THEME['green'])

    def _save_profile(self):
        if not self.current_profile:
            messagebox.showwarning("No Profile", "Create or select a profile first.")
            return
        self.current_profile.characters = list(self.selected_chars)
        self.current_profile.stages = list(self.selected_stages)
        self.roster_manager.save_profile(self.current_profile)
        self._set_status(f"Saved profile: '{self.current_profile.name}' "
                         f"({len(self.selected_chars)} chars, "
                         f"{len(self.selected_stages)} stages)", THEME['green'])

    def _rename_profile(self):
        if not self.current_profile:
            return
        old = self.current_profile.name
        new = simpledialog.askstring("Rename Profile", "New name:",
                                     initialvalue=old, parent=self)
        if not new or new.strip() == old:
            return
        self.roster_manager.rename_profile(old, new.strip())
        self.current_profile.name = new.strip()
        self._refresh_profile_list()

    def _delete_profile(self):
        if not self.current_profile:
            return
        if not messagebox.askyesno("Delete Profile",
                                   f"Delete '{self.current_profile.name}'?"):
            return
        self.roster_manager.delete_profile(self.current_profile.name)
        self.current_profile = None
        self.selected_chars.clear()
        self.selected_stages.clear()
        self._filter_chars()
        self._filter_stages()
        self._refresh_profile_list()

    def _update_profile_stats(self):
        if self.current_profile:
            self.profile_stats.config(
                text=f"Profile: {self.current_profile.name}\n"
                     f"Characters: {len(self.selected_chars)}\n"
                     f"Stages: {len(self.selected_stages)}"
            )
        else:
            self.profile_stats.config(text="No profile loaded")

    # ──────────────────────────────────────────────────────────────────────────
    #  LAUNCH
    # ──────────────────────────────────────────────────────────────────────────

    def _get_current_profile_snapshot(self):
        """Build a RosterProfile from current selection state."""
        name = self.current_profile.name if self.current_profile else "Quick Launch"
        return RosterProfile(
            name=name,
            characters=list(self.selected_chars),
            stages=list(self.selected_stages)
        )

    def _launch_mugen(self):
        if self._mugen_running:
            messagebox.showinfo("MUGEN Running", "MUGEN is already running.")
            return

        if not self.selected_chars:
            if not messagebox.askyesno("No Characters",
                                       "No characters selected. Launch anyway?"):
                return

        ok, msg = self.launcher.validate()
        if not ok:
            messagebox.showerror("Configuration Error", msg)
            return

        profile = self._get_current_profile_snapshot()
        self._launch_btn.config(state='disabled')
        self._launch_status.config(text="⏳ Writing select.def and launching MUGEN...",
                                   fg=THEME['yellow'])
        self.launcher.launch(profile)

    def _apply_only(self):
        """Write select.def without launching MUGEN."""
        ok, msg = self.launcher.validate()
        if not ok:
            messagebox.showerror("Configuration Error", msg)
            return

        profile = self._get_current_profile_snapshot()

        # Need select.def path
        self.launcher.mugen_root = self.cfg.get('mugen_root', '')
        result = self.launcher.apply_only(profile)
        if result:
            self._set_status(
                f"select.def written: {len(self.selected_chars)} chars, "
                f"{len(self.selected_stages)} stages", THEME['green']
            )
        else:
            self._set_status("Failed to write select.def!", THEME['red'])

    def _on_mugen_launch(self, profile):
        self.after(0, lambda: self._launch_status.config(
            text=f"▶ MUGEN running — {len(profile.characters)} chars loaded",
            fg=THEME['green']
        ))
        self._mugen_running = True

    def _on_mugen_exit(self):
        self._mugen_running = False
        self.after(0, lambda: (
            self._launch_btn.config(state='normal'),
            self._launch_status.config(text="MUGEN exited. select.def restored.", fg=THEME['fg_dim'])
        ))

    # ──────────────────────────────────────────────────────────────────────────
    #  SETTINGS
    # ──────────────────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self, self.cfg)
        if dlg.result:
            self.cfg.update(dlg.result)
            save_config(self.cfg)
            # Rebuild launcher with new config
            self._build_launcher()
            self._rescan()

    # ──────────────────────────────────────────────────────────────────────────
    #  HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _set_status(self, text, color=None):
        self._status_label.config(text=text, fg=color or THEME['fg'])

    def _restore_geometry(self):
        geom = self.cfg.get('window_geometry', '')
        if geom:
            try:
                self.geometry(geom)
            except Exception:
                pass

    def on_close(self):
        self.cfg['window_geometry'] = self.geometry()
        save_config(self.cfg)
        self.destroy()


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = RosterManagerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
