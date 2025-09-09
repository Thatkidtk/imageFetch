#!/usr/bin/env python3
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import platform
import os
import json

from image_scraper import (
    crawl_site,
    collect_images_from_page,
    download_all,
    zip_output_folder,
)
import json


class ImageScraperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Image Scraper")
        root.geometry("720x520")

        self.url_var = tk.StringVar()
        self.out_dir_var = tk.StringVar()
        self.crawl_var = tk.BooleanVar(value=False)
        self.max_pages_var = tk.StringVar(value="20")

        self.total = 0
        self.completed = 0
        self.out_dir_path: Path | None = None
        self.zip_path: Path | None = None
        # Default: off; can be overridden by saved prefs
        self.open_when_done_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._load_prefs()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root)
        frm.pack(fill=tk.BOTH, expand=True)

        # URL
        ttk.Label(frm, text="URL").grid(row=0, column=0, sticky="w", **pad)
        url_entry = ttk.Entry(frm, textvariable=self.url_var, width=72)
        url_entry.grid(row=0, column=1, columnspan=2, sticky="we", **pad)

        # Output directory
        ttk.Label(frm, text="Output Folder").grid(row=1, column=0, sticky="w", **pad)
        out_entry = ttk.Entry(frm, textvariable=self.out_dir_var, width=54)
        out_entry.grid(row=1, column=1, sticky="we", **pad)
        ttk.Button(frm, text="Browse", command=self.choose_dir).grid(row=1, column=2, sticky="w", **pad)

        # Crawl options
        crawl_chk = ttk.Checkbutton(frm, text="Crawl same-site links", variable=self.crawl_var, command=self._toggle_crawl)
        crawl_chk.grid(row=2, column=0, sticky="w", **pad)
        ttk.Label(frm, text="Max pages").grid(row=2, column=1, sticky="e", **pad)
        self.max_pages_entry = ttk.Entry(frm, textvariable=self.max_pages_var, width=8)
        self.max_pages_entry.grid(row=2, column=2, sticky="w", **pad)

        # Open when done
        ttk.Checkbutton(
            frm,
            text="Open folder when done",
            variable=self.open_when_done_var,
            command=self._on_open_when_done_toggle,
        ).grid(row=3, column=0, columnspan=3, sticky="w", **pad)

        # Progress
        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=3, sticky="we", **pad)
        self.progress_label = ttk.Label(frm, text="Idle")
        self.progress_label.grid(row=5, column=0, columnspan=3, sticky="w", **pad)

        # Log
        ttk.Label(frm, text="Log").grid(row=6, column=0, sticky="w", **pad)
        self.log = tk.Text(frm, height=12, wrap="word")
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(7, weight=1)
        frm.columnconfigure(1, weight=1)

        # Buttons
        btns = ttk.Frame(frm)
        btns.grid(row=8, column=0, columnspan=3, sticky="e", **pad)
        self.start_btn = ttk.Button(btns, text="Start", command=self.start)
        self.start_btn.grid(row=0, column=0, padx=6)
        self.open_folder_btn = ttk.Button(btns, text="Open Folder", command=self.open_folder, state=tk.DISABLED)
        self.open_folder_btn.grid(row=0, column=1, padx=6)
        self.open_zip_btn = ttk.Button(btns, text="Open ZIP", command=self.open_zip, state=tk.DISABLED)
        self.open_zip_btn.grid(row=0, column=2, padx=6)

        self._toggle_crawl()

    def _open_path(self, p: Path):
        try:
            if platform.system() == "Windows":
                os.startfile(p)  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(p)], check=False)
            else:
                subprocess.run(["xdg-open", str(p)], check=False)
        except Exception:
            messagebox.showinfo("Open", str(p))

    def choose_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.out_dir_var.set(d)
            self._save_prefs()

    def _toggle_crawl(self):
        state = tk.NORMAL if self.crawl_var.get() else tk.DISABLED
        self.max_pages_entry.configure(state=state)

    def log_line(self, msg: str):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def set_progress(self, total: int, completed: int):
        self.total = total
        self.completed = completed
        self.progress.configure(maximum=max(total, 1))
        self.progress['value'] = completed
        self.progress_label.configure(text=f"Downloading {completed}/{total} images...")

    def start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL.")
            return
        if not urlparse(url).scheme:
            url = "https://" + url
            self.url_var.set(url)
        # Validate domain
        if not urlparse(url).netloc:
            messagebox.showerror("Error", "Invalid URL. Please include a valid domain.")
            return

        out_dir_str = self.out_dir_var.get().strip()
        if not out_dir_str:
            default_dir_name = f"images_{urlparse(url).netloc}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            out_dir_str = str(Path.cwd() / default_dir_name)
            self.out_dir_var.set(out_dir_str)

        try:
            max_pages = int(self.max_pages_var.get()) if self.crawl_var.get() else 1
        except ValueError:
            messagebox.showwarning("Warning", "Max pages must be a number; defaulting to 20.")
            max_pages = 20

        self.start_btn.configure(state=tk.DISABLED)
        self.open_folder_btn.configure(state=tk.DISABLED)
        self.open_zip_btn.configure(state=tk.DISABLED)
        self.log.delete("1.0", tk.END)
        self.progress_label.configure(text="Starting...")
        self.progress['value'] = 0

        self.out_dir_path = Path(out_dir_str)
        # Persist chosen folder and preference before starting
        self._save_prefs()

        threading.Thread(target=self._run_scrape, args=(url, max_pages), daemon=True).start()

    def _run_scrape(self, url: str, max_pages: int):
        try:
            # Pages
            if self.crawl_var.get():
                self._ui(lambda: self.log_line(f"Crawling up to {max_pages} pages..."))
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
            try:
                (self.out_dir_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            except Exception as e:
                self._ui(lambda e=e: self.log_line(f"Failed to write manifest.json: {e}"))

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
            self._ui(lambda: self.start_btn.configure(state=tk.NORMAL))
            self._ui(lambda: self.open_folder_btn.configure(state=tk.NORMAL))
            self._ui(lambda: self.open_zip_btn.configure(state=tk.NORMAL))
            self._ui(lambda: messagebox.showinfo("Completed", f"Saved to:\n{self.out_dir_path}\n\nZIP:\n{zip_path}"))

            # Auto-open output folder if requested
            if self.open_when_done_var.get() and self.out_dir_path and self.out_dir_path.exists():
                self._ui(lambda: self._open_path(self.out_dir_path))
        except Exception as e:
            self._ui(lambda: self.start_btn.configure(state=tk.NORMAL))
            self._ui(lambda: messagebox.showerror("Error", str(e)))

    def _ui(self, fn):
        self.root.after(0, fn)

    def open_folder(self):
        if self.out_dir_path and self.out_dir_path.exists():
            self._open_path(self.out_dir_path)

    def open_zip(self):
        if self.zip_path and self.zip_path.exists():
            self._open_path(self.zip_path)

    # Preferences persistence
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
            cfg_path = self._config_file()
            if cfg_path.exists():
                data = json.load(open(cfg_path, "r", encoding="utf-8"))
                if isinstance(data, dict):
                    open_pref = data.get("open_when_done")
                    if isinstance(open_pref, bool):
                        self.open_when_done_var.set(open_pref)
                    out_dir_pref = data.get("last_out_dir")
                    if isinstance(out_dir_pref, str) and out_dir_pref:
                        self.out_dir_var.set(out_dir_pref)
        except Exception:
            pass

    def _save_prefs(self):
        try:
            cfg_dir = self._config_dir()
            cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg_path = self._config_file()
            data = {
                "open_when_done": bool(self.open_when_done_var.get()),
                "last_out_dir": self.out_dir_var.get().strip(),
            }
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _on_open_when_done_toggle(self):
        self._save_prefs()

    def _on_close(self):
        self._save_prefs()
        self.root.destroy()


def run():
    root = tk.Tk()
    app = ImageScraperGUI(root)
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    root.mainloop()


if __name__ == "__main__":
    run()
