"""V2 ChatGPT tab: user-operated website only, with V1-compatible profile behavior.

No DOM access, scripting, web API, clipboard bridge or report data exchange.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

CHAT_URL = QUrl("https://chatgpt.com/")


class ChatTab(QWidget):
    def __init__(self, *, load_website: bool = True,
                 browser_profile_root: Path | None = None,
                 ephemeral_browser: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("v2ChatGPTTab")
        self.load_website = load_website
        self.browser_profile_root = browser_profile_root
        self.ephemeral_browser = ephemeral_browser
        self.browser = None
        self.profile = None
        self.browser_page = None
        layout = QVBoxLayout(self)
        self.info = QLabel(
            "ChatGPT website · manual copy/paste only. No automatic report transfer.")
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.external = QPushButton("Open ChatGPT in default browser")
        self.external.setObjectName("v2ExternalChatGPT")
        self.external.clicked.connect(lambda: QDesktopServices.openUrl(CHAT_URL))
        layout.addWidget(self.external)
        self.open_button = QPushButton("Open embedded ChatGPT")
        self.open_button.setObjectName("v2OpenEmbeddedChatGPT")
        self.open_button.clicked.connect(self.open_website)
        layout.addWidget(self.open_button)
        self.browser_status = QLabel("Website not loaded · login is user-controlled")
        layout.addWidget(self.browser_status)

    def activate(self):
        if self.load_website:
            self.open_website()

    def open_website(self):
        if self.browser is not None:
            return
        # Load only when the user opens this tab; synthetic Qt tests and normal
        # Branch editing must not start Chromium or create browser profile files.
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView

        if self.ephemeral_browser:
            profile = QWebEngineProfile(self)
        else:
            profile = QWebEngineProfile("reportmaker-chatgpt", self)
            root = self.browser_profile_root
            if root is None:
                root = Path(QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.AppLocalDataLocation)) / "browser"
            root.mkdir(parents=True, exist_ok=True)
            profile.setPersistentStoragePath(str(root / "storage"))
            profile.setCachePath(str(root / "cache"))
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        browser = QWebEngineView(self)
        browser.setMinimumSize(0, 0)
        page = QWebEnginePage(profile, browser)
        browser.setPage(page)
        self.profile, self.browser_page, self.browser = profile, page, browser
        self.layout().insertWidget(3, browser, 1)
        browser.loadFinished.connect(
            lambda ok: self.browser_status.setText(
                "Page loaded (login not validated)." if ok
                else "Page failed — use the external browser."))
        browser.urlChanged.connect(
            lambda url: self.info.setText(
                "ChatGPT website · manual copy/paste only · Origin: " +
                (f"{url.scheme()}://{url.host()}" if url.scheme() == "https"
                 else "WARNING — not an HTTPS origin")))
        self.open_button.hide()
        browser.setUrl(CHAT_URL)
