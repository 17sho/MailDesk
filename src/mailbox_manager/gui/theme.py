from __future__ import annotations

LIGHT_THEME = """
QMainWindow, QDialog, QWidget {
    background: #f4f7fb;
    color: #172033;
}
QLabel { background-color: transparent; }
QWidget#brandWidget, QWidget#brandCopy, QWidget#concurrencyBox,
QWidget#toolbarSpacer {
    background-color: transparent;
}

QToolBar#mainToolbar {
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #e2e8f0;
    spacing: 3px;
    padding: 5px 12px;
}
QToolBar#mainToolbar::separator {
    background: #e2e8f0;
    width: 1px;
    margin: 7px 9px;
}
QToolButton {
    background: transparent;
    color: #334155;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 6px 9px;
    margin: 1px;
    font-weight: 500;
}
QToolButton:hover {
    background: #f1f5f9;
    border-color: #e2e8f0;
}
QToolButton:pressed { background: #e2e8f0; }
QToolButton:disabled { color: #a8b1c0; }
QToolButton#primaryToolButton {
    background: #2563eb;
    color: #ffffff;
    border-color: #2563eb;
    font-weight: 600;
}
QToolButton#primaryToolButton:hover {
    background: #1d4ed8;
    border-color: #1d4ed8;
}
QToolButton#primaryToolButton:disabled {
    background: #93b4f5;
    color: #ffffff;
    border-color: #93b4f5;
}
QToolButton#addAccountToolButton {
    background: #eff6ff;
    color: #1d4ed8;
    border-color: #bfdbfe;
    font-weight: 600;
}
QToolButton#addAccountToolButton:hover {
    background: #dbeafe;
    border-color: #93c5fd;
}
QToolButton#updateToolButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #2563eb, stop:1 #06b6d4);
    color: #ffffff;
    border: 1px solid #38bdf8;
    border-radius: 9px;
    padding: 7px 13px;
    font-weight: 700;
}
QToolButton#updateToolButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #1d4ed8, stop:1 #0891b2);
    border-color: #0ea5e9;
}
QToolButton#updateToolButton:pressed { background: #1d4ed8; }
QToolButton#updateToolButton[state="downloading"] {
    background: #2563eb;
    border-color: #60a5fa;
}
QToolButton#updateToolButton[state="ready"] {
    background: #059669;
    border-color: #34d399;
}
QToolButton#dangerToolButton {
    background: #ffffff;
    color: #dc2626;
    border: 1px solid #fecaca;
    padding: 6px 10px;
    font-weight: 600;
}
QToolButton#dangerToolButton:hover {
    background: #fef2f2;
    border-color: #fca5a5;
}
QToolButton#dangerToolButton:pressed { background: #fee2e2; }
QToolButton#dangerToolButton:disabled {
    background: #f8fafc;
    color: #b8c2d0;
    border-color: #e2e8f0;
}

QLabel#brandMark {
    background: #2563eb;
    color: #ffffff;
    border-radius: 9px;
    font-size: 16px;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
}
QLabel#brandTitle {
    color: #0f172a;
    font-size: 15px;
    font-weight: 700;
}
QLabel#brandSubtitle, QLabel#sectionCaption, QLabel#mutedLabel {
    color: #718096;
    font-size: 11px;
}
QLabel#sectionTitle {
    color: #0f172a;
    font-size: 15px;
    font-weight: 700;
}
QLabel#emailBodyPlaceholder {
    color: #94a3b8;
    font-size: 13px;
    padding: 24px;
}
QLabel#dashboardTitle {
    color: #0f172a;
    font-size: 22px;
    font-weight: 700;
}
QLabel#metricLabel { color: #64748b; font-size: 11px; font-weight: 600; }
QLabel#metricValue { color: #0f172a; font-size: 24px; font-weight: 700; }
QLabel#countBadge, QLabel#privacyBadge, QLabel#statusPill {
    background: #eef2ff;
    color: #4338ca;
    border-radius: 9px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#selectionBadge {
    background: #dbeafe;
    color: #1d4ed8;
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#privacyBadge, QLabel#statusPill {
    background: #ecfdf5;
    color: #047857;
}
QLabel#statusPill[state="running"] {
    background: #dbeafe;
    color: #1d4ed8;
}
QLabel#statusPill[state="warning"] {
    background: #fff7ed;
    color: #c2410c;
}

QWidget#sidebar {
    background: #f8fafc;
    border-right: 1px solid #e2e8f0;
}
QTreeWidget#groupTree {
    background: transparent;
    border: 0;
    outline: 0;
    show-decoration-selected: 0;
}
QTreeWidget#groupTree::item {
    color: #475569;
    min-height: 34px;
    padding: 2px 8px;
}
QTreeWidget#groupTree::branch { background: transparent; border: 0; }
QTreeWidget#groupTree::item:hover { background: #eef2f7; }
QTreeWidget#groupTree::item:selected {
    background: #dbeafe;
    color: #1d4ed8;
    font-weight: 600;
}
QTreeWidget#groupTree::branch:selected { background: transparent; }

QWidget#concurrencyStepper {
    background: #ffffff;
    border: 1px solid #d8e0eb;
    border-radius: 8px;
}
QWidget#concurrencyStepper QSpinBox#concurrencySpin {
    background: transparent;
    border: 0;
    border-radius: 0;
    padding: 0;
    font-weight: 600;
}
QWidget#concurrencyStepper QPushButton#spinStepButton {
    background: transparent;
    color: #64748b;
    border: 0;
    border-radius: 6px;
    padding: 0;
    min-height: 0;
    font-size: 15px;
    font-weight: 600;
}
QWidget#concurrencyStepper QPushButton#spinStepButton:hover {
    background: #eff6ff;
    color: #2563eb;
}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextBrowser {
    background: #ffffff;
    color: #172033;
    border: 1px solid #d8e0eb;
    border-radius: 7px;
    padding: 6px 9px;
    selection-background-color: #bfdbfe;
    selection-color: #172033;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QPlainTextEdit:focus, QTextBrowser:focus {
    border: 1px solid #3b82f6;
}
QLineEdit#accountSearch { padding-left: 12px; }
QComboBox { combobox-popup: 0; }
QComboBox:hover { border-color: #b8c4d4; }
QComboBox:focus { border-color: #3b82f6; }
QComboBox::drop-down {
    background: transparent;
    border: 0;
    width: 28px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #172033;
    border: 1px solid #d8e0eb;
    border-radius: 9px;
    padding: 5px;
    selection-background-color: #dbeafe;
    selection-color: #1d4ed8;
    outline: 0;
}
QComboBox QAbstractItemView::item {
    background: transparent;
    color: #273449;
    border: 0;
    border-radius: 6px;
    min-height: 32px;
    padding: 2px 10px;
    margin: 1px 0;
}
QComboBox QAbstractItemView::item:hover {
    background: #f1f5f9;
    color: #172033;
}
QComboBox QAbstractItemView::item:selected {
    background: #e7f0ff;
    color: #1d4ed8;
    font-weight: 600;
}
QComboBox QAbstractItemView::item:disabled {
    background: transparent;
    color: #a8b1c0;
}
QComboBox QAbstractItemView QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 5px 2px;
}
QComboBox QAbstractItemView QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 26px;
}
QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QComboBox QAbstractItemView QScrollBar::add-line:vertical,
QComboBox QAbstractItemView QScrollBar::sub-line:vertical {
    height: 0;
}

QPushButton {
    background: #ffffff;
    color: #334155;
    border: 1px solid #d8e0eb;
    border-radius: 7px;
    padding: 7px 14px;
    min-height: 18px;
    font-weight: 500;
}
QPushButton:hover { background: #f8fafc; border-color: #b8c4d4; }
QPushButton:pressed { background: #eef2f7; }
QPushButton:disabled { color: #a8b1c0; background: #f8fafc; }
QPushButton#primaryButton {
    background: #2563eb;
    color: #ffffff;
    border-color: #2563eb;
    font-weight: 600;
    padding: 8px 18px;
}
QPushButton#primaryButton:hover { background: #1d4ed8; border-color: #1d4ed8; }
QPushButton#ghostButton {
    background: transparent;
    border-color: transparent;
    color: #64748b;
    padding: 4px 8px;
}
QPushButton#ghostButton:hover { background: #f1f5f9; color: #334155; }
QPushButton#dangerButton {
    background: #ffffff;
    color: #dc2626;
    border-color: #fecaca;
    padding: 5px 11px;
}
QPushButton#dangerButton:hover { background: #fef2f2; border-color: #fca5a5; }
QPushButton#dangerButton:disabled {
    background: #f8fafc;
    color: #cbd5e1;
    border-color: #e2e8f0;
}

QTableView#accountTable, QTableWidget#importPreviewTable,
QTableWidget#contentFilterResults {
    background: #ffffff;
    alternate-background-color: #fbfdff;
    color: #273449;
    border: 1px solid #e1e7ef;
    border-radius: 9px;
    gridline-color: transparent;
    selection-background-color: #dbeafe;
    selection-color: #172033;
    outline: 0;
}
QTableView#accountTable::item, QTableWidget#importPreviewTable::item,
QTableWidget#contentFilterResults::item {
    border-bottom: 1px solid #edf1f6;
    padding: 7px 8px;
}
QTableView#accountTable::item:hover, QTableWidget#importPreviewTable::item:hover,
QTableWidget#contentFilterResults::item:hover {
    background: #eff6ff;
}
QTableView#accountTable::item:selected, QTableWidget#importPreviewTable::item:selected,
QTableWidget#contentFilterResults::item:selected {
    background: #c7dcff;
    color: #0f172a;
}
QTableView#accountTable::item:selected {
    background: transparent;
    color: #273449;
}
QHeaderView::section {
    background: #f8fafc;
    color: #64748b;
    padding: 9px 8px;
    border: 0;
    border-bottom: 1px solid #e1e7ef;
    font-size: 11px;
    font-weight: 600;
}
QHeaderView::section:first { border-top-left-radius: 9px; }

QFrame#messagePanel, QFrame#contentPanel, QFrame#logPanel, QFrame#metricCard,
QFrame#chartCard {
    background: #ffffff;
    border: 1px solid #e1e7ef;
    border-radius: 10px;
}
QDockWidget#logDock {
    background: #ffffff;
    border-top: 1px solid #d8e0eb;
}
QWidget#logDrawerTitle, QWidget#logDrawerContent { background: #ffffff; }
QWidget#logDrawerTitle { border-bottom: 1px solid #edf1f6; }
QListWidget#messageList {
    background: #ffffff;
    color: #273449;
    border: 0;
    outline: 0;
}
QListWidget#messageList::item {
    border-bottom: 1px solid #edf1f6;
    padding: 10px 9px;
}
QListWidget#messageList::item:hover { background: #f8fafc; }
QListWidget#messageList::item:selected {
    background: #eaf2ff;
    color: #1d4ed8;
    border-left: 3px solid #2563eb;
}
QTextBrowser#messageBody, EmailBodyView#messageBody,
QPlainTextEdit#matchView, QPlainTextEdit#logView {
    background: #ffffff;
    border: 0;
    border-radius: 0;
    padding: 10px;
}
QFrame#mailTranslationBar {
    background: #f8fbff;
    border: 1px solid #d8e7fb;
    border-radius: 9px;
    margin: 4px 0;
}
QLabel#mailTranslationLanguage {
    color: #52627a;
    font-size: 11px;
    font-weight: 500;
}
QPushButton#translationButton, QPushButton#translateMessageButton {
    background: #e8f1ff;
    color: #1d4ed8;
    border: 1px solid #b8d5ff;
    border-radius: 7px;
    padding: 5px 12px;
    min-height: 19px;
    font-weight: 600;
}
QPushButton#translationButton:hover, QPushButton#translateMessageButton:hover {
    background: #dbeafe;
    border-color: #93c5fd;
}
QPushButton#translationButton:pressed, QPushButton#translateMessageButton:pressed {
    background: #c7ddff;
}
QPushButton#translationButton:disabled, QPushButton#translateMessageButton:disabled {
    background: #f1f5f9;
    color: #94a3b8;
    border-color: #e2e8f0;
}
QPushButton#translationToggleButton {
    background: #ffffff;
    color: #475569;
    border: 1px solid #d8e0eb;
    border-radius: 7px;
    padding: 5px 11px;
    min-height: 19px;
    font-weight: 600;
}
QPushButton#translationToggleButton:hover {
    background: #f1f5f9;
    color: #1d4ed8;
    border-color: #bfdbfe;
}
QPushButton#translationToggleButton:pressed { background: #e2e8f0; }
QPlainTextEdit#logView {
    background: #fbfdff;
    color: #475569;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
}

QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #e1e7ef;
    border-radius: 8px;
    top: -1px;
}
QTabWidget#messageTabs::pane { background: #ffffff; border: 0; }
QTabBar::tab {
    background: transparent;
    color: #64748b;
    border: 0;
    padding: 8px 14px;
    margin-right: 3px;
}
QTabBar::tab:hover { color: #1d4ed8; }
QTabBar::tab:selected {
    color: #1d4ed8;
    font-weight: 600;
    border-bottom: 2px solid #2563eb;
}
QTabWidget#mainTabs {
    background: #ffffff;
    border: 0;
}
QTabWidget#mainTabs::pane {
    background: #f4f7fb;
    border: 0;
    border-top: 1px solid #dfe6ef;
    top: -1px;
}
QTabWidget#mainTabs > QTabBar {
    background: #ffffff;
    border: 0;
    qproperty-drawBase: false;
}
QTabWidget#mainTabs > QTabBar::base {
    background: transparent;
    border: 0;
}
QTabWidget#mainTabs > QTabBar::tab {
    background: transparent;
    color: #64748b;
    border: 1px solid transparent;
    border-bottom: 3px solid transparent;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    padding: 9px 19px 8px 19px;
    margin: 5px 3px 0 0;
    min-width: 96px;
}
QTabWidget#mainTabs > QTabBar::tab:first { margin-left: 10px; }
QTabWidget#mainTabs > QTabBar::tab:hover {
    background: #f1f5f9;
    color: #1d4ed8;
}
QTabWidget#mainTabs > QTabBar::tab:selected {
    background: #eaf2ff;
    color: #1d4ed8;
    border-color: #d4e5ff;
    border-bottom: 3px solid #2563eb;
    font-weight: 600;
}

QDialog#settingsDialog { background: #f4f7fb; }
QFrame#settingsHeader {
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #e2e8f0;
}
QLabel#settingsHeaderIcon {
    background: #eaf2ff;
    color: #2563eb;
    border-radius: 11px;
    font-size: 20px;
    font-weight: 700;
}
QLabel#settingsTitle {
    color: #0f172a;
    font-size: 20px;
    font-weight: 700;
}
QLabel#settingsSubtitle, QLabel#settingsPageCaption,
QLabel#settingsCardCaption, QLabel#settingsFooterHint {
    color: #718096;
    font-size: 11px;
}
QFrame#settingsShell { background: #f4f7fb; border: 0; }
QFrame#settingsSidebar {
    background: #f8fafc;
    border: 0;
    border-right: 1px solid #e2e8f0;
}
QLabel#settingsNavCaption {
    color: #94a3b8;
    font-size: 10px;
    font-weight: 700;
    padding: 0 8px;
}
QListWidget#settingsNavigation {
    background: transparent;
    border: 0;
    outline: 0;
}
QListWidget#settingsNavigation::item {
    color: #475569;
    border-radius: 8px;
    min-height: 38px;
    padding: 1px 11px;
}
QListWidget#settingsNavigation::item:hover { background: #eef2f7; }
QListWidget#settingsNavigation::item:selected {
    background: #dbeafe;
    color: #1d4ed8;
    font-weight: 600;
}
QLabel#settingsPrivacyHint {
    background: #eef2ff;
    color: #6366f1;
    border-radius: 8px;
    padding: 10px;
    font-size: 10px;
}
QStackedWidget#settingsPages, QScrollArea#settingsScroll,
QWidget#settingsPage {
    background: #f4f7fb;
    border: 0;
}
QLabel#settingsPageTitle {
    color: #0f172a;
    font-size: 18px;
    font-weight: 700;
}
QFrame#settingsCard {
    background: #ffffff;
    border: 1px solid #e1e7ef;
    border-radius: 11px;
}
QLabel#settingsCardTitle {
    color: #1e293b;
    font-size: 13px;
    font-weight: 700;
}
QLabel#settingsFieldLabel {
    color: #475569;
    font-size: 11px;
    font-weight: 600;
}
QDialog#settingsDialog QSpinBox { min-width: 150px; max-width: 220px; }
QDialog#settingsDialog QSpinBox::up-button,
QDialog#settingsDialog QSpinBox::down-button {
    background: transparent;
    border: 0;
    width: 18px;
}
QDialog#settingsDialog QLineEdit:disabled,
QDialog#settingsDialog QSpinBox:disabled,
QDialog#settingsDialog QComboBox:disabled {
    background: #f8fafc;
    color: #a0aabc;
    border-color: #e2e8f0;
}
QDialog#settingsDialog QCheckBox {
    background: transparent;
    color: #334155;
    spacing: 8px;
}
QDialog#settingsDialog QCheckBox::indicator { width: 16px; height: 16px; }
QPlainTextEdit#settingsTextArea {
    background: #fbfdff;
    font-family: "Cascadia Mono", "Consolas";
}
QFrame#settingsFooter {
    background: #ffffff;
    border: 0;
    border-top: 1px solid #e2e8f0;
}
QPushButton#secondaryButton { min-width: 84px; }
QFrame#providerInfoCard {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 10px;
}
QLabel#providerInfoIcon {
    background: #dbeafe;
    border-radius: 8px;
}
QLabel#providerInfoText { color: #315580; font-size: 11px; }
QLabel#fontPreviewLabel {
    background: #f8fbff;
    color: #172033;
    border: 1px solid #d8e4f2;
    border-radius: 9px;
    padding: 14px;
}
QPlainTextEdit#credentialTextArea {
    background: #fbfdff;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
}

QWidget#emptyAccountState { background: #ffffff; border-radius: 9px; }
QLabel#emptyStateIcon {
    background: #eff6ff;
    color: #2563eb;
    border-radius: 25px;
    font-size: 25px;
    qproperty-alignment: AlignCenter;
}
QLabel#emptyStateTitle {
    color: #0f172a;
    font-size: 17px;
    font-weight: 700;
}
QLabel#emptyStateText { color: #64748b; line-height: 1.4; }

QScrollArea#dashboardScrollArea,
QScrollArea#dashboardScrollArea > QWidget > QWidget,
QWidget#dashboardContent {
    background: #f3f6fb;
    border: 0;
}
QFrame#dashboardHeader { background: transparent; border: 0; }
QLabel#dashboardTitle { color: #0f172a; font-size: 24px; font-weight: 700; }
QLabel#dashboardSubtitle { color: #718096; font-size: 12px; }
QLabel#dashboardHealthBadge {
    background: #ecfdf5;
    color: #047857;
    border: 1px solid #a7f3d0;
    border-radius: 10px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#dashboardHealthBadge[state="warning"] {
    background: #fff7ed;
    color: #c2410c;
    border-color: #fed7aa;
}
QWidget#dashboardMetrics, QWidget#dashboardActivityRow,
QWidget#dashboardInsightsRow, QWidget#dashboardQuickGrid { background: transparent; }
QFrame#dashboardMetricCard {
    background: #ffffff;
    border: 1px solid #dfe7f1;
    border-radius: 14px;
}
QFrame#dashboardMetricCard:hover { border-color: #bfd2ea; background: #fbfdff; }
QFrame#dashboardMetricCard[metricId="abnormal"] { border-color: #f5dfbd; }
QFrame#dashboardMetricCard[metricId="proxy"][proxyEnabled="true"] {
    border-color: #c4b5fd;
    background: #fcfaff;
}
QLabel#dashboardMetricIcon { border-radius: 12px; }
QLabel#dashboardMetricIcon[metricId="accounts"] { background: #eaf2ff; }
QLabel#dashboardMetricIcon[metricId="messages"] { background: #e9fbf4; }
QLabel#dashboardMetricIcon[metricId="abnormal"] { background: #fff5e6; }
QLabel#dashboardMetricIcon[metricId="proxy"] { background: #f3efff; }
QLabel#dashboardMetricLabel { color: #65748a; font-size: 11px; font-weight: 600; }
QLabel#dashboardMetricValue { color: #0f172a; font-size: 27px; font-weight: 700; }
QLabel#dashboardMetricHint { color: #8290a3; font-size: 10px; }
QToolButton#dashboardMetricAction {
    background: #f8fafc;
    color: #475569;
    border: 1px solid #dce5ef;
    border-radius: 8px;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 600;
}
QToolButton#dashboardMetricAction:hover {
    background: #eef5ff; border-color: #bfdbfe; color: #1d4ed8;
}
QToolButton#dashboardMetricAction:disabled {
    color: #a0aec0; background: #f8fafc; border-color: #edf1f6;
}
QFrame#dashboardQuickPanel, QFrame#dashboardRecentPanel,
QFrame#dashboardChartPanel {
    background: #ffffff;
    border: 1px solid #dfe7f1;
    border-radius: 14px;
}
QLabel#dashboardPanelTitle { color: #172033; font-size: 15px; font-weight: 700; }
QLabel#dashboardPanelCaption { color: #8290a3; font-size: 10px; }
QLabel#dashboardCountBadge {
    background: #eef2ff;
    color: #4338ca;
    border-radius: 10px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 600;
}
QToolButton#dashboardRefreshButton, QToolButton#columnMenuButton {
    background: #ffffff;
    color: #475569;
    border: 1px solid #d8e0eb;
    border-radius: 8px;
    padding: 7px 11px;
}
QToolButton#dashboardRefreshButton:hover, QToolButton#columnMenuButton:hover {
    background: #f8fafc;
    border-color: #b8c4d4;
}
QToolButton#dashboardQuickAction {
    background: #f8faff;
    color: #334155;
    border: 1px solid #e0e8f3;
    border-radius: 11px;
    padding: 12px;
    min-height: 66px;
    font-weight: 600;
}
QToolButton#dashboardQuickAction:hover {
    background: #edf5ff; color: #1d4ed8; border-color: #a9c9f7;
}
QToolButton#dashboardQuickAction[actionId="abnormal_accounts"] {
    background: #fffbf5; border-color: #f3dfbf;
}
QToolButton#dashboardQuickAction[state="running"] {
    background: #dbeafe;
    color: #1d4ed8;
    border-color: #93c5fd;
}
QToolButton#dashboardQuickAction[state="stopping"] {
    background: #fff7ed;
    color: #c2410c;
    border-color: #fdba74;
}
QListWidget#dashboardRecentList {
    background: transparent;
    border: 0;
    outline: 0;
}
QListWidget#dashboardRecentList::item {
    color: #334155;
    border-bottom: 1px solid #edf1f6;
    padding: 10px 9px;
}
QListWidget#dashboardRecentList::item:hover { background: #f8fafc; }
QListWidget#dashboardRecentList::item:selected { background: #eaf2ff; color: #1d4ed8; }
QWidget#dashboardChartView { background: transparent; border: 0; }

QFrame#mailViewerHeader {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
}
QLabel#mailViewerTitle { color: #0f172a; font-size: 18px; font-weight: 700; }
QFrame#mailViewerSidebar { background: #f8fafc; border-right: 1px solid #e2e8f0; }
QFrame#mailViewerContent { background: #ffffff; }
QLabel#mailViewerSender { color: #0f172a; font-size: 15px; font-weight: 700; }
QLabel#mailViewerSenderAddress {
    color: #526176;
    font-size: 12px;
    font-weight: 600;
}
QLabel#mailViewerSubject { color: #0f172a; font-size: 20px; font-weight: 700; }
QListWidget#mailReaderList { background: transparent; border: 0; outline: 0; }
QListWidget#mailReaderList::item {
    background: #ffffff;
    color: #475569;
    border: 1px solid #e2e8f0;
    border-radius: 9px;
    padding: 10px;
    margin: 3px 1px;
}
QListWidget#mailReaderList::item:hover { background: #f8fafc; border-color: #cbd5e1; }
QListWidget#mailReaderList::item:selected {
    background: #eff6ff;
    color: #1d4ed8;
    border: 2px solid #60a5fa;
}
QTextBrowser#mailViewerBody, EmailBodyView#mailViewerBody {
    background: #ffffff; border: 0; padding: 0;
}
QFrame#mailAttachmentPanel, QFrame#composeAttachmentCard, QFrame#composeSenderCard {
    background: #f8fafc;
    border: 1px solid #dbe3ee;
    border-radius: 10px;
}
QLabel#mailAttachmentTitle, QLabel#composeFieldLabel {
    color: #334155;
    font-weight: 600;
}
QListWidget#mailAttachmentList, QListWidget#composeAttachmentList {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    outline: 0;
}
QListWidget#mailAttachmentList::item, QListWidget#composeAttachmentList::item {
    color: #334155;
    padding: 7px 9px;
}
QListWidget#mailAttachmentList::item:selected,
QListWidget#composeAttachmentList::item:selected { background: #eaf2ff; color: #1d4ed8; }
QPushButton#attachmentActionButton {
    min-height: 28px;
    padding: 3px 10px;
    border-radius: 7px;
}
QLabel#mailViewerFeedback { color: #047857; padding: 3px 8px; }
QDialog#composeDialog { background: #ffffff; }
QFrame#composeHeader { background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
QFrame#composeFooter { background: #f8fafc; border-top: 1px solid #e2e8f0; }
QWidget#composeContent { background: #ffffff; }
QLabel#composeTitle { color: #0f172a; font-size: 19px; font-weight: 700; }
QLabel#composeSubtitle, QLabel#composeHint { color: #64748b; }
QLabel#composeSenderValue { color: #1d4ed8; }
QTextEdit#composeBody {
    background: #ffffff;
    color: #172033;
    border: 1px solid #cfd8e5;
    border-radius: 9px;
    padding: 10px;
}
QTextEdit#composeBody:focus { border: 1px solid #3b82f6; }

QDialog#updateDialog { background: transparent; }
QFrame#updateCard {
    background: #ffffff;
    border: 1px solid #dbe3ee;
    border-radius: 18px;
}
QFrame#updateHeader {
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #e6ebf2;
    border-top-left-radius: 18px;
    border-top-right-radius: 18px;
}
QWidget#updateContent { background: #ffffff; }
QFrame#updateFooter {
    background: #f7f9fc;
    border: 0;
    border-top: 1px solid #e2e8f0;
    border-bottom-left-radius: 18px;
    border-bottom-right-radius: 18px;
}
QLabel#updateHeaderIcon {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #2563eb, stop:1 #0ea5a8);
    border-radius: 12px;
}
QLabel#updateTitle { color: #111827; font-size: 21px; font-weight: 700; }
QLabel#updateHeaderSubtitle { color: #8793a7; font-size: 11px; }
QToolButton#updateCloseButton {
    background: transparent;
    color: #64748b;
    border: 0;
    border-radius: 9px;
    padding: 0;
    font-size: 24px;
    font-weight: 400;
}
QToolButton#updateCloseButton:hover { background: #f1f5f9; color: #334155; }
QLabel#updateVersionBadge {
    background: #eef4ff;
    color: #2563eb;
    border: 1px solid #d6e4ff;
    border-radius: 9px;
    padding: 2px 10px;
    font-size: 13px;
    font-weight: 700;
}
QLabel#updateSummary { color: #526176; font-size: 13px; padding: 2px 0 4px 0; }
QFrame#updateSeparator { color: #e5eaf1; background: #e5eaf1; border: 0; max-height: 1px; }
QLabel#updateSectionTitle { color: #172033; font-size: 14px; font-weight: 700; }
QTextBrowser#updateReleaseNotes {
    background: #fbfcfe;
    color: #3d4b60;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 4px;
    selection-background-color: #bfdbfe;
}
QFrame#updateProgressPanel {
    background: #f5f8fc;
    border: 1px solid #dfe7f1;
    border-radius: 10px;
}
QLabel#updateProgressStatus { color: #334155; font-size: 12px; font-weight: 600; }
QLabel#updateProgressPercent { color: #2563eb; font-size: 12px; font-weight: 700; }
QLabel#updateProgressDetail { color: #718096; font-size: 11px; }
QProgressBar#updateProgressBar {
    background: #dfe7f1;
    border: 0;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
}
QProgressBar#updateProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #2563eb, stop:1 #14b8a6);
    border-radius: 4px;
}
QFrame#updateCard[state="ready"] QLabel#updateProgressStatus { color: #047857; }
QFrame#updateCard[state="error"] QLabel#updateProgressStatus,
QFrame#updateCard[state="error"] QLabel#updateProgressPercent { color: #dc2626; }
QDialog#updateDialog QPushButton#secondaryButton { min-width: 88px; padding: 8px 15px; }
QDialog#updateDialog QPushButton#primaryButton { min-width: 126px; padding: 9px 20px; }

QSplitter::handle:horizontal {
    background: #dce3ec;
    margin: 0 2px;
    border-radius: 2px;
}
QSplitter::handle:vertical {
    background: #dce3ec;
    margin: 2px 0;
    border-radius: 2px;
}
QSplitter::handle:hover { background: #60a5fa; }
QStatusBar {
    background: #ffffff;
    color: #64748b;
    border-top: 1px solid #e2e8f0;
    padding: 2px 8px;
}
QFrame#bottomToast {
    background: #172033;
    border: 1px solid #334155;
    border-radius: 11px;
}
QLabel#bottomToastIcon {
    background: #064e3b;
    color: #6ee7b7;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 700;
}
QLabel#bottomToastText {
    color: #ffffff;
    font-size: 12px;
    font-weight: 600;
}
QFrame#bottomToast[tone="warning"] QLabel#bottomToastIcon {
    background: #7c2d12;
    color: #fed7aa;
}
QMenu {
    background: #ffffff;
    color: #273449;
    border: 1px solid #d8e0eb;
    border-radius: 10px;
    padding: 6px;
    font-weight: 400;
}
QMenu::item {
    background: transparent;
    color: #273449;
    border: 0;
    border-radius: 7px;
    padding: 8px 34px 8px 30px;
    margin: 1px 0;
}
QMenu::item:selected {
    background: #edf4ff;
    color: #1d4ed8;
}
QMenu::item:checked {
    color: #273449;
}
QMenu::item:disabled {
    background: transparent;
    color: #a8b1c0;
}
QMenu::indicator {
    width: 15px;
    height: 15px;
    left: 8px;
}
QMenu::separator {
    background: #e5eaf1;
    height: 1px;
    margin: 6px 10px;
}
QMenu::scroller {
    background: #f8fafc;
    height: 18px;
}
QMenu::right-arrow {
    width: 8px;
    height: 8px;
    right: 10px;
}
QToolTip {
    background: #172033;
    color: #ffffff;
    border: 0;
    padding: 5px 8px;
}
QDialog#closeWindowDialog { background: transparent; }
QFrame#closeDialogCard {
    background: #ffffff;
    border: 1px solid #dce3ec;
    border-radius: 16px;
}
QLabel#closeDialogTitle { color: #111827; font-size: 20px; font-weight: 700; }
QLabel#closeDialogSubtitle { color: #64748b; font-size: 12px; }
QPushButton#closeDialogDismiss {
    background: transparent; border: 0; color: #94a3b8;
    font-size: 22px; font-weight: 400; padding: 0;
}
QPushButton#closeDialogDismiss:hover { background: #f1f5f9; color: #475569; }
QPushButton#closeTrayOption, QPushButton#closeExitOption {
    background: #ffffff;
    border: 1px solid #dce3ec;
    border-radius: 11px;
    padding: 0;
}
QPushButton#closeTrayOption:hover { background: #f8fbff; border-color: #93b9ff; }
QPushButton#closeExitOption:hover { background: #fff8f8; border-color: #fca5a5; }
QPushButton#closeTrayOption:focus, QPushButton#closeExitOption:focus {
    border: 2px solid #60a5fa;
}
QPushButton#closeTrayOption:disabled {
    background: #f8fafc; border-color: #e2e8f0;
}
QLabel#closeOptionTitle { color: #172033; font-size: 14px; font-weight: 600; }
QLabel#closeOptionDescription { color: #718096; font-size: 11px; font-weight: 400; }
QLabel#closeOptionArrow { color: #94a3b8; font-size: 22px; font-weight: 400; }
QLabel#closeOptionTitle:disabled, QLabel#closeOptionDescription:disabled,
QLabel#closeOptionArrow:disabled { color: #a8b1c0; }
QCheckBox#closeRememberChoice { color: #526176; font-size: 12px; spacing: 8px; }
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: #94a3b8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


DARK_THEME = """
QMainWindow, QDialog, QWidget {
    background: #0f1520;
    color: #e5eaf2;
}
QLabel { background-color: transparent; }
QWidget#brandWidget, QWidget#brandCopy, QWidget#concurrencyBox,
QWidget#toolbarSpacer {
    background-color: transparent;
}

