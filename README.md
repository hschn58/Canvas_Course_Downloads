# Canvas Course Downloads

Download all accessible files from your Canvas LMS courses. Opens a real browser window for SSO/2FA authentication, then systematically downloads every file it can find. No API key or token required — it reuses your browser session.

## How It Works

The scraper uses a two-pass approach for each course:

1. **Authenticated API pass** — After you log in through the browser, the scraper queries Canvas REST endpoints (`/api/v1/...`) using your existing session cookies. No separate API key or token setup is needed.

2. **Page-scraping pass** — Navigates to each course section in the browser and scans for download links, catching anything the first pass missed.

Files are deduplicated by URL across both passes.

## What Gets Downloaded

- **Files** — Everything in the course's Files section, preserving folder structure
- **Modules** — Attachments from module items, including files referenced in pages and assignments
- **Assignments** — Files linked in assignment descriptions, plus your own submissions
- **Pages** — Files embedded in or linked from wiki pages

## Output Structure

```
downloads/
  Course_Name/
    files/
    modules/
      Module_Name/
    assignments/
      my_submissions/
    pages/
```

## Installation

Clone the repo and install locally (not published to PyPI):

```bash
git clone https://github.com/hschn58/Canvas_Course_Downloads.git
cd Canvas_Course_Downloads
pip install .
playwright install chromium
```

## Usage

```bash
canvas-download --url https://canvas.yourinstitution.edu
```

Or equivalently, from the source directory:

```bash
cd Canvas_Course_Downloads/src
python3 -m canvas_course_downloads --url https://canvas.yourinstitution.edu
```

You can also set the URL as an environment variable to avoid passing it every time:

```bash
export CANVAS_URL=https://canvas.yourinstitution.edu
canvas-download
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--url` | Canvas instance URL | `$CANVAS_URL` |
| `-o`, `--output` | Download directory | `./downloads` |

A Chromium window will open. **Log in manually** — complete SSO and any 2FA prompts. The script waits up to 5 minutes for login.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT
