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


def count_kanji(text: str) -> int:
    """Count number of kanji characters in text."""
    return sum(1 for c in text if '\u4e00' <= c <= '\u9fff')


def has_okurigana(text: str) -> bool:
    """Check if text ends with hiragana (okurigana pattern)."""
    if not text:
        return False
    last_char = text[-1]
    return '\u3040' <= last_char <= '\u309f'  # Hiragana range


def get_reading_complexity(reading: str) -> tuple:
    """Get complexity metrics for a reading to match similar ones."""
    # Count mora (roughly length in kana)
    length = len(reading)
    # Check for special patterns
    has_dot = '・' in reading  # Multiple readings
    has_comma = '、' in reading
    has_hiragana_end = has_okurigana(reading)
    return (length // 3, has_dot or has_comma, has_hiragana_end)  # Bucketed length


def get_similar_readings(correct_reading: str, all_entries: List[VocabEntry], count: int = 3) -> List[str]:
    """Get fake readings that are similar in complexity to the correct one."""
    correct_complexity = get_reading_complexity(correct_reading)
    correct_length = len(correct_reading)
    
    # Score entries by similarity
    scored = []
    for entry in all_entries:
        if entry.reading == correct_reading:
            continue
        
        complexity = get_reading_complexity(entry.reading)
        reading_length = len(entry.reading)
        
        # Calculate similarity score (lower is better)
        score = 0
        # Length difference (penalize large differences)
        score += abs(reading_length - correct_length) * 2
        # Complexity match bonus
        if complexity[1] == correct_complexity[1]:  # Same multi-reading pattern
            score -= 5
        if complexity[2] == correct_complexity[2]:  # Same okurigana pattern
            score -= 3
        
        scored.append((score, entry.reading))
    
    # Sort by score and pick best matches
    scored.sort(key=lambda x: (x[0], random.random()))
    return [reading for score, reading in scored[:count]]


# Common kanji components/radicals for finding similar-looking kanji
SIMILAR_KANJI_GROUPS = [
    # Water radical 氵
    ['治', '洗', '洋', '流', '浅', '深', '温', '湖', '海', '港', '湾', '潮', '滝', '沼', '泳', '浴', '液', '涙', '消', '渡', '測', '演', '濃', '漁', '漢', '滅', '漏', '浪'],
    # Fire radical 火/灬
    ['火', '炎', '炉', '灯', '煙', '焼', '燃', '熱', '照', '煮', '蒸', '熟', '燥'],
    # Person radical 亻
    ['仕', '代', '休', '件', '仲', '伝', '位', '住', '体', '作', '使', '例', '供', '価', '俳', '倍', '候', '倒', '借', '値', '健', '側', '傷', '働', '像', '億', '優', '倫'],
    # Tree radical 木
    ['木', '本', '札', '机', '村', '材', '束', '杯', '松', '板', '林', '枚', '果', '枝', '柱', '校', '根', '格', '案', '桜', '梅', '械', '棒', '棟', '森', '植', '検', '業', '極', '楽', '構', '様', '権', '横', '樹', '橋', '機'],
    # Heart radical 忄/心
    ['心', '必', '忘', '応', '念', '思', '急', '性', '怒', '恐', '恥', '恋', '息', '悪', '悲', '情', '惜', '想', '意', '愛', '感', '慣', '態', '慶', '憲', '懇', '懲'],
    # Hand radical 扌
    ['打', '払', '投', '折', '抜', '押', '拝', '拾', '持', '指', '挙', '捨', '捕', '探', '接', '推', '描', '提', '換', '握', '援', '損', '搬', '携', '摘', '撮', '擦', '操', '撲'],
    # Mouth radical 口
    ['口', '古', '句', '叫', '台', '史', '右', '司', '各', '合', '吉', '同', '名', '向', '君', '否', '含', '吸', '告', '呼', '命', '和', '品', '員', '唱', '商', '問', '善', '喚', '営', '器', '噴'],
    # Sun radical 日
    ['日', '旧', '早', '明', '映', '春', '昨', '星', '昼', '時', '晩', '普', '景', '暖', '暗', '暮', '暴', '曜', '曇'],
    # Metal radical 金
    ['金', '針', '鉄', '鋭', '銀', '銅', '銭', '鋼', '録', '鏡', '鐘', '鑑'],
    # Word radical 言
    ['言', '計', '訂', '記', '訓', '託', '訪', '設', '許', '訳', '証', '詞', '詠', '詩', '試', '詰', '話', '該', '詳', '認', '誌', '語', '誠', '誤', '説', '読', '課', '調', '談', '論', '諭', '諸', '講', '謝', '識', '警', '議', '護'],
    # Foot radical 足
    ['足', '距', '跡', '路', '跳', '踊', '踏', '蹴'],
    # Ear radical 耳
    ['耳', '聞', '聖', '聴', '職'],
    # Eye radical 目
    ['目', '直', '相', '省', '看', '眠', '眼', '着', '睡', '督', '瞬'],
    # Rice radical 米
    ['米', '粉', '粋', '粒', '精', '糖', '糧'],
    # Thread radical 糸
    ['糸', '紀', '約', '紅', '納', '純', '紙', '級', '素', '紹', '細', '終', '組', '経', '結', '給', '絡', '統', '絵', '絶', '継', '続', '維', '綱', '網', '緊', '総', '緑', '線', '編', '練', '縁', '縦', '縮', '績', '繁', '織', '繰', '纏', '絞'],
]


def get_similar_kanji(target_kanji: str, count: int = 3) -> List[str]:
    """Find kanji that look similar to the target (share radicals/components)."""
    similar = []
    
    # Check each character in target
    for char in target_kanji:
        if not ('\u4e00' <= char <= '\u9fff'):
            continue
        
        # Find groups containing this kanji
        for group in SIMILAR_KANJI_GROUPS:
            if char in group:
                # Add other kanji from same group
                for k in group:
                    if k != char and k not in target_kanji and k not in similar:
                        similar.append(k)
    
    if len(similar) >= count:
        return random.sample(similar, count)
    return similar


def get_fake_answers_kanji(correct_entry: VocabEntry, all_entries: List[VocabEntry], count: int = 3) -> List[tuple]:
    """Get fake kanji answers, preferring visually similar kanji."""
    pool = get_fake_kanji_pool()
    correct_kanji = correct_entry.kanji
    kanji_count = count_kanji(correct_kanji)
    
    # First, try to find similar-looking kanji
    similar = get_similar_kanji(correct_kanji, count)
    
    # Then fill with kanji of similar length from pool
    result = [(k, '') for k in similar]
    
    # Add more from pool, preferring similar kanji count
    available = [(k, m) for k, m in pool if k != correct_kanji and k not in similar]
    
    # Sort by kanji count similarity
    available.sort(key=lambda x: (abs(count_kanji(x[0]) - kanji_count), random.random()))
    
    for item in available:
        if len(result) >= count:
            break
        result.append(item)
    
    random.shuffle(result)
    return result[:count]


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
    correct_length = len(correct_kanji)
    
    fake_options = []
    
    # 1. Add shuffled version as decoy (if multiple characters)
    if correct_length >= 2:
        chars = list(correct_kanji)
        # Try up to 5 times to get a different order
        for _ in range(5):
            random.shuffle(chars)
            shuffled = ''.join(chars)
            if shuffled != correct_kanji and shuffled not in fake_options:
                fake_options.append(shuffled)
                break
    
    # 2. Get kanji from study list with same character count
    same_length_entries = [e for e in all_entries 
                          if e.kanji != correct_kanji 
                          and len(e.kanji) == correct_length
                          and e.kanji not in fake_options]
    random.shuffle(same_length_entries)
    for e in same_length_entries:
        if len(fake_options) >= 3:
            break
        fake_options.append(e.kanji)
    
    # 3. Get similar-looking kanji with same length from pool
    if len(fake_options) < 3:
        pool = get_fake_kanji_pool()
        same_length_pool = [(k, m) for k, m in pool 
                           if len(k) == correct_length 
                           and k != correct_kanji 
                           and k not in fake_options]
        
        # Prefer similar kanji
        similar = get_similar_kanji(correct_kanji, 3)
        for s in similar:
            if len(s) == correct_length and s not in fake_options and s != correct_kanji:
                fake_options.append(s)
                if len(fake_options) >= 3:
                    break
        
        # Fill from pool
        random.shuffle(same_length_pool)
        for k, m in same_length_pool:
            if len(fake_options) >= 3:
                break
            fake_options.append(k)
    
    # 4. If still not enough (rare), use any length but prefer similar
    if len(fake_options) < 3:
        other_fake = get_fake_answers_kanji(entry, all_entries, 3 - len(fake_options))
        for k, m in other_fake:
            if k not in fake_options and k != correct_kanji:
                fake_options.append(k)
    
    # Build final options
    options = [correct_kanji] + fake_options[:3]
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
    kanji_count = count_kanji(entry.kanji)
    
    # Get fake readings that are similar in complexity
    fake_readings = get_similar_readings(correct_reading, all_entries, 3)
    
    # If not enough similar readings, fall back to any readings but filter by kanji count
    if len(fake_readings) < 3:
        other_entries = [e for e in all_entries 
                        if e.reading != correct_reading 
                        and e.reading not in fake_readings
                        # Prefer entries with similar kanji count
                        and abs(count_kanji(e.kanji) - kanji_count) <= 1]
        
        needed = 3 - len(fake_readings)
        if len(other_entries) >= needed:
            fake_readings.extend([e.reading for e in random.sample(other_entries, needed)])
        else:
            # Last resort: any readings
            remaining = [e for e in all_entries if e.reading != correct_reading and e.reading not in fake_readings]
            fake_readings.extend([e.reading for e in random.sample(remaining, min(needed, len(remaining)))])
    
    options = [correct_reading] + fake_readings[:3]
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
    kanji_count = count_kanji(correct_kanji)
    
    # First try to get similar-looking kanji
    similar = get_similar_kanji(correct_kanji, 2)
    fake_kanjis = similar.copy()
    
    # Then add kanji from study list with similar length
    other_entries = [e for e in all_entries 
                    if e.kanji != correct_kanji 
                    and e.kanji not in fake_kanjis
                    and abs(count_kanji(e.kanji) - kanji_count) <= 1]
    
    needed = 3 - len(fake_kanjis)
    if len(other_entries) >= needed:
        fake_kanjis.extend([e.kanji for e in random.sample(other_entries, needed)])
    else:
        # Add any from study list
        remaining = [e for e in all_entries if e.kanji != correct_kanji and e.kanji not in fake_kanjis]
        if remaining:
            fake_kanjis.extend([e.kanji for e in random.sample(remaining, min(needed, len(remaining)))])
    
    # If still not enough, use external pool
    if len(fake_kanjis) < 3:
        pool = get_fake_kanji_pool()
        available = [k for k, m in pool if k not in fake_kanjis and k != correct_kanji]
        # Prefer similar kanji count
        available.sort(key=lambda k: (abs(count_kanji(k) - kanji_count), random.random()))
        fake_kanjis.extend(available[:3 - len(fake_kanjis)])
    
    options = [correct_kanji] + fake_kanjis[:3]
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


def generate_scramble_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a Duolingo-style scramble question: arrange characters to form the word."""
    correct_word = entry.kanji
    characters = list(correct_word)
    
    # Calculate how many distractors to add (at least 3x the word length)
    word_length = len(characters)
    num_distractors = max(8, word_length * 3)  # At least 3x more fake options
    
    # Add distractor characters (similar-looking kanji first)
    distractors = []
    similar = get_similar_kanji(correct_word, num_distractors)
    for s in similar:
        if len(s) == 1 and s not in characters and s not in distractors:
            distractors.append(s)
    
    # Add kanji from other entries in the study list
    shuffled_entries = list(all_entries)
    random.shuffle(shuffled_entries)
    for other in shuffled_entries:
        if other.kanji != correct_word:
            for c in other.kanji:
                if c not in characters and c not in distractors and '\u4e00' <= c <= '\u9fff':
                    distractors.append(c)
                    if len(distractors) >= num_distractors:
                        break
        if len(distractors) >= num_distractors:
            break
    
    # If still not enough, add random single kanji from pool
    if len(distractors) < num_distractors:
        pool = get_fake_kanji_pool()
        random.shuffle(pool)
        for k, m in pool:
            if len(k) == 1 and k not in characters and k not in distractors:
                distractors.append(k)
                if len(distractors) >= num_distractors:
                    break
    
    # Combine and shuffle
    all_chars = characters + distractors[:num_distractors]
    random.shuffle(all_chars)
    
    return {
        'type': 'scramble',
        'question': f'Ułóż słowo oznaczające: „{entry.meanings[0]}"',
        'question_en': f'Arrange characters to form: "{entry.meanings[0]}"',
        'options': all_chars,  # Scrambled characters
        'correct': correct_word,  # The correct word to form
        'correct_answer': correct_word,
        'hint': entry.reading,  # Reading as hint
        'entry': entry
    }


def generate_reading_scramble_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a scramble question: arrange kana to form the reading of a kanji compound."""
    correct_reading = entry.reading
    
    # Remove dots and spaces from reading for the answer
    clean_reading = correct_reading.replace('・', '').replace(' ', '').replace('、', '').replace(',', '')
    
    # Break down the reading into individual kana characters
    correct_chars = list(clean_reading)
    
    # Calculate how many distractors to add (at least 3x the reading length)
    reading_length = len(correct_chars)
    num_distractors = max(8, reading_length * 2)
    
    # Common hiragana and katakana for distractors
    hiragana = list('あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ')
    katakana = list('アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポ')
    
    # Determine if the reading is mainly katakana or hiragana
    katakana_count = sum(1 for c in clean_reading if c in katakana)
    hiragana_count = sum(1 for c in clean_reading if c in hiragana)
    
    # Use the same type of kana for distractors
    if katakana_count > hiragana_count:
        kana_pool = katakana
    else:
        kana_pool = hiragana
    
    # Generate distractors
    distractors = []
    
    # First, get kana from other entries' readings
    shuffled_entries = list(all_entries)
    random.shuffle(shuffled_entries)
    for other in shuffled_entries:
        if other.reading != correct_reading:
            other_clean = other.reading.replace('・', '').replace(' ', '').replace('、', '').replace(',', '')
            for c in other_clean:
                if c not in correct_chars and c not in distractors and c in kana_pool:
                    distractors.append(c)
                    if len(distractors) >= num_distractors:
                        break
        if len(distractors) >= num_distractors:
            break
    
    # If still not enough, add random kana
    if len(distractors) < num_distractors:
        random.shuffle(kana_pool)
        for k in kana_pool:
            if k not in correct_chars and k not in distractors:
                distractors.append(k)
                if len(distractors) >= num_distractors:
                    break
    
    # Combine and shuffle all tiles
    all_chars = correct_chars + distractors[:num_distractors]
    random.shuffle(all_chars)
    
    return {
        'type': 'reading_scramble',
        'question': f'Ułóż czytanie dla: 【{entry.kanji}】',
        'question_en': f'Arrange kana to form the reading of: 【{entry.kanji}】',
        'options': all_chars,  # Scrambled kana
        'correct': clean_reading,  # The correct reading
        'correct_answer': clean_reading,
        'hint': entry.meanings[0],  # Meaning as hint
        'entry': entry
    }


def get_kanji_position_name(kanji_word: str, target_kanji: str) -> str:
    """Get the position name of a kanji in a word (pierwsze, drugie, etc.)"""
    position_names = ['pierwsze', 'drugie', 'trzecie', 'czwarte', 'piąte']
    position_names_en = ['first', 'second', 'third', 'fourth', 'fifth']
    
    # Find position of target kanji
    kanji_positions = []
    for i, c in enumerate(kanji_word):
        if '\u4e00' <= c <= '\u9fff':  # Is kanji
            kanji_positions.append((i, c))
    
    for pos, (idx, k) in enumerate(kanji_positions):
        if k == target_kanji:
            if pos < len(position_names):
                return position_names[pos], position_names_en[pos]
            return f'{pos+1}.', f'{pos+1}.'
    
    return 'pierwsze', 'first'


def generate_draw_kanji_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a drawing quiz question: Write the kanji for this meaning."""
    # Get the first kanji character
    target_kanji = None
    for c in entry.kanji:
        if '\u4e00' <= c <= '\u9fff':  # Is kanji
            target_kanji = c
            break
    
    if not target_kanji:
        target_kanji = entry.kanji[0]
    
    # Count kanji in word
    kanji_count = sum(1 for c in entry.kanji if '\u4e00' <= c <= '\u9fff')
    
    # Build question text
    if kanji_count == 1:
        # Single kanji - meaning applies directly
        question_text = f'Zapisz kanji oznaczające: „{entry.meanings[0]}"'
        question_en = f'Write the kanji meaning: "{entry.meanings[0]}"'
    else:
        # Kanji from compound - show position and meaning only
        pos_pl, pos_en = get_kanji_position_name(entry.kanji, target_kanji)
        question_text = f'Zapisz {pos_pl} kanji ze słowa „{entry.meanings[0]}"'
        question_en = f'Write the {pos_en} kanji from "{entry.meanings[0]}"'
    
    return {
        'type': 'draw_kanji',
        'question': question_text,
        'question_en': question_en,
        'options': [],  # No options for drawing
        'correct': target_kanji,
        'correct_answer': target_kanji,
        'hint': f'{entry.kanji} ({entry.reading})',
        'entry': entry
    }


def generate_stroke_order_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a stroke order quiz: Write kanji with correct stroke order (3 attempts)."""
    # Get the first kanji character
    target_kanji = None
    for c in entry.kanji:
        if '\u4e00' <= c <= '\u9fff':  # Is kanji
            target_kanji = c
            break
    
    if not target_kanji:
        target_kanji = entry.kanji[0]
    
    # Count kanji in word
    kanji_count = sum(1 for c in entry.kanji if '\u4e00' <= c <= '\u9fff')
    
    # Build question text
    if kanji_count == 1:
        # Single kanji - meaning applies directly
        question_text = f'Zapisz kanji „{entry.meanings[0]}" w poprawnej kolejności kresek'
        question_en = f'Write "{entry.meanings[0]}" with correct stroke order'
    else:
        # Kanji from compound - show position and meaning only
        pos_pl, pos_en = get_kanji_position_name(entry.kanji, target_kanji)
        question_text = f'Zapisz {pos_pl} kanji ze słowa „{entry.meanings[0]}" (poprawna kolejność kresek)'
        question_en = f'Write the {pos_en} kanji from "{entry.meanings[0]}" (correct stroke order)'
    
    return {
        'type': 'stroke_order',
        'question': question_text,
        'question_en': question_en,
        'options': [],  # No options
        'correct': target_kanji,
        'correct_answer': target_kanji,
        'hint': f'{entry.kanji} ({entry.reading})',
        'entry': entry
    }


def split_readings(reading_str: str) -> List[str]:
    """Split a reading string into individual readings."""
    # Replace Japanese comma with regular comma, then split
    normalized = reading_str.replace('、', ',')
    parts = normalized.split(',')
    # Clean up each part (strip whitespace)
    return [p.strip() for p in parts if p.strip()]


def generate_bomb_defuse_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a bomb defuse game: Match kanji+meaning with readings!"""
    # Select 2-5 pairs randomly
    max_pairs = min(5, len(all_entries))
    num_pairs = random.randint(2, max_pairs)
    
    # Calculate time: 2 seconds per pair + 4 bonus seconds
    time_limit = num_pairs * 2 + 4
    
    # Always include the main entry
    selected_entries = [entry]
    
    # Add more random entries
    other_entries = [e for e in all_entries if e.kanji != entry.kanji]
    random.shuffle(other_entries)
    
    for e in other_entries:
        if len(selected_entries) >= num_pairs:
            break
        # Prefer entries with different readings
        if e.reading not in [s.reading for s in selected_entries]:
            selected_entries.append(e)
    
    # Build pairs with kanji, meaning, and reading
    pairs = []
    readings = []
    for i, e in enumerate(selected_entries):
        pairs.append({
            'kanji': e.kanji,
            'meaning': e.meanings[0] if e.meanings else '',
            'reading': e.reading,
            'readingIdx': i  # Will be updated after shuffle
        })
        readings.append(e.reading)
    
    # Shuffle readings and update indices
    shuffled_readings = readings.copy()
    random.shuffle(shuffled_readings)
    
    # Update readingIdx to match shuffled position
    for pair in pairs:
        pair['readingIdx'] = shuffled_readings.index(pair['reading'])
    
    return {
        'type': 'bomb_defuse',
        'question': f'Rozbrój bombę! Połącz {num_pairs} par w {time_limit} sekund!',
        'question_en': f'Defuse the bomb! Match {num_pairs} pairs in {time_limit} seconds!',
        'options': [],
        'correct': 0,  # Not used directly
        'correct_answer': entry.kanji,
        'bomb_pairs': pairs,
        'bomb_readings': shuffled_readings,
        'bomb_time': time_limit,
        'entry': entry
    }


def generate_runner_game_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a runner game: Escape from gorilla by choosing correct translations!"""
    
    # Get number of checkpoints (3-5)
    num_checkpoints = random.randint(3, 5)
    
    # Always include the main entry
    selected_entries = [entry]
    
    # Add more random entries with different kanji lengths
    other_entries = [e for e in all_entries if e.kanji != entry.kanji]
    random.shuffle(other_entries)
    
    for e in other_entries:
        if len(selected_entries) >= num_checkpoints:
            break
        # Avoid entries with same kanji
        if e.kanji not in [s.kanji for s in selected_entries]:
            selected_entries.append(e)
    
    # Fill remaining with duplicates if necessary
    while len(selected_entries) < num_checkpoints:
        selected_entries.append(random.choice(other_entries))
    
    random.shuffle(selected_entries)
    
    # Build checkpoints with Polish question and 3 Japanese options
    checkpoints = []
    for e in selected_entries:
        meaning = e.meanings[0] if e.meanings else 'słowo'
        correct_kanji = e.kanji
        
        # Generate 2 fake options with same length
        fake_answers = get_fake_answers_kanji(e, all_entries, 2)
        fake_options = [f[0] for f in fake_answers]  # Extract just the kanji strings
        
        # Add distractor: reversed kanji if length > 1
        if len(correct_kanji) > 1:
            reversed_kanji = correct_kanji[::-1]
            if reversed_kanji != correct_kanji and reversed_kanji not in fake_options:
                fake_options[0] = reversed_kanji
        
        # Combine and shuffle options
        all_options = [correct_kanji] + fake_options
        random.shuffle(all_options)
        correct_idx = all_options.index(correct_kanji)
        
        checkpoints.append({
            'meaning': meaning,
            'options': all_options,
            'correct': correct_idx,
            'correctKanji': correct_kanji
        })
    
    # Calculate time: 3 seconds per checkpoint + 5 bonus seconds
    time_limit = num_checkpoints * 3 + 5
    
    return {
        'type': 'runner_game',
        'question': f'Uciekaj! Wybierz {num_checkpoints}x poprawne tłumaczenie w {time_limit} sekund!',
        'question_en': f'Run away! Choose {num_checkpoints}x correct translation in {time_limit} seconds!',
        'options': [],
        'correct': 0,
        'correct_answer': entry.kanji,
        'runner_checkpoints': checkpoints,
        'runner_time': time_limit,
        'entry': entry
    }


def generate_all_readings_question(entry: VocabEntry, all_entries: List[VocabEntry]) -> dict:
    """Generate a multi-select question: Select all valid readings for this kanji."""
    # Get the main kanji character (first kanji in compound, or the whole if single)
    target_kanji = None
    for c in entry.kanji:
        if '\u4e00' <= c <= '\u9fff':  # Is kanji
            target_kanji = c
            break
    
    if not target_kanji:
        target_kanji = entry.kanji[0]
    
    # Find all entries that contain this kanji and collect individual readings
    correct_readings = set()
    for e in all_entries:
        if target_kanji in e.kanji:
            # Split readings by comma and add each one
            for reading in split_readings(e.reading):
                correct_readings.add(reading)
    
    # If only one reading found, add the current entry's readings
    if len(correct_readings) < 2:
        for reading in split_readings(entry.reading):
            correct_readings.add(reading)
    
    correct_readings = list(correct_readings)[:6]  # Max 6 correct readings
    
    # Generate fake readings (at least 2x the correct ones)
    num_fake = max(8, len(correct_readings) * 2)
    fake_readings = []
    
    # Get individual readings from entries that DON'T contain this kanji
    other_entries = [e for e in all_entries if target_kanji not in e.kanji]
    random.shuffle(other_entries)
    
    for e in other_entries:
        for reading in split_readings(e.reading):
            if reading not in correct_readings and reading not in fake_readings:
                fake_readings.append(reading)
                if len(fake_readings) >= num_fake:
                    break
        if len(fake_readings) >= num_fake:
            break
    
    # Combine and shuffle all options
    all_options = correct_readings + fake_readings[:num_fake]
    random.shuffle(all_options)
    
    # Find indices of correct answers
    correct_indices = [all_options.index(r) for r in correct_readings]
    
    return {
        'type': 'all_readings',
        'question': f'Zaznacz wszystkie czytania dla kanji: 【{target_kanji}】',
        'question_en': f'Select all readings for kanji: 【{target_kanji}】',
        'options': all_options,
        'correct_indices': correct_indices,  # Multiple correct answers
        'correct_answer': ', '.join(correct_readings),
        'entry': entry
    }


def generate_test(entries: List[VocabEntry], num_questions: int = 20, 
                  question_types: List[str] = None) -> List[dict]:
    """Generate a complete test with mixed question types."""
    if question_types is None:
        question_types = ['kanji_to_polish', 'polish_to_kanji', 'reading', 'reading_to_kanji', 'kanji_compound', 'scramble', 'reading_scramble', 'all_readings', 'draw_kanji', 'stroke_order', 'bomb_defuse', 'runner_game']
    
    questions = []
    selected_entries = random.sample(entries, min(num_questions, len(entries)))
    
    generators = {
        'kanji_to_polish': generate_kanji_to_polish_question,
        'polish_to_kanji': generate_polish_to_kanji_question,
        'reading': generate_reading_question,
        'reading_to_kanji': generate_reading_to_kanji_question,
        'kanji_compound': generate_kanji_compound_question,
        'scramble': generate_scramble_question,
        'reading_scramble': generate_reading_scramble_question,
        'all_readings': generate_all_readings_question,
        'draw_kanji': generate_draw_kanji_question,
        'stroke_order': generate_stroke_order_question,
        'bomb_defuse': generate_bomb_defuse_question,
        'runner_game': generate_runner_game_question,
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
        
        q_data = {
            'id': i,
            'question': html.escape(q['question']),
            'options': escaped_options,
            'type': q['type'],
            'kanji': entry.kanji,
            'reading': entry.reading,
            'meaning': entry.meanings[0] if entry.meanings else '',
            'jishoUrl': f"https://jisho.org/search/{entry.kanji}"
        }
        
        # Handle different question types
        if q['type'] == 'all_readings':
            q_data['correct_indices'] = q['correct_indices']
        elif q['type'] == 'scramble':
            q_data['correct'] = q['correct']
            q_data['hint'] = q.get('hint', entry.reading)
        elif q['type'] == 'bomb_defuse':
            q_data['bomb_pairs'] = q['bomb_pairs']
            q_data['bomb_readings'] = q['bomb_readings']
            q_data['bomb_time'] = q.get('bomb_time', 15)
        elif q['type'] == 'runner_game':
            q_data['runner_checkpoints'] = q['runner_checkpoints']
            q_data['runner_time'] = q.get('runner_time', 20)
        else:
            q_data['correct'] = q.get('correct', 0)
        
        questions_js.append(q_data)
    
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
                       choices=['kanji_to_polish', 'polish_to_kanji', 'reading', 'reading_to_kanji', 'kanji_compound', 'scramble', 'reading_scramble', 'all_readings', 'draw_kanji', 'stroke_order', 'bomb_defuse', 'runner_game'],
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

