"""Rules that prevent capturing or typing into sensitive screens."""
from __future__ import annotations

import re

# Foreground processes whose screens are never captured or typed into.
BLOCKED_PROCESSES = {
    "consent.exe",  # UAC prompt
    "logonui.exe",
    "lockapp.exe",
    "credentialuibroker.exe",
    "securityhealthsystray.exe",
    "sechealthui.exe",
    "keepass.exe",
    "keepassxc.exe",
    "1password.exe",
    "bitwarden.exe",
    "lastpass.exe",
    "dashlane.exe",
    "nordpass.exe",
    "enpass.exe",
    "roboform.exe",
}

BLOCKED_TITLE = re.compile(
    r"(?i)(password|passwort|mot de passe|סיסמ|windows security|אבטחת windows|credential|sign in to|login|"
    r"התחברות|keepass|bitwarden|1password|lastpass|authenticator|bank|בנק)"
)

# Windows where typed text would be executed as a command.
SHELL_PROCESSES = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe", "conhost.exe",
    "openconsole.exe", "bash.exe", "wsl.exe", "mintty.exe", "regedit.exe", "mmc.exe",
}
RUN_DIALOG_TITLES = re.compile(r"(?i)^(run|הפעלה)$")


def window_is_sensitive(process: str, title: str) -> str | None:
    p = (process or "").lower()
    if p in BLOCKED_PROCESSES:
        return f"the foreground app ({process}) handles credentials or security"
    if title and BLOCKED_TITLE.search(title):
        return f"the window title suggests a sign-in, password or banking screen ('{title[:60]}')"
    return None


def window_executes_commands(process: str, title: str) -> bool:
    return (process or "").lower() in SHELL_PROCESSES or bool(title and RUN_DIALOG_TITLES.match(title.strip()))
