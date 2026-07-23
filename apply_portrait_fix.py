"""
apply_portrait_fix.py
Run from inside mugen-roster-manager/:
  python apply_portrait_fix.py

Replaces portrait methods (lines 384-507) with the fixed version.
Fix: ImageTk.PhotoImage() was being created on a background thread
     which silently fails in tkinter. Now only PIL decoding runs in
     the thread; PhotoImage conversion happens on the main thread.
"""
import os, sys, ast

LAUNCHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'launcher.py')
if not os.path.exists(LAUNCHER):
    print(f"ERROR: launcher.py not found at {LAUNCHER}")
    sys.exit(1)

with open(LAUNCHER, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Loaded launcher.py — {len(lines)} lines")

# Find start: line with "# ── Portrait loading"
start_line = None
for i, line in enumerate(lines):
    if '# ── Portrait loading' in line:
        start_line = i
        break

# Find end: line with "def _build_char_panel"
end_line = None
for i, line in enumerate(lines):
    if 'def _build_char_panel' in line:
        end_line = i
        break

if start_line is None:
    print("ERROR: could not find '# ── Portrait loading' in launcher.py")
    sys.exit(1)
if end_line is None:
    print("ERROR: could not find 'def _build_char_panel' in launcher.py")
    sys.exit(1)

print(f"Portrait block: lines {start_line+1}–{end_line} → replacing with fixed version")

NEW_BLOCK = '''    # ── Portrait loading ──────────────────────────────────────────────────────

    def _on_char_hover(self, event=None):
        idx = self.char_listbox.nearest(event.y)
        if idx < 0 or idx >= len(self._displayed_chars):
            return
        char = self._displayed_chars[idx]
        if char.get('def_path') == self._current_hover_char:
            return
        self._current_hover_char = char.get('def_path')
        self._show_char_info(char)

    def _on_char_leave(self, event=None):
        self._current_hover_char = None

    def _on_char_listbox_select(self, event=None):
        sel = self.char_listbox.curselection()
        if not sel:
            return
        idx = sel[-1]
        if idx < len(self._displayed_chars):
            char = self._displayed_chars[idx]
            if char.get('def_path') != self._current_hover_char:
                self._current_hover_char = char.get('def_path')
                self._show_char_info(char)

    def _show_char_info(self, char):
        display = char.get('displayname') or char.get('name') or char.get('folder', '')
        author  = char.get('author', '')
        self._info_name.config(text=display)
        self._info_author.config(text=f"by {author}" if author else "")

        if not _PIL_AVAILABLE:
            print("[portrait] PIL not available — run: pip install pillow")
            return

        def_path = char.get('def_path', '')
        abs_path = char.get('abs_path', '')

        # Cache hit — PIL Image stored, not PhotoImage
        cached = self._portrait_cache.get(def_path)
        if cached is not None:
            if cached == 'NONE':
                self._draw_no_portrait()
            else:
                self._apply_portrait(cached, def_path)
            return

        self._draw_loading()

        def _load():
            """Background thread: file I/O + pixel decode only. Returns PIL Image."""
            try:
                print(f"[portrait] loading: {abs_path}")
                from core.sff_reader import find_sff_path, get_portrait
                sff = find_sff_path(abs_path)
                if not sff:
                    print(f"[portrait] SFF not found for: {abs_path}")
                    return None
                print(f"[portrait] SFF: {sff}")
                img = get_portrait(sff)
                if img is None:
                    print("[portrait] get_portrait() returned None")
                else:
                    print(f"[portrait] decoded: {img.size} {img.mode}")
                return img
            except Exception as e:
                import traceback
                print(f"[portrait] load error: {e}")
                traceback.print_exc()
                return None

        def _done(pil_img):
            """Main thread callback: cache result and draw."""
            if pil_img is None:
                self._portrait_cache[def_path] = 'NONE'
                if self._current_hover_char == def_path:
                    self._draw_no_portrait()
            else:
                # Store PIL Image (NOT PhotoImage — PhotoImage is not thread-safe)
                self._portrait_cache[def_path] = pil_img
                if self._current_hover_char == def_path:
                    self._apply_portrait(pil_img, def_path)

        import threading
        def _worker():
            pil_img = _load()
            self.after(0, lambda: _done(pil_img))   # post back to main thread
        threading.Thread(target=_worker, daemon=True).start()

    def _apply_portrait(self, pil_img, def_path):
        """
        Scale PIL Image, convert to PhotoImage, draw on canvas.
        MUST run on the main tkinter thread.
        """
        try:
            from PIL import Image, ImageTk
            W = self._portrait_canvas_W
            H = self._portrait_canvas_H
            iw, ih = pil_img.size
            if iw == 0 or ih == 0:
                self._draw_no_portrait()
                return

            # Scale to fit box, preserve aspect ratio
            scale   = min(W / iw, H / ih)
            new_w   = max(1, int(iw * scale))
            new_h   = max(1, int(ih * scale))
            resized = pil_img.resize((new_w, new_h), Image.LANCZOS)

            # Paste onto WxH canvas, bottom-anchored
            canvas_img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            paste_x = (W - new_w) // 2
            paste_y = H - new_h
            mask = resized if resized.mode == 'RGBA' else None
            canvas_img.paste(resized, (paste_x, paste_y), mask)

            # PhotoImage created HERE on main thread — this is the critical fix
            photo = ImageTk.PhotoImage(canvas_img)

            c = self._portrait_canvas
            c.delete('all')
            self._portrait_photo = photo   # must keep reference or GC kills it
            c.create_image(0, 0, image=photo, anchor='nw')
            print(f"[portrait] drawn OK")

        except Exception as e:
            import traceback
            print(f"[portrait] draw error: {e}")
            traceback.print_exc()
            self._draw_no_portrait()

    def _draw_portrait(self, photo):
        """Legacy stub — kept for compatibility."""
        c = self._portrait_canvas
        c.delete('all')
        if photo:
            self._portrait_photo = photo
            c.create_image(0, 0, image=photo, anchor='nw')
        else:
            self._draw_no_portrait()

    def _draw_no_portrait(self):
        c = self._portrait_canvas
        c.delete('all')
        W, H = self._portrait_canvas_W, self._portrait_canvas_H
        c.create_text(W // 2, H // 2, text="no portrait",
                      fill=THEME['fg_dim'], font=('Segoe UI', 8))

    def _draw_loading(self):
        c = self._portrait_canvas
        c.delete('all')
        W, H = self._portrait_canvas_W, self._portrait_canvas_H
        c.create_text(W // 2, H // 2, text="...",
                      fill=THEME['fg_dim'], font=('Segoe UI', 14))

'''

# Splice: keep everything before start_line, insert new block, keep from end_line onward
new_lines = lines[:start_line] + [NEW_BLOCK] + lines[end_line:]
new_src = ''.join(new_lines)

# Validate syntax before writing
try:
    ast.parse(new_src)
except SyntaxError as e:
    print(f"ERROR: patched file has syntax error: {e}")
    sys.exit(1)

# Backup original
backup = LAUNCHER.replace('.py', '_pre_portrait_fix.py')
with open(backup, 'w', encoding='utf-8') as f:
    f.write(''.join(lines))
print(f"Backed up original to: {backup}")

with open(LAUNCHER, 'w', encoding='utf-8') as f:
    f.write(new_src)

print(f"Patched successfully!")
print(f"launcher.py now has {len(new_src.splitlines())} lines")
print()
print("Now run launcher.py and hover over a character.")
print("Watch the terminal for [portrait] lines.")