QToolBar#mainToolbar {
    background: #151d2a;
    border: 0;
    border-bottom: 1px solid #273244;
    spacing: 3px;
    padding: 5px 12px;
}
QToolBar#mainToolbar::separator {
    background: #2d394d;
    width: 1px;
    margin: 7px 9px;
}
QToolButton {
    background: transparent;
    color: #cbd5e1;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 6px 9px;
    margin: 1px;
    font-weight: 500;
}
QToolButton:hover { background: #202b3b; border-color: #324057; }
QToolButton:pressed { background: #29364a; }
QToolButton:disabled { color: #566277; }
QToolButton#primaryToolButton {
    background: #3b82f6;
    color: #ffffff;
    border-color: #3b82f6;
    font-weight: 600;
}
QToolButton#primaryToolButton:hover { background: #2563eb; border-color: #2563eb; }
QToolButton#primaryToolButton:disabled {
    background: #244a86;
    color: #a9c8f7;
    border-color: #31588f;
}
QToolButton#addAccountToolButton {
    background: #172a44;
    color: #93c5fd;
    border-color: #294f79;
    font-weight: 600;
}
QToolButton#addAccountToolButton:hover {
    background: #1d3b68;
    border-color: #3f6797;
}
QToolButton#updateToolButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #3b82f6, stop:1 #0891b2);
    color: #ffffff;
    border: 1px solid #38bdf8;
    border-radius: 9px;
    padding: 7px 13px;
    font-weight: 700;
}
QToolButton#updateToolButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #2563eb, stop:1 #0e7490);
    border-color: #67e8f9;
}
QToolButton#updateToolButton:pressed { background: #2563eb; }
QToolButton#updateToolButton[state="downloading"] {
    background: #2563eb;
    border-color: #60a5fa;
}
QToolButton#updateToolButton[state="ready"] {
    background: #047857;
    border-color: #34d399;
}
QToolButton#dangerToolButton {
    background: #251923;
    color: #f87171;
    border: 1px solid #5b3039;
    padding: 6px 10px;
    font-weight: 600;
}
QToolButton#dangerToolButton:hover {
    background: #3b2029;
    border-color: #7f3945;
}
QToolButton#dangerToolButton:pressed { background: #4a2430; }
QToolButton#dangerToolButton:disabled {
    background: #151d2a;
    color: #566277;
    border-color: #2b374a;
}

