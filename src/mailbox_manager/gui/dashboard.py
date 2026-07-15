from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial

from PySide6.QtCharts import (
    QChart,
    QChartView,
    QDateTimeAxis,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import QDateTime, QMargins, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.domain.status import STATUS_LABELS
from mailbox_manager.gui.icons import line_icon
from mailbox_manager.storage.enterprise_repositories import StatisticsRepository
from mailbox_manager.storage.repositories import MessageRepository


@dataclass(frozen=True, slots=True)
class QuickActionDefinition:
    """Public metadata used by both the dashboard and the settings page."""

    action_id: str
    label: str
    icon: str
    description: str


QUICK_ACTION_DEFINITIONS = (
    QuickActionDefinition("accounts", "账号管理", "users", "查看、选择和管理全部邮箱账号"),
    QuickActionDefinition("fetch", "开始批量取件", "bolt", "立即为选中的账号批量收取邮件"),
    QuickActionDefinition("add_account", "添加邮箱", "mail-plus", "添加邮箱或打开批量导入"),
    QuickActionDefinition("content_filter", "筛选与导出", "filter", "按自定义内容筛选并导出结果"),
    QuickActionDefinition("abnormal_accounts", "异常账号", "warning", "只查看需要处理的异常账号"),
)
QUICK_ACTIONS_BY_ID = {
    definition.action_id: definition for definition in QUICK_ACTION_DEFINITIONS
}
DEFAULT_QUICK_ACTION_IDS = ("accounts", "fetch", "add_account", "content_filter")
CONFIGURED_QUICK_ACTION_COUNT = 4
MAX_QUICK_ACTIONS = 6
METRICS_COMPACT_BREAKPOINT = 1120
PANELS_STACK_BREAKPOINT = 840

_QUICK_ACTION_ALIASES = {
    "account_management": "accounts",
    "batch_fetch": "fetch",
    "import": "add_account",
    "filter_export": "content_filter",
    "abnormal": "abnormal_accounts",
}


def normalize_quick_action_ids(action_ids: Sequence[str] | None) -> tuple[str, ...]:
    """Return a safe, stable shortcut list and recover from damaged settings."""

    if action_ids is None:
        return DEFAULT_QUICK_ACTION_IDS
    normalized: list[str] = []
    for raw_action_id in action_ids:
        raw_value = str(raw_action_id).strip()
        action_id = _QUICK_ACTION_ALIASES.get(raw_value, raw_value)
        if action_id in QUICK_ACTIONS_BY_ID and action_id not in normalized:
            normalized.append(action_id)
        if len(normalized) >= MAX_QUICK_ACTIONS:
            break
    return tuple(normalized) or DEFAULT_QUICK_ACTION_IDS


def configured_quick_action_ids(action_ids: Sequence[str] | None) -> tuple[str, ...]:
    """Return the four unique actions represented by the settings page."""

    normalized = list(normalize_quick_action_ids(action_ids))
    for definition in QUICK_ACTION_DEFINITIONS:
        if definition.action_id not in normalized:
            normalized.append(definition.action_id)
        if len(normalized) >= CONFIGURED_QUICK_ACTION_COUNT:
            break
    return tuple(normalized[:CONFIGURED_QUICK_ACTION_COUNT])


class _MetricCard(QFrame):
    activated = Signal()

    def __init__(
        self,
        metric_id: str,
        title: str,
        hint: str,
        icon: str,
        color: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardMetricCard")
        self.setProperty("metricId", metric_id)
        self.setProperty("accent", color)
        self.setMinimumHeight(104)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(17, 15, 15, 15)
        layout.setSpacing(13)

        icon_label = QLabel()
        icon_label.setObjectName("dashboardMetricIcon")
        icon_label.setProperty("metricId", metric_id)
        icon_label.setFixedSize(48, 48)
        icon_label.setPixmap(line_icon(icon, color, 23).pixmap(23, 23))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        copy = QVBoxLayout()
        copy.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("dashboardMetricLabel")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("dashboardMetricValue")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("dashboardMetricHint")
        copy.addWidget(title_label)
        copy.addWidget(self.value_label)
        copy.addWidget(self.hint_label)
        layout.addLayout(copy, 1)

        self.action_button = QToolButton()
        self.action_button.setObjectName("dashboardMetricAction")
        self.action_button.setProperty("metricId", metric_id)
        self.action_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_button.hide()
        self.action_button.clicked.connect(self.activated.emit)
        layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_value(self, value: int) -> None:
        self.value_label.setText(f"{value:,}")

    def set_hint(self, hint: str) -> None:
        self.hint_label.setText(hint)

    def set_action(self, text: str, icon: str, color: str) -> QToolButton:
        self.action_button.setText(text)
        self.action_button.setIcon(line_icon(icon, color, 15))
        self.action_button.setIconSize(QSize(15, 15))
        self.action_button.show()
        return self.action_button


class DashboardWidget(QWidget):
    # The original signals remain available so existing MainWindow integrations keep working.
    navigateAccountsRequested = Signal()
    startFetchRequested = Signal()
    importRequested = Signal()
    contentFilterRequested = Signal()
    recentMessageRequested = Signal(int, int)

    # New generic/customizable dashboard actions.
    quickActionRequested = Signal(str)
    abnormalAccountsRequested = Signal()
    proxyToggleRequested = Signal(bool)

    def __init__(
        self,
        statistics: StatisticsRepository,
        messages: MessageRepository,
        parent=None,
        *,
        quick_action_ids: Sequence[str] | None = None,
        proxy_enabled: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dashboard")
        self._statistics = statistics
        self._messages = messages
        self._dark = False
        self._fetch_state = "idle"
        self._proxy_enabled = bool(proxy_enabled)
        self._proxy_count = 0
        self._quick_action_ids: tuple[str, ...] = ()
        self.quick_action_buttons: dict[str, QToolButton] = {}
        self.fetch_button: QToolButton | None = None
        self._metric_columns = 0
        self._panels_stacked: bool | None = None
        self._scroll_reset_pending = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("dashboardScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root_layout.addWidget(self.scroll_area)

        self.content = QWidget()
        self.content.setObjectName("dashboardContent")
        # Compact windows should reflow instead of clipping the rightmost card.
        # Extremely small windows can still use the horizontal scrollbar.
        self.content.setMinimumSize(640, 720)
        self.scroll_area.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        # Qt's SetMinimumSize constraint rewrites the widget minimum after
        # queued layout events (629 px on macOS). Keep the constraint manual so
        # the responsive floor remains deterministic on every platform.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(26, 22, 26, 26)
        layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("dashboardHeader")
        title_row = QHBoxLayout(header)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_copy = QVBoxLayout()
        title_copy.setSpacing(2)
        title = QLabel("工作台概览")
        title.setObjectName("dashboardTitle")
        title_copy.addWidget(title)
        self.summary_label = QLabel("账号健康、邮件活动与常用操作")
        self.summary_label.setObjectName("dashboardSubtitle")
        self.summary_label.setAccessibleName("账号和收件统计摘要")
        title_copy.addWidget(self.summary_label)
        title_row.addLayout(title_copy)
        title_row.addStretch(1)
        self.health_badge = QLabel("正在统计账号状态")
        self.health_badge.setObjectName("dashboardHealthBadge")
        title_row.addWidget(self.health_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.refresh_button = QToolButton()
        self.refresh_button.setObjectName("dashboardRefreshButton")
        self.refresh_button.setText("刷新数据")
        self.refresh_button.setIcon(line_icon("refresh", "#64748b", 17))
        self.refresh_button.setIconSize(QSize(17, 17))
        self.refresh_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)
        title_row.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(header)

        self.metrics_container = QWidget()
        self.metrics_container.setObjectName("dashboardMetrics")
        self.metrics_layout = QGridLayout(self.metrics_container)
        self.metrics_layout.setContentsMargins(0, 0, 0, 0)
        self.metrics_layout.setHorizontalSpacing(12)
        self.metrics_layout.setVerticalSpacing(12)
        self.total_card = _MetricCard(
            "accounts", "账号总数", "当前工作区", "users", "#3b82f6"
        )
        self.message_card = _MetricCard(
            "messages", "本地邮件", "已安全保存", "inbox", "#10b981"
        )
        self.abnormal_card = _MetricCard(
            "abnormal", "异常账号", "需要检查", "warning", "#f59e0b"
        )
        self.proxy_card = _MetricCard(
            "proxy", "代理取件", "当前使用本地网络", "globe", "#8b5cf6"
        )
        self.abnormal_button = self.abnormal_card.set_action(
            "查看", "warning", "#d97706"
        )
        self.abnormal_button.setAccessibleName("查看所有异常账号")
        self.abnormal_card.activated.connect(self._request_abnormal_accounts)
        self.proxy_toggle_button = self.proxy_card.set_action(
            "启动", "play", "#7c3aed"
        )
        self.proxy_toggle_button.setAccessibleName("启动代理取件")
        self.proxy_card.activated.connect(self._toggle_proxy)
        self.metric_cards = (
            self.total_card,
            self.message_card,
            self.abnormal_card,
            self.proxy_card,
        )
        for index, card in enumerate(self.metric_cards):
            self.metrics_layout.addWidget(card, 0, index)
        layout.addWidget(self.metrics_container)

        self.activity_row = QWidget()
        self.activity_row.setObjectName("dashboardActivityRow")
        self.activity_layout = QGridLayout(self.activity_row)
        self.activity_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_layout.setHorizontalSpacing(12)
        self.activity_layout.setVerticalSpacing(12)

        self.quick_card = QFrame()
        self.quick_card.setObjectName("dashboardQuickPanel")
        self.quick_card.setProperty("dashboardPanel", True)
        quick_layout = QVBoxLayout(self.quick_card)
        quick_layout.setContentsMargins(17, 15, 17, 17)
        quick_layout.setSpacing(12)
        quick_header = QHBoxLayout()
        quick_header_copy = QVBoxLayout()
        quick_header_copy.setSpacing(1)
        quick_title = QLabel("快捷操作")
        quick_title.setObjectName("dashboardPanelTitle")
        quick_header_copy.addWidget(quick_title)
        quick_caption = QLabel("可在系统设置中调整显示和顺序")
        quick_caption.setObjectName("dashboardPanelCaption")
        quick_header_copy.addWidget(quick_caption)
        quick_header.addLayout(quick_header_copy)
        quick_header.addStretch(1)
        quick_layout.addLayout(quick_header)

        self.quick_grid_host = QWidget()
        self.quick_grid_host.setObjectName("dashboardQuickGrid")
        self.quick_grid = QGridLayout(self.quick_grid_host)
        self.quick_grid.setContentsMargins(0, 0, 0, 0)
        self.quick_grid.setHorizontalSpacing(10)
        self.quick_grid.setVerticalSpacing(10)
        self.quick_grid.setColumnStretch(0, 1)
        self.quick_grid.setColumnStretch(1, 1)
        quick_layout.addWidget(self.quick_grid_host, 1)
        self.activity_layout.addWidget(self.quick_card, 0, 0)

        self.recent_card = QFrame()
        self.recent_card.setObjectName("dashboardRecentPanel")
        self.recent_card.setProperty("dashboardPanel", True)
        recent_layout = QVBoxLayout(self.recent_card)
        recent_layout.setContentsMargins(17, 15, 17, 12)
        recent_layout.setSpacing(10)
        recent_header = QHBoxLayout()
        recent_header_copy = QVBoxLayout()
        recent_header_copy.setSpacing(1)
        recent_title = QLabel("最近邮件")
        recent_title.setObjectName("dashboardPanelTitle")
        recent_header_copy.addWidget(recent_title)
        recent_caption = QLabel("点击邮件可直接打开阅读")
        recent_caption.setObjectName("dashboardPanelCaption")
        recent_header_copy.addWidget(recent_caption)
        recent_header.addLayout(recent_header_copy)
        recent_header.addStretch(1)
        self.recent_count_label = QLabel("0 封")
        self.recent_count_label.setObjectName("dashboardCountBadge")
        recent_header.addWidget(self.recent_count_label)
        recent_layout.addLayout(recent_header)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("dashboardRecentList")
        self.recent_list.setWordWrap(True)
        self.recent_list.setSpacing(1)
        self.recent_list.itemClicked.connect(self._recent_activated)
        recent_layout.addWidget(self.recent_list, 1)
        self.activity_layout.addWidget(self.recent_card, 0, 1)
        self.activity_layout.setColumnStretch(0, 1)
        self.activity_layout.setColumnStretch(1, 2)
        self.activity_row.setMinimumHeight(290)
        layout.addWidget(self.activity_row, 1)

        self.insights_row = QWidget()
        self.insights_row.setObjectName("dashboardInsightsRow")
        self.insights_layout = QGridLayout(self.insights_row)
        self.insights_layout.setContentsMargins(0, 0, 0, 0)
        self.insights_layout.setHorizontalSpacing(12)
        self.insights_layout.setVerticalSpacing(12)
        self.health_card, self.health_chart = self._chart_card(
            "health", "账号健康度", "按最近连接结果统计"
        )
        self.rate_card, self.rate_chart = self._chart_card(
            "trend", "收件趋势", "最近 24 个有数据小时"
        )
        self.insights_layout.addWidget(self.health_card, 0, 0)
        self.insights_layout.addWidget(self.rate_card, 0, 1)
        self.insights_layout.setColumnStretch(0, 1)
        self.insights_layout.setColumnStretch(1, 2)
        self.insights_row.setMinimumHeight(270)
        layout.addWidget(self.insights_row, 1)

        # Establish the initial responsive floor after all children exist.
        self.content.setMinimumSize(640, 720)
        self._update_responsive_layout(self.width())
        self.set_quick_actions(quick_action_ids)
        self.set_proxy_state(proxy_enabled)
        self.refresh()

    @property
    def quick_action_ids(self) -> tuple[str, ...]:
        return self._quick_action_ids

    @property
    def proxy_enabled(self) -> bool:
        return self._proxy_enabled

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_responsive_layout(self.width())
        self._schedule_scroll_to_top()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_responsive_layout(event.size().width())
        if self.isVisible():
            self._schedule_scroll_to_top()

    def _update_responsive_layout(self, available_width: int) -> None:
        metric_columns = 2 if available_width < METRICS_COMPACT_BREAKPOINT else 4
        if metric_columns != self._metric_columns:
            for card in self.metric_cards:
                self.metrics_layout.removeWidget(card)
            for column in range(4):
                self.metrics_layout.setColumnStretch(
                    column, 1 if column < metric_columns else 0
                )
            self.metrics_layout.setRowStretch(0, 1)
            self.metrics_layout.setRowStretch(1, 1 if metric_columns == 2 else 0)
            for index, card in enumerate(self.metric_cards):
                self.metrics_layout.addWidget(
                    card,
                    index // metric_columns,
                    index % metric_columns,
                )
            self._metric_columns = metric_columns

        panels_stacked = available_width < PANELS_STACK_BREAKPOINT
        if panels_stacked != self._panels_stacked:
            for panel in (self.quick_card, self.recent_card):
                self.activity_layout.removeWidget(panel)
            for panel in (self.health_card, self.rate_card):
                self.insights_layout.removeWidget(panel)

            if panels_stacked:
                self.activity_layout.addWidget(self.quick_card, 0, 0)
                self.activity_layout.addWidget(self.recent_card, 1, 0)
                self.insights_layout.addWidget(self.health_card, 0, 0)
                self.insights_layout.addWidget(self.rate_card, 1, 0)
                activity_stretches = (1, 0)
                insight_stretches = (1, 0)
            else:
                self.activity_layout.addWidget(self.quick_card, 0, 0)
                self.activity_layout.addWidget(self.recent_card, 0, 1)
                self.insights_layout.addWidget(self.health_card, 0, 0)
                self.insights_layout.addWidget(self.rate_card, 0, 1)
                activity_stretches = (1, 2)
                insight_stretches = (1, 2)

            for column, stretch in enumerate(activity_stretches):
                self.activity_layout.setColumnStretch(column, stretch)
            for column, stretch in enumerate(insight_stretches):
                self.insights_layout.setColumnStretch(column, stretch)
            self.activity_layout.setRowStretch(0, 1)
            self.activity_layout.setRowStretch(1, 1 if panels_stacked else 0)
            self.insights_layout.setRowStretch(0, 1)
            self.insights_layout.setRowStretch(1, 1 if panels_stacked else 0)
            self._panels_stacked = panels_stacked

        self.metrics_layout.invalidate()
        self.activity_layout.invalidate()
        self.insights_layout.invalidate()
        self._sync_section_minimum_heights()
        self.content.updateGeometry()

    def _sync_section_minimum_heights(self) -> None:
        self.activity_layout.activate()
        self.insights_layout.activate()
        self.activity_row.setMinimumHeight(
            max(290, self.activity_layout.minimumSize().height())
        )
        self.insights_row.setMinimumHeight(
            max(270, self.insights_layout.minimumSize().height())
        )
        content_layout = self.content.layout()
        if content_layout is not None:
            content_layout.invalidate()
            content_layout.activate()
            layout_minimum = content_layout.minimumSize()
        else:
            layout_minimum = QSize(640, 720)
        # Preserve the vertical space needed by stacked panels while enforcing
        # the cross-platform compact-width contract ourselves.
        self.content.setMinimumSize(
            640,
            max(720, layout_minimum.height()),
        )

    def _schedule_scroll_to_top(self) -> None:
        if self._scroll_reset_pending:
            return
        self._scroll_reset_pending = True
        QTimer.singleShot(0, self._scroll_to_top)

    def _scroll_to_top(self) -> None:
        self._scroll_reset_pending = False
        vertical = self.scroll_area.verticalScrollBar()
        horizontal = self.scroll_area.horizontalScrollBar()
        vertical.setValue(vertical.minimum())
        horizontal.setValue(horizontal.minimum())

    def set_quick_actions(self, action_ids: Sequence[str] | None) -> tuple[str, ...]:
        """Rebuild the shortcuts without recreating the whole dashboard."""

        normalized = normalize_quick_action_ids(action_ids)
        while self.quick_grid.count():
            item = self.quick_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.quick_action_buttons.clear()
        self.fetch_button = None
        for row in range((MAX_QUICK_ACTIONS + 1) // 2):
            self.quick_grid.setRowStretch(row, 0)

        for index, action_id in enumerate(normalized):
            definition = QUICK_ACTIONS_BY_ID[action_id]
            button = QToolButton()
            button.setObjectName("dashboardQuickAction")
            button.setProperty("actionId", action_id)
            button.setText(definition.label)
            button.setToolTip(definition.description)
            button.setAccessibleName(definition.label)
            button.setAccessibleDescription(definition.description)
            button.setIcon(line_icon(definition.icon, "#3b82f6", 22))
            button.setIconSize(QSize(22, 22))
            button.setMinimumHeight(82)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            # Prevent QScrollArea from revealing a previously focused shortcut
            # when the dashboard tab is shown again.
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(partial(self._activate_quick_action, action_id))
            self.quick_action_buttons[action_id] = button
            if action_id == "fetch":
                self.fetch_button = button
            self.quick_grid.addWidget(button, index // 2, index % 2)

        rows = max(1, (len(normalized) + 1) // 2)
        for row in range(rows):
            self.quick_grid.setRowStretch(row, 1)
        self._quick_action_ids = normalized
        self._apply_fetch_state()
        self.quick_grid.invalidate()
        self._sync_section_minimum_heights()
        return normalized

    @staticmethod
    def _chart_card(
        chart_id: str, title: str, caption: str
    ) -> tuple[QFrame, QChartView]:
        card = QFrame()
        card.setObjectName("dashboardChartPanel")
        card.setProperty("chartId", chart_id)
        card.setProperty("dashboardPanel", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(17, 14, 17, 10)
        card_layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("dashboardPanelTitle")
        caption_label = QLabel(caption)
        caption_label.setObjectName("dashboardPanelCaption")
        chart_view = QChartView()
        chart_view.setObjectName("dashboardChartView")
        chart_view.setProperty("chartId", chart_id)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        chart_view.setMinimumHeight(190)
        chart_view.setStyleSheet("background: transparent; border: 0;")
        card_layout.addWidget(title_label)
        card_layout.addWidget(caption_label)
        card_layout.addWidget(chart_view, 1)
        return card, chart_view

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self.refresh_button.setIcon(
            line_icon("refresh", "#94a3b8" if dark else "#64748b", 17)
        )
        self._apply_fetch_state()
        self._update_proxy_card()
        self.refresh()

    def set_fetch_state(self, state: str) -> None:
        self._fetch_state = state if state in {"idle", "running", "stopping"} else "idle"
        self._apply_fetch_state()

    def _apply_fetch_state(self) -> None:
        button = self.fetch_button
        if button is None:
            return
        if self._fetch_state == "running":
            button.setText("取件进行中")
            button.setEnabled(False)
            icon_name = "refresh"
        elif self._fetch_state == "stopping":
            button.setText("正在停止…")
            button.setEnabled(False)
            icon_name = "stop"
        else:
            button.setText(QUICK_ACTIONS_BY_ID["fetch"].label)
            button.setEnabled(True)
            icon_name = "bolt"
        button.setProperty("state", self._fetch_state)
        button.setIcon(line_icon(icon_name, "#60a5fa" if self._dark else "#3b82f6", 22))
        button.style().unpolish(button)
        button.style().polish(button)

    def set_proxy_state(self, enabled: bool) -> None:
        """Reflect the persisted global proxy-fetch switch without emitting a request."""

        self._proxy_enabled = bool(enabled)
        self.proxy_card.setProperty("proxyEnabled", self._proxy_enabled)
        self._update_proxy_card()
        self.proxy_card.style().unpolish(self.proxy_card)
        self.proxy_card.style().polish(self.proxy_card)

    def set_proxy_toggle_enabled(self, enabled: bool) -> None:
        """Allow MainWindow to lock the switch while applying a state transition."""

        self.proxy_toggle_button.setEnabled(enabled)

    def _update_proxy_card(self) -> None:
        color = "#a78bfa" if self._dark else "#7c3aed"
        if self._proxy_enabled:
            self.proxy_card.set_hint(f"代理取件已开启 · {self._proxy_count} 个可用")
            self.proxy_toggle_button.setText("关闭")
            self.proxy_toggle_button.setIcon(line_icon("stop", color, 15))
            self.proxy_toggle_button.setAccessibleName("关闭代理取件")
        else:
            self.proxy_card.set_hint(f"当前使用本地网络 · {self._proxy_count} 个可用")
            self.proxy_toggle_button.setText("启动")
            self.proxy_toggle_button.setIcon(line_icon("play", color, 15))
            self.proxy_toggle_button.setAccessibleName("启动代理取件")

    def _toggle_proxy(self) -> None:
        requested_state = not self._proxy_enabled
        # MainWindow owns persistence and is the only source of truth for this
        # switch.  Keep the rendered state unchanged until that write succeeds.
        self.set_proxy_toggle_enabled(False)
        self.proxyToggleRequested.emit(requested_state)

    def _request_abnormal_accounts(self) -> None:
        self.quickActionRequested.emit("abnormal_accounts")
        self.abnormalAccountsRequested.emit()

    def _activate_quick_action(self, action_id: str, _checked: bool = False) -> None:
        del _checked
        self.quickActionRequested.emit(action_id)
        signal = {
            "accounts": self.navigateAccountsRequested,
            "fetch": self.startFetchRequested,
            "add_account": self.importRequested,
            "content_filter": self.contentFilterRequested,
            "abnormal_accounts": self.abnormalAccountsRequested,
        }[action_id]
        signal.emit()

    def refresh(self) -> None:
        stats = self._statistics.dashboard()
        overview = self._statistics.overview()
        self.summary_label.setText(
            f"管理 {overview.total_accounts} 个账号 · 已保存 {overview.total_messages} 封邮件"
        )
        self.total_card.set_value(overview.total_accounts)
        self.message_card.set_value(overview.total_messages)
        self.abnormal_card.set_value(overview.abnormal_accounts)
        self.abnormal_button.setEnabled(overview.abnormal_accounts > 0)
        self.abnormal_card.set_hint(
            "点击查看并处理" if overview.abnormal_accounts else "全部账号状态正常"
        )
        self.health_badge.setProperty(
            "state", "warning" if overview.abnormal_accounts else "healthy"
        )
        self.health_badge.setText(
            f"{overview.abnormal_accounts} 个账号待处理"
            if overview.abnormal_accounts
            else "账号状态正常"
        )
        self.health_badge.style().unpolish(self.health_badge)
        self.health_badge.style().polish(self.health_badge)
        self._proxy_count = overview.enabled_proxies
        self.proxy_card.set_value(overview.enabled_proxies)
        self._update_proxy_card()
        self._refresh_recent_messages()

        pie_series = QPieSeries()
        pie_series.setHoleSize(0.58)
        for status, count in stats.status_counts.items():
            if count:
                pie_series.append(f"{STATUS_LABELS[status]}  {count}", count)
        if not pie_series.count():
            pie_series.append("暂无账号", 1)
        health = self._new_chart()
        health.addSeries(pie_series)
        health.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        health.legend().setMarkerShape(health.legend().MarkerShape.MarkerShapeCircle)
        self.health_chart.setChart(health)

        line_series = QLineSeries()
        line_series.setPen(QPen(QColor("#60a5fa" if self._dark else "#2563eb"), 2.2))
        trend_points = stats.messages_per_hour
        if len(trend_points) == 1:
            timestamp, count = trend_points[0]
            center_ms = int(timestamp.timestamp() * 1000)
            half_bucket_ms = 30 * 60 * 1000
            # A single hourly bucket has no neighbouring point to form a line.
            # Render its one-hour span instead of leaving a detached square marker.
            line_series.append(center_ms - half_bucket_ms, count)
            line_series.append(center_ms + half_bucket_ms, count)
            line_series.setPointsVisible(False)
        else:
            line_series.setPointsVisible(bool(trend_points))
            for timestamp, count in trend_points:
                line_series.append(timestamp.timestamp() * 1000, count)
        rate = self._new_chart()
        rate.addSeries(line_series)
        # The trend series has no user-facing name.  Keeping its legend visible
        # leaves a lone blue square floating above the plot, which looks like a
        # rendering error rather than a chart key.
        rate.legend().hide()
        x_axis = QDateTimeAxis()
        x_axis.setFormat("MM-dd HH:mm")
        x_axis.setTickCount(5)
        y_axis = QValueAxis()
        y_axis.setLabelFormat("%d")
        y_axis.setMin(0)
        y_axis.setTickCount(5)
        rate.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
        rate.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
        line_series.attachAxis(x_axis)
        line_series.attachAxis(y_axis)
        if not trend_points:
            now = QDateTime.currentDateTime()
            x_axis.setRange(now.addSecs(-3600), now)
            y_axis.setRange(0, 1)
            y_axis.setTickCount(2)
        elif len(trend_points) == 1:
            timestamp, count = trend_points[0]
            point = QDateTime.fromMSecsSinceEpoch(int(timestamp.timestamp() * 1000))
            x_axis.setRange(point.addSecs(-2400), point.addSecs(2400))
            y_max = max(1, count + max(1, round(count * 0.15)))
            y_axis.setRange(0, y_max)
            y_axis.setTickCount(min(5, y_max + 1))
        self.rate_chart.setChart(rate)

    def _refresh_recent_messages(self) -> None:
        hits = self._messages.list_with_accounts(limit=6)
        self.recent_list.clear()
        for hit in hits:
            message = hit.message
            received = (
                message.received_at.astimezone().strftime("%m-%d %H:%M")
                if message.received_at
                else ""
            )
            sender = message.sender or "未知发件人"
            item = QListWidgetItem(
                f"{message.subject or '(无主题)'}\n"
                f"{hit.account_email}  ·  {sender}  ·  {received}"
            )
            item.setData(
                Qt.ItemDataRole.UserRole,
                (message.account_id or 0, message.message_id or 0),
            )
            item.setToolTip(message.subject)
            self.recent_list.addItem(item)
        self.recent_count_label.setText(f"{len(hits)} 封")
        if not hits:
            empty_item = QListWidgetItem("暂无本地邮件，完成取件后会显示在这里")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(empty_item)

    def _recent_activated(self, item: QListWidgetItem) -> None:
        value = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(value, tuple) and len(value) == 2 and value[0]:
            self.recentMessageRequested.emit(int(value[0]), int(value[1]))

    def _new_chart(self) -> QChart:
        chart = QChart()
        chart.setTheme(
            QChart.ChartTheme.ChartThemeDark
            if self._dark
            else QChart.ChartTheme.ChartThemeLight
        )
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.setMargins(QMargins(4, 5, 4, 2))
        return chart
