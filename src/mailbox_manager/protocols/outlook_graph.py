from __future__ import annotations

import base64
import binascii
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import uuid4

import httpx

from mailbox_manager.domain.models import (
    ConnectionResult,
    EmailAccount,
    FetchRequest,
    FetchResult,
    MailAttachment,
    MailFolder,
    MailMessage,
)
from mailbox_manager.domain.status import AccountStatus
from mailbox_manager.mail.parser import (
    MAX_ATTACHMENT_COUNT,
    MAX_ATTACHMENT_SIZE,
    MAX_INLINE_IMAGE_SIZE,
    MAX_TOTAL_ATTACHMENT_SIZE,
    clean_message_text,
    extract_matches,
    html_to_text,
    safe_attachment_filename,
    sanitize_email_html,
)
from mailbox_manager.mail.web_document import sanitize_email_web_source
from mailbox_manager.protocols.base import EmailClientBase
from mailbox_manager.services.send_service import OutgoingDraft, SendResult, SendStatus

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
LOGIN_ROOT = "https://login.microsoftonline.com"
GRAPH_MAX_SIMPLE_ATTACHMENT_BYTES = 3 * 1024 * 1024


class _GraphStatusError(Exception):
    def __init__(self, status_code: int, error_code: str = "") -> None:
        self.status_code = status_code
        self.error_code = error_code.casefold()


def _provider_error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        code = error.get("code")
        return code if isinstance(code, str) else ""
    return ""