QLabel#brandMark {
    background: #3b82f6;
    color: #ffffff;
    border-radius: 9px;
    font-size: 16px;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
}
QLabel#brandTitle, QLabel#sectionTitle, QLabel#emptyStateTitle {
    color: #f8fafc;
    font-weight: 700;
}
QLabel#dashboardTitle { color: #f8fafc; font-size: 22px; font-weight: 700; }
QLabel#metricLabel { color: #8c99ad; font-size: 11px; font-weight: 600; }
QLabel#metricValue { color: #f8fafc; font-size: 24px; font-weight: 700; }
QLabel#brandTitle, QLabel#sectionTitle { font-size: 15px; }
QLabel#emptyStateTitle { font-size: 17px; }
QLabel#brandSubtitle, QLabel#sectionCaption, QLabel#mutedLabel,
QLabel#emptyStateText { color: #8c99ad; font-size: 11px; }
QLabel#emailBodyPlaceholder {
    color: #718096;
    font-size: 13px;
    padding: 24px;
}
QLabel#countBadge {
    background: #242b55;
    color: #a5b4fc;
    border-radius: 9px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#privacyBadge, QLabel#statusPill {
    background: #12362d;
    color: #6ee7b7;
    border-radius: 9px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#selectionBadge {
    background: #1d3b68;
    color: #bfdbfe;
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#statusPill[state="running"] {
    background: #1d3b68;
    color: #bfdbfe;
}
QLabel#statusPill[state="warning"] {
    background: #4a2a19;
    color: #fdba74;
}

