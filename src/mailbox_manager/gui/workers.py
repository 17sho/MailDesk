from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from mailbox_manager.domain.models import EmailAccount, FetchRequest
from mailbox_manager.domain.status import AccountStatus
from mailbox_manager.protocols.oauth import OAuthTokenProvider
from mailbox_manager.protocols.smtp_client import SmtpClient
from mailbox_manager.services.discovery_service import DiscoveryService
from mailbox_manager.services.fetch_service import FetchService
from mailbox_manager.services.security_audit import GraphSecurityAuditService
from mailbox_manager.services.security_authorization import GraphDeviceAuthorizationService
from mailbox_manager.services.send_service import OutgoingDraft, SendService
from mailbox_manager.services.translation_service import TranslationService
from mailbox_manager.services.update_service import StagedUpdate, UpdateInfo, UpdateService


class FetchWorkerSignals(QObject):
    status = Signal(int, object, str)
    result = Signal(int, object)
    finished = Signal(int)


class FetchWorker(QRunnable):
    def __init__(
        self,
        service: FetchService,
        account: EmailAccount,
        request: FetchRequest,
        stop_event: threading.Event,
    ) -> None:
        super().__init__()
        self.service = service
        self.account = account
        self.request = request
        self.stop_event = stop_event
        self.signals = FetchWorkerSignals()

    @Slot()
    def run(self) -> None:
        account_id = self.account.account_id or 0
        if self.stop_event.is_set():
            self.signals.status.emit(account_id, AccountStatus.CANCELLED, "任务已停止")
            self.signals.finished.emit(account_id)
            return
        self.signals.status.emit(account_id, AccountStatus.CONNECTING, "正在连接")
        try:
            result = self.service.fetch_account(self.account, self.request)
            self.signals.result.emit(account_id, result)
            self.signals.status.emit(account_id, result.status, result.detail)
        except Exception:
            self.signals.status.emit(account_id, AccountStatus.UNKNOWN_ERROR, "收件任务异常")
        finally:
            self.signals.finished.emit(account_id)


class SmtpProbeSignals(QObject):
    result = Signal(int, object, str)
    finished = Signal(int)


class SmtpProbeWorker(QRunnable):
    def __init__(self, account: EmailAccount) -> None:
        super().__init__()
        self.account = account
        self.signals = SmtpProbeSignals()

    @Slot()
    def run(self) -> None:
        account_id = self.account.account_id or 0
        token = ""
        provider = None
        client = None
        try:
            if self.account.refresh_token and self.account.client_id:
                provider = OAuthTokenProvider()
                token = provider.access_token(self.account)
            client = SmtpClient(self.account, oauth_access_token=token)
            probe_id = client.send_probe(
                self.account.email, confirmed_owned_target=True
            )
            self.signals.result.emit(
                account_id, AccountStatus.SUCCESS, f"SMTP 探测邮件已发送：{probe_id}"
            )
        except Exception:
            self.signals.result.emit(
                account_id, AccountStatus.NETWORK_ERROR, "SMTP 探测失败，请检查配置和权限"
            )
        finally:
            if client is not None:
                client.close()
            if provider is not None:
                provider.close()
            self.signals.finished.emit(account_id)


class DiscoverySignals(QObject):
    result = Signal(int, object)
    finished = Signal(int)


class DiscoveryWorker(QRunnable):
    def __init__(self, account: EmailAccount) -> None:
        super().__init__()
        self.account = account
        self.signals = DiscoverySignals()

    @Slot()
    def run(self) -> None:
        account_id = self.account.account_id or 0
        try:
            result = DiscoveryService().discover(self.account.email, self.account.secret)
            self.signals.result.emit(account_id, result)
        except Exception:
            self.signals.result.emit(account_id, None)
        finally:
            self.signals.finished.emit(account_id)


class SecurityAuditSignals(QObject):
    result = Signal(int, object, object)
    finished = Signal(int)


class SecurityAuditWorker(QRunnable):
    def __init__(self, account: EmailAccount) -> None:
        super().__init__()
        self.account = account
        self.signals = SecurityAuditSignals()

    @Slot()
    def run(self) -> None:
        account_id = self.account.account_id or 0
        service = GraphSecurityAuditService(self.account)
        try:
            findings = service.audit_forwarding_rules()
            self.signals.result.emit(account_id, findings, None)
        except Exception as exc:
            self.signals.result.emit(account_id, [], exc)
        finally:
            service.close()
            self.signals.finished.emit(account_id)


class SecurityConsentSignals(QObject):
    challenge = Signal(int, object)
    result = Signal(int, str, object)
    finished = Signal(int)


