#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import stat
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from string import ascii_lowercase, digits
from typing import Iterable

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import pygame
except Exception as exc:  # pragma: no cover - optional runtime dependency
    pygame = None
    PYGAME_IMPORT_ERROR = exc
else:
    PYGAME_IMPORT_ERROR = None

from PySide6.QtCore import QProcess, QSettings, QStringListModel, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "SMB Remap Studio"
ORG_NAME = "tmac"
IS_WINDOWS = sys.platform.startswith("win")

KEYBOARD_ORDER = ["up", "down", "left", "right", "jump", "special"]
GAMEPAD_ORDER = ["jump", "special", "useanalog"]

DEFAULT_CONFIG = {
    "keyboard": {
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
        "jump": "space",
        "special": "shift",
    },
    "gamepad": {
        "jump": "1",
        "special": "3",
        "useanalog": "true",
    },
}

ACTION_LABELS = {
    "up": "上",
    "down": "下",
    "left": "左",
    "right": "右",
    "jump": "跳跃",
    "special": "冲刺 / 特殊",
}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenChoice:
    label: str
    token: str


@dataclass(frozen=True)
class KeyboardPreset:
    name: str
    description: str
    mapping: dict[str, str]


@dataclass(frozen=True)
class GamepadPreset:
    name: str
    description: str
    mapping: dict[str, str]
    use_analog: bool = True


@dataclass
class GameLayout:
    root_dir: Path
    game_dir: Path
    config_path: Path
    launch_program: Path | None
    launch_cwd: Path | None
    icon_path: Path | None


def normalize_token(token: str) -> str:
    return token.strip().lower()


def resource_dirs() -> list[Path]:
    dirs: list[Path] = [Path.cwd()]
    if hasattr(sys, "_MEIPASS"):
        dirs.append(Path(getattr(sys, "_MEIPASS")).resolve())
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent)
    dirs.append(Path(__file__).resolve().parent)

    unique_dirs: list[Path] = []
    seen: set[Path] = set()
    for item in dirs:
        if item not in seen:
            unique_dirs.append(item)
            seen.add(item)
    return unique_dirs


def runtime_app_dirs() -> list[Path]:
    dirs = resource_dirs()
    for base in list(dirs):
        dirs.append(base / "game")

    unique_dirs: list[Path] = []
    seen: set[Path] = set()
    for item in dirs:
        if item not in seen:
            unique_dirs.append(item)
            seen.add(item)
    return unique_dirs


def find_bundled_icon() -> Path | None:
    candidates = [
        ("assets", "app-icon.svg"),
        ("assets", "app-icon.png"),
        ("game", "icon.png"),
    ]
    for base in resource_dirs():
        for candidate in candidates:
            path = base.joinpath(*candidate)
            if path.is_file():
                return path
    return None


def detect_default_root() -> Path | None:
    for candidate in runtime_app_dirs():
        try:
            return resolve_game_layout(candidate).root_dir
        except ConfigError:
            continue
    return None


def find_parent_root(game_dir: Path) -> Path:
    parent = game_dir.parent
    parent_markers = [
        parent / "start.bash",
        parent / "SuperMeatBoy.exe",
    ]
    if game_dir.name == "game" and any(marker.is_file() for marker in parent_markers):
        return parent
    return game_dir


def detect_launch_target(root_dir: Path, game_dir: Path) -> tuple[Path | None, Path | None]:
    candidates: list[tuple[Path, Path]] = []

    windows_candidates = [
        (root_dir / "SuperMeatBoy.exe", root_dir),
        (game_dir / "SuperMeatBoy.exe", game_dir),
    ]
    linux_candidates = []
    if (root_dir / "start.bash").is_file():
        linux_candidates.append((root_dir / "start.bash", root_dir))

    arch = platform.machine().lower()
    if arch in {"x86_64", "amd64"}:
        linux_candidates.extend(
            [
                (game_dir / "amd64" / "SuperMeatBoy", game_dir),
                (game_dir / "x86" / "SuperMeatBoy", game_dir),
            ]
        )
    else:
        linux_candidates.extend(
            [
                (game_dir / "x86" / "SuperMeatBoy", game_dir),
                (game_dir / "amd64" / "SuperMeatBoy", game_dir),
            ]
        )

    candidates.extend(windows_candidates if IS_WINDOWS else linux_candidates)
    candidates.extend(linux_candidates if IS_WINDOWS else windows_candidates)
    launch_program, launch_cwd = next(((program, cwd) for program, cwd in candidates if program.is_file()), (None, None))
    return launch_program, launch_cwd


def dependency_update_hint() -> str:
    return "请运行仓库里的 setup 脚本更新依赖，或使用最新打包版。"