QWidget#sidebar { background: #121a26; border-right: 1px solid #273244; }
QTreeWidget#groupTree {
    background: transparent;
    border: 0;
    outline: 0;
    show-decoration-selected: 0;
}
QTreeWidget#groupTree::item {
    color: #aeb9c9;
    min-height: 34px;
    padding: 2px 8px;
}
QTreeWidget#groupTree::branch { background: transparent; border: 0; }
QTreeWidget#groupTree::item:hover { background: #1c2737; }
QTreeWidget#groupTree::item:selected {
    background: #18345e;
    color: #93c5fd;
    font-weight: 600;
}
QTreeWidget#groupTree::branch:selected { background: transparent; }

QWidget#concurrencyStepper {
    background: #151d2a;
    border: 1px solid #334156;
    border-radius: 8px;
}
QWidget#concurrencyStepper QSpinBox#concurrencySpin {
    background: transparent;
    border: 0;
    border-radius: 0;
    padding: 0;
    font-weight: 600;
}
QWidget#concurrencyStepper QPushButton#spinStepButton {
    background: transparent;
    color: #8c99ad;
    border: 0;
    border-radius: 6px;
    padding: 0;
    min-height: 0;
    font-size: 15px;
    font-weight: 600;
}
QWidget#concurrencyStepper QPushButton#spinStepButton:hover {
    background: #1d3b68;
    color: #93c5fd;
}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextBrowser {
    background: #151d2a;
    color: #e5eaf2;
    border: 1px solid #334156;
    border-radius: 7px;
    padding: 6px 9px;
    selection-background-color: #1d4ed8;
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QPlainTextEdit:focus, QTextBrowser:focus { border: 1px solid #60a5fa; }
QLineEdit#accountSearch { padding-left: 12px; }
QComboBox { combobox-popup: 0; }
QComboBox:hover { border-color: #465873; }
QComboBox:focus { border-color: #60a5fa; }
QComboBox::drop-down {
    background: transparent;
    border: 0;
    width: 28px;
}
QComboBox QAbstractItemView {
    background: #151d2a;
    color: #e5eaf2;
    border: 1px solid #334156;
    border-radius: 9px;
    padding: 5px;
    selection-background-color: #18345e;
    selection-color: #93c5fd;
    outline: 0;
}
QComboBox QAbstractItemView::item {
    background: transparent;
    color: #d7deea;
    border: 0;
    border-radius: 6px;
    min-height: 32px;
    padding: 2px 10px;
    margin: 1px 0;
}
QComboBox QAbstractItemView::item:hover {
    background: #1c2737;
    color: #f8fafc;
}
QComboBox QAbstractItemView::item:selected {
    background: #18345e;
    color: #bfdbfe;
    font-weight: 600;
}
QComboBox QAbstractItemView::item:disabled {
    background: transparent;
    color: #667386;
}
QComboBox QAbstractItemView QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 5px 2px;
}
QComboBox QAbstractItemView QScrollBar::handle:vertical {
    background: #3a475c;
    border-radius: 4px;
    min-height: 26px;
}
QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {
    background: #526177;
}
QComboBox QAbstractItemView QScrollBar::add-line:vertical,
QComboBox QAbstractItemView QScrollBar::sub-line:vertical {
    height: 0;
}

QPushButton {
    background: #192332;
    color: #d5dce7;
    border: 1px solid #334156;
    border-radius: 7px;
    padding: 7px 14px;
    min-height: 18px;
    font-weight: 500;
}
QPushButton:hover { background: #202c3d; border-color: #465873; }
QPushButton:pressed { background: #27364a; }
QPushButton:disabled { color: #566277; background: #151d2a; }
QPushButton#primaryButton {
    background: #3b82f6;
    color: #ffffff;
    border-color: #3b82f6;
    font-weight: 600;
    padding: 8px 18px;
}
QPushButton#primaryButton:hover { background: #2563eb; border-color: #2563eb; }
QPushButton#ghostButton {
    background: transparent;
    border-color: transparent;
    color: #8c99ad;
    padding: 4px 8px;
}
QPushButton#ghostButton:hover { background: #202b3b; color: #d5dce7; }
QPushButton#dangerButton {
    background: #192332;
    color: #f87171;
    border-color: #5b3039;
    padding: 5px 11px;
}
QPushButton#dangerButton:hover { background: #3b2029; border-color: #7f3945; }
QPushButton#dangerButton:disabled {
    background: #151d2a;
    color: #566277;
    border-color: #2b374a;
}

QTableView#accountTable, QTableWidget#importPreviewTable,
QTableWidget#contentFilterResults {
    background: #151d2a;
    alternate-background-color: #172130;
    color: #d7deea;
    border: 1px solid #2b374a;
    border-radius: 9px;
    gridline-color: transparent;
    selection-background-color: #18345e;
    selection-color: #f8fafc;
    outline: 0;
}
QTableView#accountTable::item, QTableWidget#importPreviewTable::item,
QTableWidget#contentFilterResults::item {
    border-bottom: 1px solid #222e40;
    padding: 7px 8px;
}
QTableView#accountTable::item:hover, QTableWidget#importPreviewTable::item:hover,
QTableWidget#contentFilterResults::item:hover {
    background: #1b2b43;
}
QTableView#accountTable::item:selected, QTableWidget#importPreviewTable::item:selected,
QTableWidget#contentFilterResults::item:selected {
    background: #214b80;
    color: #f8fafc;
}
QTableView#accountTable::item:selected {
    background: transparent;
    color: #d7deea;
}
QHeaderView::section {
    background: #182230;
    color: #8c99ad;
    padding: 9px 8px;
    border: 0;
    border-bottom: 1px solid #2b374a;
    font-size: 11px;
    font-weight: 600;
}

