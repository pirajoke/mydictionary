#!/usr/bin/env python3
"""Generate example sentences for words.json using Claude API."""

import json
import yaml
import anthropic
from pathlib import Path

BASE_DIR = Path(__file__).parent
WORDS_FILE = BASE_DIR / "words.json"
BATCH_SIZE = 50  # words per API call

# Load API key from tg-bot config
TG_CONFIG = yaml.safe_load(open(Path.home() / "tg-bot" / "config_bot.yaml"))
API_KEY = TG_CONFIG["anthropic"]["api_key"]


def load_words():
    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_words(words):
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)


def generate_batch(client, batch):
    """Generate example sentences for a batch of words."""
    word_list = "\n".join(f"{i+1}. {w['en']}" for i, w in enumerate(batch))

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                "Generate a short, natural English example sentence for each word below. "
                "The sentence should clearly demonstrate the word's meaning. "
                "Keep sentences 5-12 words. Return ONLY a JSON array of strings, one per word, same order.\n\n"
                f"{word_list}"
            ),
        }],
    )

    text = resp.content[0].text.strip()
    # Extract JSON array from response
    start = text.index("[")
    end = text.rindex("]") + 1
    return json.loads(text[start:end])


def main():
    words = load_words()
    client = anthropic.Anthropic(api_key=API_KEY)

    # Only process words without examples
    indices = [i for i, w in enumerate(words) if not w.get("example")]
    print(f"Need examples for {len(indices)} / {len(words)} words")

    for batch_start in range(0, len(indices), BATCH_SIZE):
        batch_indices = indices[batch_start:batch_start + BATCH_SIZE]
        batch_words = [words[i] for i in batch_indices]

        print(f"Generating {batch_start + 1}-{batch_start + len(batch_indices)}...")
        try:
            examples = generate_batch(client, batch_words)
            for idx, example in zip(batch_indices, examples):
                words[idx]["example"] = example
            save_words(words)  # Save after each batch
            print(f"  Saved {len(examples)} examples")
        except Exception as e:
            print(f"  Error: {e}")
            continue

    print("Done!")


if __name__ == "__main__":
    main()
