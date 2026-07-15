# MailDesk v0.3.8

## macOS crash fix

- Fixed the PyInstaller/PySide6 QtWebEngine framework layout on both Intel and Apple Silicon builds.
- QtWebEngine Helper and Chromium resources are now collected under `Versions/A`, matching the framework's public `Helpers` and `Resources` symlinks.
- Fixed the `SIGABRT` crash when selecting a message and initializing `QWebEngineProfile` on macOS 13 and later.

## Release verification

- The macOS pipeline verifies the resolved Helper executable and Chromium resource paths.
- The packaged app must initialize the real email reader and exit cleanly before ZIP or DMG artifacts are created.
- Windows and macOS remain on the same stable v0.3.8 release line.
