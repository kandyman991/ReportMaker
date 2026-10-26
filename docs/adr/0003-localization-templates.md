# ADR-0003 — Open-ended languages and independent templates
Status: Accepted | Date: 2026-10-26

Decision: Language tags are dynamic strings (BCP-47 style), not a fixed list. Report text, module titles, captions and table text can each hold original and per-locale variants. The UI language is separate. Export supports one language, multiple separate files, or bilingual/multilingual layouts.

Templates/Word import remain separate from logical content. Imported Word files may contain floating shapes; support high-fidelity fill mode and explicitly report what cannot become an editable native block.

Tradeoff: More up-front model work and export tests in return for long-term extensibility.
