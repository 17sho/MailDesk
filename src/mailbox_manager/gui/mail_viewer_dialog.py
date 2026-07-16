from __future__ import annotations

import base64
import re
from html import escape as html_escape
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.domain.models import EmailAccount, MailAttachment, MailMessage
from mailbox_manager.gui.email_body_view import EmailBodyView
from mailbox_manager.gui.workers import TranslationWorker
from mailbox_manager.mail.display import (
    MessageDisplayContent,
    select_stored_message_display_content,
)
from mailbox_manager.mail.parser import clean_message_text
from mailbox_manager.mail.web_document import prepare_email_web_document
from mailbox_manager.services.translation_service import (
    DEFAULT_TRANSLATION_LANGUAGE,
    TRANSLATION_LANGUAGES,
    TranslationError,
    TranslationService,
    translation_language_label,
)
from mailbox_manager.storage.repositories import MessageRepository


class MailViewerDialog(QDialog):
    fetchRequested = Signal(int)
    filterRequested = Signal()
    composeRequested = Signal(int)

    def __init__(
        self,
        account: EmailAccount,
        messages: list[MailMessage],
        *,
        dark: bool = False,
        selected_message_id: int | None = None,
        message_repository: MessageRepository | None = None,
        translation_service: TranslationService | None = None,
        translation_language: str = DEFAULT_TRANSLATION_LANGUAGE,
        translation_confirm: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mailViewerDialog")
        self.setWindowTitle(f"邮件阅读器 · {account.email}")
        self.resize(1320, 820)
        self.setMinimumSize(960, 620)
        self.setModal(False)
        self.account_id = account.account_id or 0
        self._account = account
        self._message_repository = message_repository
        self._translation_service = translation_service or TranslationService()
        self._translation_language = _valid_translation_language(translation_language)
        self._translation_confirm = bool(translation_confirm)
        self._messages: list[MailMessage] = []
        self._dark = dark
        self._pool = QThreadPool(self)
        self._translation_workers: dict[int, TranslationWorker] = {}
        self._render_generation = 0
        self._translation_generation = 0
        self._active_translation_generation: int | None = None
        self._current_message: MailMessage | None = None
        self._current_display_content: MessageDisplayContent | None = None
        self._translation_source_text = ""
        self._translated_text = ""
        self._showing_translation = False
        self._closed = False
        self._visible_attachments: tuple[MailAttachment, ...] = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        header.setObjectName("mailViewerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 13, 14, 13)
        title_copy = QVBoxLayout()
        title_copy.setSpacing(1)
        title = QLabel("邮件阅读器")
        title.setObjectName("mailViewerTitle")
        account_label = QLabel(account.email)
        account_label.setObjectName("sectionCaption")
        title_copy.addWidget(title)
        title_copy.addWidget(account_label)
        header_layout.addLayout(title_copy)
        header_layout.addStretch(1)
        self.fetch_button = QPushButton("立即取件")
        self.fetch_button.setObjectName("primaryButton")
        self.fetch_button.clicked.connect(lambda: self.fetchRequested.emit(self.account_id))
        header_layout.addWidget(self.fetch_button)
        compose_button = QPushButton("写邮件")
        compose_button.clicked.connect(
            lambda: self.composeRequested.emit(self.account_id)
        )
        header_layout.addWidget(compose_button)
        filter_button = QPushButton("筛选导出")
        filter_button.clicked.connect(self.filterRequested.emit)
        header_layout.addWidget(filter_button)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)
        header_layout.addWidget(close_button)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mailViewerSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(7)
        sidebar = QFrame()
        sidebar.setObjectName("mailViewerSidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 10, 12)
        sidebar_layout.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索当前邮箱的主题、发件人或正文…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._populate_lists)
        sidebar_layout.addWidget(self.search_input)
        self.folder_tabs = QTabWidget()
        self.folder_tabs.setObjectName("mailViewerFolders")
        self.inbox_list = self._new_message_list()
        self.special_list = self._new_message_list()
        self.folder_tabs.addTab(self.inbox_list, "收件箱")
        self.folder_tabs.addTab(self.special_list, "其他文件夹")
        sidebar_layout.addWidget(self.folder_tabs, 1)
        splitter.addWidget(sidebar)

        content = QFrame()
        content.setObjectName("mailViewerContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 14, 18, 16)
        content_layout.setSpacing(8)
        self.sender_label = QLabel("选择一封邮件")
        self.sender_label.setObjectName("mailViewerSender")
        self.sender_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.sender_address_label = QLabel()
        self.sender_address_label.setObjectName("mailViewerSenderAddress")
        self.sender_address_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.subject_label = QLabel()
        self.subject_label.setObjectName("mailViewerSubject")
        self.subject_label.setWordWrap(True)
        self.meta_label = QLabel()
        self.meta_label.setObjectName("sectionCaption")
        self.meta_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(self.sender_label)
        content_layout.addWidget(self.sender_address_label)
        content_layout.addWidget(self.subject_label)
        content_layout.addWidget(self.meta_label)
        self._build_translation_bar(content_layout)
        self._build_attachment_panel(content_layout)
        self.body = EmailBodyView()
        self.body.setObjectName("mailViewerBody")
        self.body.anchorClicked.connect(self._open_link)
        self.body.feedbackRequested.connect(self._show_feedback)
        content_layout.addWidget(self.body, 1)
        self.feedback_label = QLabel()
        self.feedback_label.setObjectName("mailViewerFeedback")
        self.feedback_label.hide()
        content_layout.addWidget(self.feedback_label)
        splitter.addWidget(content)
        splitter.setSizes([390, 930])
        root.addWidget(splitter, 1)

        self.set_messages(messages, selected_message_id=selected_message_id)

    def _build_translation_bar(self, layout: QVBoxLayout) -> None:
        self.translation_bar = QFrame()
        self.translation_bar.setObjectName("mailTranslationBar")
        translation_layout = QHBoxLayout(self.translation_bar)
        translation_layout.setContentsMargins(10, 6, 8, 6)
        translation_layout.setSpacing(8)
        self.translation_language_label = QLabel()
        self.translation_language_label.setObjectName("mailTranslationLanguage")
        translation_layout.addWidget(self.translation_language_label)
        translation_layout.addStretch(1)
        self.translation_toggle_button = QPushButton("查看原文")
        self.translation_toggle_button.setObjectName("translationToggleButton")
        self.translation_toggle_button.clicked.connect(self._toggle_translation_view)
        self.translation_toggle_button.hide()
        translation_layout.addWidget(self.translation_toggle_button)
        self.translate_button = QPushButton("翻译邮件")
        self.translate_button.setObjectName("translateMessageButton")
        self.translate_button.setToolTip(
            "仅发送当前邮件正文到翻译服务，不发送附件、账号密码或 Token"
        )
        self.translate_button.clicked.connect(self._translate_current_message)
        translation_layout.addWidget(self.translate_button)
        layout.addWidget(self.translation_bar)
        self._refresh_translation_controls()

    def _build_attachment_panel(self, layout: QVBoxLayout) -> None:
        self.attachment_panel = QFrame()
        self.attachment_panel.setObjectName("mailAttachmentPanel")
        panel_layout = QVBoxLayout(self.attachment_panel)
        panel_layout.setContentsMargins(12, 9, 12, 10)
        panel_layout.setSpacing(7)
        header = QHBoxLayout()
        self.attachment_title = QLabel("附件")
        self.attachment_title.setObjectName("mailAttachmentTitle")
        header.addWidget(self.attachment_title)
        header.addStretch(1)
        self.save_attachment_button = QPushButton("保存选中")
        self.save_attachment_button.setObjectName("attachmentActionButton")
        self.save_attachment_button.clicked.connect(self._save_selected_attachment)
        header.addWidget(self.save_attachment_button)
        self.save_all_attachments_button = QPushButton("全部保存")
        self.save_all_attachments_button.setObjectName("attachmentActionButton")
        self.save_all_attachments_button.clicked.connect(self._save_all_attachments)
        header.addWidget(self.save_all_attachments_button)
        panel_layout.addLayout(header)
        self.attachment_list = QListWidget()
        self.attachment_list.setObjectName("mailAttachmentList")
        self.attachment_list.setMaximumHeight(104)
        self.attachment_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.attachment_list.itemDoubleClicked.connect(
            lambda _item: self._save_selected_attachment()
        )
        panel_layout.addWidget(self.attachment_list)
        self.attachment_panel.hide()
        layout.addWidget(self.attachment_panel)

    def _new_message_list(self) -> QListWidget:
        widget = QListWidget()
        widget.setObjectName("mailReaderList")
        widget.setWordWrap(True)
        widget.setSpacing(3)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        widget.setTextElideMode(Qt.TextElideMode.ElideRight)
        widget.currentItemChanged.connect(self._message_changed)
        return widget

    def set_messages(
        self,
        messages: list[MailMessage],
        *,
        selected_message_id: int | None = None,
    ) -> None:
        self._messages = messages
        self._populate_lists()
        if selected_message_id is not None:
            for widget in (self.inbox_list, self.special_list):
                for row in range(widget.count()):
                    item = widget.item(row)
                    index = item.data(Qt.ItemDataRole.UserRole)
                    if (
                        isinstance(index, int)
                        and self._messages[index].message_id == selected_message_id
                    ):
                        self.folder_tabs.setCurrentWidget(widget)
                        widget.setCurrentRow(row)
                        return
        if self.inbox_list.count():
            self.inbox_list.setCurrentRow(0)
        elif self.special_list.count():
            self.folder_tabs.setCurrentWidget(self.special_list)
            self.special_list.setCurrentRow(0)

    def _populate_lists(self, *_args) -> None:
        query = self.search_input.text().strip().casefold() if hasattr(self, "search_input") else ""
        self.inbox_list.clear()
        self.special_list.clear()
        inbox_count = 0
        special_count = 0
        for index, message in enumerate(self._messages):
            haystack = (
                f"{message.subject}\n{message.sender_name}\n{message.sender}\n"
                f"{message.text_body}"
            ).casefold()
            if query and query not in haystack:
                continue
            widget = self.inbox_list if message.folder.casefold() == "inbox" else self.special_list
            received = (
                message.received_at.astimezone().strftime("%m-%d %H:%M")
                if message.received_at
                else ""
            )
            preview = " ".join(clean_message_text(message.text_body).split())[:105]
            sender = message.sender_display or "未知发件人"
            item = QListWidgetItem(
                f"{sender}   {received}\n{message.subject or '(无主题)'}\n{preview}"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(message.subject)
            widget.addItem(item)
            if widget is self.inbox_list:
                inbox_count += 1
            else:
                special_count += 1
        self.folder_tabs.setTabText(0, f"收件箱  {inbox_count}")
        self.folder_tabs.setTabText(1, f"其他文件夹  {special_count}")

    def _message_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or not 0 <= index < len(self._messages):
            return
        other = self.special_list if current.listWidget() is self.inbox_list else self.inbox_list
        other.blockSignals(True)
        other.clearSelection()
        other.setCurrentRow(-1)
        other.blockSignals(False)
        self._show_message(self._messages[index])

    def _show_message(self, message: MailMessage) -> None:
        self._render_generation += 1
        self._invalidate_translation()
        self._current_message = message
        self.sender_label.setText(f"发件人：{message.sender_name or '未提供名称'}")
        self.sender_address_label.setText(f"邮箱：{message.sender or '未知邮箱'}")
        self.subject_label.setText(message.subject or "(无主题)")
        received = (
            message.received_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            if message.received_at
            else "时间未知"
        )
        self.meta_label.setText(f"{received}  ·  {message.folder}")
        self._populate_attachments(message.attachments)
        display_content = select_stored_message_display_content(message)
        self._current_display_content = display_content
        self._translation_source_text = clean_message_text(message.text_body)
        if not self._translation_source_text and message.text_body.strip():
            self._translation_source_text = message.text_body.replace("\x00", "").strip()
        if not self._translation_source_text:
            self._translation_source_text = clean_message_text(
                display_content.html_fragment or display_content.source_html
            )
        self._refresh_translation_controls()
        self._render_original_view()

    def _render_original_view(self) -> None:
        display_content = self._current_display_content
        if display_content is None:
            return
        self._showing_translation = False
        if display_content.uses_html:
            self._render_html(display_content.source_html)
        else:
            self._render_plain_body(display_content.plain_text)
        if self._translated_text:
            self.translation_toggle_button.setText("查看译文")
            self.translation_toggle_button.show()

    def _render_plain_body(self, text: str) -> None:
        if self._attachment_gallery_html():
            self._render_html(
                f"<div>{html_escape(text).replace(chr(10), '<br>')}</div>"
            )
        else:
            self.body.setPlainText(text)

    def _render_translation_view(self) -> None:
        if not self._translated_text:
            return
        self._showing_translation = True
        self._render_plain_body(self._translated_text)
        self.translation_toggle_button.setText("查看原文")
        self.translation_toggle_button.show()

    def _toggle_translation_view(self) -> None:
        if not self._translated_text:
            return
        if self._showing_translation:
            self._render_original_view()
        else:
            self._render_translation_view()

    def _translate_current_message(self) -> None:
        source_text = self._translation_source_text.strip()
        if self._current_message is None or not source_text:
            self._show_feedback("当前邮件没有可翻译的正文")
            return
        expected_generation = self._translation_generation
        if self._translation_confirm:
            language = translation_language_label(self._translation_language)
            answer = QMessageBox.question(
                self,
                "确认翻译邮件",
                "翻译时会将当前邮件正文发送到 Google 公共翻译服务。\n"
                "不会发送附件、邮箱密码、Refresh Token 或账号配置。\n\n"
                f"目标语言：{language}\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if expected_generation != self._translation_generation or self._closed:
            return
        self._translation_generation += 1
        generation = self._translation_generation
        self._active_translation_generation = generation
        self.translate_button.setEnabled(False)
        self.translate_button.setText("正在翻译…")
        worker = TranslationWorker(
            generation,
            source_text,
            self._translation_language,
            self._translation_service,
        )
        worker.signals.result.connect(self._translation_loaded)
        worker.signals.finished.connect(self._translation_finished)
        self._translation_workers[generation] = worker
        self._pool.start(worker)

    def _translation_loaded(
        self, generation: int, translated: str, error: object
    ) -> None:
        if self._closed or generation != self._translation_generation:
            return
        self._active_translation_generation = None
        self.translate_button.setEnabled(bool(self._translation_source_text))
        if error is not None:
            self.translate_button.setText("重试翻译")
            detail = (
                str(error)
                if isinstance(error, TranslationError)
                else "翻译失败，请稍后重试"
            )
            QMessageBox.warning(self, "翻译失败", detail)
            return
        if not translated.strip():
            self.translate_button.setText("重试翻译")
            QMessageBox.warning(self, "翻译失败", "翻译服务没有返回有效内容")
            return
        self.translate_button.setText("重新翻译")
        self._translated_text = translated.strip()
        self._render_translation_view()
        self._show_feedback(
            f"已翻译为{translation_language_label(self._translation_language)}"
        )

    def _translation_finished(self, generation: int) -> None:
        self._translation_workers.pop(generation, None)
        if (
            not self._closed
            and generation == self._translation_generation
            and self._active_translation_generation == generation
        ):
            self._active_translation_generation = None
            self.translate_button.setEnabled(bool(self._translation_source_text))
            self.translate_button.setText("翻译邮件")

    def _invalidate_translation(self) -> None:
        self._translation_generation += 1
        self._active_translation_generation = None
        self._translated_text = ""
        self._showing_translation = False
        if hasattr(self, "translation_toggle_button"):
            self.translation_toggle_button.hide()
            self.translation_toggle_button.setText("查看原文")
        if hasattr(self, "translate_button"):
            self.translate_button.setText("翻译邮件")

    def update_translation_settings(
        self, target_language: str, require_confirmation: bool
    ) -> None:
        """Apply translation preferences to an already open reader."""

        language = _valid_translation_language(target_language)
        language_changed = language != self._translation_language
        self._translation_language = language
        self._translation_confirm = bool(require_confirmation)
        if language_changed:
            was_showing_translation = self._showing_translation
            self._invalidate_translation()
            if was_showing_translation and self._current_display_content is not None:
                self._render_original_view()
        self._refresh_translation_controls()

    def _refresh_translation_controls(self) -> None:
        if not hasattr(self, "translation_language_label"):
            return
        suffix = " · 翻译前确认" if self._translation_confirm else ""
        self.translation_language_label.setText(
            f"目标语言：{translation_language_label(self._translation_language)}{suffix}"
        )
        if hasattr(self, "translate_button") and self._active_translation_generation is None:
            self.translate_button.setEnabled(bool(self._translation_source_text))

    def _populate_attachments(
        self, attachments: tuple[MailAttachment, ...]
    ) -> None:
        self._visible_attachments = tuple(
            attachment
            for attachment in attachments
            if attachment.disposition.casefold() != "inline"
        )
        self.attachment_list.clear()
        for index, attachment in enumerate(self._visible_attachments):
            size = _format_size(attachment.size)
            state = " · 内容过大，仅保存了信息" if attachment.is_truncated else ""
            item = QListWidgetItem(
                f"{attachment.filename or '未命名附件'}    {size}{state}"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(
                f"类型：{attachment.content_type or '未知'}\n大小：{size}"
            )
            self.attachment_list.addItem(item)
        count = len(self._visible_attachments)
        total = sum(max(0, attachment.size) for attachment in self._visible_attachments)
        self.attachment_title.setText(f"附件 {count} 个 · {_format_size(total)}")
        self.attachment_panel.setVisible(bool(self._visible_attachments))
        self.save_all_attachments_button.setEnabled(bool(self._visible_attachments))
        if self._visible_attachments:
            self.attachment_list.setCurrentRow(0)

    def _selected_attachment(self) -> MailAttachment | None:
        if self._current_message is None:
            return None
        item = self.attachment_list.currentItem()
        if item is None:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or not 0 <= index < len(self._visible_attachments):
            return None
        return self._visible_attachments[index]

    def _attachment_with_content(
        self, attachment: MailAttachment
    ) -> MailAttachment | None:
        if attachment.content is not None:
            return attachment
        if self._message_repository is None or attachment.attachment_id is None:
            return None
        return self._message_repository.get_attachment(attachment.attachment_id)

    def _save_selected_attachment(self) -> None:
        attachment = self._selected_attachment()
        if attachment is None:
            return
        loaded = self._attachment_with_content(attachment)
        if loaded is None or loaded.content is None or loaded.is_truncated:
            QMessageBox.warning(
                self,
                "附件不可用",
                "该附件内容没有保存在本地。请重新取件；过大的附件可能被安全限制跳过。",
            )
            return
        filename = _safe_filename(loaded.filename)
        target, _ = QFileDialog.getSaveFileName(
            self,
            "保存附件",
            filename,
            "所有文件 (*.*)",
        )
        if not target:
            return
        try:
            Path(target).write_bytes(loaded.content)
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self._show_feedback(f"附件已保存 · {Path(target).name}")

    def _save_all_attachments(self) -> None:
        if self._current_message is None or not self._visible_attachments:
            return
        directory = QFileDialog.getExistingDirectory(self, "选择附件保存目录")
        if not directory:
            return
        saved = 0
        skipped = 0
        target_directory = Path(directory)
        try:
            used_names = {
                path.name.casefold() for path in target_directory.iterdir()
            }
        except OSError:
            used_names = set()
        for attachment in self._visible_attachments:
            loaded = self._attachment_with_content(attachment)
            if loaded is None or loaded.content is None or loaded.is_truncated:
                skipped += 1
                continue
            filename = _unique_filename(_safe_filename(loaded.filename), used_names)
            try:
                (target_directory / filename).write_bytes(loaded.content)
            except OSError:
                skipped += 1
                continue
            saved += 1
        self._show_feedback(f"附件保存完成 · 成功 {saved} · 跳过 {skipped}")

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        if self._current_message is not None:
            if self._showing_translation:
                self._render_translation_view()
            else:
                self._render_original_view()

    def _render_html(self, fragment: str) -> None:
        self.body.setHtml(
            prepare_email_web_document(
                fragment + self._attachment_gallery_html(),
                preheader_hint=(
                    self._current_message.subject if self._current_message else ""
                ),
            )
        )

    def _attachment_gallery_html(self) -> str:
        figures: list[str] = []
        for attachment in self._visible_attachments:
            if not attachment.content_type.casefold().startswith("image/"):
                continue
            loaded = self._attachment_with_content(attachment)
            if (
                loaded is None
                or loaded.content is None
                or loaded.is_truncated
                or len(loaded.content) > 4 * 1024 * 1024
            ):
                continue
            encoded = base64.b64encode(loaded.content).decode("ascii")
            figures.append(
                "<figure>"
                f'<img src="data:{html_escape(loaded.content_type)};base64,{encoded}" '
                f'alt="{html_escape(loaded.filename)}">'
                f"<figcaption>{html_escape(loaded.filename)}</figcaption>"
                "</figure>"
            )
        return (
            '<section class="attachment-gallery"><b>图片附件</b>'
            + "".join(figures)
            + "</section>"
            if figures
            else ""
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closed = True
        self._translation_generation += 1
        self._active_translation_generation = None
        self.body.shutdown()
        super().closeEvent(event)

    def _copy_link(self, link: QUrl) -> None:
        if link.scheme().casefold() not in {"http", "https", "mailto"}:
            return
        QApplication.clipboard().setText(link.toString())
        self._show_feedback("链接已复制")

    def _show_feedback(self, message: str) -> None:
        self.feedback_label.setText(message)
        self.feedback_label.show()
        QTimer.singleShot(2600, self.feedback_label.hide)

    def _open_link(self, url: QUrl) -> None:
        if url.scheme().casefold() not in {"http", "https", "mailto"}:
            return
        answer = QMessageBox.question(
            self,
            "打开外部链接",
            f"即将在系统默认程序中打开：\n{url.toString()[:500]}\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(url)


def _format_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


def _safe_filename(value: str) -> str:
    name = Path(value or "附件").name.strip().rstrip(". ") or "附件"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:180] or "附件"


def _unique_filename(filename: str, used_names: set[str]) -> str:
    candidate = filename
    stem = Path(filename).stem or "附件"
    suffix = Path(filename).suffix
    counter = 2
    while candidate.casefold() in used_names:
        candidate = f"{stem} ({counter}){suffix}"
        counter += 1
    used_names.add(candidate.casefold())
    return candidate


def _valid_translation_language(value: str) -> str:
    supported = {code for code, _label in TRANSLATION_LANGUAGES}
    return value if value in supported else DEFAULT_TRANSLATION_LANGUAGE
