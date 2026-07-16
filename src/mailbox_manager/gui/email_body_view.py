from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMenu, QVBoxLayout, QWidget
from shiboken6 import delete as delete_qobject

from mailbox_manager.mail.parser import clean_message_text, html_to_text
from mailbox_manager.mail.web_document import prepare_plain_web_document


class _EmailRequestFilter(QWebEngineUrlRequestInterceptor):
    """Allow email images while denying every other external resource."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.blocked_requests = 0
        self.allowed_image_requests = 0

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        scheme = info.requestUrl().scheme().casefold()
        if scheme in {"about", "data", "qrc"}:
            return
        if (
            scheme in {"http", "https"}
            and info.resourceType()
            == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeImage
        ):
            self.allowed_image_requests += 1
            return
        self.blocked_requests += 1
        info.block(True)


class _EmailPage(QWebEnginePage):
    externalLinkActivated = Signal(QUrl)

    def acceptNavigationRequest(
        self,
        url: QUrl,
        navigation_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        del is_main_frame
        if navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if url.scheme().casefold() in {"http", "https", "mailto"}:
                self.externalLinkActivated.emit(url)
            return False
        return url.scheme().casefold() in {"about", "data", "qrc"}

    def createWindow(self, window_type):
        del window_type
        return None


class _DocumentSnapshot:
    def __init__(self, owner: EmailBodyView) -> None:
        self._owner = owner

    def toHtml(self) -> str:
        return self._owner._html


class EmailBodyView(QWidget):
    """A browser-quality email body widget with image-only network access.

    The extracted HTML is rendered directly. Remote images may load like they do in a
    normal mail client, while JavaScript, storage, plugins, downloads, popups and every
    non-image browser request remain disabled. Links are surfaced to the owning window.
    """

    anchorClicked = Signal(QUrl)
    feedbackRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plain_text = ""
        self._placeholder = ""
        self._html = ""
        self._shutdown = False
        self._document_snapshot = _DocumentSnapshot(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._profile = QWebEngineProfile(self)
        self._profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )
        self._profile.setHttpUserAgent("MailDesk isolated email reader")
        self._request_filter = _EmailRequestFilter(self)
        self._profile.setUrlRequestInterceptor(self._request_filter)
        self._profile.downloadRequested.connect(lambda download: download.cancel())

        self._page = _EmailPage(self._profile, self)
        self._page.externalLinkActivated.connect(self.anchorClicked)
        self._configure_settings(self._page.settings())

        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._show_context_menu)
        self._view.setStyleSheet("background:#ffffff; border:0;")
        layout.addWidget(self._view)

    @staticmethod
    def _configure_settings(settings: QWebEngineSettings) -> None:
        disabled = (
            QWebEngineSettings.WebAttribute.AllowRunningInsecureContent,
            QWebEngineSettings.WebAttribute.AutoLoadIconsForPage,
            QWebEngineSettings.WebAttribute.DnsPrefetchEnabled,
            QWebEngineSettings.WebAttribute.FullScreenSupportEnabled,
            QWebEngineSettings.WebAttribute.HyperlinkAuditingEnabled,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.JavascriptCanPaste,
            QWebEngineSettings.WebAttribute.JavascriptEnabled,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            QWebEngineSettings.WebAttribute.LocalStorageEnabled,
            QWebEngineSettings.WebAttribute.NavigateOnDropEnabled,
            QWebEngineSettings.WebAttribute.PdfViewerEnabled,
            QWebEngineSettings.WebAttribute.PluginsEnabled,
            QWebEngineSettings.WebAttribute.ScreenCaptureEnabled,
            QWebEngineSettings.WebAttribute.WebGLEnabled,
        )
        for attribute in disabled:
            settings.setAttribute(attribute, False)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            True,
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, True)

    @property
    def blocked_request_count(self) -> int:
        return self._request_filter.blocked_requests

    @property
    def allowed_image_request_count(self) -> int:
        return self._request_filter.allowed_image_requests

    def setHtml(self, html: str) -> None:
        self._html = html
        self._plain_text = clean_message_text(html_to_text(html))
        self._view.setHtml(html, QUrl("about:blank"))

    def setPlainText(self, text: str) -> None:
        self._plain_text = clean_message_text(text)
        visible = self._plain_text or self._placeholder
        self._html = prepare_plain_web_document(visible)
        self._view.setHtml(self._html, QUrl("about:blank"))

    def setPlaceholderText(self, text: str) -> None:
        self._placeholder = text

    def toPlainText(self) -> str:
        return self._plain_text

    def document(self) -> _DocumentSnapshot:
        return self._document_snapshot

    def clear(self) -> None:
        self._plain_text = ""
        self._html = prepare_plain_web_document(self._placeholder)
        self._view.setHtml(self._html, QUrl("about:blank"))

    def copy(self) -> None:
        self._page.triggerAction(QWebEnginePage.WebAction.Copy)

    def selectAll(self) -> None:
        self._page.triggerAction(QWebEnginePage.WebAction.SelectAll)

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        self._view.stop()
        # Explicit destruction keeps QtWebEngine helper processes from lingering after
        # the owning reader closes. The order is important: view -> page -> profile.
        delete_qobject(self._view)
        delete_qobject(self._page)
        delete_qobject(self._profile)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)

    def _show_context_menu(self, position: QPoint) -> None:
        request = self._view.lastContextMenuRequest()
        menu = QMenu(self)
        link = request.linkUrl()
        is_link = link.scheme().casefold() in {"http", "https", "mailto"}
        copy_link = menu.addAction("复制链接")
        copy_link.setEnabled(is_link)
        open_link = menu.addAction("打开链接")
        open_link.setEnabled(is_link)
        menu.addSeparator()
        copy_text = menu.addAction("复制选中文字")
        copy_text.setEnabled(bool(request.selectedText()))
        select_all = menu.addAction("全选正文")
        selected = menu.exec(self._view.mapToGlobal(position))
        if selected is copy_link:
            QApplication.clipboard().setText(link.toString())
            self.feedbackRequested.emit("链接已复制")
        elif selected is open_link:
            self.anchorClicked.emit(link)
        elif selected is copy_text:
            self.copy()
            self.feedbackRequested.emit("文字已复制")
        elif selected is select_all:
            self.selectAll()
