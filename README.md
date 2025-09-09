# Image Scraper

Simple app (CLI + GUI) that asks for a URL, finds images on the page (and optionally on sameâ€‘site pages), saves them to a folder, and creates a ZIP archive for easy download.

## Setup

1. Ensure Python 3.10+ is installed.
2. (Optional) Create and activate a virtual environment.
3. Install dependencies:

```
pip install -r requirements.txt
```

## CLI Usage

Run the script and follow the prompts:

```
python image_scraper.py
```
python.exe -m pip install --upgrade pip

Prompts:
- Enter a URL (e.g., `https://example.com`).
- Choose an output folder (defaults to a timestamped folder like `images_example.com_YYYYMMDD_HHMMSS`).
- Choose whether to crawl same-site links and how many pages (default 20).

The app saves all downloadable images and writes a `manifest.json` in the output folder with details.

After downloads complete, the CLI also creates a ZIP archive next to the output folder.

## GUI Usage

Run the GUI and fill in the fields:

```
python image_scraper_gui.py
```

- URL: page to scrape.
- Output Folder: pick a folder (or leave blank to auto-create).
- Crawl same-site links: enable and set Max pages to traverse.
- Click Start to begin; a progress bar tracks downloads.
 - Option: "Open folder when done" will open the output folder automatically when the job completes (Windows/macOS/Linux).

When finished, the GUI enables buttons to open the output folder and the ZIP archive.

## Install From GitHub (Recommended)

Option A — pipx (isolated, recommended) (isolated, recommended)

```
pipx install "git+https://github.com/Thatkidtk/imageFetch.git"
```

Then run the app:

```
imageFetch
```

Install a specific version (tag):

```
pipx install "git+https://github.com/Thatkidtk/imageFetch.git@v0.1.0"
```

Option B — pip (user install) (user install)

```
python -m pip install --user "git+https://github.com/Thatkidtk/imageFetch.git"
```

If the `imageFetch` command isnâ€™t found after installation, add your Python Scripts folder to PATH. On Windows this is typically:

- `%USERPROFILE%\AppData\Roaming\Python\Python3XX\Scripts` (user installs)

On macOS/Linux (user installs), ensure `$HOME/.local/bin` is on PATH:

```
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

If `tkinter` is missing on Linux, install it via your package manager:

```
sudo apt-get install -y python3-tk   # Debian/Ubuntu
```

You can also run this helper from the repo to add it automatically:

```
powershell -ExecutionPolicy Bypass -File scripts/add_imagefetch_to_path.ps1
```

## Releases

- Download wheels or source archives from the Releases page:
  - https://github.com/Thatkidtk/imageFetch/releases
- Install a wheel directly (example):

```
python -m pip install --user \
  https://github.com/Thatkidtk/imageFetch/releases/download/v0.1.0/image_scraper_app-0.1.0-py3-none-any.whl
```

## Install as a Command

To run the GUI by typing `imageFetch` anywhere:

1. (Recommended) Create and activate a virtual environment.
2. From this project folder, install in editable mode:

```
pip install -e .
```

3. Now you can launch the GUI with:

```
imageFetch
```

If `imageFetch` is not found, ensure your Python Scripts directory is on PATH. On Windows, this is typically something like `%USERPROFILE%\AppData\Local\Programs\Python\Python311\Scripts` or your virtualenv's `Scripts` folder.

## Notes

- Finds images from `<img>`, `srcset`, `<source>`, OpenGraph/Twitter meta tags, inline styles, `<style>` blocks, and linked CSS files.
- Downloads images concurrently with basic de-duplication and file name safety.
- Data URLs are listed in the manifest but not saved as files.
- Crawling is limited to the same domain when enabled.
- After completion, a ZIP archive is created for the output folder (both CLI and GUI).

