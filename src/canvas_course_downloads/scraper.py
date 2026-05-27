import re
import urllib.parse
from pathlib import Path

from playwright.sync_api import TimeoutError as PwTimeout

from .models import Course


def sanitize(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def unique_path(dest_dir: Path, filename: str) -> Path:
    path = dest_dir / filename
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    i = 2
    while True:
        path = dest_dir / f"{stem}_{i}{suffix}"
        if not path.exists():
            return path
        i += 1


def login(page, base_url: str) -> None:
    page.goto(f"{base_url}/login")
    print("Please log in through the browser (SSO + Duo)...")
    page.wait_for_function(
        """(baseUrl) => {
            const url = window.location.href;
            return url.startsWith(baseUrl) && !url.includes('/login');
        }""",
        base_url,
        timeout=300_000,
        polling=1000,
    )
    print("Logged in!")


def get_courses(api, base_url: str) -> list[Course]:
    courses_data = api_get_json(api, f"{base_url}/api/v1/courses?per_page=100")
    courses = []
    for c in courses_data:
        course_id = str(c.get("id", ""))
        name = c.get("name", "")
        if not course_id or not name:
            continue
        courses.append(
            Course(id=course_id, name=sanitize(name), url=f"{base_url}/courses/{course_id}")
        )

    print(f"Found {len(courses)} courses")
    for c in courses:
        print(f"  - {c.name}")
    return courses


def download_file(api, url: str, dest_dir: Path, downloaded_urls: set[str]) -> None:
    if url in downloaded_urls:
        return
    downloaded_urls.add(url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        resp = api.get(url, max_redirects=10, timeout=60_000)
        if resp.status != 200:
            print(f"    [fail] HTTP {resp.status} for {url[-50:]}")
            return

        cd = resp.headers.get("content-disposition", "")
        fname = None
        if "filename" in cd:
            match = re.search(r"filename\*?=['\"]?(?:UTF-8'')?([^'\";]+)", cd)
            if match:
                fname = urllib.parse.unquote(match.group(1).strip("'\""))
        if not fname:
            path = urllib.parse.urlparse(resp.url).path
            fname = urllib.parse.unquote(path.split("/")[-1])
        if not fname or fname == "download":
            path = urllib.parse.urlparse(url).path
            parts = [p for p in path.split("/") if p and p != "download"]
            fname = parts[-1] if parts else "unknown"

        fname = sanitize(fname)
        dest_path = unique_path(dest_dir, fname)
        body = resp.body()
        dest_path.write_bytes(body)
        print(f"    [ok] {fname} ({len(body) // 1024}KB)")
    except Exception as e:
        print(f"    [fail] {url[-50:]} ({e})")


def collect_file_urls_from_page(page, base_url: str) -> set[str]:
    urls = set()
    for a in page.query_selector_all("a[href]"):
        href = a.get_attribute("href") or ""
        full = href if href.startswith("http") else base_url + href

        if "/files/" in href and not href.endswith("/files") and not href.endswith("/files/"):
            parsed = urllib.parse.urlparse(full)
            path = parsed.path
            if not path.endswith("/download"):
                path = path.rstrip("/") + "/download"
            urls.add(urllib.parse.urlunparse(parsed._replace(path=path)))

        elif "/attachments/" in href and "download" in href:
            urls.add(full)

        elif "/submissions/" in href and "download" in href:
            urls.add(full)

        elif "download" in href and ("canvas" in href or base_url in full):
            text = (a.inner_text() or "").strip()
            if text.lower().startswith("download") or re.search(r"\.\w{2,4}$", text):
                urls.add(full)

    return urls


def api_get_json(api, url: str) -> list[dict]:
    results = []
    while url:
        resp = api.get(url, timeout=30_000)
        if resp.status != 200:
            break
        data = resp.json()
        if not isinstance(data, list):
            break
        results.extend(data)
        link_header = resp.headers.get("link", "")
        url = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split("<")[1].split(">")[0]
    return results


# --------------- API-based scrapers ---------------


def scrape_files_api(api, course: Course, course_dir: Path, downloaded_urls: set[str]) -> None:
    print("  [files - api]")
    dest_dir = course_dir / "files"
    base_url = course.url.rsplit("/courses/", 1)[0]

    folders = api_get_json(api, f"{base_url}/api/v1/courses/{course.id}/folders?per_page=100")
    if not folders:
        print("    [skip] No folders or no access")
        return

    for folder in folders:
        folder_name = folder.get("full_name", "").replace("course files", "").strip("/") or "root"
        folder_id = folder.get("id")
        files = api_get_json(api, f"{base_url}/api/v1/folders/{folder_id}/files?per_page=100")
        folder_dest = dest_dir / sanitize(folder_name) if folder_name != "root" else dest_dir
        for f in files:
            file_url = f.get("url")
            if file_url:
                download_file(api, file_url, folder_dest, downloaded_urls)


def scrape_modules_api(api, course: Course, course_dir: Path, downloaded_urls: set[str]) -> None:
    print("  [modules - api]")
    dest_dir = course_dir / "modules"
    base_url = course.url.rsplit("/courses/", 1)[0]

    modules = api_get_json(api, f"{base_url}/api/v1/courses/{course.id}/modules?per_page=100")
    if not modules:
        print("    [skip] No modules or no access")
        return

    for mod in modules:
        mod_name = sanitize(mod.get("name", "unnamed"))
        items = api_get_json(
            api, f"{base_url}/api/v1/courses/{course.id}/modules/{mod['id']}/items?per_page=100"
        )
        mod_dest = dest_dir / mod_name

        for item in items:
            item_type = item.get("type", "")

            if item_type == "File":
                content_id = item.get("content_id")
                if not content_id:
                    continue
                try:
                    resp = api.get(
                        f"{base_url}/api/v1/courses/{course.id}/files/{content_id}",
                        timeout=30_000,
                    )
                    if resp.status != 200:
                        continue
                    file_url = resp.json().get("url")
                    if file_url:
                        download_file(api, file_url, mod_dest, downloaded_urls)
                except Exception:
                    continue

            elif item_type in ("Page", "Assignment"):
                url = item.get("url")
                if not url:
                    continue
                try:
                    resp = api.get(url, timeout=30_000)
                    if resp.status != 200:
                        continue
                    body = resp.json().get("body") or resp.json().get("description") or ""
                    for match in re.finditer(r"/files/(\d+)", body):
                        file_id = match.group(1)
                        file_resp = api.get(
                            f"{base_url}/api/v1/courses/{course.id}/files/{file_id}",
                            timeout=30_000,
                        )
                        if file_resp.status == 200:
                            file_url = file_resp.json().get("url")
                            if file_url:
                                download_file(api, file_url, mod_dest, downloaded_urls)
                except Exception:
                    continue


def scrape_assignments_api(
    api, course: Course, course_dir: Path, downloaded_urls: set[str]
) -> None:
    print("  [assignments - api]")
    dest_dir = course_dir / "assignments"
    base_url = course.url.rsplit("/courses/", 1)[0]

    assignments = api_get_json(
        api, f"{base_url}/api/v1/courses/{course.id}/assignments?per_page=100"
    )
    if not assignments:
        print("    [skip] No assignments or no access")
        return

    for a in assignments:
        desc = a.get("description") or ""
        for match in re.finditer(r"/files/(\d+)", desc):
            file_id = match.group(1)
            try:
                resp = api.get(
                    f"{base_url}/api/v1/courses/{course.id}/files/{file_id}", timeout=30_000
                )
                if resp.status == 200:
                    file_url = resp.json().get("url")
                    if file_url:
                        download_file(api, file_url, dest_dir, downloaded_urls)
            except Exception:
                continue

        sub_resp = api.get(
            f"{base_url}/api/v1/courses/{course.id}/assignments/{a['id']}/submissions/self",
            timeout=30_000,
        )
        if sub_resp.status == 200:
            sub = sub_resp.json()
            for att in sub.get("attachments") or []:
                file_url = att.get("url")
                if file_url:
                    download_file(api, file_url, dest_dir / "my_submissions", downloaded_urls)


def scrape_pages_api(api, course: Course, course_dir: Path, downloaded_urls: set[str]) -> None:
    print("  [pages - api]")
    dest_dir = course_dir / "pages"
    base_url = course.url.rsplit("/courses/", 1)[0]

    pages = api_get_json(api, f"{base_url}/api/v1/courses/{course.id}/pages?per_page=100")
    if not pages:
        print("    [skip] No pages or no access")
        return

    for pg in pages:
        page_url = pg.get("url")
        if not page_url:
            continue
        try:
            resp = api.get(
                f"{base_url}/api/v1/courses/{course.id}/pages/{page_url}", timeout=30_000
            )
            if resp.status != 200:
                continue
            body = resp.json().get("body") or ""
            for match in re.finditer(r"/files/(\d+)", body):
                file_id = match.group(1)
                file_resp = api.get(
                    f"{base_url}/api/v1/courses/{course.id}/files/{file_id}", timeout=30_000
                )
                if file_resp.status == 200:
                    file_url = file_resp.json().get("url")
                    if file_url:
                        download_file(api, file_url, dest_dir, downloaded_urls)
        except Exception:
            continue


# --------------- Page-scraping fallback ---------------


def scrape_modules_page(
    page, api, course: Course, course_dir: Path, base_url: str, downloaded_urls: set[str]
) -> None:
    print("  [modules - page scrape]")
    try:
        page.goto(f"{course.url}/modules", timeout=30_000)
        page.wait_for_load_state("networkidle")
    except PwTimeout:
        return

    if "unauthorized" in page.url or "login" in page.url:
        return

    dest_dir = course_dir / "modules"

    for url in collect_file_urls_from_page(page, base_url):
        download_file(api, url, dest_dir, downloaded_urls)

    item_links = []
    for a in page.query_selector_all("a.ig-title[href], a[href*='/modules/items/']"):
        href = a.get_attribute("href") or ""
        if "/pages/" in href or "/assignments/" in href or "/files/" in href:
            item_links.append(href if href.startswith("http") else base_url + href)

    for link in item_links:
        try:
            page.goto(link, timeout=15_000)
            page.wait_for_load_state("networkidle")
            for url in collect_file_urls_from_page(page, base_url):
                download_file(api, url, dest_dir, downloaded_urls)
        except PwTimeout:
            continue


def scrape_assignments_page(
    page, api, course: Course, course_dir: Path, base_url: str, downloaded_urls: set[str]
) -> None:
    print("  [assignments - page scrape]")
    try:
        page.goto(f"{course.url}/assignments", timeout=30_000)
        page.wait_for_load_state("networkidle")
    except PwTimeout:
        return

    if "unauthorized" in page.url or "login" in page.url:
        return

    assignment_links = []
    for a in page.query_selector_all("a.ig-title[href], a[href*='/assignments/']"):
        href = a.get_attribute("href") or ""
        if "/assignments/" in href:
            full = href if href.startswith("http") else base_url + href
            if full not in assignment_links:
                assignment_links.append(full)

    dest_dir = course_dir / "assignments"
    for link in assignment_links:
        try:
            page.goto(link, timeout=15_000)
            page.wait_for_load_state("networkidle")
            for url in collect_file_urls_from_page(page, base_url):
                download_file(api, url, dest_dir, downloaded_urls)
        except PwTimeout:
            continue


def scrape_pages_page(
    page, api, course: Course, course_dir: Path, base_url: str, downloaded_urls: set[str]
) -> None:
    print("  [pages - page scrape]")
    try:
        page.goto(f"{course.url}/pages", timeout=30_000)
        page.wait_for_load_state("networkidle")
    except PwTimeout:
        return

    if "unauthorized" in page.url or "login" in page.url:
        return

    page_links = []
    for a in page.query_selector_all("a[href*='/pages/']"):
        href = a.get_attribute("href") or ""
        if "/pages/" in href:
            full = href if href.startswith("http") else base_url + href
            if full not in page_links:
                page_links.append(full)

    dest_dir = course_dir / "pages"
    for link in page_links:
        try:
            page.goto(link, timeout=15_000)
            page.wait_for_load_state("networkidle")
            for url in collect_file_urls_from_page(page, base_url):
                download_file(api, url, dest_dir, downloaded_urls)
        except PwTimeout:
            continue


# --------------- Main ---------------


def run(base_url: str, download_dir: Path) -> None:
    from playwright.sync_api import sync_playwright

    download_dir.mkdir(exist_ok=True)
    downloaded_urls: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        login(page, base_url)

        api = context.request
        courses = get_courses(api, base_url)
        courses.sort(key=lambda c: c.name)

        for course in courses:
            print(f"\n=== {course.name} ===")
            course_dir = download_dir / course.name

            scrape_files_api(api, course, course_dir, downloaded_urls)
            scrape_modules_api(api, course, course_dir, downloaded_urls)
            scrape_assignments_api(api, course, course_dir, downloaded_urls)
            scrape_pages_api(api, course, course_dir, downloaded_urls)

            scrape_modules_page(page, api, course, course_dir, base_url, downloaded_urls)
            scrape_assignments_page(page, api, course, course_dir, base_url, downloaded_urls)
            scrape_pages_page(page, api, course, course_dir, base_url, downloaded_urls)

        browser.close()
        print("\nDone!")
