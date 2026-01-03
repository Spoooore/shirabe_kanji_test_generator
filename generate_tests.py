#!/usr/bin/env python3
"""
Kanji Test Generator - Creates multiple choice tests from .shirabe files
"""

import json
import random
import os
import glob
from dataclasses import dataclass
from typing import List, Optional
import html
import urllib.request
import urllib.parse
import time

# Cache for fetched kanji data
FAKE_KANJI_CACHE_FILE = os.path.join(os.path.dirname(__file__), '.kanji_cache.json')
FAKE_KANJI_POOL = []

# Minimal fallback list if API is unavailable
FALLBACK_KANJI_POOL = [
    ("食べる", "jeść"), ("飲む", "pić"), ("行く", "iść"), ("来る", "przyjść"),
    ("見る", "widzieć"), ("聞く", "słyszeć"), ("話す", "mówić"), ("読む", "czytać"),
    ("書く", "pisać"), ("買う", "kupować"), ("待つ", "czekać"), ("知る", "wiedzieć"),
    ("思う", "myśleć"), ("作る", "tworzyć"), ("持つ", "trzymać"), ("出る", "wychodzić"),
]


def fetch_jisho_words(keyword: str, pages: int = 3) -> List[tuple]:
    """Fetch words from Jisho API."""
    results = []
    
    for page in range(1, pages + 1):
        try:
            url = f"https://jisho.org/api/v1/search/words?keyword={urllib.parse.quote(keyword)}&page={page}"
            req = urllib.request.Request(url, headers={'User-Agent': 'KanjiTestGenerator/1.0'})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                
            for item in data.get('data', []):
                japanese = item.get('japanese', [{}])[0]
                word = japanese.get('word') or japanese.get('reading', '')
                reading = japanese.get('reading', '')
                
                # Get English meaning (we'll use it as placeholder since Polish isn't available)
                senses = item.get('senses', [{}])
                meanings = []
                for sense in senses:
                    meanings.extend(sense.get('english_definitions', []))
                
                meaning = meanings[0] if meanings else ''
                
                if word and meaning and any('\u4e00' <= c <= '\u9fff' for c in word):
                    results.append((word, meaning))
            
            time.sleep(0.3)  # Be nice to the API
            
        except Exception as e:
            print(f"   Warning: Failed to fetch page {page} for '{keyword}': {e}")
            break
    
    return results


