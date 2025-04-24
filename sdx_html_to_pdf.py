"""
Scrape HTML content from specified websites, render web pages with images,
and convert the rendered content into PDF format.
- Target URLs:
    https://third-bit.com/sdxpy/
    https://third-bit.com/sdxjs/
"""

import os
import traceback
import tempfile
import pdfkit
import requests
from io import BytesIO
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from PyPDF2 import PdfMerger


# Global variable for the temporary CSS file
temp_css_file = None


def create_temp_css_file():
    """Creates a temporary CSS file to hide the sidebar and returns its path."""
    global temp_css_file
    css_content = (
        ".sidebar { display: none !important; visibility: hidden !important; }"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".css", delete=False) as f:
        f.write(css_content)
        temp_css_file = f.name
    print(f"Created temporary CSS file: {temp_css_file}")
    return temp_css_file


def cleanup_temp_css_file():
    """Removes the temporary CSS file."""
    global temp_css_file
    if temp_css_file and os.path.exists(temp_css_file):
        os.remove(temp_css_file)
        print(f"Removed temporary CSS file: {temp_css_file}")


def check_wkhtmltopdf():
    """Check if wkhtmltopdf is installed and accessible, or use path from env."""
    wkhtmltopdf_path = f"wkhtmltox/bin/wkhtmltopdf.exe"
    try:
        if wkhtmltopdf_path:
            config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
        else:
            config = pdfkit.configuration()
        if not config.wkhtmltopdf or not os.path.isfile(config.wkhtmltopdf):
            raise OSError
        return config
    except Exception:
        print(
            "Error: wkhtmltopdf executable not found.\n"
            "Download: https://wkhtmltopdf.org/downloads.html"
        )
        exit(1)


def fetch_html(url):
    """Fetches the HTML content of a given URL using requests."""
    try:
        print(f"Fetching (requests): {url}")
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def get_internal_links(base_url, html):
    """Extracts internal links from the sidebar of an HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc
    links = []
    sidebar = soup.find("div", class_="sidebar")
    if sidebar:
        for a in sidebar.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(base_url, href)
            if urlparse(full_url).netloc == base_domain and full_url.startswith(
                base_url
            ):
                url = full_url.split("#")[0]
                title = a.get_text(strip=True) or url
                if (url, title) not in links and "zip" not in url:
                    links.append((url, title))
    return links


def render_page_to_pdf(page_url, config=None):
    """Renders a web page to a PDF in memory using pdfkit.from_url while hiding the sidebar.
    Preserves original styles by rendering directly from the URL.
    """
    try:
        if not page_url:
            print("Error: Page URL is empty.")
            return None

        print(f"Rendering PDF for {page_url}")
        pdf_bytes = BytesIO()

        try:
            options = [
                ("quiet", ""),
                ("no-outline", None),
                ("encoding", "UTF-8"),
                ("enable-local-file-access", None),
                ("custom-header", [("Referer", page_url)]),
                # Pass the global temporary CSS file
                ("user-style-sheet", temp_css_file),
            ]

            pdf_data = pdfkit.from_url(
                url=page_url, options=options, configuration=config
            )
            pdf_bytes.write(pdf_data)
        except Exception as render_exc:
            print(f"Exception during pdfkit rendering: {render_exc}")
            traceback.print_exc()

        print("PDF rendered successfully for:", page_url)
        pdf_bytes.seek(0)
        return pdf_bytes
    except Exception as e:
        print(f"Error rendering page to PDF: {e}")
        traceback.print_exc()
        return None


# Add bookmarks to the merged PDF with chapter structure
def add_bookmarks_with_chapters(merger, bookmarks):
    """Add hierarchical bookmarks to the PDF with proper chapter numbering."""
    chapter_num = 1
    in_chapter_section = False

    for title, page_num in bookmarks:
        try:
            # Check for chapter beginning
            if "introduction" in title.lower():
                in_chapter_section = True

            # Format title with chapter number if in chapters section
            if in_chapter_section:
                formatted_title = f"Chapter {chapter_num}: {title}"
                chapter_num += 1
            else:
                formatted_title = title

            # Check for end of chapters section
            if "conclusion" in title.lower():
                in_chapter_section = False

            # Add the bookmark
            merger.add_outline_item(
                title=formatted_title, page_number=page_num, parent=None
            )
            print(f"Added bookmark: {formatted_title} at page {page_num}")

        except Exception as e:
            print(f"⚠️ Could not add bookmark '{title}' at page {page_num}: {e}")


if __name__ == "__main__":
    config = check_wkhtmltopdf()

    # Create the temporary CSS file once
    create_temp_css_file()

    try:
        target_urls = [
            ("https://third-bit.com/sdxpy/", "sdxpy.pdf"),
            ("https://third-bit.com/sdxjs/", "sdxjs.pdf"),
        ]

        for base_url, pdf_name in target_urls:
            print(f"Processing website: {base_url}")
            merger = PdfMerger()
            bookmarks = []
            current_page = 0

            try:
                root_html = fetch_html(base_url)
                if not root_html:
                    print(f"Failed to fetch root HTML from {base_url}, skipping...")
                    continue

                link_tuples = get_internal_links(base_url, root_html)
                all_links = [(base_url, "Home")] + [
                    lt for lt in link_tuples if lt[0] != base_url
                ]
                print(f"Found {len(all_links)} pages to process.")

                for i, (url, title) in enumerate(all_links, 1):
                    print(f"Processing page {i}/{len(all_links)}: {url}")
                    try:
                        pdf_bytes = render_page_to_pdf(url, title, config=config)
                        if pdf_bytes:
                            merger.append(pdf_bytes)
                            # Get number of pages in this chapter
                            from PyPDF2 import PdfReader

                            pdf_bytes.seek(0)
                            reader = PdfReader(pdf_bytes)
                            num_pages = len(reader.pages)
                            # Add bookmark at the current page
                            bookmarks.append((title, current_page))
                            current_page += num_pages
                            print(f"✅ Successfully rendered and added page: {title}")
                        else:
                            print(f"⚠️ Failed to render PDF for: {url}")
                    except Exception as e:
                        print(f"⚠️ Error during PDF rendering for {url}: {e}")
                        traceback.print_exc()

                # Use the function to add bookmarks
                add_bookmarks_with_chapters(merger, bookmarks)

                if merger.pages:
                    print(f"Saving merged PDF to: {pdf_name}")
                    try:
                        with open(pdf_name, "wb") as f:
                            merger.write(f)
                        print(f"✅ Successfully created: {pdf_name}")
                    except Exception as e:
                        print(f"Error saving PDF {pdf_name}: {e}")
                        traceback.print_exc()
                    finally:
                        merger.close()
                else:
                    print(f"⚠️ No pages were added to the PDF for {base_url}.")
                    merger.close()

            except Exception as e:
                print(f"An error occurred while processing {base_url}: {e}")
                traceback.print_exc()
            finally:
                print(f"Finished processing {base_url}\n{'='*30}")

    finally:
        # Clean up the temporary CSS file at the end
        cleanup_temp_css_file()

    print("✨ PDF generation process completed. ✨")
