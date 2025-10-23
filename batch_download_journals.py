#!/usr/bin/env python3
"""
Batch script to download all articles from multiple journals using OpenAlex API.
Reads journal names from a text file and saves each journal's articles to separate JSON files.
"""

import requests
import json
import time
import os
import random
import string
from urllib.parse import urlencode
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
from datetime import datetime


# OpenAlex API configuration
OPENALEX_API_BASE = "https://api.openalex.org"
BASE_EMAIL = "ztonys@outlook.com"
MAX_WORKERS = 2  # Further reduced to avoid rate limits
PER_PAGE = 200
REQUEST_DELAY = 0.5  # Increased to 0.5 seconds (2 requests per second max)
MAX_RETRIES = 3  # Maximum number of retries for failed requests
RETRY_DELAY = 5  # Increased retry delay to 5 seconds


def generate_random_email() -> str:
    """
    Generate a random email address based on the base email.
    This helps distribute requests across different email identifiers.
    
    Returns:
        Random email address string
    """
    # Extract domain from base email
    if "@" in BASE_EMAIL:
        username, domain = BASE_EMAIL.split("@", 1)
    else:
        username = BASE_EMAIL
        domain = "outlook.com"
    
    # Add random suffix to username
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{username}+{random_suffix}@{domain}"


def retry_on_error(func):
    """
    Decorator to retry a function on error with exponential backoff.
    
    Args:
        func: Function to retry
        
    Returns:
        Wrapped function with retry logic
    """
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    print(f"  Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"  All {MAX_RETRIES} attempts failed: {e}")
        raise last_exception
    return wrapper


def read_journal_list(filename: str) -> List[str]:
    """
    Read journal names from a text file.
    
    Args:
        filename: Path to the text file containing journal names (one per line)
        
    Returns:
        List of journal names
    """
    with open(filename, 'r', encoding='utf-8') as f:
        journals = [line.strip() for line in f if line.strip()]
    return journals


@retry_on_error
def search_journal_by_name(journal_name: str) -> Optional[Dict]:
    """
    Search for a journal by name and return the best match.
    
    Args:
        journal_name: Name of the journal to search for
        
    Returns:
        Dictionary containing journal information or None if not found
    """
    params = {
        "search": journal_name,
        "per-page": 10,
        "mailto": generate_random_email()
    }
    
    url = f"{OPENALEX_API_BASE}/sources?{urlencode(params)}"
    
    time.sleep(REQUEST_DELAY)  # Rate limiting
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    if data.get("results") and len(data["results"]) > 0:
        return data["results"][0]
    else:
        return None


@retry_on_error
def get_total_works_count(journal_id: str) -> int:
    """
    Get the total number of works published in the journal.
    
    Args:
        journal_id: OpenAlex ID of the journal
        
    Returns:
        Total number of works
    """
    params = {
        "filter": f"primary_location.source.id:{journal_id}",
        "per-page": 1,
        "mailto": generate_random_email()
    }
    
    url = f"{OPENALEX_API_BASE}/works?{urlencode(params)}"
    
    time.sleep(REQUEST_DELAY)  # Rate limiting
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("meta", {}).get("count", 0)


@retry_on_error
def fetch_works_page(journal_id: str, page: int) -> List[Dict]:
    """
    Fetch a single page of works from the journal.
    
    Args:
        journal_id: OpenAlex ID of the journal
        page: Page number to fetch (1-indexed)
        
    Returns:
        List of work dictionaries
    """
    params = {
        "filter": f"primary_location.source.id:{journal_id}",
        "per-page": PER_PAGE,
        "page": page,
        "mailto": generate_random_email()
    }
    
    url = f"{OPENALEX_API_BASE}/works?{urlencode(params)}"
    
    time.sleep(REQUEST_DELAY)  # Rate limiting
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])


def extract_corresponding_authors(authorships: List[Dict]) -> List[str]:
    """
    Extract names of corresponding authors from authorships list.
    
    Args:
        authorships: List of authorship dictionaries
        
    Returns:
        List of corresponding author names
    """
    corresponding = []
    for authorship in authorships:
        if authorship.get("is_corresponding", False):
            author_name = authorship.get("author", {}).get("display_name", "Unknown")
            corresponding.append(author_name)
    return corresponding


def extract_all_authors(authorships: List[Dict]) -> List[str]:
    """
    Extract all author names from authorships list.
    
    Args:
        authorships: List of authorship dictionaries
        
    Returns:
        List of all author names in order
    """
    authors = []
    for authorship in authorships:
        author_name = authorship.get("author", {}).get("display_name", "Unknown")
        authors.append(author_name)
    return authors


def reconstruct_abstract_from_inverted_index(inverted_index: Dict) -> str:
    """
    Reconstruct abstract text from inverted index format.
    
    Args:
        inverted_index: Dictionary mapping words to their positions
        
    Returns:
        Reconstructed abstract text
    """
    if not inverted_index:
        return ""
    
    word_positions = []
    
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    
    word_positions.sort(key=lambda x: x[0])
    abstract = " ".join([word for _, word in word_positions])
    
    return abstract


