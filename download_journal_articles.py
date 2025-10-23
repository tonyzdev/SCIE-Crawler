#!/usr/bin/env python3
"""
Script to download all articles from a journal using OpenAlex API.
"""

import requests
import json
import csv
import time
from urllib.parse import urlencode
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse


# OpenAlex API configuration
OPENALEX_API_BASE = "https://api.openalex.org"
POLITE_EMAIL = "ztonys@outlook.com"  # Replace with your email for polite pool access
MAX_WORKERS = 5  # Number of concurrent requests
PER_PAGE = 200  # Maximum items per page allowed by OpenAlex


def search_journal_by_name(journal_name: str) -> Optional[Dict]:
    """
    Search for a journal by name and return the best match.
    
    Args:
        journal_name: Name of the journal to search for
        
    Returns:
        Dictionary containing journal information or None if not found
    """
    print(f"Searching for journal: {journal_name}")
    
    params = {
        "search": journal_name,
        "per-page": 10,
        "mailto": POLITE_EMAIL
    }
    
    url = f"{OPENALEX_API_BASE}/sources?{urlencode(params)}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("results") and len(data["results"]) > 0:
            # Return the first (best) match
            journal = data["results"][0]
            print(f"Found journal: {journal.get('display_name')} (ID: {journal.get('id')})")
            return journal
        else:
            print(f"No journal found matching: {journal_name}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Error searching for journal: {e}")
        return None


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
        "mailto": POLITE_EMAIL
    }
    
    url = f"{OPENALEX_API_BASE}/works?{urlencode(params)}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("meta", {}).get("count", 0)
    except requests.exceptions.RequestException as e:
        print(f"Error getting works count: {e}")
        return 0


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
        "mailto": POLITE_EMAIL
    }
    
    url = f"{OPENALEX_API_BASE}/works?{urlencode(params)}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page {page}: {e}")
        return []


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
    
    # Get publication date
    pub_date = work.get("publication_date", "")
    
    # Get abstract - check inverted index first, then plain abstract
    abstract = ""
    abstract_inverted_index = work.get("abstract_inverted_index")
    if abstract_inverted_index:
        # Reconstruct abstract from inverted index
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
    
    # Create a list to hold words at their positions
    word_positions = []
    
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    
    # Sort by position and join
    word_positions.sort(key=lambda x: x[0])
    abstract = " ".join([word for _, word in word_positions])
    
    return abstract


def download_all_works(journal_id: str, total_count: int) -> List[Dict]:
    """
    Download all works from a journal using concurrent requests.
    
    Args:
        journal_id: OpenAlex ID of the journal
        total_count: Total number of works to download
        
    Returns:
        List of processed work dictionaries
    """
    # Calculate number of pages needed
    num_pages = (total_count + PER_PAGE - 1) // PER_PAGE
    print(f"Downloading {total_count} works across {num_pages} pages...")
    
    all_works = []
    
    # Use ThreadPoolExecutor for concurrent downloads
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all page fetch tasks
        future_to_page = {
            executor.submit(fetch_works_page, journal_id, page): page 
            for page in range(1, num_pages + 1)
        }
        
        # Process completed tasks
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            try:
                works = future.result()
                all_works.extend(works)
                print(f"Downloaded page {page}/{num_pages} ({len(works)} works)")
            except Exception as e:
                print(f"Error processing page {page}: {e}")
    
    print(f"Total works downloaded: {len(all_works)}")
    
    # Process all works
    print("Processing works...")
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
    print(f"Saved {len(works)} works to {filename}")


def save_to_csv(works: List[Dict], filename: str) -> None:
    """
    Save works to a CSV file.
    
    Args:
        works: List of work dictionaries
        filename: Output filename
    """
    if not works:
        print("No works to save")
        return
    
    # Get all unique keys from all works
    fieldnames = list(works[0].keys())
    
    with open(filename, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(works)
    
    print(f"Saved {len(works)} works to {filename}")


def main():
    """
    Main function to orchestrate the download process.
    """
    parser = argparse.ArgumentParser(
        description="Download all articles from a journal using OpenAlex API"
    )
    parser.add_argument(
        "journal_name",
        help="Name of the journal to download articles from"
    )
    parser.add_argument(
        "-o", "--output",
        default="journal_articles",
        help="Output filename (without extension, default: journal_articles)"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "csv", "both"],
        default="both",
        help="Output format (default: both)"
    )
    parser.add_argument(
        "-e", "--email",
        help="Your email address for OpenAlex polite pool (recommended)"
    )
    
    args = parser.parse_args()
    
    # Update email if provided
    if args.email:
        global POLITE_EMAIL
        POLITE_EMAIL = args.email
    
    # Start timer
    start_time = time.time()
    
    # Step 1: Search for the journal
    journal = search_journal_by_name(args.journal_name)
    if not journal:
        print("Failed to find journal. Exiting.")
        return
    
    journal_id = journal.get("id")
    
    # Step 2: Get total works count
    total_count = get_total_works_count(journal_id)
    print(f"Total works in journal: {total_count}")
    
    if total_count == 0:
        print("No works found for this journal. Exiting.")
        return
    
    # Step 3: Download all works
    works = download_all_works(journal_id, total_count)
    
    if not works:
        print("No works were downloaded. Exiting.")
        return
    
    # Step 4: Save to files
    if args.format in ["json", "both"]:
        save_to_json(works, f"{args.output}.json")
    
    if args.format in ["csv", "both"]:
        save_to_csv(works, f"{args.output}.csv")
    
    # End timer
    elapsed_time = time.time() - start_time
    print(f"\nCompleted in {elapsed_time:.2f} seconds")
    print(f"Average time per work: {elapsed_time/len(works):.3f} seconds")


if __name__ == "__main__":
    main()

