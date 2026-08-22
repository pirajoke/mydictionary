# Locked specification: versioned AI prompt contracts

Date: 2026-08-22

## Outcome

The reviewed system instructions used by AI Tutor and Mirror are versioned as
plain-text repository artifacts and loaded by the runtime. Code and the prompt
library cannot silently diverge.

## Acceptance criteria

- **AC-1:** AI Tutor runtime instructions are loaded from
  `prompts/ai-tutor-v1.txt` and exactly match that reviewed file after only a
  trailing newline is normalized.
- **AC-2:** Mirror runtime instructions are loaded from
  `prompts/mirror-v2.txt` and exactly match that reviewed file after only a
  trailing newline is normalized.
- **AC-3:** `prompts/README.md` identifies each runtime contract, its version,
  code consumer, evaluation surface, and change procedure.
- **EC-1:** A reviewed prompt file may contain Unicode and multiline text
  without semantic rewriting by the loader.
- **ERR-1:** A missing, non-regular, symlinked, invalid UTF-8, or blank prompt
  contract fails closed during runtime import with a non-secret configuration
  error.

## Constraints

- No new dependency.
- Provider requests, feature flags, credits, schemas, user data, and production
  credentials are unchanged.
- Existing instruction text is moved without changing its meaning.
- Mutable Mirror administrator guidance and response schemas remain in code;
  renaming historical `*_ru` response fields is out of scope.

## Verification mapping

- AC-1, AC-2, EC-1, ERR-1: `tests/test_prompt_contracts.py`.
- AC-3: repository documentation check in the same test module.
