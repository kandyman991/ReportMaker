"""Offline, allowlisted origin for the privileged studio; never shared with ChatGPT."""
from collections import OrderedDict
from hashlib import sha256
from importlib.resources import files

from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile,
    QWebEngineSettings, QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestJob,
    QWebEngineUrlScheme, QWebEngineUrlSchemeHandler)

ORIGIN = "rmstudio://app/"
ENTRY = ORIGIN + "index.html"
scheme = QWebEngineUrlScheme(b"rmstudio")
scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort)
scheme.setDefaultPort(443)
scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
QWebEngineUrlScheme.registerScheme(scheme)


def trusted_url(url):
    return (url.scheme() == "rmstudio" and url.host() == "app"
            and url.port() in (-1, 443) and not url.userInfo()
            and not url.hasQuery() and not url.hasFragment())


class StudioRequests(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()
        # data is used only for internally generated PDF page PNGs; CSP limits it to images.
        info.block(not (trusted_url(url) or url.scheme() == "data"))


class StudioPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, main_frame):
        return main_frame and url.toString() == ENTRY and kind == self.NavigationType.NavigationTypeTyped

    def createWindow(self, kind):
        return None


class StudioResources(QWebEngineUrlSchemeHandler):
    """Thumbnails render on demand, with a bounded encoded-image LRU."""
    CACHE_LIMIT = 32 * 1024 * 1024

    def __init__(self, parent, html):
        super().__init__(parent)
        self.html = html.encode("utf-8")
        self.sources = {}
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.renders = 0
        self.digests = {}
        self.digest_computations = 0
        self._used_sources = set()
        self._used_digests = set()

    def clear_media(self):
        self.sources.clear()
        self.cache.clear()
        self.cache_bytes = 0
        self.digests.clear()

    def begin_projection(self):
        self._used_sources.clear()
        self._used_digests.clear()

    def end_projection(self):
        self.sources = {k: v for k, v in self.sources.items() if k in self._used_sources}
        self.digests = {k: v for k, v in self.digests.items() if k in self._used_digests}
        for key in list(self.cache):
            if key not in self.sources:
                self.cache_bytes -= len(self.cache.pop(key))

    def image_url(self, data, visual, edge):
        identity = id(data)
        self._used_digests.add(identity)
        cached = self.digests.get(identity)
        if cached is None or cached[0] is not data:
            cached = (data, sha256(data).digest())
            self.digests[identity] = cached
            self.digest_computations += 1
        key = sha256(cached[1] + repr((visual, edge)).encode()).hexdigest()
        self._used_sources.add(key)
        self.sources[key] = (data, visual, edge)
        return ORIGIN + "media/" + key

    def image_bytes(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        from ..photo_editor import render_photo
        data, visual, edge = self.sources[key]
        image = render_photo(data, visual, max_edge=edge)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        if image.isNull() or not image.save(buf, "PNG"):
            raise ValueError("Unable to render photo")
        result = bytes(buf.data())
        self.renders += 1
        while self.cache and self.cache_bytes + len(result) > self.CACHE_LIMIT:
            _, old = self.cache.popitem(last=False)
            self.cache_bytes -= len(old)
        if len(result) <= self.CACHE_LIMIT:
            self.cache[key] = result
            self.cache_bytes += len(result)
        return result

    def requestStarted(self, job):
        url = job.requestUrl()
        try:
            if not trusted_url(url) or bytes(job.requestMethod()) != b"GET":
                raise ValueError("Untrusted request")
            path = url.path()
            if path == "/index.html":
                mime, data = b"text/html", self.html
            elif path in ("/studio.css", "/studio.js", "/transport.js", "/events.js"):
                mime = b"text/css" if path.endswith(".css") else b"application/javascript"
                data = files("reportmaker.v2").joinpath("web_assets", path[1:]).read_bytes()
            elif path == "/qwebchannel.js":
                from .web_ui import _load_qwebchannel_js
                mime, data = b"application/javascript", _load_qwebchannel_js().encode()
            elif path.startswith("/media/"):
                mime, data = b"image/png", self.image_bytes(path[len("/media/"):])
            else:
                raise ValueError("Unknown resource")
            buffer = QBuffer(job)
            buffer.setData(data)
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            job.reply(mime, buffer)
        except Exception:
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)


def install_studio(view, html):
    profile = QWebEngineProfile()
    interceptor = StudioRequests(profile)
    profile.setUrlRequestInterceptor(interceptor)
    resources = StudioResources(profile, html)
    profile.installUrlSchemeHandler(b"rmstudio", resources)
    profile.downloadRequested.connect(lambda download: download.cancel())
    page = StudioPage(profile, view)
    # QWebEnginePage must release Chromium before its profile is destroyed.
    # QObject destroys children after the derived page destructor has run.
    profile.setParent(page)
    for flag in (QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
                 QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                 QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls):
        page.settings().setAttribute(flag, False)
    view.setPage(page)
    # Python references must outlive Chromium's asynchronous callbacks.
    view.studio_profile, view.studio_interceptor = profile, interceptor
    return resources
