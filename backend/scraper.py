"""
PartSelect.com Scraper
======================
Scrapes comprehensive Refrigerator and Dishwasher part data directly from PartSelect.com.
Uses curl_cffi with Chrome impersonation to bypass bot protection.
Designed to run safely over a long period with randomized delays.
"""

import json
import time
import random
import re
import os
from curl_cffi import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.partselect.com"
OUTPUT_FILE = "products.json"

# Main category pages
CATEGORY_PAGES = [
    "/Dishwasher-Parts.htm",
    "/Refrigerator-Parts.htm",
]


def get_session():
    """Create a new curl_cffi session impersonating Chrome."""
    return requests.Session(impersonate="chrome")


def safe_request(session, url, max_retries=3):
    """Make a request with retries and error handling."""
    for attempt in range(max_retries):
        try:
            response = session.get(url, timeout=30)
            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                print(f"  [!] 403 Forbidden on {url}. Waiting 60s before retry...")
                time.sleep(60)
            elif response.status_code == 429:
                print(f"  [!] Rate limited on {url}. Waiting 120s before retry...")
                time.sleep(120)
            else:
                print(f"  [!] HTTP {response.status_code} on {url}")
                return None
        except Exception as e:
            print(f"  [!] Request error on {url}: {e}")
            if attempt < max_retries - 1:
                time.sleep(30)
    return None


def discover_part_urls(session):
    """
    Phase 1: Discover part URLs from category pages and brand subcategory pages.
    Returns a set of unique part page URLs.
    """
    all_part_urls = set()
    subcategory_urls = set()

    print("=" * 60)
    print("PHASE 1: Discovering Part URLs")
    print("=" * 60)

    # Step 1: Crawl main category pages
    for category_path in CATEGORY_PAGES:
        url = f"{BASE_URL}{category_path}"
        print(f"\nCrawling main category: {url}")

        response = safe_request(session, url)
        if not response:
            continue

        soup = BeautifulSoup(response.text, "lxml")

        # Extract part links (PS pattern)
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            # Part pages have /PS followed by digits
            if re.match(r"^/PS\d+", href) and ".htm" in href:
                # Strip fragment and query params for deduplication
                clean_href = href.split("#")[0].split("?")[0]
                full_url = f"{BASE_URL}{clean_href}"
                all_part_urls.add(full_url)

        # Extract brand subcategory links
        appliance_type = "Dishwasher" if "Dishwasher" in category_path else "Refrigerator"
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if (
                appliance_type in href
                and "Parts.htm" in href
                and href != category_path
                and not href.startswith("http")
            ):
                subcategory_urls.add(f"{BASE_URL}{href}")

        print(f"  Found {len(all_part_urls)} part URLs so far")
        time.sleep(random.uniform(5.0, 10.0))

    # Step 2: Crawl brand subcategory pages
    print(f"\nFound {len(subcategory_urls)} brand subcategory pages to crawl")

    for i, sub_url in enumerate(sorted(subcategory_urls)):
        print(f"  [{i+1}/{len(subcategory_urls)}] Crawling: {sub_url}")

        response = safe_request(session, sub_url)
        if not response:
            continue

        soup = BeautifulSoup(response.text, "lxml")

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if re.match(r"^/PS\d+", href) and ".htm" in href:
                clean_href = href.split("#")[0].split("?")[0]
                full_url = f"{BASE_URL}{clean_href}"
                all_part_urls.add(full_url)

        print(f"    Total unique parts discovered: {len(all_part_urls)}")
        time.sleep(random.uniform(8.0, 15.0))

    print(f"\n{'=' * 60}")
    print(f"Phase 1 Complete: {len(all_part_urls)} unique part URLs discovered")
    print(f"{'=' * 60}\n")

    return all_part_urls