def load_kanji_cache() -> Optional[List[tuple]]:
    """Load kanji from cache file if it exists and is recent."""
    try:
        if os.path.exists(FAKE_KANJI_CACHE_FILE):
            stat = os.stat(FAKE_KANJI_CACHE_FILE)
            # Cache valid for 7 days
            if time.time() - stat.st_mtime < 7 * 24 * 60 * 60:
                with open(FAKE_KANJI_CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [(item['word'], item['meaning']) for item in data]
    except Exception:
        pass
    return None


def save_kanji_cache(kanji_list: List[tuple]):
    """Save kanji to cache file."""
    try:
        data = [{'word': word, 'meaning': meaning} for word, meaning in kanji_list]
        with open(FAKE_KANJI_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"   Warning: Could not save cache: {e}")


def fetch_fake_kanji_pool(force_refresh: bool = False) -> List[tuple]:
    """
    Fetch a large pool of kanji/words from Jisho API.
    Uses caching to avoid repeated API calls.
    """
    global FAKE_KANJI_POOL
    
    # Try loading from cache first
    if not force_refresh:
        cached = load_kanji_cache()
        if cached:
            print(f"   📦 Loaded {len(cached)} kanji from cache")
            FAKE_KANJI_POOL = cached
            return cached
    
    print("   🌐 Fetching kanji from Jisho API...")
    all_words = []
    
    # Fetch from different JLPT levels and common words
    sources = [
        ("#jlpt-n5", 3),   # ~150 words
        ("#jlpt-n4", 3),   # ~150 words  
        ("#jlpt-n3", 4),   # ~200 words
        ("#jlpt-n2", 4),   # ~200 words
        ("#jlpt-n1", 3),   # ~150 words
        ("#common", 5),    # ~250 common words
    ]
    
    for keyword, pages in sources:
        print(f"      Fetching {keyword}...")
        words = fetch_jisho_words(keyword, pages)
        all_words.extend(words)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_words = []
    for word, meaning in all_words:
        if word not in seen:
            seen.add(word)
            unique_words.append((word, meaning))
    
    if unique_words:
        print(f"   ✅ Fetched {len(unique_words)} unique kanji/words")
        save_kanji_cache(unique_words)
        FAKE_KANJI_POOL = unique_words
        return unique_words
    else:
        print("   ⚠️  Could not fetch from API, using fallback list")
        FAKE_KANJI_POOL = FALLBACK_KANJI_POOL
        return FALLBACK_KANJI_POOL


def get_fake_kanji_pool() -> List[tuple]:
    """Get the fake kanji pool, fetching if needed."""
    global FAKE_KANJI_POOL
    if not FAKE_KANJI_POOL:
        return fetch_fake_kanji_pool()
    return FAKE_KANJI_POOL


@dataclass
class VocabEntry:
    reading: str
    kanji: str
    meanings: List[str]
    source_file: str


def parse_shirabe_file(filepath: str) -> List[VocabEntry]:
    """Parse a .shirabe JSON file and extract vocabulary entries."""
    entries = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    bookmarks = data.get('ShirabeJisho', {}).get('Bookmarks', {}).get('list', [])
    
    for bookmark in bookmarks:
        if bookmark.get('type') == 3:
            value = bookmark.get('value', '')
            parts = value.split('\x1c')  # Field separator
            
            if len(parts) >= 3:
                reading = parts[0]
                kanji = parts[1]
                # Split meanings by \x1d (record separator)
                meanings_raw = '\x1d'.join(parts[2:])
                meanings = [m.strip() for m in meanings_raw.split('\x1d') if m.strip()]
                
                entries.append(VocabEntry(
                    reading=reading,
                    kanji=kanji,
                    meanings=meanings,
                    source_file=os.path.basename(filepath)
                ))
    
    return entries


def get_available_files(directory: str) -> List[str]:
    """Get list of available .shirabe files in directory."""
    files = glob.glob(os.path.join(directory, '*.shirabe'))
    return sorted([os.path.basename(f) for f in files])


def load_all_vocab(directory: str, file_filter: List[str] = None) -> List[VocabEntry]:
    """Load vocabulary from .shirabe files in a directory.
    
    Args:
        directory: Path to directory containing .shirabe files
        file_filter: Optional list of file patterns to include (e.g., ['1411-1420', '1431-1440'])
                    If None, loads all .shirabe files
    """
    all_entries = []
    all_files = glob.glob(os.path.join(directory, '*.shirabe'))
    
    for filepath in sorted(all_files):
        filename = os.path.basename(filepath)
        
        # If filter is specified, check if file matches any pattern
        if file_filter:
            match = False
            for pattern in file_filter:
                # Match by range (e.g., "1411-1420") or full filename
                if pattern in filename or pattern == filename.replace('.shirabe', ''):
                    match = True
                    break
            if not match:
                continue
        
        entries = parse_shirabe_file(filepath)
        all_entries.extend(entries)
    
    return all_entries


def get_fake_answers_kanji(correct_entry: VocabEntry, all_entries: List[VocabEntry], count: int = 3) -> List[tuple]:
    """Get fake kanji answers from the external pool."""
    pool = get_fake_kanji_pool()
    # Avoid using kanji that's too similar to the correct answer
    available = [item for item in pool if item[0] != correct_entry.kanji]
    return random.sample(available, min(count, len(available)))


def get_fake_answers_meaning(correct_entry: VocabEntry, all_entries: List[VocabEntry], count: int = 3) -> List[str]:
    """Get fake meaning answers from other entries or the fake pool."""
    fake_meanings = []
    
    # First, try to get meanings from other entries in the study list
    other_entries = [e for e in all_entries if e.kanji != correct_entry.kanji]
    random.shuffle(other_entries)
    
    for entry in other_entries:
        if len(fake_meanings) >= count:
            break
        for meaning in entry.meanings:
            # Avoid similar meanings
            if meaning.lower() not in [m.lower() for m in correct_entry.meanings]:
                if meaning not in fake_meanings:
                    fake_meanings.append(meaning)
                    if len(fake_meanings) >= count:
                        break
    
    # If we need more, use the fake pool
    pool = get_fake_kanji_pool()
    while len(fake_meanings) < count and pool:
        fake_item = random.choice(pool)
        if fake_item[1] not in fake_meanings:
            fake_meanings.append(fake_item[1])
    
    return fake_meanings[:count]


def generate_kanji_to_polish_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a question: Show kanji compound, pick correct Polish meaning."""
    correct_meaning = entry.meanings[0]  # Use first meaning as primary
    fake_meanings = get_fake_answers_meaning(entry, all_entries, 3)
    
    options = [correct_meaning] + fake_meanings
    random.shuffle(options)
    correct_index = options.index(correct_meaning)
    
    return {
        'type': 'kanji_to_polish',
        'question': f'Co oznacza: 【{entry.kanji}】?',
        'question_en': f'What does 【{entry.kanji}】 mean?',
        'options': options,
        'correct': correct_index,
        'correct_answer': correct_meaning,
        'entry': entry
    }


def generate_polish_to_kanji_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a question: Show Polish meaning, pick correct kanji."""
    correct_kanji = entry.kanji
    fake_kanjis = get_fake_answers_kanji(entry, all_entries, 3)
    
    # Show only kanji, no readings (pure kanji recognition)
    options = [correct_kanji] + [k for k, m in fake_kanjis]
    random.shuffle(options)
    correct_index = options.index(correct_kanji)
    
    return {
        'type': 'polish_to_kanji',
        'question': f'Przetłumacz na japoński: „{entry.meanings[0]}"',
        'question_en': f'Translate to Japanese: "{entry.meanings[0]}"',
        'options': options,
        'correct': correct_index,
        'correct_answer': correct_kanji,
        'entry': entry
    }


def generate_reading_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a question: Show kanji, pick correct reading."""
    correct_reading = entry.reading
    
    # Get fake readings from other entries
    other_entries = [e for e in all_entries if e.reading != correct_reading]
    fake_readings = random.sample([e.reading for e in other_entries], min(3, len(other_entries)))
    
    options = [correct_reading] + fake_readings
    random.shuffle(options)
    correct_index = options.index(correct_reading)
    
    return {
        'type': 'reading',
        'question': f'Jakie jest czytanie dla: 【{entry.kanji}】?',
        'question_en': f'What is the reading of 【{entry.kanji}】?',
        'options': options,
        'correct': correct_index,
        'correct_answer': correct_reading,
        'entry': entry
    }


def generate_reading_to_kanji_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a question: Show reading, pick which kanji has that reading."""
    correct_kanji = entry.kanji
    
    # Get fake kanji from other entries in the study list (not external pool)
    other_entries = [e for e in all_entries if e.kanji != correct_kanji]
    if len(other_entries) >= 3:
        fake_entries = random.sample(other_entries, 3)
        fake_kanjis = [e.kanji for e in fake_entries]
    else:
        # Fallback to external pool if not enough entries
        pool = get_fake_kanji_pool()
        fake_kanjis = [k for k, m in random.sample(pool, 3)]
    
    options = [correct_kanji] + fake_kanjis
    random.shuffle(options)
    correct_index = options.index(correct_kanji)
    
    return {
        'type': 'reading_to_kanji',
        'question': f'Które kanji ma czytanie: 「{entry.reading}」?',
        'question_en': f'Which kanji has the reading: 「{entry.reading}」?',
        'options': options,
        'correct': correct_index,
        'correct_answer': correct_kanji,
        'entry': entry
    }


def generate_kanji_compound_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a question: Show kanji with reading hint, ask for meaning."""
    correct_meaning = entry.meanings[0]
    fake_meanings = get_fake_answers_meaning(entry, all_entries, 3)
    
    options = [correct_meaning] + fake_meanings
    random.shuffle(options)
    correct_index = options.index(correct_meaning)
    
    return {
        'type': 'kanji_compound',
        'question': f'Co oznacza 【{entry.kanji}】 ({entry.reading})?',
        'question_en': f'What does 【{entry.kanji}】 ({entry.reading}) mean?',
        'options': options,
        'correct': correct_index,
        'correct_answer': correct_meaning,
        'entry': entry
    }


def generate_test(entries: List[VocabEntry], num_questions: int = 20, 
                  question_types: List[str] = None) -> List[dict]:
    """Generate a complete test with mixed question types."""
    if question_types is None:
        question_types = ['kanji_to_polish', 'polish_to_kanji', 'reading', 'reading_to_kanji', 'kanji_compound']
    
    questions = []
    selected_entries = random.sample(entries, min(num_questions, len(entries)))
    
    generators = {
        'kanji_to_polish': generate_kanji_to_polish_question,
        'polish_to_kanji': generate_polish_to_kanji_question,
        'reading': generate_reading_question,
        'reading_to_kanji': generate_reading_to_kanji_question,
        'kanji_compound': generate_kanji_compound_question,
    }
    
    for entry in selected_entries:
        q_type = random.choice(question_types)
        question = generators[q_type](entry, entries)
        questions.append(question)
    
    return questions


def print_test_console(questions: List[dict]):
    """Print test to console in a nice format."""
    print("\n" + "=" * 60)
    print("📝 KANJI TEST - カンジテスト")
    print("=" * 60 + "\n")
    
    for i, q in enumerate(questions, 1):
        print(f"\n【問題 {i}】 {q['question']}")
        print("-" * 40)
        
        for j, option in enumerate(q['options']):
            letter = chr(ord('a') + j)
            print(f"  {letter}) {option}")
        
        print()
    
    print("\n" + "=" * 60)
    print("📋 ANSWER KEY - 答え")
    print("=" * 60 + "\n")
    
    for i, q in enumerate(questions, 1):
        correct_letter = chr(ord('a') + q['correct'])
        print(f"{i}. {correct_letter}) {q['correct_answer']}")


# Path to HTML template
TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), 'template.html')


def load_template() -> str:
    """Load HTML template from file."""
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        return f.read()


def generate_html_test(questions: List[dict], title: str = "Kanji Test") -> str:
    """Generate an interactive HTML test from template."""
    
    # Prepare questions data for JSON
    questions_js = []
    for i, q in enumerate(questions):
        escaped_options = [html.escape(str(opt)) for opt in q['options']]
        entry = q['entry']
        questions_js.append({
            'id': i,
            'question': html.escape(q['question']),
            'options': escaped_options,
            'correct': q['correct'],
            'type': q['type'],
            'kanji': entry.kanji,
            'reading': entry.reading,
            'meaning': entry.meanings[0] if entry.meanings else '',
            'jishoUrl': f"https://jisho.org/search/{entry.kanji}"
        })
    
    # Load and fill template
    template = load_template()
    html_content = template.replace('%%TITLE%%', html.escape(title))
    html_content = html_content.replace('%%QUESTIONS_JSON%%', json.dumps(questions_js, ensure_ascii=False))
    
    return html_content


def main():
    """Main function to generate tests."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate kanji tests from .shirabe files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                                    # Test all files
  %(prog)s -f 1411-1420                       # Test only 1411-1420 range
  %(prog)s -f 1411-1420 1431-1440             # Test specific ranges
  %(prog)s -f 1411-1420 -n 10 -o test1.html   # 10 questions from 1411-1420
  %(prog)s --list-files                       # Show available files
        '''
    )
    parser.add_argument('-d', '--directory', default='.', help='Directory containing .shirabe files')
    parser.add_argument('-f', '--files', nargs='+', metavar='RANGE',
                       help='Specific file ranges to include (e.g., 1411-1420 1431-1440)')
    parser.add_argument('--list-files', action='store_true',
                       help='List available .shirabe files and exit')
    parser.add_argument('-n', '--num-questions', type=int, default=20, help='Number of questions')
    parser.add_argument('-o', '--output', default='test.html', help='Output HTML file')
    parser.add_argument('-c', '--console', action='store_true', help='Print test to console')
    parser.add_argument('-t', '--types', nargs='+', 
                       choices=['kanji_to_polish', 'polish_to_kanji', 'reading', 'reading_to_kanji', 'kanji_compound'],
                       help='Question types to include')
    parser.add_argument('--title', default='Kanji Test', help='Test title')
    parser.add_argument('--refresh-kanji', action='store_true', 
                       help='Force refresh kanji cache from Jisho API')
    parser.add_argument('--offline', action='store_true',
                       help='Use only cached/fallback kanji (no API calls)')
    
    args = parser.parse_args()
    
    # List files mode
    if args.list_files:
        available = get_available_files(args.directory)
        if available:
            print("📁 Available .shirabe files:")
            for f in available:
                # Parse file to count entries
                entries = parse_shirabe_file(os.path.join(args.directory, f))
                range_name = f.replace('.shirabe', '')
                print(f"   • {range_name} ({len(entries)} entries)")
        else:
            print("❌ No .shirabe files found in directory")
        return
    
    # Load vocabulary
    if args.files:
        print(f"📚 Loading vocabulary from: {', '.join(args.files)}...")
    else:
        print(f"📚 Loading vocabulary from {args.directory} (all files)...")
    
    entries = load_all_vocab(args.directory, args.files)
    
    if args.files:
        # Show which files were actually loaded
        loaded_files = set(e.source_file for e in entries)
        print(f"   Loaded files: {', '.join(sorted(loaded_files))}")
    
    print(f"   Found {len(entries)} vocabulary entries")
    
    if not entries:
        print("❌ No vocabulary entries found!")
        return
    
    # Load fake kanji pool
    print("🀄 Loading fake kanji pool for wrong answers...")
    if args.offline:
        # Use cached or fallback only
        cached = load_kanji_cache()
        if cached:
            global FAKE_KANJI_POOL
            FAKE_KANJI_POOL = cached
            print(f"   📦 Loaded {len(cached)} kanji from cache")
        else:
            FAKE_KANJI_POOL = FALLBACK_KANJI_POOL
            print(f"   ⚠️  Using fallback list ({len(FALLBACK_KANJI_POOL)} kanji)")
    else:
        fetch_fake_kanji_pool(force_refresh=args.refresh_kanji)
    
    # Generate test
    print(f"🎲 Generating test with {args.num_questions} questions...")
    questions = generate_test(entries, args.num_questions, args.types)
    
    if args.console:
        print_test_console(questions)
    
    # Generate HTML
    output_path = args.output
    if os.path.exists(output_path):
        print(f"📄 Overwriting existing test: {output_path}")
    else:
        print(f"📄 Generating HTML test: {output_path}")
    
    html_content = generate_html_test(questions, args.title)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Test saved to {output_path}")
    print(f"   Open in your browser to take the test!")


if __name__ == '__main__':
    main()

