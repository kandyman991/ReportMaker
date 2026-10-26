# ADR-0002 — ChatGPT as an ordinary browser website
Status: Accepted with Windows validation pending | Date: 2026-10-26

Decision: A resizable Qt WebEngine website panel can display https://chatgpt.com, with persistent profile best effort. Provide an explicit default-browser fallback. Transfer text to the editor only through user-initiated manual copy/paste.

Forbidden: OpenAI API/SDK integration, purchased tokens, agent automation, DOM/code injection, interception of ChatGPT messages, cookie export, credential storage outside the browser engine, fabricated login compatibility or auth workaround.

Security boundary: Treat pasted text as untrusted, insert plain text. Qt WebEngine stores normal browser cookies/cache only in user-local app data. Avoid logging URLs containing query secrets. The site may refuse embedded authentication; respect that result and use fallback. Browser profile must not be bundled with report exports.

Validation: M0 acceptance checklist includes real Windows account-login attempt by the user, URL/domain observation, persistent-session behavior if allowed, and fallback. No real account credentials in automated tests.
