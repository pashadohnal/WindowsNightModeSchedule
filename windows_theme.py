"""Switch the current user's Windows light/dark preference and notify windows.

Usage:
    python windows_theme.py dark
    python windows_theme.py light
    python windows_theme.py refresh

"refresh" sends the notifications without changing the registry.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
from time import sleep


PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

# Win32 message and SendMessageTimeout flags from winuser.h.
WM_SETTINGCHANGE = 0x001A
WM_THEMECHANGED = 0x031A
HWND_BROADCAST = 0xFFFF
SMTO_ABORTIFHUNG = 0x0002
SMTO_ERRORONEXIT = 0x0020
MESSAGE_TIMEOUT_MS = 1_000


def require_windows() -> None:
    if os.name != "nt":
        raise SystemExit("This script can only run on Windows.")


def set_theme_preferences(use_dark_mode: bool) -> None:
    """Write both current-user light/dark preferences."""
    import winreg

    # Windows stores 0 for dark and 1 for light.
    use_light_theme = 0 if use_dark_mode else 1

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        PERSONALIZE_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(
            key,
            "AppsUseLightTheme",
            0,
            winreg.REG_DWORD,
            use_light_theme,
        )
        winreg.SetValueEx(
            key,
            "SystemUsesLightTheme",
            0,
            winreg.REG_DWORD,
            use_light_theme,
        )


def configure_send_message_timeout():
    """Load User32 and describe SendMessageTimeoutW's C signature to ctypes."""
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send_message_timeout = user32.SendMessageTimeoutW

    # DWORD_PTR and LRESULT are pointer-sized on Windows.
    dword_ptr = ctypes.c_size_t
    lresult = wintypes.LPARAM

    send_message_timeout.argtypes = (
        wintypes.HWND,                  # hWnd
        wintypes.UINT,                  # Msg
        wintypes.WPARAM,                # wParam
        wintypes.LPARAM,                # lParam
        wintypes.UINT,                  # fuFlags
        wintypes.UINT,                  # uTimeout
        ctypes.POINTER(dword_ptr),       # lpdwResult
    )
    send_message_timeout.restype = lresult

    return send_message_timeout, dword_ptr


def redraw_window(hwnd: int) -> None:
    """Force a window to redraw itself."""
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.RedrawWindow.argtypes = (
        wintypes.HWND,  # hWnd
        wintypes.LPRECT,  # lprUpdate
        wintypes.HRGN,  # hrgnUpdate
        wintypes.UINT,  # flags
    )
    user32.RedrawWindow.restype = wintypes.BOOL

    RDW_INVALIDATE = 0x0001
    RDW_UPDATENOW = 0x0100
    RDW_ERASE = 0x0004

    if not user32.RedrawWindow(hwnd, None, None, RDW_INVALIDATE | RDW_UPDATENOW | RDW_ERASE):
        raise ctypes.WinError(ctypes.get_last_error())

def broadcast_theme_notifications() -> list[str]:
    """Notify top-level windows that color/theme state may have changed."""
    send_message_timeout, dword_ptr = configure_send_message_timeout()
    warnings: list[str] = []

    # Keep this buffer alive until the synchronous call returns. The
    # "ImmersiveColorSet" name is widely used by Windows theme switchers, but
    # Microsoft does not document it as a stable public dark-mode contract.
    setting_name = ctypes.create_unicode_buffer("ImmersiveColorSet")
    setting_name_address = ctypes.cast(setting_name, ctypes.c_void_p).value

    messages = (
        (WM_SETTINGCHANGE, setting_name_address, "WM_SETTINGCHANGE"),
        (WM_THEMECHANGED, 0, "WM_THEMECHANGED"),
    )

    for message, lparam, name in messages:
        receiver_result = dword_ptr()
        ctypes.set_last_error(0)

        completed = send_message_timeout(
            HWND_BROADCAST,
            message,
            0,
            lparam,
            SMTO_ABORTIFHUNG | SMTO_ERRORONEXIT,
            MESSAGE_TIMEOUT_MS,
            ctypes.byref(receiver_result),
        )

        if not completed:
            error = ctypes.get_last_error()
            detail = f"Windows error {error}" if error else "no detailed error"
            warnings.append(f"{name} failed or timed out ({detail}).")

    return warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Set the current user's Windows light/dark preference and broadcast "
            "theme-related notifications."
        )
    )
    parser.add_argument(
        "action",
        choices=("dark", "light", "refresh"),
        help="Select a theme, or only resend notifications with 'refresh'.",
    )
    return parser.parse_args()


def main() -> int:

    user32 = ctypes.windll.user32

    taskbar_handles = []

     # Get primary taskbar
    h_primary = user32.FindWindowW("Shell_TrayWnd", None)
    if h_primary:
        taskbar_handles.append(h_primary)
        
    # Enumerate and get all secondary taskbars
    h_secondary = None
    while True:
        h_secondary = user32.FindWindowExW(None, h_secondary, "Shell_SecondaryTrayWnd", None)
        if not h_secondary:
            break
        taskbar_handles.append(h_secondary)

    require_windows()
    args = parse_args()

    if args.action != "refresh":
        set_theme_preferences(use_dark_mode=args.action == "dark")
        print(f"Stored the {args.action} preference for apps and system UI.")



    warnings = broadcast_theme_notifications()
    if warnings:
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        print(
            "Some windows may not have refreshed. Reopening the affected window "
            "or restarting Explorer may still be necessary.",
            file=sys.stderr,
        )
        return 1

    sleep(1)  # Give Explorer a moment to process the theme change 
    # 2. Redraw ALL found taskbars to force them to pick up the new registry theme
    # Constants for RedrawWindow: RDW_INVALIDATE (0x0001) | RDW_UPDATENOW (0x0004) | RDW_ERASE (0x0004) | RDW_ALLCHILDREN (0x0080)
    
    for hwnd in taskbar_handles:
        # If your custom redraw_window function takes an HWND, use it here:
        # redraw_window(hwnd)
        
        # Or call the Win32 API directly to force an immediate deep redraw:
        redraw_window(hwnd)
    
    print("Theme notifications were broadcast to top-level windows.")
    print("Explorer may still retain cached UI; this script does not restart it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