class OutlookGraphClient(EmailClientBase):
    def __init__(
        self,
        account: EmailAccount,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        proxy: str | None = None,
    ) -> None:
        self._account = account
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            transport=transport,
            follow_redirects=False,
            headers={"Accept": "application/json"},
            proxy=proxy,
        )
        self._access_token = ""
        self._expires_at = datetime.min.replace(tzinfo=UTC)

    def _token(self) -> str:
        if self._access_token and datetime.now(UTC) < self._expires_at:
            return self._access_token
        tenant = quote(self._account.tenant or "common", safe="")
        response = self._client.post(
            f"{LOGIN_ROOT}/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": self._account.client_id,
                "grant_type": "refresh_token",
                "refresh_token": self._account.refresh_token,
            },
        )
        if response.status_code >= 400:
            raise _GraphStatusError(response.status_code, _provider_error_code(response))
        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise _GraphStatusError(401)
        expires_in = payload.get("expires_in", 3600)
        try:
            lifetime = max(60, min(int(expires_in), 86_400))
        except (TypeError, ValueError):
            lifetime = 3600
        self._access_token = token
        self._expires_at = datetime.now(UTC) + timedelta(seconds=lifetime - 30)
        return token

    def _get(self, url: str, params: dict[str, str | int] | None = None) -> dict[str, object]:
        response = self._client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {self._token()}"},
        )
        if response.status_code >= 400:
            raise _GraphStatusError(response.status_code, _provider_error_code(response))
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Microsoft Graph 返回了无效数据")
        return payload

    def test_connection(self) -> ConnectionResult:
        try:
            self._get(f"{GRAPH_ROOT}/me", {"$select": "id"})
            return ConnectionResult(AccountStatus.SUCCESS, "Graph 连接成功")
        except Exception as exc:
            status, detail = _classify_graph_error(exc)
            return ConnectionResult(status, detail)

    def list_folders(self) -> list[MailFolder]:
        try:
            payload = self._get(f"{GRAPH_ROOT}/me/mailFolders", {"$top": 100})
            return [
                MailFolder(str(item.get("id", "")), str(item.get("displayName", "")))
                for item in payload.get("value", [])
                if isinstance(item, dict) and item.get("id")
            ]
        except Exception:
            return []

    def fetch_messages(self, request: FetchRequest) -> FetchResult:
        messages: list[MailMessage] = []
        try:
            remaining: int | None = None if request.unlimited else request.max_messages
            folders = [(folder, folder) for folder in request.folders]
            if request.include_special_folders:
                known_references = {item[0].casefold() for item in folders}
                known_labels = {item[1].casefold() for item in folders}
                for candidate in self.list_folders():
                    if not _is_special_graph_folder(candidate):
                        continue
                    if (
                        candidate.name.casefold() in known_references
                        or candidate.display_name.casefold() in known_labels
                    ):
                        continue
                    folders.append(
                        (candidate.name, candidate.display_name or candidate.name)
                    )
                    known_references.add(candidate.name.casefold())
                    known_labels.add(candidate.display_name.casefold())
            for folder_reference, folder_label in folders:
                if remaining is not None and remaining <= 0:
                    break
                folder_id = (
                    "inbox"
                    if folder_reference.casefold() == "inbox"
                    else quote(folder_reference, safe="")
                )
                url = f"{GRAPH_ROOT}/me/mailFolders/{folder_id}/messages"
                first_page = True
                seen_urls: set[str] = set()
                while url and (remaining is None or remaining > 0):
                    if url in seen_urls:
                        break
                    seen_urls.add(url)
                    payload = self._get(
                        url,
                        {
                            "$top": 50 if remaining is None else min(remaining, 50),
                            "$select": (
                                "id,subject,from,toRecipients,receivedDateTime,body,"
                                "internetMessageHeaders,hasAttachments"
                            ),
                            "$orderby": "receivedDateTime desc",
                        }
                        if first_page
                        else None,
                    )
                    first_page = False
                    page_had_known_message = False
                    for item in payload.get("value", []):
                        if isinstance(item, dict):
                            message_id = str(item.get("id", ""))
                            if (folder_label, message_id) in request.known_transport_ids:
                                page_had_known_message = True
                                continue
                            message = self._parse_item(item, folder_label, request)
                            messages.append(message)
                            if (
                                message.matched_values
                                and request.post_action.value != "none"
                            ):
                                self.apply_action(
                                    message,
                                    request.post_action,
                                    request.action_target_folder,
                                    confirmed=request.confirmed_actions,
                                )
                            if remaining is not None:
                                remaining -= 1
                                if remaining <= 0:
                                    break
                    # Graph returns newest-first. Once cached mail appears, older
                    # pages need no body parsing or attachment requests.
                    if page_had_known_message:
                        break
                    next_link = payload.get("@odata.nextLink")
                    url = (
                        next_link
                        if isinstance(next_link, str) and next_link.startswith(GRAPH_ROOT)
                        else ""
                    )
            return FetchResult(AccountStatus.SUCCESS, tuple(messages), "Graph 收取完成")
        except Exception as exc:
            status, detail = _classify_graph_error(exc)
            return FetchResult(status, tuple(messages), detail)

    def _parse_item(
        self, item: dict[str, object], folder: str, request: FetchRequest
    ) -> MailMessage:
        body_value = item.get("body")
        body = body_value if isinstance(body_value, dict) else {}
        content = body.get("content", "")
        raw_content = str(content)[:2_000_000]
        message_id = str(item.get("id", ""))
        attachments = (
            self._message_attachments(message_id)
            if item.get("hasAttachments") or "cid:" in raw_content.casefold()
            else ()
        )
        html_body = ""
        web_html_body = ""
        if str(body.get("contentType", "")).casefold() == "html":
            inline_images = self._inline_images(attachments)
            html_body = sanitize_email_html(
                raw_content,
                inline_images=inline_images,
                remote_policy="preserve",
            )
            web_html_body = sanitize_email_web_source(
                raw_content,
                inline_images=inline_images,
                remote_policy="preserve",
            )
            text = html_to_text(raw_content)
        else:
            text = clean_message_text(raw_content)
        sender_value = item.get("from")
        sender = _graph_address(sender_value)
        sender_name = _graph_address_name(sender_value)
        recipient_values = item.get("toRecipients")
        recipients = tuple(
            address
            for address in (_graph_address(value) for value in recipient_values or [])
            if address
        )
        catch_all = ""
        header_values = item.get("internetMessageHeaders")
        for header in header_values or []:
            if isinstance(header, dict) and str(header.get("name", "")).casefold() in {
                "x-original-to",
                "delivered-to",
            }:
                catch_all = str(header.get("value", "")).casefold()
                break
        received_at = None
        received_value = item.get("receivedDateTime")
        if isinstance(received_value, str):
            with suppress(ValueError):
                received_at = datetime.fromisoformat(received_value.replace("Z", "+00:00"))
        subject = str(item.get("subject", ""))[:2000]
        return MailMessage(
            provider_message_id=message_id,
            folder=folder,
            transport_id=str(item.get("id", "")),
            subject=subject,
            sender=sender,
            sender_name=sender_name,
            recipients=recipients,
            catch_all_recipient=catch_all or (recipients[0] if recipients else ""),
            received_at=received_at,
            text_body=text,
            html_body=html_body,
            web_html_body=web_html_body,
            matched_values=extract_matches(
                f"{subject}\n{text}",
                keywords=request.keywords,
                custom_pattern=request.custom_pattern,
            ),
            attachments=attachments,
        )

    def _message_attachments(
        self, message_id: str
    ) -> tuple[MailAttachment, ...]:
        if not message_id:
            return ()
        identifier = quote(message_id, safe="")
        try:
            payload = self._get(
                f"{GRAPH_ROOT}/me/messages/{identifier}/attachments",
                {
                    "$top": 100,
                    "$select": (
                        "id,name,contentType,size,contentId,isInline,contentBytes"
                    ),
                },
            )
        except Exception:
            # A missing or oversized attachment must not make the readable message disappear.
            return ()
        attachments: list[MailAttachment] = []
        used_names: set[str] = set()
        stored_bytes = 0
        for item in payload.get("value", []):
            if not isinstance(item, dict) or len(attachments) >= MAX_ATTACHMENT_COUNT:
                continue
            index = len(attachments) + 1
            content_id = str(item.get("contentId", "")).strip().strip("<>").casefold()
            content_type = (
                str(item.get("contentType", "")).casefold()
                or "application/octet-stream"
            )
            filename = safe_attachment_filename(
                item.get("name") or f"附件-{index}",
                fallback_index=index,
            )
            filename = _unique_graph_filename(filename, used_names)
            try:
                declared_size = max(0, int(item.get("size", 0)))
            except (TypeError, ValueError):
                declared_size = 0
            encoded = item.get("contentBytes")
            raw: bytes | None = None
            truncated = declared_size > MAX_ATTACHMENT_SIZE
            if (
                not truncated
                and isinstance(encoded, str)
                and len(encoded) <= MAX_ATTACHMENT_SIZE * 2
            ):
                try:
                    candidate = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error):
                    candidate = b""
                if candidate and len(candidate) <= MAX_ATTACHMENT_SIZE:
                    if stored_bytes + len(candidate) <= MAX_TOTAL_ATTACHMENT_SIZE:
                        raw = candidate
                        stored_bytes += len(candidate)
                    else:
                        truncated = True
                elif encoded:
                    truncated = True
            elif encoded or declared_size:
                truncated = True
            size = declared_size or (len(raw) if raw is not None else 0)
            attachments.append(
                MailAttachment(
                    filename=filename,
                    content_type=content_type,
                    size=size,
                    content_id=content_id,
                    disposition="inline" if item.get("isInline") else "attachment",
                    provider_attachment_id=str(item.get("id", "")),
                    content=raw,
                    is_truncated=truncated or raw is None,
                )
            )
        return tuple(attachments)

    @staticmethod
    def _inline_images(
        attachments: tuple[MailAttachment, ...],
    ) -> dict[str, tuple[str, bytes]]:
        return {
            attachment.content_id: (attachment.content_type, attachment.content)
            for attachment in attachments
            if attachment.disposition == "inline"
            and attachment.content_id
            and attachment.content is not None
            and attachment.content_type.startswith("image/")
            and len(attachment.content) <= MAX_INLINE_IMAGE_SIZE
        }

    def send_message(self, draft: OutgoingDraft) -> SendResult:
        """Submit a message through Graph sendMail using simple file attachments."""

        tracking_id = str(uuid4())
        if (
            any(
                attachment.size > GRAPH_MAX_SIMPLE_ATTACHMENT_BYTES
                for attachment in draft.attachments
            )
            or draft.attachment_bytes > GRAPH_MAX_SIMPLE_ATTACHMENT_BYTES
        ):
            return SendResult(
                SendStatus.ATTACHMENT_TOO_LARGE,
                "Microsoft Graph 直接发件的附件总大小不能超过 3 MB",
                tracking_id,
            )
        message: dict[str, object] = {
            "subject": draft.subject,
            "body": {
                "contentType": "HTML" if draft.html_body else "Text",
                "content": draft.html_body or draft.text_body,
            },
            "toRecipients": _graph_recipients(draft.to),
            "internetMessageHeaders": [
                {"name": "x-maildesk-tracking-id", "value": tracking_id}
            ],
        }
        if draft.cc:
            message["ccRecipients"] = _graph_recipients(draft.cc)
        if draft.bcc:
            message["bccRecipients"] = _graph_recipients(draft.bcc)
        if draft.attachments:
            message["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": attachment.filename,
                    "contentType": attachment.content_type,
                    "contentBytes": base64.b64encode(attachment.content).decode("ascii"),
                }
                for attachment in draft.attachments
            ]
        try:
            response = self._client.post(
                f"{GRAPH_ROOT}/me/sendMail",
                json={"message": message, "saveToSentItems": draft.save_to_sent},
                headers={
                    "Authorization": f"Bearer {self._token()}",
                    "client-request-id": tracking_id,
                    "return-client-request-id": "true",
                },
            )
            if response.status_code < 200 or response.status_code >= 300:
                raise _GraphStatusError(
                    response.status_code,
                    _provider_error_code(response),
                )
            return SendResult(SendStatus.SUCCESS, "邮件已提交给 Microsoft Graph", tracking_id)
        except Exception as exc:
            status, detail = _classify_graph_send_error(exc)
            return SendResult(status, detail, tracking_id)

    def close(self) -> None:
        self._access_token = ""
        self._client.close()

    def apply_action(
        self,
        message: MailMessage,
        action,
        target_folder: str = "",
        *,
        confirmed: bool = False,
    ) -> bool:
        from mailbox_manager.domain.models import PostAction

        if not confirmed or not message.transport_id or action is PostAction.NONE:
            return False
        identifier = quote(message.transport_id, safe="")
        base = f"{GRAPH_ROOT}/me/messages/{identifier}"
        headers = {"Authorization": f"Bearer {self._token()}"}
        if action is PostAction.MARK_READ:
            response = self._client.patch(base, json={"isRead": True}, headers=headers)
        elif action is PostAction.MOVE:
            if not target_folder:
                return False
            destination_id = target_folder
            normalized_target = target_folder.casefold()
            for folder in self.list_folders():
                if normalized_target in {
                    folder.name.casefold(),
                    folder.display_name.casefold(),
                }:
                    destination_id = folder.name
                    break
            response = self._client.post(
                f"{base}/move",
                json={"destinationId": destination_id},
                headers=headers,
            )
        elif action is PostAction.DELETE:
            response = self._client.delete(base, headers=headers)
        else:
            return False
        if response.status_code >= 400:
            raise _GraphStatusError(response.status_code)
        return True