def scrape_part_page(session, url):
    """
    Scrape detailed information from a single PartSelect.com part page.
    Returns a dict with part data, or None on failure.
    """
    response = safe_request(session, url)
    if not response:
        return None

    soup = BeautifulSoup(response.text, "lxml")
    html = response.text

    data = {
        "part_number": "",
        "title": "",
        "description": "",
        "price": "",
        "compatibility_text": "",
        "troubleshooting_text": "",
        "qna_text": "",
        "installation_video": "",
        "url": url,
    }

    # --- Title ---
    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.text.strip()

    # --- PS Part Number (from URL) ---
    ps_match = re.search(r"PS(\d+)", url)
    if ps_match:
        data["part_number"] = f"PS{ps_match.group(1)}"

    # --- Description ---
    desc_section = soup.find("div", class_="pd__description")
    if not desc_section:
        # Fallback: look for the h2 that says "Specifications" and get the text after it
        for h2 in soup.find_all("h2"):
            if "Specifications" in h2.text:
                desc_section = h2.parent
                break
    if desc_section:
        data["description"] = desc_section.get_text(separator=" ", strip=True)[:2000]

    # --- Price ---
    price_el = soup.find("span", class_="price")
    if price_el:
        price_text = price_el.get_text(strip=True)
        # Extract just the dollar amount
        price_match = re.search(r"\$[\d,.]+", price_text)
        if price_match:
            data["price"] = price_match.group(0)

    # --- Q&A Content ---
    qna_div = soup.find("div", id="QuestionsAndAnswersContent")
    if qna_div:
        # Get all the readable Q&A text
        qna_text = qna_div.get_text(separator="\n", strip=True)
        data["qna_text"] = qna_text[:5000]  # Cap at 5000 chars

    # --- Compatible Models ---
    # Look for model numbers mentioned in the page
    # PartSelect pages often list compatible models in various sections
    model_numbers = set()

    # Check for a models section
    models_section = soup.find("div", id="ModelsList") or soup.find(
        "div", class_="pd__models"
    )
    if models_section:
        data["compatibility_text"] = models_section.get_text(
            separator=" ", strip=True
        )[:3000]
    else:
        # Extract model numbers from the whole page using pattern matching
        # Common appliance model patterns: letters followed by digits and sometimes more letters
        model_pattern = re.findall(
            r"\b[A-Z]{2,5}\d{3,}[A-Z0-9]*\b", html[:100000]
        )
        # Filter to likely model numbers (longer than 7 chars, not PS numbers)
        models = set(
            m for m in model_pattern if len(m) > 7 and not m.startswith("PS")
        )
        if models:
            data["compatibility_text"] = (
                "Compatible models include: " + ", ".join(list(models)[:50])
            )

    # --- YouTube Videos ---
    youtube_ids = re.findall(r"youtube\.com/embed/([a-zA-Z0-9_-]+)", html)
    if youtube_ids:
        data["installation_video"] = (
            f"https://www.youtube.com/watch?v={youtube_ids[0]}"
        )

    # --- Troubleshooting / Symptoms ---
    # Look for symptoms or troubleshooting sections
    for section_id in ["Troubleshooting", "Symptoms", "PartSymptoms"]:
        section = soup.find("div", id=section_id) or soup.find(
            "section", id=section_id
        )
        if section:
            data["troubleshooting_text"] = section.get_text(
                separator="\n", strip=True
            )[:3000]
            break

    # Ensure we at least got a title
    if not data["title"]:
        return None

    return data


def load_existing_data():
    """Load previously scraped data for resume support."""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r") as f:
                data = json.load(f)
                print(f"Loaded {len(data)} previously scraped parts from {OUTPUT_FILE}")
                return data
        except (json.JSONDecodeError, IOError):
            print(f"Warning: Could not parse {OUTPUT_FILE}, starting fresh.")
    return []


def save_data(data):
    """Save data to JSON file."""
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def main():
    print("=" * 60)
    print("PartSelect.com Comprehensive Scraper")
    print("Targeting: Refrigerator + Dishwasher Parts")
    print("=" * 60)

    session = get_session()

    # Phase 1: Discover URLs
    all_part_urls = discover_part_urls(session)

    # Convert to sorted list for deterministic ordering
    all_part_urls = sorted(all_part_urls)
    print(f"Will scrape up to {len(all_part_urls)} part pages\n")

    # Phase 2: Scrape Details
    print("=" * 60)
    print("PHASE 2: Scraping Part Details")
    print("=" * 60)

    scraped_data = load_existing_data()
    scraped_urls = {item["url"] for item in scraped_data}

    successful = 0
    skipped = 0
    failed = 0

    for i, url in enumerate(all_part_urls):
        if url in scraped_urls:
            skipped += 1
            continue

        print(f"\n[{i+1}/{len(all_part_urls)}] Scraping: {url}")
        part_data = scrape_part_page(session, url)

        if part_data:
            scraped_data.append(part_data)
            scraped_urls.add(url)
            successful += 1
            print(
                f"  ✓ {part_data['part_number']} - {part_data['title'][:60]}"
            )

            # Save incrementally every 5 successful scrapes
            if successful % 5 == 0:
                save_data(scraped_data)
                print(
                    f"  >>> Saved {len(scraped_data)} total parts to {OUTPUT_FILE}"
                )
        else:
            failed += 1
            print(f"  ✗ Failed to extract data")

        # Randomized delay to avoid IP bans (8-20 seconds)
        delay = random.uniform(8.0, 20.0)
        print(f"  Sleeping {delay:.1f}s...")
        time.sleep(delay)

    # Final save
    save_data(scraped_data)

    print(f"\n{'=' * 60}")
    print(f"Scraping Complete!")
    print(f"  Total parts in database: {len(scraped_data)}")
    print(f"  New parts scraped: {successful}")
    print(f"  Skipped (already scraped): {skipped}")
    print(f"  Failed: {failed}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
