import os
import time
import re
import argparse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, unquote
import subprocess
import requests
import shutil

# Constants
BASE_URL = "https://example.org/d/"
DOWNLOAD_DIR = "downloads"
COMPLETED_FILE = "COMPLETED.TXT"
MAX_CONCURRENT_DOWNLOADS = 4
DELAY_BETWEEN_REQUESTS = 3  # in seconds
PREFERRED_DOMAIN = "download.example.lol"
MAX_RETRIES = 3  # Maximum retry attempts for a page
SERVICE_UNAVAILABLE_RETRIES = 2  # Retries for server errors (wget exit status 8 or HTTP 503)
SERVICE_UNAVAILABLE_DELAY = 15  # Delay in seconds for server errors

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Common English words
COMMON_ENGLISH_WORDS = [
    "the", "and", "of", "to", "a", "in", "is", "it", "you", "that", "he", "was", "for", "on", "are", "with", "as",
    "I", "his", "they", "be", "at", "one", "have", "this", "from", "or", "had", "by", "not", "but", "what", "all",
    "security", "architecture", "how", "why", "forensics", "series", "digital", "river", "publishers", "students",
    "research", "hunting", "book", "god", "system", "methods", "embedded", "controller", "learning", "crisis",
    "intervention", "stories", "born", "crime"
]

# Foreign stopwords for common non-English elements
FOREIGN_STOPWORDS = [
    "matemática", "psychologie", "etudes", "le", "la", "de", "del", "das", "dos", "es", "et", "für", "y", "en"
]

def read_last_completed():
    """Reads the last completed page number from the COMPLETED file."""
    if os.path.exists(COMPLETED_FILE):
        with open(COMPLETED_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                print(f"COMPLETED file is invalid. Starting from page 1.")
    return 1  # Default start page if COMPLETED file doesn't exist or is invalid

def write_last_completed(page_number):
    """Writes the last completed page number to the COMPLETED file."""
    with open(COMPLETED_FILE, "w") as f:
        f.write(str(page_number))

def fetch_page_links(page_number):
    """Fetches the links to .EPUB and .PDF files from a page with error handling for 404 and 503."""
    url = f"{BASE_URL}{page_number}"
    for attempt in range(SERVICE_UNAVAILABLE_RETRIES + 1):
        try:
            print(f"Visiting: {url} (Attempt {attempt + 1}/{SERVICE_UNAVAILABLE_RETRIES + 1})")
            response = requests.get(url, timeout=10)

            if response.status_code == 404:
                print(f"Page {page_number} not found (404). Skipping.")
                return []  # Return an empty list to indicate no files found

            if response.status_code == 503:
                print("Received 503 Service Unavailable. Pausing for 15 seconds...")
                time.sleep(SERVICE_UNAVAILABLE_DELAY)
                continue

            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            links = [
                a['href'] for a in soup.find_all("a", href=True)
                if a['href'].lower().endswith(('.epub', '.pdf')) 
                and PREFERRED_DOMAIN in urlparse(a['href']).netloc
            ]
            return links
        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page_number}: {e}")
            if attempt == SERVICE_UNAVAILABLE_RETRIES:
                print(f"Failed to fetch page {page_number} after {SERVICE_UNAVAILABLE_RETRIES + 1} attempts.")
    return []


def is_english_file(filename):
    """Determines if a filename is likely English."""
    decoded_name = unquote(filename).lower()

    # Comprehensive list of patterns for non-English scripts
    NON_ENGLISH_PATTERNS = [
        r'[一-龥]',  # Japanese/Chinese characters
        r'[α-ωΑ-Ω]',  # Greek letters
        r'[а-яА-Я]',  # Russian Cyrillic characters
    ]

    # Check for clearly non-English characters
    for pattern in NON_ENGLISH_PATTERNS:
        if re.search(pattern, decoded_name):
            print(f"Skipped (non-English characters found): {decoded_name}")
            print(f" - Found pattern: {pattern}")
            return False

    # Tokenize the filename into individual words
    words = re.findall(r'\b\w+\b', decoded_name)
    total_words = len(words)

    # Count English words
    english_word_count = sum(word in COMMON_ENGLISH_WORDS for word in words)

    # Check for foreign stopwords as whole words
    found_foreign_words = [word for word in words if word in FOREIGN_STOPWORDS]
    if found_foreign_words:
        print(f"Skipped (foreign words found): {decoded_name}")
        print(f" - Found foreign words: {', '.join(found_foreign_words)}")
        return False

    # Allow download if we are uncertain (lean towards downloading)
    if english_word_count == 0 or english_word_count / total_words < 0.4:
        print(f"Uncertain, downloading anyway: {decoded_name}")
        return True

    # Default to considering the file English
    return True

