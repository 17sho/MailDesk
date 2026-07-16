from __future__ import annotations

import re
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager import __version__
from mailbox_manager.domain.models import FetchRequest, PostAction, ProxyType
from mailbox_manager.gui.appearance import (
    DEFAULT_FONT_WEIGHT,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    normalized_appearance,
)
from mailbox_manager.gui.close_dialog import (
    CLOSE_ACTION_ASK,
    CLOSE_ACTION_EXIT,
    CLOSE_ACTION_TRAY,
)
from mailbox_manager.gui.dashboard import (
    QUICK_ACTION_DEFINITIONS,
    configured_quick_action_ids,
)
from mailbox_manager.gui.icons import line_icon
from mailbox_manager.mail.parser import extract_matches
from mailbox_manager.services.translation_service import (
    DEFAULT_TRANSLATION_LANGUAGE,
    TRANSLATION_LANGUAGES,
)


class EnterpriseSettingsDialog(QDialog):
    addProxyRequested = Signal()
    updateCheckRequested = Signal()

    def __init__(
        self,
        values: dict[str, object] | None = None,
        parent=None,
        *,
        webhook_options: list[tuple[int, str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        values = values or {}
        self._webhook_options = list(webhook_options or [])
        self.setWindowTitle("MailDesk · 系统设置")
        self.setMinimumSize(720, 520)
        available = self.screen().availableGeometry()
        self.resize(
            min(940, max(720, available.width() - 80)),
            min(700, max(520, available.height() - 80)),
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())

        shell = QFrame()
        shell.setObjectName("settingsShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self._build_navigation())

        self.pages = QStackedWidget()
        self.pages.setObjectName("settingsPages")
        self.pages.addWidget(self._fetch_page(values))
        self.pages.addWidget(self._schedule_page(values))
        self.pages.addWidget(self._proxy_page(values))
        self.pages.addWidget(self._webhook_page())
        self.pages.addWidget(self._rule_page())
        self.pages.addWidget(self._translation_page(values))
        self.pages.addWidget(self._appearance_page(values))
        self.pages.addWidget(self._dashboard_page(values))
        self.pages.addWidget(self._update_page())
        shell_layout.addWidget(self.pages, 1)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        layout.addWidget(shell, 1)
        layout.addWidget(self._build_footer())

        self.post_action.currentIndexChanged.connect(self._sync_post_action_controls)
        self.schedule_enabled.toggled.connect(self._sync_schedule_controls)
        self._sync_post_action_controls()
        self._sync_schedule_controls()

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("settingsHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 20, 26, 18)
        header_layout.setSpacing(13)
        mark = QLabel()
        mark.setObjectName("settingsHeaderIcon")
        mark.setFixedSize(42, 42)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(line_icon("settings", "#2563eb", 22).pixmap(22, 22))
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel("系统设置")
        title.setObjectName("settingsTitle")
        subtitle = QLabel("管理收件策略、显示字体、深色主题、网络代理和自动化连接")
        subtitle.setObjectName("settingsSubtitle")
        copy.addWidget(title)
        copy.addWidget(subtitle)
        header_layout.addWidget(mark)
        header_layout.addLayout(copy)
        header_layout.addStretch(1)
        return header

    def _build_navigation(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("settingsSidebar")
        sidebar.setFixedWidth(190)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 20, 14, 18)
        sidebar_layout.setSpacing(10)
        caption = QLabel("设置分类")
        caption.setObjectName("settingsNavCaption")
        sidebar_layout.addWidget(caption)
        self.navigation = QListWidget()
        self.navigation.setObjectName("settingsNavigation")
        self.navigation.setSpacing(3)
        self.navigation.addItems(
            [
                "收件与处理",
                "调度与节流",
                "网络代理",
                "Webhook 对接",
                "自动化规则",
                "邮件翻译",
                "外观与字体",
                "工作台",
                "系统更新",
            ]
        )
        sidebar_layout.addWidget(self.navigation, 1)
        privacy = QLabel("账号凭据使用本机密钥\n加密保存在当前设备")
        privacy.setObjectName("settingsPrivacyHint")
        privacy.setWordWrap(True)
        sidebar_layout.addWidget(privacy)
        return sidebar

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 14)
        footer_layout.setSpacing(12)
        hint = QLabel("更改将在保存后应用到后续任务")
        hint.setObjectName("settingsFooterHint")
        footer_layout.addWidget(hint)
        footer_layout.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.save_button.setText("保存设置")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setDefault(True)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.setText("取消")
        cancel_button.setObjectName("secondaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer_layout.addWidget(buttons)
        return footer

    def _new_page(
        self, title_text: str, caption_text: str
    ) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        page = QWidget()
        page.setObjectName("settingsPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(26, 23, 26, 26)
        page_layout.setSpacing(16)
        title = QLabel(title_text)
        title.setObjectName("settingsPageTitle")
        caption = QLabel(caption_text)
        caption.setObjectName("settingsPageCaption")
        caption.setWordWrap(True)
        page_layout.addWidget(title)
        page_layout.addWidget(caption)
        scroll.setWidget(page)
        return scroll, page_layout

    def _add_card(
        self,
        page_layout: QVBoxLayout,
        title_text: str,
        caption_text: str = "",
    ) -> QFormLayout:
        card = QFrame()
        card.setObjectName("settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(7)
        title = QLabel(title_text)
        title.setObjectName("settingsCardTitle")
        card_layout.addWidget(title)
        if caption_text:
            caption = QLabel(caption_text)
            caption.setObjectName("settingsCardCaption")
            caption.setWordWrap(True)
            card_layout.addWidget(caption)
        form = QFormLayout()
        form.setContentsMargins(0, 9, 0, 0)
        form.setHorizontalSpacing(28)
        form.setVerticalSpacing(13)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        card_layout.addLayout(form)
        page_layout.addWidget(card)
        return form

    @staticmethod
    def _add_row(form: QFormLayout, label_text: str, field: QWidget) -> None:
        label = QLabel(label_text)
        label.setObjectName("settingsFieldLabel")
        form.addRow(label, field)

    @staticmethod
    def _prepare_line_edit(editor: QLineEdit, placeholder: str = "") -> QLineEdit:
        editor.setClearButtonEnabled(True)
        if placeholder:
            editor.setPlaceholderText(placeholder)
        return editor

    def _fetch_page(self, values: dict[str, object]) -> QScrollArea:
        page, layout = self._new_page(
            "收件与邮件处理",
            "控制每次取件范围，以及命中验证码或关键词后的可选动作。",
        )
        range_form = self._add_card(
            layout,
            "收取范围",
            "上限对每个账号的每次任务生效，只保存本地尚未收取的邮件；首次使用“不限制”可能耗时较久。",
        )
        self.folders = self._prepare_line_edit(
            QLineEdit(",".join(values.get("folders", ["INBOX"]))),
            "例如：INBOX,Archive",
        )
        self.max_messages = QSpinBox()
        self.max_messages.setRange(0, 1_000_000)
        self.max_messages.setSpecialValueText("不限制")
        self.max_messages.setValue(int(values.get("max_messages", 20)))
        self.max_messages.setSuffix(" 封")
        self.max_messages.setToolTip(
            "“立即取件”、批量取件和定时取件都会使用此上限；0 表示不限制。"
        )
        self.include_special = QCheckBox("同时扫描垃圾邮件与已删除邮件")
        self.include_special.setChecked(bool(values.get("include_special", False)))
        self.save_eml = QCheckBox("保存每封邮件的 EML 原件（会明显增加磁盘占用）")
        self.save_eml.setChecked(bool(values.get("save_eml", False)))
        self._add_row(range_form, "目标文件夹", self.folders)
        self._add_row(range_form, "每账号每次最多新增（0=不限）", self.max_messages)
        self._add_row(range_form, "深度扫描", self.include_special)
        self._add_row(range_form, "邮件原件", self.save_eml)

        extraction_form = self._add_card(
            layout,
            "提取结果规则",
            "验证码会继续自动识别；还可设置要命中的文字，以及需要提取的正则内容。",
        )
        keyword_values = values.get("extract_keywords", FetchRequest().keywords)
        if isinstance(keyword_values, (list, tuple)):
            keyword_text = "\n".join(str(item) for item in keyword_values)
        else:
            keyword_text = str(keyword_values)
        self.extract_keywords = QPlainTextEdit(keyword_text)
        self.extract_keywords.setPlaceholderText(
            "每行或逗号分隔，例如：\nverification code\n验证码\nReset Password"
        )
        self.extract_keywords.setMaximumHeight(90)
        self.extract_keywords.setTabChangesFocus(True)
        self.extract_pattern = self._prepare_line_edit(
            QLineEdit(str(values.get("extract_pattern", ""))),
            r"例如：https?://[^\s]+ 或 (?i)order[- ]?id[:：]\s*[A-Z0-9-]+",
        )
        self._add_row(extraction_form, "关键词", self.extract_keywords)
        self._add_row(extraction_form, "自定义正则", self.extract_pattern)

        action_form = self._add_card(
            layout,
            "匹配后的邮件处理",
            "移动或删除属于有副作用操作，只有明确确认后才会执行。",
        )
        self.post_action = QComboBox()
        for action, label in (
            (PostAction.NONE, "仅提取，不修改邮件"),
            (PostAction.MARK_READ, "匹配后标记已读"),
            (PostAction.MOVE, "匹配后移动到文件夹"),
            (PostAction.DELETE, "匹配后删除邮件"),
        ):
            self.post_action.addItem(label, action.value)
        current_action = str(values.get("post_action", PostAction.NONE.value))
        self.post_action.setCurrentIndex(max(0, self.post_action.findData(current_action)))
        self.action_target = self._prepare_line_edit(
            QLineEdit(str(values.get("action_target", ""))),
            "选择“移动”时填写，例如：Processed",
        )
        self.confirm_actions = QCheckBox("我已理解并确认执行上述邮件操作")
        self.confirm_actions.setChecked(bool(values.get("confirm_actions", False)))
        self._add_row(action_form, "命中后操作", self.post_action)
        self._add_row(action_form, "目标文件夹", self.action_target)
        self._add_row(action_form, "操作确认", self.confirm_actions)
        layout.addStretch(1)
        return page

    def _schedule_page(self, values: dict[str, object]) -> QScrollArea:
        page, layout = self._new_page(
            "调度与并发节流",
            "设置无人值守取件周期，并限制同一网络身份的请求密度。",
        )
        schedule_form = self._add_card(
            layout,
            "定时收件",
            "定时任务对当前账号分组生效，程序驻留托盘时仍会运行。",
        )
        self.schedule_enabled = QCheckBox("为当前分组启用定时收件")
        self.schedule_enabled.setChecked(bool(values.get("schedule_enabled", False)))
        self.schedule_interval = QSpinBox()
        self.schedule_interval.setRange(1, 10_080)
        self.schedule_interval.setValue(int(values.get("schedule_interval", 5)))
        self.schedule_interval.setSuffix(" 分钟")
        self._add_row(schedule_form, "任务状态", self.schedule_enabled)
        self._add_row(schedule_form, "监控周期", self.schedule_interval)

        throttle_form = self._add_card(
            layout,
            "请求节流",
            "适当的随机间隔可降低服务商限流概率；0 秒表示不额外等待。",
        )
        self.interval_min = QSpinBox()
        self.interval_min.setRange(0, 3600)
        self.interval_min.setValue(int(values.get("login_interval_min", 0)))
        self.interval_min.setSuffix(" 秒")
        self.interval_max = QSpinBox()
        self.interval_max.setRange(0, 3600)
        self.interval_max.setValue(int(values.get("login_interval_max", 0)))
        self.interval_max.setSuffix(" 秒")
        self.ip_concurrency = QSpinBox()
        self.ip_concurrency.setRange(1, 50)
        self.ip_concurrency.setValue(int(values.get("ip_concurrency", 2)))
        self.ip_concurrency.setSuffix(" 个")
        self._add_row(throttle_form, "账号最小间隔", self.interval_min)
        self._add_row(throttle_form, "账号最大间隔", self.interval_max)
        self._add_row(throttle_form, "单网络身份并发", self.ip_concurrency)
        layout.addStretch(1)
        return page

    def _translation_page(self, values: dict[str, object]) -> QScrollArea:
        page, layout = self._new_page(
            "邮件翻译",
            "设置阅读器的默认目标语言；翻译只会在你点击按钮后执行。",
        )
        language_form = self._add_card(
            layout,
            "默认翻译语言",
            "阅读器会自动识别原文语言，并将正文翻译为下面选择的语言。",
        )
        self.translation_language = QComboBox()
        for code, label in TRANSLATION_LANGUAGES:
            self.translation_language.addItem(label, code)
        current_language = str(
            values.get("translation_language", DEFAULT_TRANSLATION_LANGUAGE)
        )
        index = self.translation_language.findData(current_language)
        self.translation_language.setCurrentIndex(max(0, index))
        self._add_row(language_form, "目标语言", self.translation_language)

        privacy_form = self._add_card(
            layout,
            "隐私与确认",
            "翻译时仅发送当前邮件正文，不发送邮箱密码、Refresh Token、附件或账号配置。",
        )
        provider = QLabel("Google 公共翻译服务 · 自动检测原文语言")
        provider.setObjectName("translationProviderLabel")
        provider.setWordWrap(True)
        self.translation_confirm = QCheckBox("每次发送正文进行翻译前向我确认")
        self.translation_confirm.setChecked(
            bool(values.get("translation_confirm", True))
        )
        self._add_row(privacy_form, "翻译服务", provider)
        self._add_row(privacy_form, "发送确认", self.translation_confirm)
        layout.addStretch(1)
        return page

    def _dashboard_page(self, values: dict[str, object]) -> QScrollArea:
        page, layout = self._new_page(
            "工作台快捷操作",
            "选择并排列概览页上的四个常用入口，保存后立即更新。",
        )
        shortcut_form = self._add_card(
            layout,
            "四个快捷入口",
            "每个位置选择一个不同功能；从上到下对应工作台中的排列顺序。",
        )
        selected = configured_quick_action_ids(values.get("dashboard_quick_actions"))
        self.dashboard_quick_action_boxes: list[QComboBox] = []
        for position, current in enumerate(selected, 1):
            combo = QComboBox()
            combo.setAccessibleName(f"工作台快捷入口 {position}")
            for definition in QUICK_ACTION_DEFINITIONS:
                combo.addItem(definition.label, definition.action_id)
            combo.setCurrentIndex(max(0, combo.findData(current)))
            self.dashboard_quick_action_boxes.append(combo)
            self._add_row(shortcut_form, f"快捷入口 {position}", combo)

        behavior_form = self._add_card(
            layout,
            "入口说明",
            "“异常账号”会直接打开账号页并筛选所有异常状态；“代理开关”会切换全局代理池。",
        )
        hint = QLabel("账号固定代理始终优先于全局代理池，不受快捷入口排列影响。")
        hint.setObjectName("translationProviderLabel")
        hint.setWordWrap(True)
        self._add_row(behavior_form, "优先级", hint)

        close_form = self._add_card(
            layout,
            "关闭窗口",
            "决定点击主窗口关闭按钮时，是保留后台任务还是完全退出。",
        )
        self.close_action = QComboBox()
        self.close_action.addItem("每次询问", CLOSE_ACTION_ASK)
        self.close_action.addItem("最小化到系统托盘", CLOSE_ACTION_TRAY)
        self.close_action.addItem("直接退出应用", CLOSE_ACTION_EXIT)
        selected_close_action = str(values.get("close_action", CLOSE_ACTION_ASK))
        self.close_action.setCurrentIndex(
            max(0, self.close_action.findData(selected_close_action))
        )
        self._add_row(close_form, "关闭按钮操作", self.close_action)
        layout.addStretch(1)
        return page

    def _appearance_page(self, values: dict[str, object]) -> QScrollArea:
        page, layout = self._new_page(
            "外观与字体",
            "调整整个软件的文字大小、字重与字体，并统一浅色和深色界面的可读性。",
        )
        appearance = normalized_appearance(values)
        theme_form = self._add_card(
            layout,
            "界面主题",
            "保存后立即应用到主窗口、设置、菜单、提示框和邮件阅读器工具区域。",
        )
        self.dark_theme = QCheckBox("启用深色模式")
        self.dark_theme.setChecked(bool(appearance["dark_theme"]))
        self._add_row(theme_form, "颜色模式", self.dark_theme)

        font_form = self._add_card(
            layout,
            "全局文字",
            "正文会使用下面的基础设置；标题、工具栏和菜单会自动保持清晰的字重层级。",
        )
        self.font_family = QComboBox()
        self.font_family.addItem("跟随系统推荐字体", "")
        installed = set(QFontDatabase.families())
        preferred = (
            "Microsoft YaHei UI",
            "PingFang SC",
            "Noto Sans CJK SC",
            "Segoe UI",
        )
        for family in preferred:
            if family in installed:
                self.font_family.addItem(family, family)
        current_family = str(appearance["font_family"])
        family_index = self.font_family.findData(current_family)
        if current_family and family_index < 0:
            self.font_family.addItem(current_family, current_family)
            family_index = self.font_family.count() - 1
        self.font_family.setCurrentIndex(max(0, family_index))

        self.font_size = QSpinBox()
        self.font_size.setRange(MIN_FONT_SIZE, MAX_FONT_SIZE)
        self.font_size.setValue(int(appearance["font_size"]))
        self.font_size.setSuffix(" pt")
        self.font_weight = QComboBox()
        for label, weight in (
            ("标准", 400),
            ("清晰（推荐）", 500),
            ("半粗", 600),
        ):
            self.font_weight.addItem(label, weight)
        self.font_weight.setCurrentIndex(
            max(0, self.font_weight.findData(int(appearance["font_weight"])))
        )
        self._add_row(font_form, "字体", self.font_family)
        self._add_row(font_form, "文字大小", self.font_size)
        self._add_row(font_form, "文字粗细", self.font_weight)

        preview_form = self._add_card(
            layout,
            "效果预览",
            "预览仅展示文字参数；颜色模式会在保存后切换。",
        )
        self.font_preview = QLabel("MailDesk 邮箱工作台 · 验证码 482913 · Aa 123")
        self.font_preview.setObjectName("fontPreviewLabel")
        self.font_preview.setWordWrap(True)
        self._add_row(preview_form, "示例", self.font_preview)
        self.font_family.currentIndexChanged.connect(self._update_font_preview)
        self.font_size.valueChanged.connect(self._update_font_preview)
        self.font_weight.currentIndexChanged.connect(self._update_font_preview)
        self._update_font_preview()
        layout.addStretch(1)
        return page

    def _update_font_preview(self, *_args) -> None:
        family = str(self.font_family.currentData() or self.font().family())
        font = QFont(family)
        font.setPointSize(self.font_size.value())
        font.setWeight(QFont.Weight(int(self.font_weight.currentData())))
        self.font_preview.setFont(font)

    def _proxy_page(self, values: dict[str, object]) -> QScrollArea:
        page, layout = self._new_page(
            "网络代理",
            "批量保存 HTTP 或 SOCKS5 代理，之后可在账号右键菜单中进行一对一绑定。",
        )
        switch_form = self._add_card(
            layout,
            "全局代理池",
            "开启后，未绑定固定代理的账号会轮询使用已启用代理；关闭后改为本地直连。",
        )
        self.proxy_fetch_enabled = QCheckBox("启用全局代理池取件")
        self.proxy_fetch_enabled.setChecked(
            bool(values.get("proxy_fetch_enabled", False))
        )
        fixed_hint = QLabel("账号已绑定固定代理时，始终优先使用该代理。")
        fixed_hint.setObjectName("translationProviderLabel")
        self._add_row(switch_form, "代理状态", self.proxy_fetch_enabled)
        self._add_row(switch_form, "路由规则", fixed_hint)

        single_form = self._add_card(
            layout,
            "添加单个代理",
            "适合逐个填写名称、类型、主机、端口和认证信息；保存后立即加入代理池。",
        )
        single_row = QWidget()
        single_layout = QHBoxLayout(single_row)
        single_layout.setContentsMargins(0, 0, 0, 0)
        self.proxy_count_label = QLabel(
            f"当前已保存 {int(values.get('proxy_count', 0))} 个代理"
        )
        self.proxy_count_label.setObjectName("translationProviderLabel")
        single_layout.addWidget(self.proxy_count_label)
        single_layout.addStretch(1)
        self.add_proxy_button = QPushButton("添加单个代理")
        self.add_proxy_button.setObjectName("primaryButton")
        self.add_proxy_button.setIcon(line_icon("globe", "#ffffff", 16))
        self.add_proxy_button.clicked.connect(self.addProxyRequested.emit)
        single_layout.addWidget(self.add_proxy_button)
        self._add_row(single_form, "代理管理", single_row)

        form = self._add_card(
            layout,
            "导入代理",
            "每行保存一个代理；用户名和密码会使用本机密钥加密。",
        )
        self.proxy_type = QComboBox()
        self.proxy_type.addItem("HTTP / HTTPS", ProxyType.HTTP.value)
        self.proxy_type.addItem("SOCKS5", ProxyType.SOCKS5.value)
        self.proxy_text = QPlainTextEdit()
        self.proxy_text.setObjectName("settingsTextArea")
        self.proxy_text.setMinimumHeight(250)
        self.proxy_text.setPlaceholderText(
            "支持格式：IP:Port:User:Pass\n例如：127.0.0.1:1080:user:password"
        )
        self._add_row(form, "代理类型", self.proxy_type)
        self._add_row(form, "代理列表", self.proxy_text)
        layout.addStretch(1)
        return page

    def set_proxy_count(self, count: int) -> None:
        self.proxy_count_label.setText(f"当前已保存 {max(0, count)} 个代理")

    def _update_page(self) -> QScrollArea:
        page, layout = self._new_page(
            "系统更新",
            "手动检查 GitHub 上最新的 MailDesk 正式版本；不需要登录 GitHub。",
        )
        update_form = self._add_card(
            layout,
            "版本与更新",
            "检查会在后台执行，不会阻塞账号管理或正在进行的取件任务。",
        )
        version = QLabel(f"MailDesk v{__version__} · 正式更新通道")
        version.setObjectName("translationProviderLabel")
        version.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.update_check_button = QPushButton("检查系统更新")
        self.update_check_button.setObjectName("primaryButton")
        self.update_check_button.setIcon(line_icon("refresh", "#ffffff", 16))
        self.update_check_button.clicked.connect(self.updateCheckRequested.emit)
        self._add_row(update_form, "当前版本", version)
        self._add_row(update_form, "更新操作", self.update_check_button)
        security_form = self._add_card(
            layout,
            "安全校验",
            "只有 Ed25519 发布签名、版本、文件名、体积和 SHA-256 全部匹配，才允许下载与安装。",
        )
        security = QLabel("仅跟踪正式 Release；草稿和预发行版本不会自动安装。")
        security.setObjectName("translationProviderLabel")
        security.setWordWrap(True)
        self._add_row(security_form, "更新策略", security)
        layout.addStretch(1)
        return page

    def _webhook_page(self) -> QScrollArea:
        page, layout = self._new_page(
            "Webhook 消息推送",
            "提取到验证码或关键词后，将结构化结果安全推送到你的 HTTPS 服务。",
        )
        endpoint_form = self._add_card(
            layout,
            "推送端点",
            "仅允许 HTTPS 地址；允许主机用于阻止规则向未知域名发送数据。",
        )
        self.webhook_name = self._prepare_line_edit(QLineEdit(), "例如：业务自动化")
        self.webhook_url = self._prepare_line_edit(
            QLineEdit(), "https://hooks.example.com/mail"
        )
        self.webhook_hosts = self._prepare_line_edit(
            QLineEdit(), "hooks.example.com, automation.example.net"
        )
        self._add_row(endpoint_form, "配置名称", self.webhook_name)
        self._add_row(endpoint_form, "推送地址", self.webhook_url)
        self._add_row(endpoint_form, "允许主机", self.webhook_hosts)

        security_form = self._add_card(
            layout,
            "签名校验",
            "配置 HMAC 密钥后，每次请求都会携带 SHA-256 签名。",
        )
        self.webhook_secret = self._prepare_line_edit(
            QLineEdit(), "留空则不生成签名"
        )
        self.webhook_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._add_row(security_form, "HMAC 密钥", self.webhook_secret)
        layout.addStretch(1)
        return page

    def _rule_page(self) -> QScrollArea:
        page, layout = self._new_page(
            "自动化规则",
            "新增一条关键词或正则规则，并配置匹配后的邮件操作或安全转发。",
        )
        match_form = self._add_card(layout, "匹配条件")
        self.rule_name = self._prepare_line_edit(QLineEdit(), "例如：账单验证码")
        self.rule_pattern = self._prepare_line_edit(
            QLineEdit(), "关键词或正则表达式"
        )
        self._add_row(match_form, "规则名称", self.rule_name)
        self._add_row(match_form, "匹配内容", self.rule_pattern)

        action_form = self._add_card(
            layout,
            "匹配后动作",
            "转发邮箱必须是你已确认拥有的地址。",
        )
        self.rule_action = QComboBox()
        for action, label in (
            (PostAction.NONE, "仅记录匹配结果"),
            (PostAction.MARK_READ, "标记邮件已读"),
            (PostAction.MOVE, "移动邮件"),
            (PostAction.DELETE, "删除邮件"),
        ):
            self.rule_action.addItem(label, action.value)
        self.rule_target = self._prepare_line_edit(
            QLineEdit(), "选择“移动邮件”时填写"
        )
        self.rule_webhook = QComboBox()
        self.rule_webhook.addItem("不推送 Webhook", None)
        self.rule_webhook.addItem("使用本次新增的 Webhook", "new")
        for webhook_id, name in self._webhook_options:
            self.rule_webhook.addItem(name, webhook_id)
        self.rule_forward = self._prepare_line_edit(
            QLineEdit(), "你确认拥有的目标邮箱"
        )
        self._add_row(action_form, "邮件操作", self.rule_action)
        self._add_row(action_form, "移动目标", self.rule_target)
        self._add_row(action_form, "Webhook 推送", self.rule_webhook)
        self._add_row(action_form, "安全转发到", self.rule_forward)
        layout.addStretch(1)
        return page

    def _sync_post_action_controls(self) -> None:
        action = self.post_action.currentData()
        self.action_target.setEnabled(action == PostAction.MOVE.value)
        self.confirm_actions.setEnabled(action != PostAction.NONE.value)

    def _sync_schedule_controls(self, _checked: bool | None = None) -> None:
        self.schedule_interval.setEnabled(self.schedule_enabled.isChecked())

    def accept(self) -> None:
        values = self.values()
        action = PostAction(str(values["post_action"]))
        if action is not PostAction.NONE and not values["confirm_actions"]:
            self.navigation.setCurrentRow(0)
            self.confirm_actions.setFocus()
            QMessageBox.warning(
                self,
                "请确认邮件操作",
                "启用邮件后处理前，请勾选操作确认。当前设置内容已保留。",
            )
            return
        if action is PostAction.MOVE and not values["action_target"]:
            self.navigation.setCurrentRow(0)
            self.action_target.setFocus()
            QMessageBox.warning(
                self,
                "缺少目标文件夹",
                "选择移动邮件时必须填写目标文件夹。当前设置内容已保留。",
            )
            return
        if int(values["login_interval_max"]) < int(values["login_interval_min"]):
            self.navigation.setCurrentRow(1)
            QMessageBox.warning(
                self,
                "节流设置无效",
                "账号最大间隔不能小于最小间隔。当前设置内容已保留。",
            )
            return
        quick_actions = values["dashboard_quick_actions"]
        if not isinstance(quick_actions, list) or len(set(quick_actions)) != 4:
            self.navigation.setCurrentRow(7)
            QMessageBox.warning(
                self,
                "快捷入口重复",
                "工作台的四个快捷入口必须选择不同功能。当前设置内容已保留。",
            )
            return
        webhook_name = str(values["webhook_name"])
        webhook_url = str(values["webhook_url"])
        if bool(webhook_name) != bool(webhook_url):
            self.navigation.setCurrentRow(3)
            QMessageBox.warning(
                self,
                "Webhook 配置不完整",
                "新增 Webhook 时必须同时填写名称和 HTTPS 地址。",
            )
            return
        if webhook_url:
            parsed = urlsplit(webhook_url)
            allowed_hosts = set(values["webhook_hosts"])
            if parsed.scheme.casefold() != "https" or not parsed.hostname:
                self.navigation.setCurrentRow(3)
                QMessageBox.warning(
                    self,
                    "Webhook 地址无效",
                    "Webhook 必须使用包含有效主机名的 HTTPS 地址。",
                )
                return
            if parsed.hostname.casefold() not in allowed_hosts:
                self.navigation.setCurrentRow(3)
                QMessageBox.warning(
                    self,
                    "Webhook 主机未允许",
                    "请将 Webhook 地址中的主机名加入允许主机列表。",
                )
                return
        rule_name = str(values["rule_name"])
        rule_pattern = str(values["rule_pattern"])
        if bool(rule_name) != bool(rule_pattern):
            self.navigation.setCurrentRow(4)
            QMessageBox.warning(
                self,
                "自动化规则不完整",
                "新增规则时必须同时填写规则名称和匹配内容。",
            )
            return
        if rule_pattern:
            try:
                re.compile(rule_pattern)
            except re.error as exc:
                self.navigation.setCurrentRow(4)
                QMessageBox.warning(self, "匹配表达式无效", str(exc))
                return
        extract_pattern = str(values["extract_pattern"])
        if extract_pattern:
            try:
                extract_matches("", keywords=(), custom_pattern=extract_pattern)
            except ValueError as exc:
                self.navigation.setCurrentRow(0)
                QMessageBox.warning(self, "提取正则无效", str(exc))
                return
        extract_keywords = values["extract_keywords"]
        if isinstance(extract_keywords, list) and (
            len(extract_keywords) > 100
            or any(len(str(item)) > 200 for item in extract_keywords)
        ):
            self.navigation.setCurrentRow(0)
            QMessageBox.warning(self, "提取关键词过多", "最多 100 个关键词，每个不超过 200 字。")
            return
        if values["rule_webhook_id"] == "new" and not webhook_url:
            self.navigation.setCurrentRow(3)
            QMessageBox.warning(
                self,
                "缺少新 Webhook",
                "规则选择了“本次新增的 Webhook”，请先填写 Webhook 配置。",
            )
            return
        rule_action = PostAction(str(values["rule_action"]))
        if rule_action is PostAction.MOVE and not values["rule_target"]:
            self.navigation.setCurrentRow(4)
            QMessageBox.warning(self, "缺少移动目标", "移动规则必须填写目标文件夹。")
            return
        if (
            rule_pattern
            and (rule_action is not PostAction.NONE or values["rule_forward"])
            and not values["confirm_actions"]
        ):
            self.navigation.setCurrentRow(0)
            QMessageBox.warning(
                self,
                "请确认自动化操作",
                "执行邮件操作或自动转发前，请在收件页勾选操作确认。",
            )
            return
        super().accept()

    def values(self) -> dict[str, object]:
        return {
            "folders": [item.strip() for item in self.folders.text().split(",") if item.strip()],
            "max_messages": self.max_messages.value(),
            "include_special": self.include_special.isChecked(),
            "save_eml": self.save_eml.isChecked(),
            "extract_keywords": [
                item.strip()
                for item in re.split(r"[,，\n]+", self.extract_keywords.toPlainText())
                if item.strip()
            ],
            "extract_pattern": self.extract_pattern.text().strip(),
            "post_action": self.post_action.currentData(),
            "action_target": self.action_target.text().strip(),
            "confirm_actions": self.confirm_actions.isChecked(),
            "schedule_enabled": self.schedule_enabled.isChecked(),
            "schedule_interval": self.schedule_interval.value(),
            "login_interval_min": self.interval_min.value(),
            "login_interval_max": self.interval_max.value(),
            "ip_concurrency": self.ip_concurrency.value(),
            "proxy_type": self.proxy_type.currentData(),
            "proxy_text": self.proxy_text.toPlainText(),
            "proxy_fetch_enabled": self.proxy_fetch_enabled.isChecked(),
            "webhook_name": self.webhook_name.text().strip(),
            "webhook_url": self.webhook_url.text().strip(),
            "webhook_secret": self.webhook_secret.text(),
            "webhook_hosts": [
                item.strip().casefold()
                for item in self.webhook_hosts.text().split(",")
                if item.strip()
            ],
            "rule_name": self.rule_name.text().strip(),
            "rule_pattern": self.rule_pattern.text().strip(),
            "rule_action": self.rule_action.currentData(),
            "rule_target": self.rule_target.text().strip(),
            "rule_webhook_id": self.rule_webhook.currentData(),
            "rule_forward": self.rule_forward.text().strip().casefold(),
            "translation_language": self.translation_language.currentData(),
            "translation_confirm": self.translation_confirm.isChecked(),
            "dark_theme": self.dark_theme.isChecked(),
            "font_family": str(self.font_family.currentData() or ""),
            "font_size": self.font_size.value(),
            "font_weight": int(self.font_weight.currentData() or DEFAULT_FONT_WEIGHT),
            "dashboard_quick_actions": [
                combo.currentData() for combo in self.dashboard_quick_action_boxes
            ],
            "close_action": self.close_action.currentData(),
        }