def process_work(work: Dict) -> Dict:
    """
    Process a single work and extract relevant information.
    
    Args:
        work: Raw work dictionary from OpenAlex API
        
    Returns:
        Dictionary with processed work information
    """
    authorships = work.get("authorships", [])
    all_authors = extract_all_authors(authorships)
    corresponding_authors = extract_corresponding_authors(authorships)
    
    pub_date = work.get("publication_date", "")
    
    # Get abstract
    abstract = ""
    abstract_inverted_index = work.get("abstract_inverted_index")
    if abstract_inverted_index:
        abstract = reconstruct_abstract_from_inverted_index(abstract_inverted_index)
    
    processed = {
        "title": work.get("title", "No title"),
        "doi": work.get("doi", ""),
        "publication_date": pub_date,
        "publication_year": work.get("publication_year", ""),
        "authors": "; ".join(all_authors) if all_authors else "No authors",
        "corresponding_authors": "; ".join(corresponding_authors) if corresponding_authors else "",
        "abstract": abstract,
        "cited_by_count": work.get("cited_by_count", 0),
        "openalex_id": work.get("id", ""),
        "type": work.get("type", ""),
    }
    
    return processed


def download_all_works(journal_id: str, total_count: int) -> List[Dict]:
    """
    Download all works from a journal using concurrent requests.
    
    Args:
        journal_id: OpenAlex ID of the journal
        total_count: Total number of works to download
        
    Returns:
        List of processed work dictionaries
    """
    num_pages = (total_count + PER_PAGE - 1) // PER_PAGE
    
    all_works = []
    
    # Use ThreadPoolExecutor for concurrent downloads
    # Submit tasks with slight delay to avoid burst requests
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for page in range(1, num_pages + 1):
            future = executor.submit(fetch_works_page, journal_id, page)
            futures.append((future, page))
            # Small delay between task submissions to stagger requests
            if page % MAX_WORKERS == 0:
                time.sleep(REQUEST_DELAY * 0.5)
        
        for future, page in futures:
            try:
                works = future.result()
                all_works.extend(works)
            except Exception as e:
                print(f"  Error processing page {page}: {e}")
    
    # Process all works
    processed_works = [process_work(work) for work in all_works]
    
    return processed_works


