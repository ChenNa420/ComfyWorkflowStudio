from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

APP_TITLE = "童语工坊 Launcher"
APP_VERSION = "v1.0"
BG = "#0e1218"
PANEL = "#11171f"
BORDER = "#2b3440"
MUTED = "#7d8998"
ORANGE = "#ff6b00"
GREEN = "#5bd042"
BLUE = "#269bff"
FOLDER = "#d77b2b"
ONLINE = "#43d563"
OFFLINE = "#6f7b89"

LAUNCHER_DIR = Path(__file__).resolve().parent
ROOT = LAUNCHER_DIR.parent
CONFIG_PATH = LAUNCHER_DIR / "launcher-config.json"
LOG_DIR = ROOT / "storage" / "logs"
LOG_PATH = LOG_DIR / "launcher.log"

DEFAULT_CONFIG = {
    "webUrl": "http://127.0.0.1:5174",
    "apiUrl": "http://127.0.0.1:8100",
    "comfyUrl": "http://127.0.0.1:8188",
    "comfyStartBat": "",
}

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def load_config() -> dict[str, str]:
    data = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            for key in data:
                value = loaded.get(key)
                if isinstance(value, str):
                    data[key] = value
        except Exception:
            logging.exception("Failed to read launcher config")
    return data


def save_config(config: dict[str, str]) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def port_open(port: int, timeout: float = 0.22) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.config_data = load_config()
        self.status_labels: dict[str, tk.Label] = {}
        self._closing = False

        self.title(APP_TITLE)
        self.geometry("590x310")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.after(150, self.refresh_status)

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=BG, height=30)
        header.pack(fill="x", padx=14, pady=(7, 4))
        header.pack_propagate(False)

        tk.Label(
            header,
            text=APP_VERSION,
            bg=BG,
            fg=MUTED,
            font=("Consolas", 8),
        ).pack(side="left", padx=(1, 0), pady=(3, 0))

        tk.Label(
            header,
            text="ComfyWorkflowStudio Launcher",
            bg=BG,
            fg=GREEN,
            font=("Microsoft YaHei UI", 12, "bold"),
        ).place(relx=0.5, rely=0.5, anchor="center")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="x", padx=12, pady=(0, 4))
        for column in range(3):
            body.grid_columnconfigure(column, weight=1, uniform="launcher_columns")

        services_outer, services = self._make_column(body, "-- SERVICES --", ORANGE)
        browser_outer, browser = self._make_column(body, "-- BROWSER --", GREEN)
        status_outer, status = self._make_column(body, "-- STATUS --", BLUE)

        services_outer.grid(row=0, column=0, padx=(0, 5), sticky="nsew")
        browser_outer.grid(row=0, column=1, padx=5, sticky="nsew")
        status_outer.grid(row=0, column=2, padx=(5, 0), sticky="nsew")

        self._action_button(services, "启动工作台", ORANGE, self.start_workbench).pack(fill="x", padx=6, pady=3)
        self._action_button(services, "停止工作台", ORANGE, self.stop_workbench).pack(fill="x", padx=6, pady=3)
        self._action_button(services, "重启工作台", ORANGE, self.restart_workbench).pack(fill="x", padx=6, pady=3)
        self._action_button(services, "启动 ComfyUI", ORANGE, self.start_comfyui).pack(fill="x", padx=6, pady=3)

        self._action_button(browser, "打开童语工坊", GREEN, lambda: self.open_url("webUrl")).pack(fill="x", padx=6, pady=3)
        self._action_button(browser, "打开 API", GREEN, lambda: self.open_url("apiUrl")).pack(fill="x", padx=6, pady=3)
        self._action_button(browser, "打开 ComfyUI", GREEN, lambda: self.open_url("comfyUrl")).pack(fill="x", padx=6, pady=3)
        self._action_button(browser, "设置 ComfyUI BAT", GREEN, self.choose_comfy_bat).pack(fill="x", padx=6, pady=3)

        for key, label, port in (
            ("api", "API       8100", 8100),
            ("web", "WEB       5174", 5174),
            ("comfy", "ComfyUI   8188", 8188),
            ("cdp", "GPT CDP   9222", 9222),
            ("relay", "Relay     9333", 9333),
        ):
            row = tk.Frame(status, bg=PANEL)
            row.pack(fill="x", pady=4)
            dot = tk.Label(row, text="●", bg=PANEL, fg=OFFLINE, font=("Consolas", 11, "bold"))
            dot.pack(side="left", padx=(9, 6))
            text = tk.Label(row, text=label, bg=PANEL, fg=MUTED, font=("Consolas", 8, "bold"))
            text.pack(side="left")
            self.status_labels[key] = dot

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x", padx=12, pady=(2, 6))

        folders = tk.Frame(self, bg=BG)
        folders.pack(fill="x", padx=10)
        folder_specs = [
            ("Project", ROOT),
            ("Output", ROOT / "storage" / "outputs"),
            ("Workflows", ROOT / "workflows"),
            ("Logs", LOG_DIR),
            ("GPT Browser", ROOT / "storage" / "chatgpt-image-browser"),
        ]
        for index, (label, path) in enumerate(folder_specs):
            button = self._action_button(folders, label, FOLDER, lambda p=path: self.open_folder(p), width=13)
            button.grid(row=0, column=index, padx=3, sticky="ew")
            folders.grid_columnconfigure(index, weight=1)

        self.footer = tk.Label(
            self,
            text="桌面快捷方式双击即可打开此面板 · 状态每 3 秒自动刷新",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        )
        self.footer.pack(fill="x", padx=12, pady=(7, 0))

    def _make_column(self, parent: tk.Widget, title: str, accent: str) -> tuple[tk.Frame, tk.Frame]:
        outer = tk.Frame(parent, bg=BG, height=185)
        outer.grid_propagate(False)
        outer.configure(height=185)

        tk.Label(
            outer,
            text=title,
            bg=BG,
            fg=accent,
            font=("Microsoft YaHei UI", 8, "bold"),
        ).pack(fill="x", pady=(0, 3))

        panel = tk.Frame(outer, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        panel.pack(fill="both", expand=True)
        return outer, panel

    def _action_button(
        self,
        parent: tk.Widget,
        text: str,
        accent: str,
        command,
        width: int = 18,
    ) -> tk.Frame:
        shell = tk.Frame(parent, bg=accent, bd=0, highlightthickness=0)
        button = tk.Button(
            shell,
            text=text,
            command=command,
            bg=PANEL,
            fg=accent,
            activebackground="#19222d",
            activeforeground=accent,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Microsoft YaHei UI", 8, "bold"),
            cursor="hand2",
            width=width,
            height=1,
            padx=5,
            pady=3,
        )
        button.pack(fill="both", expand=True, padx=1, pady=1)
        button.bind("<Enter>", lambda _event: button.configure(bg="#18212b"))
        button.bind("<Leave>", lambda _event: button.configure(bg=PANEL))
        return shell

    def _run_powershell(self, script_name: str, wait: bool = False) -> None:
        script = ROOT / script_name
        if not script.exists():
            messagebox.showerror(APP_TITLE, f"找不到脚本：\n{script}")
            return

        args = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        logging.info("Launching %s", script)
        if wait:
            subprocess.run(args, cwd=ROOT, creationflags=CREATE_NO_WINDOW, check=False)
        else:
            subprocess.Popen(args, cwd=ROOT, creationflags=CREATE_NO_WINDOW)

    def start_workbench(self) -> None:
        self.footer.config(text="正在启动童语工坊…")
        self._run_powershell("start-workbench.ps1")

    def stop_workbench(self) -> None:
        self.footer.config(text="正在停止童语工坊…")
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self) -> None:
        self._run_powershell("stop-workbench.ps1", wait=True)
        self.after(0, lambda: self.footer.config(text="停止命令已完成"))

    def restart_workbench(self) -> None:
        self.footer.config(text="正在重启童语工坊…")
        threading.Thread(target=self._restart_worker, daemon=True).start()

    def _restart_worker(self) -> None:
        self._run_powershell("stop-workbench.ps1", wait=True)
        time.sleep(1.2)
        self.after(0, lambda: self._run_powershell("start-workbench.ps1"))
        self.after(0, lambda: self.footer.config(text="重启命令已提交"))

    def choose_comfy_bat(self) -> bool:
        initial = self.config_data.get("comfyStartBat", "")
        initial_dir = str(Path(initial).parent) if initial and Path(initial).exists() else str(ROOT)
        selected = filedialog.askopenfilename(
            title="选择 Start ComfyUI.bat",
            initialdir=initial_dir,
            filetypes=[("Windows Batch", "*.bat"), ("All files", "*.*")],
        )
        if not selected:
            return False

        self.config_data["comfyStartBat"] = selected
        try:
            save_config(self.config_data)
        except Exception as exc:
            logging.exception("Failed to save config")
            messagebox.showerror(APP_TITLE, f"保存配置失败：\n{exc}")
            return False

        self.footer.config(text=f"已保存 ComfyUI 启动脚本：{Path(selected).name}")
        return True

    def start_comfyui(self) -> None:
        raw = self.config_data.get("comfyStartBat", "")
        path = Path(raw) if raw else None
        if path is None or not path.exists():
            if not self.choose_comfy_bat():
                return
            path = Path(self.config_data["comfyStartBat"])

        try:
            subprocess.Popen(["cmd.exe", "/c", str(path)], cwd=path.parent)
            self.footer.config(text="已提交 ComfyUI 启动命令")
        except Exception as exc:
            logging.exception("Failed to start ComfyUI")
            messagebox.showerror(APP_TITLE, f"启动 ComfyUI 失败：\n{exc}")

    def open_url(self, key: str) -> None:
        url = self.config_data.get(key, "")
        if not url:
            messagebox.showwarning(APP_TITLE, "该地址尚未配置。")
            return
        webbrowser.open(url)

    def open_folder(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            logging.exception("Failed to open folder %s", path)
            messagebox.showerror(APP_TITLE, f"无法打开目录：\n{path}\n\n{exc}")

    def refresh_status(self) -> None:
        if self._closing:
            return

        def worker() -> None:
            result = {
                "api": port_open(8100),
                "web": port_open(5174),
                "comfy": port_open(8188),
                "cdp": port_open(9222),
                "relay": port_open(9333),
            }
            self.after(0, lambda: self._apply_status(result))

        threading.Thread(target=worker, daemon=True).start()
        self.after(3000, self.refresh_status)

    def _apply_status(self, status: dict[str, bool]) -> None:
        if self._closing:
            return
        for key, online in status.items():
            label = self.status_labels.get(key)
            if label:
                label.config(fg=ONLINE if online else OFFLINE)

    def _on_close(self) -> None:
        self._closing = True
        self.destroy()


def main() -> int:
    setup_logging()
    try:
        app = Launcher()
        app.mainloop()
        return 0
    except Exception as exc:
        logging.exception("Launcher crashed")
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                APP_TITLE,
                f"Launcher 启动失败：\n{exc}\n\n日志：\n{LOG_PATH}",
            )
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
