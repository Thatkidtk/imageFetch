#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
import subprocess
import threading
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    import customtkinter as ctk
except Exception:  # pragma: no cover - fallback to legacy GUI
    ctk = None

from tkinter import messagebox  # used in fallback cases

from image_scraper import (
    crawl_site,
    collect_images_from_page,
    download_all,
    zip_output_folder,
)


def _open_path(p: Path):
    try:
        if platform.system() == "Windows":
            os.startfile(p)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.run(["open", str(p)], check=False)
        else:
            subprocess.run(["xdg-open", str(p)], check=False)
    except Exception:
        messagebox.showinfo("Open", str(p))


class ModernImageScraperGUI:
    def __init__(self):
        if ctk is None:
            raise RuntimeError("customtkinter is required for the modern GUI")

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("imageFetch")
        self.root.geometry("860x600")
        self.root.minsize(720, 520)

        # Data
        self.url_var = ctk.StringVar()
        self.out_dir_var = ctk.StringVar()
        self.crawl_var = ctk.BooleanVar(value=False)
        self.max_pages_var = ctk.StringVar(value="20")
        self.open_when_done_var = ctk.BooleanVar(value=False)

        self.total = 0
        self.completed = 0
        self.out_dir_path: Path | None = None
        self.zip_path: Path | None = None

        self._build_ui()
        self._load_prefs()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # Preferences
    def _config_dir(self) -> Path:
        if platform.system() == "Windows":
            base = Path(os.environ.get("APPDATA", Path.home()))
            return base / "imageFetch"
        else:
            return Path.home() / ".config" / "imageFetch"

    def _config_file(self) -> Path:
        return self._config_dir() / "config.json"

    def _load_prefs(self):
        try:
            cfg = self._config_file()
            if cfg.exists():
                data = json.load(open(cfg, "r", encoding="utf-8"))
                if isinstance(data, dict):
                    owd = data.get("open_when_done")
                    if isinstance(owd, bool):
                        self.open_when_done_var.set(owd)
                    last_out = data.get("last_out_dir")
                    if isinstance(last_out, str) and last_out:
                        self.out_dir_var.set(last_out)
                    theme = data.get("theme")
                    if theme in {"Light", "Dark", "System"}:
                        self.appearance_option.set(theme)
                        self._on_theme_change(theme)
                    color = data.get("color_theme")
                    if color in {"blue", "green", "dark-blue"}:
                        self.color_option.set(color)
                        ctk.set_default_color_theme(color)
        except Exception:
            pass

    def _save_prefs(self):
        try:
            cfg_dir = self._config_dir()
            cfg_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "open_when_done": bool(self.open_when_done_var.get()),
                "last_out_dir": self.out_dir_var.get().strip(),
                "theme": self.appearance_option.get(),
                "color_theme": self.color_option.get(),
            }
            json.dump(data, open(self._config_file(), "w", encoding="utf-8"), indent=2)
        except Exception:
            pass

    # UI
    def _build_ui(self):
        # Header bar
        top = ctk.CTkFrame(self.root)
        top.pack(fill="x", padx=16, pady=(16, 8))

        title = ctk.CTkLabel(top, text="imageFetch", font=ctk.CTkFont(size=22, weight="bold"))
        title.pack(side="left")
        subtitle = ctk.CTkLabel(top, text="Save images from any page or site", font=ctk.CTkFont(size=13))
        subtitle.pack(side="left", padx=(10, 0))

        # Theme controls
        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="right")
        self.appearance_option = ctk.CTkOptionMenu(right, values=["System", "Light", "Dark"], command=self._on_theme_change)
        self.appearance_option.set("System")
        self.appearance_option.pack(side="right", padx=(8, 0))
        self.color_option = ctk.CTkOptionMenu(right, values=["blue", "green", "dark-blue"], command=self._on_color_change)
        self.color_option.set("blue")
        self.color_option.pack(side="right")

        # Content
        body = ctk.CTkFrame(self.root)
        body.pack(fill="both", expand=True, padx=16, pady=8)

        grid = body
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_rowconfigure(7, weight=1)

        # URL
        ctk.CTkLabel(grid, text="URL").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self.url_entry = ctk.CTkEntry(grid, textvariable=self.url_var, placeholder_text="https://example.com")
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky="we", padx=8, pady=8)

        # Output folder
        ctk.CTkLabel(grid, text="Output Folder").grid(row=1, column=0, sticky="w", padx=8, pady=8)
        self.out_entry = ctk.CTkEntry(grid, textvariable=self.out_dir_var, placeholder_text="Auto-create folder")
        self.out_entry.grid(row=1, column=1, sticky="we", padx=8, pady=8)
        ctk.CTkButton(grid, text="Browse", command=self.choose_dir).grid(row=1, column=2, sticky="w", padx=8, pady=8)

        # Crawl options
        self.crawl_chk = ctk.CTkCheckBox(grid, text="Crawl same-site links", variable=self.crawl_var, command=self._toggle_crawl)
        self.crawl_chk.grid(row=2, column=0, sticky="w", padx=8, pady=8)
        ctk.CTkLabel(grid, text="Max pages").grid(row=2, column=1, sticky="e", padx=8, pady=8)
        self.max_pages_entry = ctk.CTkEntry(grid, textvariable=self.max_pages_var, width=90)
        self.max_pages_entry.grid(row=2, column=2, sticky="w", padx=8, pady=8)

        # Open when done
        self.open_when_chk = ctk.CTkCheckBox(grid, text="Open folder when done", variable=self.open_when_done_var, command=self._save_prefs)
        self.open_when_chk.grid(row=3, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 8))

        # Progress
        self.progress = ctk.CTkProgressBar(grid)
        self.progress.set(0)
        self.progress.grid(row=4, column=0, columnspan=3, sticky="we", padx=8, pady=(6, 2))
        self.progress_label = ctk.CTkLabel(grid, text="Idle")
        self.progress_label.grid(row=5, column=0, columnspan=3, sticky="w", padx=8)

        # Log
        ctk.CTkLabel(grid, text="Log").grid(row=6, column=0, sticky="w", padx=8, pady=(8, 0))
        self.log = ctk.CTkTextbox(grid, height=220)
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)

        # Buttons
        btns = ctk.CTkFrame(grid, fg_color="transparent")
        btns.grid(row=8, column=0, columnspan=3, sticky="e", padx=8, pady=(0, 8))
        self.start_btn = ctk.CTkButton(btns, text="Start", command=self.start)
        self.start_btn.grid(row=0, column=0, padx=6)
        self.open_folder_btn = ctk.CTkButton(btns, text="Open Folder", command=self.open_folder, state="disabled")
        self.open_folder_btn.grid(row=0, column=1, padx=6)
        self.open_zip_btn = ctk.CTkButton(btns, text="Open ZIP", command=self.open_zip, state="disabled")
        self.open_zip_btn.grid(row=0, column=2, padx=6)

        self._toggle_crawl()

    # UI helpers
    def _on_theme_change(self, value: str):
        v = value or "System"
        ctk.set_appearance_mode(v.lower())
        self._save_prefs()

    def _on_color_change(self, value: str):
        v = value or "blue"
        ctk.set_default_color_theme(v)
        self._save_prefs()

    def _toggle_crawl(self):
        state = "normal" if self.crawl_var.get() else "disabled"
        self.max_pages_entry.configure(state=state)

    def _ui(self, fn):
        self.root.after(0, fn)

    def log_line(self, msg: str):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def set_progress(self, total: int, completed: int):
        self.total = max(total, 1)
        self.completed = completed
        self.progress.set(min(1.0, completed / self.total))
        self.progress_label.configure(text=f"Downloading {completed}/{total} images...")

    # Actions
    def choose_dir(self):
        import tkinter.filedialog as fd
        d = fd.askdirectory()
        if d:
            self.out_dir_var.set(d)
            self._save_prefs()

    def start(self):
        url = (self.url_var.get() or "").strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL.")
            return
        if not urlparse(url).scheme:
            url = "https://" + url
            self.url_var.set(url)
        if not urlparse(url).netloc:
            messagebox.showerror("Error", "Invalid URL. Please include a valid domain.")
            return

        out_dir_str = (self.out_dir_var.get() or "").strip()
        if not out_dir_str:
            default_dir_name = f"images_{urlparse(url).netloc}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            out_dir_str = str(Path.cwd() / default_dir_name)
            self.out_dir_var.set(out_dir_str)

        # Disable controls
        self.start_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        self.open_zip_btn.configure(state="disabled")
        self.log.delete("1.0", "end")
        self.progress_label.configure(text="Starting...")
        self.progress.set(0)

        self.out_dir_path = Path(out_dir_str)
        self._save_prefs()

        threading.Thread(target=self._run_scrape, args=(url,), daemon=True).start()

    def _run_scrape(self, url: str):
        try:
            # Pages
            if self.crawl_var.get():
                self._ui(lambda: self.log_line(f"Crawling up to {self.max_pages_var.get()} pages..."))
                try:
                    max_pages = max(1, int(self.max_pages_var.get()))
                except Exception:
                    max_pages = 20
                pages = crawl_site(url, max_pages=max_pages)
            else:
                pages = [url]
            self._ui(lambda: self.log_line(f"Scanning {len(pages)} page(s) for images..."))

            # Collect images
            all_images = set()
            all_css = set()
            for p in pages:
                imgs, css = collect_images_from_page(p)
                all_images.update(imgs)
                all_css.update(css)
                self._ui(lambda p=p, i=len(imgs): self.log_line(f"Found {i} images on {p}"))

            data_images = {u for u in all_images if u.startswith("data:image/")}
            http_images = [u for u in all_images if not u.startswith("data:")]

            self._ui(lambda: self.log_line(f"Found {len(all_images)} images ({len(http_images)} downloadable, {len(data_images)} data URLs)."))

            # Download with progress
            def progress_cb(total, completed):
                self._ui(lambda: self.set_progress(total, completed))

            successes, failures = download_all(http_images, self.out_dir_path, progress_cb=progress_cb)

            manifest = {
                "source_pages": pages,
                "downloaded": [{"url": u, "path": p} for (u, p) in successes],
                "failed": failures,
                "data_urls": list(data_images)[:50],
                "css_files": list(all_css),
            }
            (self.out_dir_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            # Zip
            try:
                zip_path = zip_output_folder(self.out_dir_path)
                self.zip_path = zip_path
            except Exception as e:
                self._ui(lambda e=e: self.log_line(f"Failed to create ZIP: {e}"))
                zip_path = None

            self._ui(lambda: self.log_line(f"Downloaded {len(successes)} images; failed {len(failures)}."))
            if zip_path:
                self._ui(lambda: self.log_line(f"Created ZIP: {zip_path}"))
            self._ui(lambda: self.progress_label.configure(text="Done."))
            self._ui(lambda: self.start_btn.configure(state="normal"))
            self._ui(lambda: self.open_folder_btn.configure(state="normal"))
            self._ui(lambda: self.open_zip_btn.configure(state="normal"))

            # Auto-open
            if self.open_when_done_var.get() and self.out_dir_path and self.out_dir_path.exists():
                self._ui(lambda: _open_path(self.out_dir_path))
        except Exception as e:
            self._ui(lambda: self.start_btn.configure(state="normal"))
            self._ui(lambda: messagebox.showerror("Error", str(e)))

    def open_folder(self):
        if self.out_dir_path and self.out_dir_path.exists():
            _open_path(self.out_dir_path)

    def open_zip(self):
        if self.zip_path and self.zip_path.exists():
            _open_path(self.zip_path)

    def _on_close(self):
        self._save_prefs()
        self.root.destroy()


def run():
    if ctk is None:
        # Fallback to classic GUI if customtkinter not available
        try:
            from image_scraper_gui import run as classic_run
            classic_run()
            return
        except Exception as e:  # pragma: no cover
            print("customtkinter is required for modern GUI. Fallback failed:", e)
            return
    app = ModernImageScraperGUI()
    app.root.mainloop()