QFrame#messagePanel, QFrame#contentPanel, QFrame#logPanel, QFrame#metricCard,
QFrame#chartCard {
    background: #151d2a;
    border: 1px solid #2b374a;
    border-radius: 10px;
}
QDockWidget#logDock {
    background: #121a26;
    border-top: 1px solid #334156;
}
QWidget#logDrawerTitle, QWidget#logDrawerContent { background: #121a26; }
QWidget#logDrawerTitle { border-bottom: 1px solid #222e40; }
QListWidget#messageList {
    background: #151d2a;
    color: #d7deea;
    border: 0;
    outline: 0;
}
QListWidget#messageList::item { border-bottom: 1px solid #222e40; padding: 10px 9px; }
QListWidget#messageList::item:hover { background: #1a2535; }
QListWidget#messageList::item:selected {
    background: #18345e;
    color: #bfdbfe;
    border-left: 3px solid #60a5fa;
}
QTextBrowser#messageBody, EmailBodyView#messageBody,
QPlainTextEdit#matchView, QPlainTextEdit#logView {
    background: #151d2a;
    border: 0;
    border-radius: 0;
    padding: 10px;
}
QFrame#mailTranslationBar {
    background: #142238;
    border: 1px solid #29415f;
    border-radius: 9px;
    margin: 4px 0;
}
QLabel#mailTranslationLanguage {
    color: #aeb9c9;
    font-size: 11px;
    font-weight: 500;
}
QPushButton#translationButton, QPushButton#translateMessageButton {
    background: #1d3b68;
    color: #bfdbfe;
    border: 1px solid #315e92;
    border-radius: 7px;
    padding: 5px 12px;
    min-height: 19px;
    font-weight: 600;
}
QPushButton#translationButton:hover, QPushButton#translateMessageButton:hover {
    background: #244b7c;
    border-color: #4b78aa;
}
QPushButton#translationButton:pressed, QPushButton#translateMessageButton:pressed {
    background: #28558d;
}
QPushButton#translationButton:disabled, QPushButton#translateMessageButton:disabled {
    background: #182231;
    color: #69768a;
    border-color: #2b374a;
}
QPushButton#translationToggleButton {
    background: #151d2a;
    color: #c4cedc;
    border: 1px solid #344258;
    border-radius: 7px;
    padding: 5px 11px;
    min-height: 19px;
    font-weight: 600;
}
QPushButton#translationToggleButton:hover {
    background: #1c293a;
    color: #bfdbfe;
    border-color: #3b5f88;
}
QPushButton#translationToggleButton:pressed { background: #243349; }
QPlainTextEdit#logView {
    background: #121a26;
    color: #aeb9c9;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
}