def _unique_graph_filename(filename: str, used_names: set[str]) -> str:
    candidate = filename
    stem, dot, suffix = filename.rpartition(".")
    if not dot:
        stem, suffix = filename, ""
    counter = 2
    while candidate.casefold() in used_names:
        candidate = f"{stem} ({counter}){'.' + suffix if suffix else ''}"
        counter += 1
    used_names.add(candidate.casefold())
    return candidate


def _graph_address(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    email_address = value.get("emailAddress")
    if not isinstance(email_address, dict):
        return ""
    address = email_address.get("address")
    return str(address).casefold() if address else ""


def _graph_address_name(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    email_address = value.get("emailAddress")
    if not isinstance(email_address, dict):
        return ""
    return str(email_address.get("name") or "").strip()[:500]


def _graph_recipients(values: tuple[str, ...]) -> list[dict[str, dict[str, str]]]:
    return [{"emailAddress": {"address": address}} for address in values]


def _is_special_graph_folder(folder: MailFolder) -> bool:
    normalized = f"{folder.name} {folder.display_name}".casefold()
    return any(
        token in normalized
        for token in (
            "junk",
            "spam",
            "trash",
            "deleted",
            "垃圾",
            "废件",
            "已删除",
            "删除邮件",
        )
    )


def _classify_graph_error(exc: Exception) -> tuple[AccountStatus, str]:
    if isinstance(exc, _GraphStatusError):
        if exc.error_code == "invalid_grant":
            return AccountStatus.AUTH_FAILED, "Refresh Token 已失效或被撤销"
        if exc.error_code in {"invalid_client", "unauthorized_client"}:
            return AccountStatus.CONFIG_ERROR, "Microsoft Client ID 无效或不允许此授权方式"
        if exc.error_code in {"interaction_required", "consent_required"}:
            return AccountStatus.AUTH_FAILED, "Microsoft 账号需要重新登录并授权"
        if exc.status_code == 403:
            return AccountStatus.AUTH_FAILED, "Microsoft Graph 缺少 Mail.Read 邮件读取权限"
        if exc.status_code in {400, 401}:
            return AccountStatus.AUTH_FAILED, "Microsoft OAuth 鉴权失败，请检查授权信息"
        if exc.status_code == 429:
            return AccountStatus.RATE_LIMITED, "Microsoft Graph 请求受到限流，请稍后重试"
        if exc.status_code >= 500:
            return AccountStatus.NETWORK_ERROR, "Microsoft Graph 服务暂时不可用"
    if isinstance(exc, httpx.TimeoutException):
        return AccountStatus.TIMEOUT, "Microsoft Graph 连接超时"
    if isinstance(exc, httpx.HTTPError):
        return AccountStatus.NETWORK_ERROR, "无法连接 Microsoft Graph"
    return AccountStatus.UNKNOWN_ERROR, "Microsoft Graph 返回了无法处理的数据"


def _classify_graph_send_error(exc: Exception) -> tuple[SendStatus, str]:
    if isinstance(exc, _GraphStatusError):
        if exc.error_code == "invalid_grant":
            return SendStatus.AUTH_FAILED, "Refresh Token 已失效或被撤销"
        if exc.error_code in {"invalid_client", "unauthorized_client"}:
            return SendStatus.CONFIG_ERROR, "Microsoft Client ID 无效或不允许此授权方式"
        if exc.error_code in {"interaction_required", "consent_required"}:
            return SendStatus.AUTH_FAILED, "Microsoft 账号需要重新登录并授权"
        if exc.error_code in {
            "errormessagesizeexceeded",
            "requestentitytoolarge",
        } or exc.status_code == 413:
            return SendStatus.ATTACHMENT_TOO_LARGE, "邮件或附件超过 Microsoft Graph 限制"
        if exc.status_code == 403:
            return SendStatus.AUTH_FAILED, "Microsoft Graph 缺少 Mail.Send 发件权限"
        if exc.status_code == 401:
            return SendStatus.AUTH_FAILED, "Microsoft OAuth 鉴权失败，请重新授权"
        if exc.status_code == 400:
            return SendStatus.VALIDATION_ERROR, "Microsoft Graph 无法接受发件内容"
        if exc.status_code == 429:
            return SendStatus.RATE_LIMITED, "Microsoft Graph 发件受到限流，请稍后重试"
        if exc.status_code >= 500:
            return SendStatus.PROVIDER_ERROR, "Microsoft Graph 发件服务暂时不可用"
        return SendStatus.PROVIDER_ERROR, "Microsoft Graph 拒绝了本次发件"
    if isinstance(exc, httpx.TimeoutException):
        return SendStatus.TIMEOUT, "Microsoft Graph 发件连接超时"
    if isinstance(exc, httpx.HTTPError):
        return SendStatus.NETWORK_ERROR, "无法连接 Microsoft Graph 发件服务"
    if isinstance(exc, (TypeError, ValueError)):
        return SendStatus.VALIDATION_ERROR, "Microsoft Graph 发件数据格式不正确"
    return SendStatus.UNKNOWN_ERROR, "Microsoft Graph 发件发生未知错误"