def friendly_filename(url):
    """Converts URL-encoded filenames into a human-readable format."""
    return unquote(url.split("/")[-1])

def download_with_wget(url):
    """Downloads a file using wget and moves it to the downloads directory once complete."""
    filename = friendly_filename(url)
    temp_path = os.path.join(os.getcwd(), filename)  # Download to CWD first
    final_path = os.path.join(DOWNLOAD_DIR, filename)

    if os.path.exists(final_path):
        print(f"File already completed: {filename}")
        return True

    for attempt in range(SERVICE_UNAVAILABLE_RETRIES + 1):
        try:
            print(f"Downloading/resuming: {filename} (Attempt {attempt + 1}/{SERVICE_UNAVAILABLE_RETRIES + 1})")
            result = subprocess.run(
                ["wget", "-c", "-O", temp_path, url],  # Save directly to temp_path
                check=True
            )
            if result.returncode == 0:
                print(f"Completed: {filename}")
                # Move the file to the downloads directory
                shutil.move(temp_path, final_path)
                print(f"Moved to downloads directory: {final_path}")
                return True
        except subprocess.CalledProcessError as e:
            print(f"Error downloading {filename}: {e}")
            if e.returncode == 8:  # Server error
                print(f"Server error (exit status 8) for {filename}. Retrying after 15 seconds...")
                time.sleep(SERVICE_UNAVAILABLE_DELAY)
            else:
                print(f"Unexpected error for {filename}. Skipping.")
                break  # For other errors, stop retrying
    # If retries fail, clean up partial downloads
    if os.path.exists(temp_path):
        os.remove(temp_path)
    print(f"Failed to download {filename} after {SERVICE_UNAVAILABLE_RETRIES + 1} attempts.")
    return False

def process_links(links):
    """Filters English files and downloads them."""
    unique_links = list(set(links))
    filtered_links = []
    skipped_links = []

    for link in unique_links:
        decoded_name = friendly_filename(link)
        if is_english_file(decoded_name):
            filtered_links.append(link)
            print(f"Ready to download: {decoded_name}")
        else:
            skipped_links.append(decoded_name)

    # Log skipped files explicitly
    if skipped_links:
        print("\nSkipped files:")
        for skipped in skipped_links:
            print(f" - {skipped}")

    # Download valid files
    if filtered_links:
        print(f"Downloading {len(filtered_links)} files concurrently.")
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS) as executor:
            executor.map(download_with_wget, filtered_links)

def process_page_with_retries(page_number):
    """Processes a single page with retries."""
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\nProcessing page {page_number}, attempt {attempt}/{MAX_RETRIES}")
        file_links = fetch_page_links(page_number)

        if not file_links:
            print(f"No files found on page {page_number}. Skipping.")
            return True  # No files to process, consider it done

        process_links(file_links)
        return True  # Success!

    print(f"Page {page_number} failed after {MAX_RETRIES} attempts. Skipping.")
    return False

def main(start_page, end_page):
    for page_number in range(start_page, end_page + 1):
        if process_page_with_retries(page_number):
            write_last_completed(page_number)
            print(f"Page {page_number} completed.")
        else:
            print(f"Page {page_number} was skipped after multiple retries.")
        time.sleep(DELAY_BETWEEN_REQUESTS)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Concurrent Downloader with Page Limits")
    parser.add_argument("--start", type=int, help="Starting page number")
    parser.add_argument("--end", type=int, required=True, help="Ending page number")
    args = parser.parse_args()

    start_page = args.start if args.start else read_last_completed()
    main(start_page, args.end)