QTabWidget::pane {
    background: #151d2a;
    border: 1px solid #2b374a;
    border-radius: 8px;
    top: -1px;
}
QTabWidget#messageTabs::pane { background: #151d2a; border: 0; }
QTabBar::tab {
    background: transparent;
    color: #8c99ad;
    border: 0;
    padding: 8px 14px;
    margin-right: 3px;
}
QTabBar::tab:hover { color: #93c5fd; }
QTabBar::tab:selected {
    color: #93c5fd;
    font-weight: 600;
    border-bottom: 2px solid #60a5fa;
}
QTabWidget#mainTabs {
    background: #151d2a;
    border: 0;
}
QTabWidget#mainTabs::pane {
    background: #0f1520;
    border: 0;
    border-top: 1px solid #2b374a;
    top: -1px;
}
QTabWidget#mainTabs > QTabBar {
    background: #151d2a;
    border: 0;
    qproperty-drawBase: false;
}
QTabWidget#mainTabs > QTabBar::base {
    background: transparent;
    border: 0;
}
QTabWidget#mainTabs > QTabBar::tab {
    background: transparent;
    color: #8c99ad;
    border: 1px solid transparent;
    border-bottom: 3px solid transparent;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    padding: 9px 19px 8px 19px;
    margin: 5px 3px 0 0;
    min-width: 96px;
}
QTabWidget#mainTabs > QTabBar::tab:first { margin-left: 10px; }
QTabWidget#mainTabs > QTabBar::tab:hover {
    background: #1c2737;
    color: #bfdbfe;
}
QTabWidget#mainTabs > QTabBar::tab:selected {
    background: #172a44;
    color: #bfdbfe;
    border-color: #29415f;
    border-bottom: 3px solid #60a5fa;
    font-weight: 600;
}

QDialog#settingsDialog { background: #0f1520; }
QFrame#settingsHeader {
    background: #151d2a;
    border: 0;
    border-bottom: 1px solid #273244;
}
QLabel#settingsHeaderIcon {
    background: #18345e;
    color: #93c5fd;
    border-radius: 11px;
    font-size: 20px;
    font-weight: 700;
}
QLabel#settingsTitle {
    color: #f8fafc;
    font-size: 20px;
    font-weight: 700;
}
QLabel#settingsSubtitle, QLabel#settingsPageCaption,
QLabel#settingsCardCaption, QLabel#settingsFooterHint {
    color: #8c99ad;
    font-size: 11px;
}
QFrame#settingsShell { background: #0f1520; border: 0; }
QFrame#settingsSidebar {
    background: #121a26;
    border: 0;
    border-right: 1px solid #273244;
}
QLabel#settingsNavCaption {
    color: #69768a;
    font-size: 10px;
    font-weight: 700;
    padding: 0 8px;
}
QListWidget#settingsNavigation {
    background: transparent;
    border: 0;
    outline: 0;
}
QListWidget#settingsNavigation::item {
    color: #aeb9c9;
    border-radius: 8px;
    min-height: 38px;
    padding: 1px 11px;
}
QListWidget#settingsNavigation::item:hover { background: #1c2737; }
QListWidget#settingsNavigation::item:selected {
    background: #18345e;
    color: #bfdbfe;
    font-weight: 600;
}
QLabel#settingsPrivacyHint {
    background: #242b55;
    color: #a5b4fc;
    border-radius: 8px;
    padding: 10px;
    font-size: 10px;
}
QStackedWidget#settingsPages, QScrollArea#settingsScroll,
QWidget#settingsPage {
    background: #0f1520;
    border: 0;
}
QLabel#settingsPageTitle {
    color: #f8fafc;
    font-size: 18px;
    font-weight: 700;
}
QFrame#settingsCard {
    background: #151d2a;
    border: 1px solid #2b374a;
    border-radius: 11px;
}
QLabel#settingsCardTitle {
    color: #e5eaf2;
    font-size: 13px;
    font-weight: 700;
}
QLabel#settingsFieldLabel {
    color: #aeb9c9;
    font-size: 11px;
    font-weight: 600;
}
QDialog#settingsDialog QSpinBox { min-width: 150px; max-width: 220px; }
QDialog#settingsDialog QSpinBox::up-button,
QDialog#settingsDialog QSpinBox::down-button {
    background: transparent;
    border: 0;
    width: 18px;
}
QDialog#settingsDialog QLineEdit:disabled,
QDialog#settingsDialog QSpinBox:disabled,
QDialog#settingsDialog QComboBox:disabled {
    background: #121a26;
    color: #69768a;
    border-color: #263348;
}
QDialog#settingsDialog QCheckBox {
    background: transparent;
    color: #d5dce7;
    spacing: 8px;
}
QDialog#settingsDialog QCheckBox::indicator { width: 16px; height: 16px; }
QPlainTextEdit#settingsTextArea {
    background: #121a26;
    font-family: "Cascadia Mono", "Consolas";
}
QFrame#settingsFooter {
    background: #151d2a;
    border: 0;
    border-top: 1px solid #273244;
}
QPushButton#secondaryButton { min-width: 84px; }
QFrame#providerInfoCard {
    background: #172a44;
    border: 1px solid #294f79;
    border-radius: 10px;
}
QLabel#providerInfoIcon {
    background: #1d3b68;
    border-radius: 8px;
}
QLabel#providerInfoText { color: #a9c8f7; font-size: 11px; }
QLabel#fontPreviewLabel {
    background: #101722;
    color: #f1f5f9;
    border: 1px solid #344258;
    border-radius: 9px;
    padding: 14px;
}
QPlainTextEdit#credentialTextArea {
    background: #121a26;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
}