def resolve_game_layout(selected_dir: os.PathLike[str] | str) -> GameLayout:
    path = Path(selected_dir).expanduser().resolve()

    if (path / "game" / "buttonmap.cfg").is_file():
        root_dir = path
        game_dir = path / "game"
    elif (path / "buttonmap.cfg").is_file():
        game_dir = path
        root_dir = find_parent_root(path)
    else:
        raise ConfigError("未找到 buttonmap.cfg。请选择游戏安装根目录，或直接选择包含 buttonmap.cfg 的目录。")

    config_path = game_dir / "buttonmap.cfg"
    icon_candidates = [
        game_dir / "icon.png",
        root_dir / "icon.png",
        root_dir / "game" / "icon.png",
    ]
    icon_path = next((item for item in icon_candidates if item.is_file()), None)

    launch_program, launch_cwd = detect_launch_target(root_dir, game_dir)

    return GameLayout(
        root_dir=root_dir,
        game_dir=game_dir,
        config_path=config_path,
        launch_program=launch_program,
        launch_cwd=launch_cwd,
        icon_path=icon_path,
    )


def load_buttonmap(config_path: Path) -> dict[str, dict[str, str]]:
    text = config_path.read_text(encoding="utf-8", errors="ignore")
    sections = {
        "keyboard": dict(DEFAULT_CONFIG["keyboard"]),
        "gamepad": dict(DEFAULT_CONFIG["gamepad"]),
    }
    matches = re.finditer(r"(?ms)\b(\w+)\s*\{(.*?)\}", text)
    found_any = False
    for match in matches:
        found_any = True
        section_name = match.group(1).strip().lower()
        body = match.group(2)
        if section_name not in sections:
            sections[section_name] = {}
        for pair in re.finditer(r'(?m)^\s*(\w+)\s*=\s*"([^"]*)"\s*;', body):
            key = pair.group(1).strip().lower()
            value = normalize_token(pair.group(2))
            sections[section_name][key] = value
    if not found_any:
        raise ConfigError(f"无法解析配置文件：{config_path}")
    return sections


