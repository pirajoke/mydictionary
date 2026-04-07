#!/usr/bin/env python3
"""Audit word translations using Claude API. Finds wrong/inaccurate translations."""

import json
import yaml
import anthropic
from pathlib import Path

BASE_DIR = Path(__file__).parent
WORDS_FILE = BASE_DIR / "words.json"
BATCH_SIZE = 80

TG_CONFIG = yaml.safe_load(open(Path.home() / "tg-bot" / "config_bot.yaml"))
API_KEY = TG_CONFIG["anthropic"]["api_key"]


def load_words():
    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def audit_batch(client, batch, start_idx):
    """Check translations for a batch of words. Returns list of issues."""
    lines = []
    for i, w in enumerate(batch):
        lines.append(f"{start_idx + i}. {w['en']} → {w['ru']}")
    word_list = "\n".join(lines)

    resp = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                "You are auditing an English-Russian vocabulary list for a learning app.\n"
                "Check each translation below. For EACH word, decide:\n"
                "- OK: translation is correct and natural\n"
                "- FIX: translation is wrong, inaccurate, unnatural, or has typos\n\n"
                "Rules:\n"
                "- Russian translations should be in dictionary form (infinitive for verbs, nominative for nouns)\n"
                "- Full sentences as 'words' are bad entries — mark as REMOVE\n"
                "- Typos in Russian count as FIX\n"
                "- Genitive/plural forms instead of base form count as FIX\n"
                "- If a word has multiple valid translations, the given one should be the most common\n\n"
                "Return ONLY a JSON array. Each element:\n"
                '{"idx": <number>, "status": "OK"|"FIX"|"REMOVE", "ru_fix": "<corrected translation or null>", "reason": "<short reason or null>"}\n\n'
                "Only include FIX and REMOVE entries (skip OK ones to save space).\n"
                "If all are OK, return []\n\n"
                f"{word_list}"
            ),
        }],
    )

    text = resp.content[0].text.strip()
    start = text.index("[")
    end = text.rindex("]") + 1
    return json.loads(text[start:end])


def main():
    words = load_words()
    client = anthropic.Anthropic(api_key=API_KEY)

    all_issues = []
    for batch_start in range(0, len(words), BATCH_SIZE):
        batch = words[batch_start:batch_start + BATCH_SIZE]
        print(f"Auditing {batch_start + 1}-{batch_start + len(batch)}...")
        try:
            issues = audit_batch(client, batch, batch_start)
            all_issues.extend(issues)
            if issues:
                for iss in issues:
                    print(f"  [{iss['idx']}] {iss['status']}: {words[iss['idx']]['en']} → {words[iss['idx']]['ru']}")
                    if iss.get('ru_fix'):
                        print(f"         FIX → {iss['ru_fix']} ({iss.get('reason', '')})")
        except Exception as e:
            print(f"  Error: {e}")

    # Save audit report
    with open(BASE_DIR / "audit_report.json", "w", encoding="utf-8") as f:
        json.dump(all_issues, f, ensure_ascii=False, indent=2)

    print(f"\nTotal issues: {len(all_issues)}")
    fixes = [i for i in all_issues if i["status"] == "FIX"]
    removes = [i for i in all_issues if i["status"] == "REMOVE"]
    print(f"  FIX: {len(fixes)}")
    print(f"  REMOVE: {len(removes)}")
    print(f"Report saved to audit_report.json")


if __name__ == "__main__":
    main()