def save_to_json(works: List[Dict], filename: str) -> None:
    """
    Save works to a JSON file.
    
    Args:
        works: List of work dictionaries
        filename: Output filename
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(works, f, indent=2, ensure_ascii=False)


def is_valid_json_file(filepath: str) -> bool:
    """
    Check if a file exists and contains valid JSON data.
    
    Args:
        filepath: Path to the JSON file
        
    Returns:
        True if file exists and contains valid JSON, False otherwise
    """
    if not os.path.exists(filepath):
        return False
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Check if it's a list (our expected format)
            return isinstance(data, list)
    except (json.JSONDecodeError, IOError):
        return False


def process_single_journal(journal_name: str, line_number: int, output_dir: str) -> Dict:
    """
    Process a single journal and save its articles.
    
    Args:
        journal_name: Name of the journal
        line_number: Line number in the input file (1-indexed)
        output_dir: Directory to save output files
        
    Returns:
        Dictionary with processing results
    """
    output_file = os.path.join(output_dir, f"{line_number}.json")
    
    # Check if file already exists and is valid (resume capability)
    if is_valid_json_file(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                articles_count = len(existing_data)
            print(f"[{line_number}] {journal_name}: Already processed ({articles_count} articles), skipping")
            return {
                "line_number": line_number,
                "journal_name": journal_name,
                "status": "skipped",
                "articles_count": articles_count,
                "message": "File already exists and is valid"
            }
        except Exception:
            # If we can't read the file, we'll reprocess it
            print(f"[{line_number}] {journal_name}: Existing file corrupted, reprocessing")
            pass
    
    print(f"[{line_number}] Processing: {journal_name}")
    
    # Search for journal with retry
    try:
        journal = search_journal_by_name(journal_name)
        if not journal:
            print(f"[{line_number}] {journal_name}: Not found in OpenAlex database")
            return {
                "line_number": line_number,
                "journal_name": journal_name,
                "status": "not_found",
                "message": "Journal not found in OpenAlex database"
            }
    except Exception as e:
        print(f"[{line_number}] {journal_name}: Failed to search - {e}")
        return {
            "line_number": line_number,
            "journal_name": journal_name,
            "status": "failed",
            "message": f"Search failed: {str(e)}"
        }
    
    journal_id = journal.get("id")
    journal_display_name = journal.get("display_name", journal_name)
    
    # Get total works count with retry
    try:
        total_count = get_total_works_count(journal_id)
        print(f"[{line_number}] {journal_display_name}: {total_count} articles")
    except Exception as e:
        print(f"[{line_number}] {journal_display_name}: Failed to get article count - {e}")
        return {
            "line_number": line_number,
            "journal_name": journal_name,
            "journal_display_name": journal_display_name,
            "status": "failed",
            "message": f"Failed to get article count: {str(e)}"
        }
    
    if total_count == 0:
        print(f"[{line_number}] {journal_display_name}: No articles found")
        # Still save an empty result
        save_to_json([], output_file)
        return {
            "line_number": line_number,
            "journal_name": journal_name,
            "journal_display_name": journal_display_name,
            "status": "success",
            "articles_count": 0,
            "message": "No articles"
        }
    
    # Download all works with retry
    try:
        works = download_all_works(journal_id, total_count)
        
        # Save to JSON
        save_to_json(works, output_file)
        
        print(f"[{line_number}] {journal_display_name}: Saved {len(works)} articles to {line_number}.json")
        
        return {
            "line_number": line_number,
            "journal_name": journal_name,
            "journal_display_name": journal_display_name,
            "status": "success",
            "articles_count": len(works),
            "message": "Success"
        }
        
    except Exception as e:
        print(f"[{line_number}] {journal_display_name}: Download failed - {e}")
        return {
            "line_number": line_number,
            "journal_name": journal_name,
            "journal_display_name": journal_display_name,
            "status": "failed",
            "message": f"Download failed: {str(e)}"
        }


def save_progress_log(results: List[Dict], log_file: str) -> None:
    """
    Save processing progress to a log file.
    
    Args:
        results: List of processing results
        log_file: Path to log file
    """
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def print_summary(results: List[Dict]) -> None:
    """
    Print summary statistics of the batch processing.
    
    Args:
        results: List of processing results
    """
    total = len(results)
    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    not_found = sum(1 for r in results if r["status"] == "not_found")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    total_articles = sum(r.get("articles_count", 0) for r in results if r["status"] in ["success", "skipped"])
    
    print("\n" + "="*60)
    print("BATCH PROCESSING SUMMARY")
    print("="*60)
    print(f"Total journals processed: {total}")
    print(f"Successfully downloaded: {success}")
    print(f"Skipped (already exists): {skipped}")
    print(f"Not found in database: {not_found}")
    print(f"Failed (errors): {failed}")
    print(f"Total articles: {total_articles}")
    print("="*60)


def main():
    """
    Main function to orchestrate batch download process.
    """
    parser = argparse.ArgumentParser(
        description="Batch download articles from multiple journals using OpenAlex API"
    )
    parser.add_argument(
        "input_file",
        help="Text file containing journal names (one per line)"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="output",
        help="Output directory for JSON files (default: output)"
    )
    parser.add_argument(
        "-s", "--start",
        type=int,
        default=1,
        help="Start from line number (1-indexed, default: 1)"
    )
    parser.add_argument(
        "-e", "--end",
        type=int,
        help="End at line number (1-indexed, optional)"
    )
    parser.add_argument(
        "-l", "--log",
        default="batch_log.json",
        help="Log file for processing results (default: batch_log.json)"
    )
    
    args = parser.parse_args()
    
    # Create output directory if not exists
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Read journal list
    print(f"Reading journal list from {args.input_file}...")
    journals = read_journal_list(args.input_file)
    print(f"Total journals in file: {len(journals)}")
    
    # Determine range
    start_idx = args.start - 1  # Convert to 0-indexed
    end_idx = args.end if args.end else len(journals)
    
    journals_to_process = journals[start_idx:end_idx]
    print(f"Processing journals from line {args.start} to {end_idx}")
    print(f"Total to process: {len(journals_to_process)}")
    print(f"Output directory: {args.output_dir}")
    print(f"Log file: {args.log}")
    print()
    print("Rate limiting settings:")
    print(f"  - Request delay: {REQUEST_DELAY}s between requests")
    print(f"  - Max concurrent workers: {MAX_WORKERS}")
    print(f"  - Per-page results: {PER_PAGE}")
    print(f"  - Using randomized email addresses for polite pool")
    print()
    
    # Start timer
    start_time = time.time()
    
    # Process each journal
    results = []
    for idx, journal_name in enumerate(journals_to_process):
        line_number = start_idx + idx + 1  # Convert back to 1-indexed line number
        
        result = process_single_journal(journal_name, line_number, args.output_dir)
        results.append(result)
        
        # Save progress periodically (every 10 journals)
        if len(results) % 10 == 0:
            save_progress_log(results, args.log)
        
        # Add delay between journals to avoid overwhelming the API
        # Longer delay if we just downloaded data (not skipped)
        if result["status"] in ["success"]:
            time.sleep(2)  # 2 second delay after successful download
        else:
            time.sleep(0.5)  # Shorter delay for skipped/failed journals
        
        print()  # Empty line for readability
    
    # Save final log
    save_progress_log(results, args.log)
    
    # Print summary
    elapsed_time = time.time() - start_time
    print_summary(results)
    print(f"\nTotal time: {elapsed_time:.2f} seconds")
    print(f"Average time per journal: {elapsed_time/len(results):.2f} seconds")
    print(f"\nLog saved to: {args.log}")


if __name__ == "__main__":
    main()

