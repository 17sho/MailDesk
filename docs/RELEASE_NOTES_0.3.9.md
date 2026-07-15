# MailDesk v0.3.9

This release focuses on reliable cross-platform updates, portable user data,
incremental mail synchronization, and smaller macOS packages.

## Highlights

- Frozen Windows and macOS builds now keep `MailDesk Data` and
  `.maildesk-update` beside the installed application. Downloads and atomic
  replacement therefore stay on the same disk selected by the user.
- Existing databases, protected key markers, logs, and optional EML files are
  migrated from the legacy system profile after a SQLite integrity check.
- The update check, download, and installer hand-off use a dedicated serial
  thread pool, so slow IMAP jobs cannot block “Restart and install”.
- Windows `onefile`/`onedir` and macOS `.app` updates replace only program
  files. The sibling `MailDesk Data` directory survives updates and rollbacks.
- IMAP UID, POP3 UIDL, and Microsoft Graph message IDs are persisted. Later
  refreshes download only unseen mail and skip repeated Graph attachment calls.
- “Fetch now” checks one newest unseen message for the active account.
- Remote images load concurrently, validate actual PNG/JPEG/GIF/WebP
  signatures, and use a bounded in-memory cache. Reading a complete MIME/Graph
  message does not require saving an EML file.
- Saving EML originals is now opt-in, reducing long-term disk usage.
- macOS builds exclude unused Qt 3D, Multimedia, PDF, Virtual Keyboard, and
  unrelated binding frameworks while retaining the WebEngine reader stack.

## Upgrade note

Older clients still stage v0.3.9 in their legacy profile directory. On the
first v0.3.9 startup MailDesk acknowledges that old installer before moving
data, preventing a false rollback. Legacy cache cleanup is completed safely on
the next launch. If an older client cannot start its installer at all, install
v0.3.9 manually once; automatic updates from v0.3.9 onward use the new layout.

Windows and macOS remain on the same stable v0.3.9 release line. macOS builds
are produced natively for Apple Silicon and Intel and remain unsigned/notarized
because the project has no Apple Developer ID certificate.
