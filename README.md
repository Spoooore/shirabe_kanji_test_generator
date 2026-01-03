# 漢字テスト Generator

Generate interactive kanji tests from ShirabeJisho `.shirabe` bookmark files.

## Features

- 📝 **5 question types:**
  - Kanji → Polish translation
  - Polish → Kanji translation
  - Reading selection (choose correct reading)
  - Reading → Kanji matching
  - Kanji compound meaning

- 🌐 **Jisho API integration** - fetches additional kanji for fake answers
- 📱 **Mobile-friendly** - works on iPad/Safari
- 📊 **Results summary** with mistakes list and Jisho links
- 📋 **Copy mistakes** to clipboard for review

## Usage

### List available files
```bash
python3 generate_tests.py --list-files
```

### Generate test from all files
```bash
python3 generate_tests.py -n 30 --title "My Test" -o my_test.html
```

### Generate test from specific ranges
```bash
python3 generate_tests.py -f 1411-1420 1431-1440 -n 20 -o test.html
```

### Options

| Flag | Description |
|------|-------------|
| `-f, --files` | Specific file ranges to include |
| `-n, --num-questions` | Number of questions (default: 20) |
| `-o, --output` | Output HTML filename (default: test.html) |
| `-t, --types` | Question types to include |
| `--title` | Test title |
| `--list-files` | Show available .shirabe files |
| `--refresh-kanji` | Force refresh kanji cache from Jisho API |
| `--offline` | Use only cached kanji (no API calls) |
| `-c, --console` | Print test to console |

### Question types

- `kanji_to_polish` - Show kanji, pick Polish meaning
- `polish_to_kanji` - Show Polish, pick kanji
- `reading` - Show kanji, pick correct reading
- `reading_to_kanji` - Show reading, pick which kanji has it
- `kanji_compound` - Show kanji with reading hint, pick meaning

## Files

- `generate_tests.py` - Main script
- `template.html` - HTML template for tests
- `*.shirabe` - ShirabeJisho bookmark files (your vocabulary)

## Example

```bash
# Generate 25 questions from range 1441-1450
python3 generate_tests.py -f 1441-1450 -n 25 --title "Kanji Test 1441-1450" -o kanji_test.html
```

Then open `kanji_test.html` in any browser!

## Requirements

- Python 3.6+
- Internet connection (for Jisho API, first run only - results are cached)

## License

MIT

