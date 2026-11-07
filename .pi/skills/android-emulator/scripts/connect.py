#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

UI = Path(__file__).with_name("ui.py")


def ui(device, timeout, *args):
    subprocess.run([sys.executable, str(UI), "--device", device, "--timeout", str(timeout), *args],
                   check=True, timeout=timeout + 10)


def adb(device, *args, timeout=15):
    sdk = Path(os.environ.get("ANDROID_SDK_ROOT", os.environ.get("ANDROID_HOME", str(Path.home() / "Android/Sdk"))))
    return subprocess.run([str(sdk / "platform-tools/adb"), "-s", device, *args],
                          capture_output=True, text=True, check=True, timeout=timeout)


def replace_text(device, tag, value, timeout):
    ui(device, timeout, "tap", tag)
    adb(device, "shell", "input", "keyevent", "KEYCODE_MOVE_END")
    adb(device, "shell", "input", "keyevent", *(("KEYCODE_DEL",) * 60))
    if value:
        adb(device, "shell", "input", "text", value)


def connect(device, url, password, timeout):
    if not device.startswith("emulator-"):
        raise ValueError("only emulator targets are permitted")
    if not url.startswith("http://"):
        raise ValueError("url must start with http:// (the app rejects anything else)")
    ui(device, timeout, "tap", "nav_tab_chats")
    ui(device, timeout, "tap", "account_entry")
    ui(device, timeout, "tap", "account_sign_out")
    ui(device, timeout, "tap", "connect_server")
    replace_text(device, "connect_server", url, timeout)
    ui(device, timeout, "tap", "connect_method_password")
    replace_text(device, "connect_password", password, timeout)
    ui(device, timeout, "tap", "connect_submit")
    ui(device, timeout, "wait", "nav_tab_chats")
    message = adb(device, "shell", "uiautomator", "dump", "/dev/tty").stdout
    if "connect_message" in message and "text=\"\"" not in message.split("connect_message", 1)[1][:200]:
        raise ValueError("the app reported a connection error; inspect the screen before retrying")
    print(f"connected {device} to {url}")


def main():
    parser = argparse.ArgumentParser(description="Drive the app's Connect screen by tags (emulator only)")
    parser.add_argument("--device", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--password-env", default="LLMDOCK_TEST_PASSWORD",
                        help="environment variable holding the password; never passed on argv")
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    password = os.environ.get(args.password_env)
    if not password:
        parser.error(f"set {args.password_env} in the environment (the password is not an argument)")
    try:
        connect(args.device, args.url, password, args.timeout)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"connect failed: {error}")


if __name__ == "__main__":
    main()