QWidget#emptyAccountState { background: #151d2a; border-radius: 9px; }
QLabel#emptyStateIcon {
    background: #18345e;
    color: #93c5fd;
    border-radius: 25px;
    font-size: 25px;
    qproperty-alignment: AlignCenter;
}

QScrollArea#dashboardScrollArea,
QScrollArea#dashboardScrollArea > QWidget > QWidget,
QWidget#dashboardContent { background: #0f1520; border: 0; }
QFrame#dashboardHeader { background: transparent; border: 0; }
QLabel#dashboardTitle { color: #f8fafc; font-size: 24px; font-weight: 700; }
QLabel#dashboardSubtitle { color: #8c99ad; font-size: 12px; }
QLabel#dashboardHealthBadge {
    background: #123b32;
    color: #6ee7b7;
    border: 1px solid #246657;
    border-radius: 10px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#dashboardHealthBadge[state="warning"] {
    background: #4a2a19; color: #fdba74; border-color: #7c4a28;
}
QWidget#dashboardMetrics, QWidget#dashboardActivityRow,
QWidget#dashboardInsightsRow, QWidget#dashboardQuickGrid { background: transparent; }
QFrame#dashboardMetricCard {
    background: #151d2a;
    border: 1px solid #2b374a;
    border-radius: 14px;
}
QFrame#dashboardMetricCard:hover { background: #182232; border-color: #3c4b61; }
QFrame#dashboardMetricCard[metricId="abnormal"] { border-color: #60462c; }
QFrame#dashboardMetricCard[metricId="proxy"][proxyEnabled="true"] {
    border-color: #5b4b8a; background: #1b1930;
}
QLabel#dashboardMetricIcon { border-radius: 12px; }
QLabel#dashboardMetricIcon[metricId="accounts"] { background: #18345e; }
QLabel#dashboardMetricIcon[metricId="messages"] { background: #123b32; }
QLabel#dashboardMetricIcon[metricId="abnormal"] { background: #4a2a19; }
QLabel#dashboardMetricIcon[metricId="proxy"] { background: #2d234a; }
QLabel#dashboardMetricLabel { color: #9ba8ba; font-size: 11px; font-weight: 600; }
QLabel#dashboardMetricValue { color: #f8fafc; font-size: 27px; font-weight: 700; }
QLabel#dashboardMetricHint { color: #7f8b9d; font-size: 10px; }
QToolButton#dashboardMetricAction {
    background: #192332;
    color: #b8c3d2;
    border: 1px solid #334156;
    border-radius: 8px;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 600;
}
QToolButton#dashboardMetricAction:hover {
    background: #1d3b68; border-color: #365f91; color: #bfdbfe;
}
QToolButton#dashboardMetricAction:disabled {
    color: #667386; background: #151d2a; border-color: #273244;
}
QFrame#dashboardQuickPanel, QFrame#dashboardRecentPanel,
QFrame#dashboardChartPanel {
    background: #151d2a; border: 1px solid #2b374a; border-radius: 14px;
}
QLabel#dashboardPanelTitle { color: #edf2f7; font-size: 15px; font-weight: 700; }
QLabel#dashboardPanelCaption { color: #7f8b9d; font-size: 10px; }
QLabel#dashboardCountBadge {
    background: #242b55;
    color: #a5b4fc;
    border-radius: 10px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 600;
}
QToolButton#dashboardRefreshButton, QToolButton#columnMenuButton {
    background: #151d2a;
    color: #aeb9c9;
    border: 1px solid #334156;
    border-radius: 8px;
    padding: 7px 11px;
}
QToolButton#dashboardRefreshButton:hover, QToolButton#columnMenuButton:hover {
    background: #202c3d;
    border-color: #465873;
}
QToolButton#dashboardQuickAction {
    background: #192332;
    color: #d5dce7;
    border: 1px solid #2b374a;
    border-radius: 10px;
    padding: 12px;
    min-height: 62px;
    font-weight: 600;
}
QToolButton#dashboardQuickAction:hover {
    background: #1b2b43; border-color: #365a88; color: #bfdbfe;
}
QToolButton#dashboardQuickAction[actionId="abnormal_accounts"] {
    background: #211d1a; border-color: #5a422b;
}
QToolButton#dashboardQuickAction[state="running"] {
    background: #1d3b68;
    color: #bfdbfe;
    border-color: #365f91;
}
QToolButton#dashboardQuickAction[state="stopping"] {
    background: #4a2a19;
    color: #fdba74;
    border-color: #7c4a28;
}
QListWidget#dashboardRecentList { background: transparent; border: 0; outline: 0; }
QListWidget#dashboardRecentList::item {
    color: #cbd5e1;
    border-bottom: 1px solid #222e40;
    padding: 9px 8px;
}
QListWidget#dashboardRecentList::item:hover { background: #1c2737; }
QListWidget#dashboardRecentList::item:selected { background: #18345e; color: #bfdbfe; }
QWidget#dashboardChartView { background: transparent; border: 0; }

QFrame#mailViewerHeader { background: #101827; border-bottom: 1px solid #273244; }
QLabel#mailViewerTitle { color: #f8fafc; font-size: 18px; font-weight: 700; }
QFrame#mailViewerSidebar { background: #121a26; border-right: 1px solid #273244; }
QFrame#mailViewerContent { background: #0f1520; }
QLabel#mailViewerSender { color: #f8fafc; font-size: 15px; font-weight: 700; }
QLabel#mailViewerSenderAddress {
    color: #aeb9c9;
    font-size: 12px;
    font-weight: 600;
}
QLabel#mailViewerSubject { color: #f8fafc; font-size: 20px; font-weight: 700; }
QListWidget#mailReaderList { background: transparent; border: 0; outline: 0; }
QListWidget#mailReaderList::item {
    background: #151d2a;
    color: #aeb9c9;
    border: 1px solid #2b374a;
    border-radius: 9px;
    padding: 10px;
    margin: 3px 1px;
}
QListWidget#mailReaderList::item:hover { background: #1c2737; border-color: #3a475c; }
QListWidget#mailReaderList::item:selected {
    background: #18345e;
    color: #e5eaf2;
    border: 2px solid #60a5fa;
}
QTextBrowser#mailViewerBody, EmailBodyView#mailViewerBody {
    background: #ffffff; border: 0; padding: 0;
}
QFrame#mailAttachmentPanel, QFrame#composeAttachmentCard, QFrame#composeSenderCard {
    background: #151d2a;
    border: 1px solid #2b374a;
    border-radius: 10px;
}
QLabel#mailAttachmentTitle, QLabel#composeFieldLabel {
    color: #d5dce7;
    font-weight: 600;
}
QListWidget#mailAttachmentList, QListWidget#composeAttachmentList {
    background: #101722;
    border: 1px solid #2b374a;
    border-radius: 7px;
    outline: 0;
}
QListWidget#mailAttachmentList::item, QListWidget#composeAttachmentList::item {
    color: #cbd5e1;
    padding: 7px 9px;
}
QListWidget#mailAttachmentList::item:selected,
QListWidget#composeAttachmentList::item:selected { background: #18345e; color: #bfdbfe; }
QPushButton#attachmentActionButton {
    min-height: 28px;
    padding: 3px 10px;
    border-radius: 7px;
}
QLabel#mailViewerFeedback { color: #6ee7b7; padding: 3px 8px; }
QDialog#composeDialog { background: #0f1520; }
QFrame#composeHeader { background: #101827; border-bottom: 1px solid #273244; }
QFrame#composeFooter { background: #101827; border-top: 1px solid #273244; }
QWidget#composeContent { background: #0f1520; }
QLabel#composeTitle { color: #f8fafc; font-size: 19px; font-weight: 700; }
QLabel#composeSubtitle, QLabel#composeHint { color: #8c99ad; }
QLabel#composeSenderValue { color: #93c5fd; }
QTextEdit#composeBody {
    background: #101722;
    color: #e5eaf2;
    border: 1px solid #344258;
    border-radius: 9px;
    padding: 10px;
}
QTextEdit#composeBody:focus { border: 1px solid #3b82f6; }

