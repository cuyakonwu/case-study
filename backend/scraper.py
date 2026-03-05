import json
import time
import random
import os
from curl_cffi import requests
from bs4 import BeautifulSoup

# This script is designed to run slowly and robustly over a long period
# to scrape comprehensive Refrigerator and Dishwasher part data from AppliancePartsPros.
# We will crawl the category pages to get a list of parts, then scrape each part's details.

BASE_URL = "https://www.appliancepartspros.com"
OUTPUT_FILE = "products.json"

# We target specific categories for Refrigerators and Dishwashers
CATEGORIES = [
    # Refrigerator Categories (Examples)
    "/refrigerator-parts.html",
    # Dishwasher Categories
    "/dishwasher-parts.html"
]

def get_session():
    return requests.Session(impersonate="chrome")

def extract_part_urls(html_content):
    """Extracts individual part URLs from a category listing page."""
    soup = BeautifulSoup(html_content, 'lxml')
    part_links = set()

    # AppliancePartsPros typically lists parts with links containing '-ap' followed by numbers
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if '-ap' in href.lower() and '.html' in href.lower() and not href.startswith('#'):
            # Ensure it's a full URL
            if href.startswith('/'):
                full_url = f"{BASE_URL}{href}"
                part_links.add(full_url)
    return list(part_links)

def scrape_part_details(url, session):
    """Scrapes the detailed information for a single part."""
    print(f"Scraping details from: {url}")
    try:
        response = session.get(url, timeout=30)
        if response.status_code != 200:
            print(f"Failed to fetch {url}: Status {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'lxml')

        # Initialize data structure
        data = {
            "part_number": "",
            "title": "",
            "description": "",
            "compatibility_text": "",
            "troubleshooting_text": "",
            "url": url,
            "image_url": ""
        }

        # Title
        title_el = soup.find('h1')
        if title_el:
            data['title'] = title_el.text.strip()

        # Part Number (usually found near the title or in specific spans)
        # Often formatted as "Item # AP6019471" or "Mfg # WPW10321304"
        part_info_div = soup.find('div', class_='item-info') or soup.find('div', class_='part-info')
        if part_info_div:
            mfg_num = part_info_div.find(string=lambda text: text and 'Mfg #' in text)
            if mfg_num:
                data['part_number'] = mfg_num.parent.text.replace('Mfg #', '').strip()
            else:
                 # Fallback to AP number from URL
                url_parts = url.split('-')
                ap_part = [p for p in url_parts if p.startswith('ap')]
                if ap_part:
                    data['part_number'] = ap_part[0].upper().replace('.HTML', '')

        # Description
        desc_el = soup.find('div', class_='item-description') or soup.find('p', itemprop='description')
        if desc_el:
            data['description'] = desc_el.text.strip()

        # Troubleshooting / Q&A
        qna_section = soup.find('div', id='questions-answers')
        if qna_section:
            data['troubleshooting_text'] = qna_section.text.strip()[:3000] # Limit size

        symptoms_section = soup.find('div', class_='symptoms')
        if symptoms_section:
             data['troubleshooting_text'] += "\n\nCommon Symptoms:\n" + symptoms_section.text.strip()

        # Cross Reference / Compatibility
        cross_ref = soup.find('div', class_='cross-reference') or soup.find('div', id='models-panel')
        if cross_ref:
            data['compatibility_text'] = cross_ref.text.strip()[:2000]

        # Basic Image extraction
        img_el = soup.find('img', itemprop='image')
        if img_el and img_el.get('src'):
             data['image_url'] = img_el['src']

        # Ensure we at least got a title
        if not data['title']:
            return None

        return data

    except Exception as e:
        print(f"Error processing {url}: {e}")
        return None

def main():
    print("Starting robust AppliancePartsPros scraper...")
    session = get_session()
    all_part_urls = set()

    # Phase 1: Gather URLs from Category Pages
    print("--- Phase 1: Gathering Part URLs ---")
    for category in CATEGORIES:
        category_url = f"{BASE_URL}{category}"
        print(f"Crawling category: {category_url}")
        try:
            response = session.get(category_url, timeout=30)
            if response.status_code == 200:
                urls = extract_part_urls(response.text)
                all_part_urls.update(urls)
                print(f"Found {len(urls)} part URLs in this category.")
            else:
                 print(f"Failed to load category {category_url}: {response.status_code}")
        except Exception as e:
            print(f"Error crawling {category_url}: {e}")

        # Polite delay between category pages
        time.sleep(random.uniform(3.0, 7.0))

    all_part_urls = list(all_part_urls)[:200] # Limit to 200 parts for the case study scope to ensure it completes reasonably, adjust if needed
    print(f"Total unique part URLs gathered: {len(all_part_urls)}. Preparing to scrape details.")

    # Phase 2: Scrape Details
    print("\n--- Phase 2: Scraping Part Details ---")

    # Load existing data to resume if interrupted
    scraped_data = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r') as f:
                scraped_data = json.load(f)
                print(f"Loaded {len(scraped_data)} previously scraped parts.")
        except json.JSONDecodeError:
            print("Warning: Could not parse existing products.json, starting fresh.")

    scraped_urls = {item['url'] for item in scraped_data}

    successful_scrapes = 0

    for i, url in enumerate(all_part_urls):
        if url in scraped_urls:
             print(f"Skipping {url} (already scraped)")
             continue

        print(f"[{i+1}/{len(all_part_urls)}]")
        part_data = scrape_part_details(url, session)

        if part_data:
            scraped_data.append(part_data)
            successful_scrapes += 1
            scraped_urls.add(url)

            # Save incrementally very often in case of crashes/bans
            if successful_scrapes % 5 == 0:
                with open(OUTPUT_FILE, 'w') as f:
                    json.dump(scraped_data, f, indent=4)
                print(f">>> Incrementally saved {len(scraped_data)} parts to {OUTPUT_FILE}")

        # Critical: Random, long delays to prevent IP bans.
        # The user requested safety over speed.
        delay = random.uniform(5.0, 15.0)
        print(f"Sleeping for {delay:.2f} seconds to avoid IP ban...")
        time.sleep(delay)

    # Final Save
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(scraped_data, f, indent=4)
    print(f"\nScraping complete! Successfully gathered {len(scraped_data)} total parts.")

if __name__ == "__main__":
    main()