def format_buttonmap(sections: dict[str, dict[str, str]]) -> str:
    keyboard = dict(DEFAULT_CONFIG["keyboard"])
    keyboard.update(sections.get("keyboard", {}))
    gamepad = dict(DEFAULT_CONFIG["gamepad"])
    gamepad.update(sections.get("gamepad", {}))

    lines = ["keyboard", "{"]
    for key in KEYBOARD_ORDER:
        lines.append(f'\t{key}="{normalize_token(keyboard[key])}";')
    for key in sorted(set(keyboard) - set(KEYBOARD_ORDER)):
        lines.append(f'\t{key}="{normalize_token(keyboard[key])}";')

    lines.extend(["}", "", "gamepad", "{"])
    for key in GAMEPAD_ORDER:
        lines.append(f'\t{key}="{normalize_token(gamepad[key])}";')
    for key in sorted(set(gamepad) - set(GAMEPAD_ORDER)):
        lines.append(f'\t{key}="{normalize_token(gamepad[key])}";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_buttonmap(config_path: Path, sections: dict[str, dict[str, str]]) -> Path:
    if not config_path.is_file():
        raise ConfigError(f"配置文件不存在：{config_path}")

    backup_path = config_path.with_name(f"{config_path.name}.bak")
    shutil.copy2(config_path, backup_path)

    original_mode = stat.S_IMODE(config_path.stat().st_mode)
    temp_path = config_path.with_name(f"{config_path.name}.tmp")
    temp_path.write_text(format_buttonmap(sections), encoding="utf-8")
    os.chmod(temp_path, original_mode)
    os.replace(temp_path, config_path)
    return backup_path


def build_keyboard_choices() -> list[TokenChoice]:
    choices = [
        TokenChoice("上方向键", "up"),
        TokenChoice("下方向键", "down"),
        TokenChoice("左方向键", "left"),
        TokenChoice("右方向键", "right"),
        TokenChoice("空格", "space"),
        TokenChoice("回车", "return"),
        TokenChoice("Tab", "tab"),
        TokenChoice("Escape", "escape"),
        TokenChoice("退格", "backspace"),
        TokenChoice("左 Shift", "shift"),
        TokenChoice("右 Shift", "rshift"),
        TokenChoice("左 Ctrl", "control"),
        TokenChoice("右 Ctrl", "rcontrol"),
        TokenChoice("左 Alt", "alt"),
        TokenChoice("右 Alt", "ralt"),
        TokenChoice("Insert", "insert"),
        TokenChoice("Delete", "delete"),
        TokenChoice("Home", "home"),
        TokenChoice("End", "end"),
        TokenChoice("Page Up", "pageup"),
        TokenChoice("Page Down", "pagedown"),
    ]
    choices.extend(TokenChoice(f"字母 {letter.upper()}", letter) for letter in ascii_lowercase)
    choices.extend(TokenChoice(f"数字 {digit}", digit) for digit in digits)
    return choices


KEYBOARD_CHOICES = build_keyboard_choices()
KEYBOARD_CHOICE_LABELS = {choice.token: choice.label for choice in KEYBOARD_CHOICES}
GAMEPAD_CHOICES = [TokenChoice(f"按钮 {index}", str(index)) for index in range(1, 17)]

KEYBOARD_PRESETS = [
    KeyboardPreset(
        "官方默认",
        "方向键移动，Space 跳跃，Shift 冲刺",
        {
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
            "jump": "space",
            "special": "shift",
        },
    ),
    KeyboardPreset(
        "WASD + 空格",
        "WASD 移动，Space 跳跃，左 Shift 冲刺",
        {
            "up": "w",
            "down": "s",
            "left": "a",
            "right": "d",
            "jump": "space",
            "special": "shift",
        },
    ),
    KeyboardPreset(
        "WASD + J/K",
        "WASD 移动，J 跳跃，K 冲刺",
        {
            "up": "w",
            "down": "s",
            "left": "a",
            "right": "d",
            "jump": "j",
            "special": "k",
        },
    ),
    KeyboardPreset(
        "IJKL + N/M",
        "IJKL 移动，N 跳跃，M 冲刺",
        {
            "up": "i",
            "down": "k",
            "left": "j",
            "right": "l",
            "jump": "n",
            "special": "m",
        },
    ),
    KeyboardPreset(
        "ZX 经典位",
        "方向键移动，Z 跳跃，X 冲刺",
        {
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
            "jump": "z",
            "special": "x",
        },
    ),
]

GAMEPAD_PRESETS = [
    GamepadPreset("手柄默认", "跳跃 1，特殊 3，开启模拟摇杆", {"jump": "1", "special": "3"}, True),
    GamepadPreset("A / B", "跳跃 1，特殊 2，开启模拟摇杆", {"jump": "1", "special": "2"}, True),
    GamepadPreset("X / A", "跳跃 3，特殊 1，开启模拟摇杆", {"jump": "3", "special": "1"}, True),
]

CAPTURE_KEY_MAP = {
    Qt.Key_Up: "up",
    Qt.Key_Down: "down",
    Qt.Key_Left: "left",
    Qt.Key_Right: "right",
    Qt.Key_Space: "space",
    Qt.Key_Return: "return",
    Qt.Key_Enter: "return",
    Qt.Key_Tab: "tab",
    Qt.Key_Escape: "escape",
    Qt.Key_Backspace: "backspace",
    Qt.Key_Shift: "shift",
    Qt.Key_Control: "control",
    Qt.Key_Alt: "alt",
    Qt.Key_Insert: "insert",
    Qt.Key_Delete: "delete",
    Qt.Key_Home: "home",
    Qt.Key_End: "end",
    Qt.Key_PageUp: "pageup",
    Qt.Key_PageDown: "pagedown",
}


def capture_token_from_event(event: QKeyEvent) -> str | None:
    key = event.key()
    if key in CAPTURE_KEY_MAP:
        return CAPTURE_KEY_MAP[key]

    text = event.text()
    if text and len(text) == 1 and text.isascii() and text.isalnum():
        return text.lower()
    return None


def describe_token(token: str) -> str:
    normalized = normalize_token(token)
    label = KEYBOARD_CHOICE_LABELS.get(normalized)
    if label:
        return f"{label} ({normalized})"
    return normalized


def gamepad_capture_backend_name() -> str:
    return "pygame" if pygame is not None else "未安装"


class TokenComboBox(QComboBox):
    def __init__(self, items: Iterable[TokenChoice], placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(260)
        self.setMaxVisibleItems(18)

        self._display_to_token: dict[str, str] = {}
        displays: list[str] = []
        for item in items:
            display = f"{item.label} ({item.token})"
            self.addItem(display, item.token)
            self._display_to_token[display] = item.token
            displays.append(display)

        self.lineEdit().setPlaceholderText(placeholder)
        self.lineEdit().setClearButtonEnabled(True)

        completer = QCompleter(QStringListModel(displays), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(completer)

    def token(self) -> str:
        current_text = self.currentText().strip()
        if current_text in self._display_to_token:
            return normalize_token(self._display_to_token[current_text])
        index = self.currentIndex()
        if index >= 0 and current_text == self.itemText(index):
            return normalize_token(str(self.itemData(index)))
        return normalize_token(current_text)

    def set_token(self, token: str) -> None:
        normalized = normalize_token(token)
        index = self.findData(normalized)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            self.setEditText(normalized)


class KeyCaptureDialog(QDialog):
    def __init__(self, action_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.captured_token: str | None = None
        self.setWindowTitle(f"录入按键 - {action_label}")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        title = QLabel(f"为“{action_label}”按下一个键")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        hint = QLabel("支持方向键、字母、数字、Space、Enter、Shift、Ctrl、Alt 等常用键。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #5f6b7a;")
        self.result_label = QLabel("等待输入…")
        self.result_label.setStyleSheet(
            "background: #f5f8ff; border: 1px solid #c8d8ff; border-radius: 12px; "
            "padding: 14px; font-weight: 600;"
        )
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.result_label)
        layout.addWidget(cancel_button, 0, Qt.AlignRight)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        token = capture_token_from_event(event)
        if token:
            self.captured_token = token
            self.result_label.setText(f"已识别：{describe_token(token)}")
            self.accept()
            return
        self.result_label.setText("这个键当前不在快速录入范围内，请改用搜索或直接输入 token。")
        self.result_label.setStyleSheet(
            "background: #fff6f3; border: 1px solid #ffd0c2; border-radius: 12px; "
            "padding: 14px; font-weight: 600; color: #b04a2f;"
        )


class GamepadCaptureDialog(QDialog):
    def __init__(self, action_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.action_label = action_label
        self.captured_token: str | None = None
        self._joystick_names: dict[int, str] = {}
        self._backend_ready = False

        self.setWindowTitle(f"录入手柄按钮 - {action_label}")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        title = QLabel(f"为“{action_label}”按下一个手柄按钮")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        hint = QLabel(
            "只识别物理按钮按下事件。这里会把 pygame 读到的 0 基按钮号自动换算成"
            " Super Meat Boy 配置里使用的 1 基编号。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #5f6b7a;")

        self.backend_label = QLabel(f"检测后端：{gamepad_capture_backend_name()}")
        self.backend_label.setStyleSheet("color: #325172; font-weight: 600;")
        self.device_label = QLabel("正在扫描手柄…")
        self.device_label.setWordWrap(True)
        self.device_label.setStyleSheet(
            "background: #f5f8ff; border: 1px solid #c8d8ff; border-radius: 12px; padding: 12px;"
        )
        self.result_label = QLabel("等待按下手柄按钮…")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(
            "background: #f5f8ff; border: 1px solid #c8d8ff; border-radius: 12px; "
            "padding: 14px; font-weight: 600;"
        )

        self.refresh_button = QPushButton("重新扫描")
        self.refresh_button.clicked.connect(self.initialize_backend)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addWidget(self.refresh_button)
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.backend_label)
        layout.addWidget(self.device_label)
        layout.addWidget(self.result_label)
        layout.addLayout(button_row)

        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.poll_events)

        self.initialize_backend()

    def initialize_backend(self) -> None:
        self._backend_ready = False
        self._joystick_names = {}
        if pygame is None:
            self.device_label.setText("当前环境未安装 pygame，无法使用手柄自动识别。")
            self.result_label.setText(dependency_update_hint())
            self.result_label.setStyleSheet(
                "background: #fff6f3; border: 1px solid #ffd0c2; border-radius: 12px; "
                "padding: 14px; font-weight: 600; color: #b04a2f;"
            )
            return

        try:
            if not pygame.display.get_init():
                pygame.display.init()
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            pygame.event.clear()
            has_joystick = self.refresh_joysticks()
            self._backend_ready = True
            if has_joystick:
                self.result_label.setText("等待按下手柄按钮…")
                self.result_label.setStyleSheet(
                    "background: #f5f8ff; border: 1px solid #c8d8ff; border-radius: 12px; "
                    "padding: 14px; font-weight: 600;"
                )
            self.timer.start()
        except Exception as exc:
            self.device_label.setText(f"手柄扫描失败：{exc}")
            self.result_label.setText("后端初始化失败。你仍然可以手动输入按钮编号。")
            self.result_label.setStyleSheet(
                "background: #fff6f3; border: 1px solid #ffd0c2; border-radius: 12px; "
                "padding: 14px; font-weight: 600; color: #b04a2f;"
            )

    def refresh_joysticks(self) -> bool:
        assert pygame is not None
        self._joystick_names = {}
        count = pygame.joystick.get_count()
        if count <= 0:
            self.device_label.setText("没有检测到手柄。插上手柄后点“重新扫描”，再按目标按钮。")
            self.result_label.setText("当前没有可录入的手柄。插上手柄后重新扫描即可。")
            self.result_label.setStyleSheet(
                "background: #fffaf0; border: 1px solid #ffd88a; border-radius: 12px; "
                "padding: 14px; font-weight: 600; color: #8a5a00;"
            )
            return False

        names: list[str] = []
        for index in range(count):
            joystick = pygame.joystick.Joystick(index)
            if not joystick.get_init():
                joystick.init()
            instance_id = joystick.get_instance_id() if hasattr(joystick, "get_instance_id") else index
            name = joystick.get_name() or f"控制器 {index + 1}"
            self._joystick_names[instance_id] = name
            names.append(f"{index + 1}. {name}")
        self.device_label.setText("已检测到手柄：\n" + "\n".join(names))
        self.result_label.setText("已检测到手柄。现在按下目标按钮即可完成录入。")
        self.result_label.setStyleSheet(
            "background: #f5f8ff; border: 1px solid #c8d8ff; border-radius: 12px; "
            "padding: 14px; font-weight: 600;"
        )
        return True

    def poll_events(self) -> None:
        if pygame is None or not self._backend_ready:
            return
        try:
            pygame.event.pump()
            events = pygame.event.get([pygame.JOYBUTTONDOWN, pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED])
        except Exception as exc:
            self.timer.stop()
            self.device_label.setText(f"轮询失败：{exc}")
            self.result_label.setText("手柄事件轮询中断。你仍然可以手动输入按钮编号。")
            self.result_label.setStyleSheet(
                "background: #fff6f3; border: 1px solid #ffd0c2; border-radius: 12px; "
                "padding: 14px; font-weight: 600; color: #b04a2f;"
            )
            return

        for event in events:
            if event.type in {pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED}:
                self.refresh_joysticks()
                continue
            if event.type == pygame.JOYBUTTONDOWN:
                button_number = int(event.button) + 1
                instance_id = getattr(event, "instance_id", getattr(event, "joy", -1))
                joystick_name = self._joystick_names.get(instance_id, "未知手柄")
                self.captured_token = str(button_number)
                self.result_label.setText(
                    f"已识别：{joystick_name} 的按钮 {button_number}\n将写入 token：{self.captured_token}"
                )
                self.accept()
                return

    def done(self, result: int) -> None:
        self.timer.stop()
        super().done(result)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings(ORG_NAME, "smb-remap-studio")
        self.game_layout: GameLayout | None = None
        self.config_cache: dict[str, dict[str, str]] | None = None
        self.keyboard_fields: dict[str, TokenComboBox] = {}

        self.setWindowTitle(APP_NAME)
        self.resize(940, 760)
        self.apply_window_icon()
        self.apply_font_tuning()
        self.apply_stylesheet()

        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setSpacing(16)
        root_layout.setContentsMargins(18, 18, 18, 18)

        root_layout.addWidget(self.build_header())
        root_layout.addWidget(self.build_path_group())
        root_layout.addWidget(self.build_presets_group())
        root_layout.addWidget(self.build_keyboard_group())
        root_layout.addWidget(self.build_gamepad_group())
        root_layout.addWidget(self.build_note_group())
        root_layout.addLayout(self.build_button_row())

        self.status_label = QLabel("请选择 Super Meat Boy 目录。")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("statusLabel")
        root_layout.addWidget(self.status_label)

        self.set_controls_enabled(False)
        self.load_initial_directory()

    def build_header(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("SMB Remap Studio")
        title.setObjectName("heroTitle")
        subtitle = QLabel(
            "为桌面版 Super Meat Boy 做一个真正顺手的改键器。"
            "支持搜索、直接录键、快速预设、备份和一键启动。"
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("heroSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return wrapper

    def build_path_group(self) -> QGroupBox:
        group = QGroupBox("游戏目录")
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        self.root_line = QLineEdit()
        self.root_line.setReadOnly(True)
        self.config_line = QLineEdit()
        self.config_line.setReadOnly(True)

        choose_button = QPushButton("选择目录")
        choose_button.clicked.connect(self.choose_directory)
        open_button = QPushButton("打开配置目录")
        open_button.clicked.connect(self.open_config_directory)
        self.reload_button = QPushButton("重新读取")
        self.reload_button.clicked.connect(self.reload_config)

        layout.addWidget(QLabel("根目录"), 0, 0)
        layout.addWidget(self.root_line, 0, 1)
        layout.addWidget(choose_button, 0, 2)
        layout.addWidget(QLabel("配置文件"), 1, 0)
        layout.addWidget(self.config_line, 1, 1)
        layout.addWidget(open_button, 1, 2)
        layout.addWidget(self.reload_button, 1, 3)
        return group

    def build_presets_group(self) -> QGroupBox:
        group = QGroupBox("快速预设")
        layout = QVBoxLayout(group)
        keyboard_title = QLabel("键盘方案")
        keyboard_title.setObjectName("sectionTitle")
        layout.addWidget(keyboard_title)

        keyboard_grid = QGridLayout()
        keyboard_grid.setHorizontalSpacing(10)
        keyboard_grid.setVerticalSpacing(10)
        for index, preset in enumerate(KEYBOARD_PRESETS):
            button = QPushButton(f"{preset.name}\n{preset.description}")
            button.setProperty("presetButton", True)
            button.setToolTip(preset.description)
            button.clicked.connect(lambda checked=False, value=preset: self.apply_keyboard_preset(value))
            button.setMinimumHeight(72)
            keyboard_grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(keyboard_grid)

        gamepad_title = QLabel("手柄方案")
        gamepad_title.setObjectName("sectionTitle")
        layout.addWidget(gamepad_title)

        pad_row = QHBoxLayout()
        pad_row.setSpacing(10)
        for preset in GAMEPAD_PRESETS:
            button = QPushButton(f"{preset.name}\n{preset.description}")
            button.setProperty("presetButton", True)
            button.setToolTip(preset.description)
            button.clicked.connect(lambda checked=False, value=preset: self.apply_gamepad_preset(value))
            button.setMinimumHeight(72)
            pad_row.addWidget(button)
        layout.addLayout(pad_row)
        return group

    def build_keyboard_group(self) -> QGroupBox:
        group = QGroupBox("键盘映射")
        layout = QFormLayout(group)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(10)
        for action in KEYBOARD_ORDER:
            combo = TokenComboBox(KEYBOARD_CHOICES, "搜索键名或直接输入 token")
            capture_button = QPushButton("录入按键")
            capture_button.clicked.connect(lambda checked=False, value=action: self.capture_keyboard_binding(value))

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            row_layout.addWidget(combo, 1)
            row_layout.addWidget(capture_button)

            self.keyboard_fields[action] = combo
            layout.addRow(ACTION_LABELS[action], row_widget)
        return group

    def build_gamepad_group(self) -> QGroupBox:
        group = QGroupBox("手柄映射")
        layout = QFormLayout(group)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(10)
        self.pad_jump = TokenComboBox(GAMEPAD_CHOICES, "输入按钮编号，例如 1")
        self.pad_special = TokenComboBox(GAMEPAD_CHOICES, "输入按钮编号，例如 3")
        self.use_analog = QCheckBox("启用模拟摇杆")
        self.pad_capture_hint = QLabel(
            "自动识别后端："
            + gamepad_capture_backend_name()
            + ("。可直接按下手柄按钮录入。" if pygame is not None else "。当前未安装，录入按钮会提示你更新依赖。")
        )
        self.pad_capture_hint.setWordWrap(True)
        self.pad_capture_hint.setStyleSheet("color: #536171;")

        jump_row = QWidget()
        jump_layout = QHBoxLayout(jump_row)
        jump_layout.setContentsMargins(0, 0, 0, 0)
        jump_layout.setSpacing(10)
        jump_layout.addWidget(self.pad_jump, 1)
        jump_button = QPushButton("录入按钮")
        jump_button.clicked.connect(lambda: self.capture_gamepad_binding("jump"))
        jump_layout.addWidget(jump_button)

        special_row = QWidget()
        special_layout = QHBoxLayout(special_row)
        special_layout.setContentsMargins(0, 0, 0, 0)
        special_layout.setSpacing(10)
        special_layout.addWidget(self.pad_special, 1)
        special_button = QPushButton("录入按钮")
        special_button.clicked.connect(lambda: self.capture_gamepad_binding("special"))
        special_layout.addWidget(special_button)

        layout.addRow("", self.pad_capture_hint)
        layout.addRow("跳跃", jump_row)
        layout.addRow("冲刺 / 特殊", special_row)
        layout.addRow("", self.use_analog)
        return group

    def build_note_group(self) -> QGroupBox:
        group = QGroupBox("使用说明")
        layout = QVBoxLayout(group)
        note = QLabel(
            "这不是系统级按键劫持器，只会改游戏自己的 buttonmap.cfg。"
            "你可以用预设快速套用，也可以搜索“空格 / shift / a / pageup”这类键名。"
            "如果下拉框里没有你要的值，还能直接输入原始 token。"
            "手柄按钮自动识别依赖 pygame；识别到的按钮号会自动转换成游戏配置使用的 1 基编号。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #536171; line-height: 1.5;")
        layout.addWidget(note)
        return group

    def build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self.defaults_button = QPushButton("恢复默认")
        self.defaults_button.clicked.connect(self.restore_defaults)
        self.save_button = QPushButton("保存配置")
        self.save_button.setProperty("primary", True)
        self.save_button.clicked.connect(self.save_config)
        self.launch_button = QPushButton("启动游戏")
        self.launch_button.clicked.connect(self.launch_game)

        row.addWidget(self.defaults_button)
        row.addStretch(1)
        row.addWidget(self.save_button)
        row.addWidget(self.launch_button)
        return row

    def apply_window_icon(self) -> None:
        icon_path = find_bundled_icon()
        if icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))

    def apply_font_tuning(self) -> None:
        font = QFont()
        font.setPointSize(10)
        QApplication.instance().setFont(font)

    def apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f4f7fb;
            }
            QWidget {
                color: #1f2933;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d9e3f0;
                border-radius: 14px;
                margin-top: 14px;
                font-weight: 700;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #324861;
            }
            QLineEdit, QComboBox {
                background: #ffffff;
                border: 1px solid #c7d4e5;
                border-radius: 10px;
                padding: 8px 10px;
                min-height: 20px;
            }
            QComboBox::drop-down {
                width: 30px;
                border: none;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #c7d4e5;
                border-radius: 11px;
                padding: 9px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                border-color: #5a88ff;
                background: #f7faff;
            }
            QPushButton[primary="true"] {
                background: #2d6df6;
                color: #ffffff;
                border-color: #2d6df6;
            }
            QPushButton[primary="true"]:hover {
                background: #2259cb;
                border-color: #2259cb;
            }
            QPushButton[presetButton="true"] {
                text-align: left;
                padding: 12px 14px;
                background: #f9fbff;
            }
            QLabel#heroTitle {
                font-size: 28px;
                font-weight: 800;
                color: #19324f;
            }
            QLabel#heroSubtitle {
                color: #5f6b7a;
                font-size: 13px;
            }
            QLabel#sectionTitle {
                font-size: 13px;
                font-weight: 700;
                color: #4c6177;
                margin-top: 2px;
            }
            QLabel#statusLabel {
                background: #eef4ff;
                border: 1px solid #c6d9ff;
                border-radius: 12px;
                padding: 12px;
                color: #27415f;
                font-weight: 600;
            }
            """
        )

    def load_initial_directory(self) -> None:
        saved_root = self.settings.value("root_dir", "", str)
        candidates = [Path(saved_root)] if saved_root else []
        default_root = detect_default_root()
        if default_root:
            candidates.append(default_root)
        for candidate in candidates:
            try:
                self.set_root_directory(candidate)
                return
            except ConfigError:
                continue

    def set_controls_enabled(self, enabled: bool) -> None:
        for combo in self.keyboard_fields.values():
            combo.setEnabled(enabled)
        self.pad_jump.setEnabled(enabled)
        self.pad_special.setEnabled(enabled)
        self.use_analog.setEnabled(enabled)
        self.reload_button.setEnabled(enabled)
        self.defaults_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.launch_button.setEnabled(enabled and self.game_layout and self.game_layout.launch_program is not None)

    def choose_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择 Super Meat Boy 根目录或 game 目录",
            str(self.game_layout.root_dir if self.game_layout else Path.home()),
        )
        if selected:
            try:
                self.set_root_directory(Path(selected))
            except ConfigError as exc:
                QMessageBox.warning(self, APP_NAME, str(exc))

    def set_root_directory(self, path: Path) -> None:
        layout = resolve_game_layout(path)
        self.game_layout = layout
        self.root_line.setText(str(layout.root_dir))
        self.config_line.setText(str(layout.config_path))
        self.settings.setValue("root_dir", str(layout.root_dir))
        if layout.icon_path:
            self.setWindowIcon(QIcon(str(layout.icon_path)))
        self.reload_config()

    def open_config_directory(self) -> None:
        if not self.game_layout:
            QMessageBox.information(self, APP_NAME, "还没有加载任何游戏目录。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.game_layout.config_path.parent)))

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)
        if self.statusBar():
            self.statusBar().showMessage(message, 5000)

    def reload_config(self) -> None:
        if not self.game_layout:
            self.set_status("请选择 Super Meat Boy 目录。")
            self.set_controls_enabled(False)
            return
        try:
            self.config_cache = load_buttonmap(self.game_layout.config_path)
        except Exception as exc:
            self.set_status(f"读取失败：{exc}")
            self.set_controls_enabled(False)
            if not isinstance(exc, ConfigError):
                QMessageBox.critical(self, APP_NAME, f"读取配置失败：{exc}")
            return

        self.populate_fields(self.config_cache)
        launch_state = "可启动" if self.game_layout.launch_program else "未找到启动程序"
        self.set_status(
            f"已加载配置。根目录：{self.game_layout.root_dir} | 配置：{self.game_layout.config_path} | 启动状态：{launch_state}"
        )
        self.set_controls_enabled(True)

    def populate_fields(self, sections: dict[str, dict[str, str]]) -> None:
        keyboard = dict(DEFAULT_CONFIG["keyboard"])
        keyboard.update(sections.get("keyboard", {}))
        gamepad = dict(DEFAULT_CONFIG["gamepad"])
        gamepad.update(sections.get("gamepad", {}))
        for action, combo in self.keyboard_fields.items():
            combo.set_token(keyboard[action])
        self.pad_jump.set_token(gamepad["jump"])
        self.pad_special.set_token(gamepad["special"])
        self.use_analog.setChecked(normalize_token(gamepad.get("useanalog", "true")) == "true")

    def apply_keyboard_preset(self, preset: KeyboardPreset) -> None:
        for action, token in preset.mapping.items():
            self.keyboard_fields[action].set_token(token)
        self.set_status(f"已套用键盘预设：{preset.name}。记得保存。")

    def apply_gamepad_preset(self, preset: GamepadPreset) -> None:
        self.pad_jump.set_token(preset.mapping["jump"])
        self.pad_special.set_token(preset.mapping["special"])
        self.use_analog.setChecked(preset.use_analog)
        self.set_status(f"已套用手柄预设：{preset.name}。记得保存。")

    def capture_keyboard_binding(self, action: str) -> None:
        dialog = KeyCaptureDialog(ACTION_LABELS[action], self)
        if dialog.exec() == QDialog.Accepted and dialog.captured_token:
            self.keyboard_fields[action].set_token(dialog.captured_token)
            self.set_status(f"已为“{ACTION_LABELS[action]}”录入：{describe_token(dialog.captured_token)}。")

    def capture_gamepad_binding(self, action: str) -> None:
        if pygame is None:
            reason = str(PYGAME_IMPORT_ERROR) if PYGAME_IMPORT_ERROR else "未知原因"
            QMessageBox.information(
                self,
                APP_NAME,
                "当前环境还没有可用的手柄识别后端。\n\n"
                f"原因：{reason}\n\n"
                + dependency_update_hint(),
            )
            return

        label = "跳跃" if action == "jump" else "冲刺 / 特殊"
        dialog = GamepadCaptureDialog(label, self)
        if dialog.exec() == QDialog.Accepted and dialog.captured_token:
            target = self.pad_jump if action == "jump" else self.pad_special
            target.set_token(dialog.captured_token)
            self.set_status(f"已为“{label}”录入手柄按钮：{dialog.captured_token}。")

    def restore_defaults(self) -> None:
        self.populate_fields(DEFAULT_CONFIG)
        self.set_status("已恢复到默认映射，尚未保存到文件。")

    def collect_sections(self) -> dict[str, dict[str, str]]:
        keyboard: dict[str, str] = {}
        for action, combo in self.keyboard_fields.items():
            token = combo.token()
            if not token:
                raise ConfigError(f"{ACTION_LABELS[action]} 不能为空。")
            keyboard[action] = token

        gamepad_jump = self.pad_jump.token()
        gamepad_special = self.pad_special.token()
        if not gamepad_jump or not gamepad_special:
            raise ConfigError("手柄按键不能为空。")

        return {
            "keyboard": keyboard,
            "gamepad": {
                "jump": gamepad_jump,
                "special": gamepad_special,
                "useanalog": "true" if self.use_analog.isChecked() else "false",
            },
        }

    def duplicate_tokens(self, mapping: dict[str, str]) -> dict[str, list[str]]:
        reverse: dict[str, list[str]] = {}
        for action, token in mapping.items():
            reverse.setdefault(token, []).append(action)
        return {token: actions for token, actions in reverse.items() if len(actions) > 1}

    def save_config(self) -> None:
        if not self.game_layout:
            QMessageBox.warning(self, APP_NAME, "请先选择有效的游戏目录。")
            return
        try:
            sections = self.collect_sections()
        except ConfigError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return

        duplicates = self.duplicate_tokens(sections["keyboard"])
        if duplicates:
            lines = []
            for token, actions in duplicates.items():
                labels = "、".join(ACTION_LABELS.get(action, action) for action in actions)
                lines.append(f"{token}: {labels}")
            answer = QMessageBox.question(
                self,
                APP_NAME,
                "检测到重复键位：\n"
                + "\n".join(lines)
                + "\n\n这通常不是理想设置。仍然保存吗？",
            )
            if answer != QMessageBox.Yes:
                return

        try:
            backup_path = write_buttonmap(self.game_layout.config_path, sections)
            self.config_cache = sections
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"保存失败：{exc}")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.set_status(f"已保存配置，备份文件：{backup_path} | 时间：{timestamp}")
        QMessageBox.information(self, APP_NAME, f"保存成功。\n备份文件：{backup_path}")

    def launch_game(self) -> None:
        if not self.game_layout or not self.game_layout.launch_program:
            QMessageBox.warning(self, APP_NAME, "未找到可启动的游戏程序。")
            return
        ok = QProcess.startDetached(
            str(self.game_layout.launch_program),
            [],
            str(self.game_layout.launch_cwd or self.game_layout.root_dir),
        )
        if not ok:
            QMessageBox.critical(
                self,
                APP_NAME,
                "启动失败，请检查 start.bash、SuperMeatBoy.exe 或 Linux 游戏二进制是否可执行。",
            )
            return
        self.set_status(f"已启动游戏：{self.game_layout.launch_program}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--root", type=Path, default=None, help="指定游戏根目录或 game 目录。")
    parser.add_argument("--smoke-test", action="store_true", help="只做界面和路径初始化检查。")
    parser.add_argument("--export-screenshot", type=Path, default=None, help="导出主界面截图到指定路径。")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    window = MainWindow()
    if args.root is not None:
        try:
            window.set_root_directory(args.root)
        except ConfigError as exc:
            QMessageBox.critical(window, APP_NAME, str(exc))
            return 2
    window.show()
    app.processEvents()

    if args.export_screenshot is not None:
        target = args.export_screenshot.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        pixmap = window.grab()
        if not pixmap.save(str(target)):
            return 3
        return 0

    if args.smoke_test:
        return 0

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