QDialog#updateDialog { background: transparent; }
QFrame#updateCard {
    background: #111925;
    border: 1px solid #2b374a;
    border-radius: 18px;
}
QFrame#updateHeader {
    background: #151d2a;
    border: 0;
    border-bottom: 1px solid #2b374a;
    border-top-left-radius: 18px;
    border-top-right-radius: 18px;
}
QWidget#updateContent { background: #111925; }
QFrame#updateFooter {
    background: #151d2a;
    border: 0;
    border-top: 1px solid #2b374a;
    border-bottom-left-radius: 18px;
    border-bottom-right-radius: 18px;
}
QLabel#updateHeaderIcon {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #3b82f6, stop:1 #0f9fa5);
    border-radius: 12px;
}
QLabel#updateTitle { color: #f8fafc; font-size: 21px; font-weight: 700; }
QLabel#updateHeaderSubtitle { color: #78869b; font-size: 11px; }
QToolButton#updateCloseButton {
    background: transparent;
    color: #8c99ad;
    border: 0;
    border-radius: 9px;
    padding: 0;
    font-size: 24px;
    font-weight: 400;
}
QToolButton#updateCloseButton:hover { background: #202b3b; color: #e5eaf2; }
QLabel#updateVersionBadge {
    background: #172f54;
    color: #93c5fd;
    border: 1px solid #244c80;
    border-radius: 9px;
    padding: 2px 10px;
    font-size: 13px;
    font-weight: 700;
}
QLabel#updateSummary { color: #a1adbf; font-size: 13px; padding: 2px 0 4px 0; }
QFrame#updateSeparator { color: #2b374a; background: #2b374a; border: 0; max-height: 1px; }
QLabel#updateSectionTitle { color: #e5eaf2; font-size: 14px; font-weight: 700; }
QTextBrowser#updateReleaseNotes {
    background: #0f1621;
    color: #c0c9d6;
    border: 1px solid #2b374a;
    border-radius: 10px;
    padding: 4px;
    selection-background-color: #244c80;
}
QFrame#updateProgressPanel {
    background: #141e2d;
    border: 1px solid #2b3a50;
    border-radius: 10px;
}
QLabel#updateProgressStatus { color: #d5dce7; font-size: 12px; font-weight: 600; }
QLabel#updateProgressPercent { color: #60a5fa; font-size: 12px; font-weight: 700; }
QLabel#updateProgressDetail { color: #8491a5; font-size: 11px; }
QProgressBar#updateProgressBar {
    background: #2a3648;
    border: 0;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
}
QProgressBar#updateProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #3b82f6, stop:1 #14b8a6);
    border-radius: 4px;
}
QFrame#updateCard[state="ready"] QLabel#updateProgressStatus { color: #6ee7b7; }
QFrame#updateCard[state="error"] QLabel#updateProgressStatus,
QFrame#updateCard[state="error"] QLabel#updateProgressPercent { color: #f87171; }
QDialog#updateDialog QPushButton#secondaryButton { min-width: 88px; padding: 8px 15px; }
QDialog#updateDialog QPushButton#primaryButton { min-width: 126px; padding: 9px 20px; }

QSplitter::handle:horizontal {
    background: #2d3a4e;
    margin: 0 2px;
    border-radius: 2px;
}
QSplitter::handle:vertical {
    background: #2d3a4e;
    margin: 2px 0;
    border-radius: 2px;
}
QSplitter::handle:hover { background: #3b82f6; }
QStatusBar {
    background: #151d2a;
    color: #8c99ad;
    border-top: 1px solid #273244;
    padding: 2px 8px;
}
QFrame#bottomToast {
    background: #e5eaf2;
    border: 1px solid #f8fafc;
    border-radius: 11px;
}
QLabel#bottomToastIcon {
    background: #047857;
    color: #ffffff;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 700;
}
QLabel#bottomToastText {
    color: #172033;
    font-size: 12px;
    font-weight: 600;
}
QFrame#bottomToast[tone="warning"] QLabel#bottomToastIcon {
    background: #c2410c;
    color: #ffffff;
}
QMenu {
    background: #151d2a;
    color: #d7deea;
    border: 1px solid #334156;
    border-radius: 10px;
    padding: 6px;
    font-weight: 400;
}
QMenu::item {
    background: transparent;
    color: #d7deea;
    border: 0;
    border-radius: 7px;
    padding: 8px 34px 8px 30px;
    margin: 1px 0;
}
QMenu::item:selected {
    background: #1b3150;
    color: #bfdbfe;
}
QMenu::item:checked {
    color: #d7deea;
}
QMenu::item:disabled {
    background: transparent;
    color: #667386;
}
QMenu::indicator {
    width: 15px;
    height: 15px;
    left: 8px;
}
QMenu::separator {
    background: #2b374a;
    height: 1px;
    margin: 6px 10px;
}
QMenu::scroller {
    background: #121a26;
    height: 18px;
}
QMenu::right-arrow {
    width: 8px;
    height: 8px;
    right: 10px;
}
QToolTip {
    background: #e8edf5;
    color: #0f1520;
    border: 1px solid #ffffff;
    border-radius: 6px;
    padding: 6px 9px;
}
QMessageBox QLabel { color: #e8edf5; min-width: 280px; }
QMessageBox QPushButton { min-width: 82px; }
QProgressBar {
    background: #101722;
    color: #e8edf5;
    border: 1px solid #344258;
    border-radius: 6px;
    text-align: center;
    min-height: 16px;
}
QProgressBar::chunk { background: #3b82f6; border-radius: 5px; }
QFileDialog QListView, QFileDialog QTreeView,
QFileDialog QHeaderView::section {
    background: #111925;
    color: #e5eaf2;
    border-color: #2b374a;
}
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: #3a475c;
    border-radius: 4px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover { background: #526177; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QDialog#closeWindowDialog { background: transparent; }
QFrame#closeDialogCard {
    background: #151d2a;
    border: 1px solid #334155;
    border-radius: 16px;
}
QLabel#closeDialogTitle { color: #f8fafc; font-size: 20px; font-weight: 700; }
QLabel#closeDialogSubtitle { color: #94a3b8; font-size: 12px; }
QPushButton#closeDialogDismiss {
    background: transparent; border: 0; color: #718096;
    font-size: 22px; font-weight: 400; padding: 0;
}
QPushButton#closeDialogDismiss:hover { background: #202b3b; color: #d5dce7; }
QPushButton#closeTrayOption, QPushButton#closeExitOption {
    background: #192332;
    border: 1px solid #334155;
    border-radius: 11px;
    padding: 0;
}
QPushButton#closeTrayOption:hover { background: #172a44; border-color: #3b82f6; }
QPushButton#closeExitOption:hover { background: #342027; border-color: #ef4444; }
QPushButton#closeTrayOption:focus, QPushButton#closeExitOption:focus {
    border: 2px solid #60a5fa;
}
QPushButton#closeTrayOption:disabled {
    background: #121a26; border-color: #273244;
}
QLabel#closeOptionTitle { color: #e5eaf2; font-size: 14px; font-weight: 600; }
QLabel#closeOptionDescription { color: #8c99ad; font-size: 11px; font-weight: 400; }
QLabel#closeOptionArrow { color: #718096; font-size: 22px; font-weight: 400; }
QLabel#closeOptionTitle:disabled, QLabel#closeOptionDescription:disabled,
QLabel#closeOptionArrow:disabled { color: #566277; }
QCheckBox#closeRememberChoice { color: #aab4c5; font-size: 12px; spacing: 8px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a475c; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #526177; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