class SecurityConsentWorker(QRunnable):
    def __init__(self, account: EmailAccount) -> None:
        super().__init__()
        self.account = account
        self.signals = SecurityConsentSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        account_id = self.account.account_id or 0
        service = GraphDeviceAuthorizationService()
        try:
            challenge = service.request_challenge(self.account)
            self.signals.challenge.emit(account_id, challenge)
            refresh_token = service.wait_for_refresh_token(
                self.account,
                challenge,
                cancelled=self._cancelled.is_set,
            )
            self.signals.result.emit(account_id, refresh_token, None)
        except Exception as exc:
            self.signals.result.emit(account_id, "", exc)
        finally:
            service.close()
            self.signals.finished.emit(account_id)


class TranslationSignals(QObject):
    result = Signal(int, str, object)
    finished = Signal(int)


class TranslationWorker(QRunnable):
    def __init__(
        self,
        generation: int,
        text: str,
        target_language: str,
        service: TranslationService,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.text = text
        self.target_language = target_language
        self.service = service
        self.signals = TranslationSignals()

    @Slot()
    def run(self) -> None:
        try:
            translated = self.service.translate(
                self.text,
                target_language=self.target_language,
            )
            self.signals.result.emit(self.generation, translated, None)
        except Exception as exc:
            self.signals.result.emit(self.generation, "", exc)
        finally:
            self.signals.finished.emit(self.generation)


class SendBatchSignals(QObject):
    result = Signal(object, object)
    finished = Signal()


class SendBatchWorker(QRunnable):
    def __init__(
        self,
        service: SendService,
        accounts: list[EmailAccount],
        draft: OutgoingDraft,
    ) -> None:
        super().__init__()
        self.service = service
        self.accounts = accounts
        self.draft = draft
        self.signals = SendBatchSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.send_batch(
                self.accounts,
                self.draft,
                confirmed=True,
            )
            self.signals.result.emit(result, None)
        except Exception as exc:
            self.signals.result.emit(None, exc)
        finally:
            self.signals.finished.emit()


class UpdateCheckSignals(QObject):
    result = Signal(object, object)
    finished = Signal()


class UpdateCheckWorker(QRunnable):
    """Check GitHub releases without blocking the Qt event loop."""

    def __init__(self, service: UpdateService) -> None:
        super().__init__()
        self.service = service
        self.signals = UpdateCheckSignals()

    @Slot()
    def run(self) -> None:
        try:
            update: UpdateInfo | None = self.service.check_for_update()
            self.signals.result.emit(update, None)
        except Exception as exc:
            self.signals.result.emit(None, exc)
        finally:
            self.signals.finished.emit()


class UpdateInstallSignals(QObject):
    status = Signal(str)
    result = Signal(object, object)
    finished = Signal()


class UpdateInstallWorker(QRunnable):
    """Verify staged files and hand off to the updater without blocking Qt."""

    def __init__(self, service: UpdateService, staged: StagedUpdate) -> None:
        super().__init__()
        self.service = service
        self.staged = staged
        self.signals = UpdateInstallSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.status.emit("正在校验暂存更新文件…")
            plan = self.service.create_installer_plan(self.staged)
            self.signals.status.emit("正在启动外部安装助手…")
            self.service.launch_installer(plan)
            self.signals.result.emit(plan, None)
        except Exception as exc:
            self.signals.result.emit(None, exc)
        finally:
            self.signals.finished.emit()


class UpdateDownloadSignals(QObject):
    progress = Signal(str, int, object)
    status = Signal(str, str)
    result = Signal(str, object, object)
    finished = Signal(str)


class UpdateDownloadWorker(QRunnable):
    """Download, verify and safely stage an update in the background."""

    def __init__(
        self,
        service: UpdateService,
        update: UpdateInfo,
        operation_id: str = "",
    ) -> None:
        super().__init__()
        self.service = service
        self.update = update
        self.operation_id = operation_id
        self.signals = UpdateDownloadSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.status.emit(self.operation_id, "正在下载并校验更新包…")
            downloaded = self.service.download_update(
                self.update,
                progress=lambda received, total: self.signals.progress.emit(
                    self.operation_id, received, total
                ),
                cancelled=self._cancelled.is_set,
            )
            self.signals.status.emit(self.operation_id, "下载完成，正在安全解压…")
            staged: StagedUpdate = self.service.stage_update(
                downloaded,
                cancelled=self._cancelled.is_set,
            )
            self.signals.result.emit(self.operation_id, staged, None)
        except Exception as exc:
            self.signals.result.emit(self.operation_id, None, exc)
        finally:
            self.signals.finished.emit(self.operation_id)
