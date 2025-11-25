import sys
import os
import re
import requests
import zipfile
import io
import shutil
import getpass
import glob
import subprocess
from math import ceil

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFrame, QMessageBox, QCheckBox, 
    QSizePolicy, QSpacerItem, QProgressBar, QPlainTextEdit, QWidget
)
from PySide6.QtGui import QFontDatabase, QFont, QIcon, QPainter, QColor, QPen
from PySide6.QtCore import Qt, QObject, Signal, QThread, QTimer, QRect, QPropertyAnimation, QSettings, QEasingCurve

from cryptography.fernet import Fernet
import nbtlib
from nbtlib import tag

GITHUB_REPO = "USERNAME/PRIVATEREPO"
BRANCH = "master"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/modpacks"
ZIP_URL = f"https://api.github.com/repos/{GITHUB_REPO}/zipball/{BRANCH}"

USERNAME = getpass.getuser()
MINECRAFT_PATH = os.path.join("C:\\Users", USERNAME, "AppData", "Roaming", ".minecraft")

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def read_github_token():
    token_path = resource_path("penny.txt")
    if not os.path.isfile(token_path):
        QMessageBox.critical(None, "Ошибка", f"Файл с токеном {token_path} не найден!")
        
        sys.exit(1)
    with open(token_path, "r", encoding="utf-8") as f:
        return f.read().strip()

GITHUB_TOKEN = read_github_token()
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def fetch_modpack_list():
    try:
        response = requests.get(GITHUB_API_URL, headers=HEADERS)
        response.raise_for_status()
        folders = [item['name'] for item in response.json() if item['type'] == 'dir']
        return folders
    except Exception as e:
        QMessageBox.warning(None, "Ошибка", f"Не удалось получить список модпаков:\n{e}")
        return []

def rename_mods_folder(minecraft_path):
    mods_path = os.path.join(minecraft_path, "mods")
    if not os.path.exists(mods_path):
        return

    index = 1
    while True:
        new_name = f"mods-{index}"
        new_path = os.path.join(minecraft_path, new_name)
        if not os.path.exists(new_path):
            try:
                os.rename(mods_path, new_path)
            except Exception as e:
                QMessageBox.critical(None, "Ошибка", f"Не удалось переименовать папку mods: {e}")
                return
            break
        index += 1

def delete_mods_folder(minecraft_path):
    mods_path = os.path.join(minecraft_path, "mods")
    if os.path.exists(mods_path):
        try:
            shutil.rmtree(mods_path)
        except Exception as e:
            QMessageBox.critical(None, "Ошибка", f"Не удалось удалить папку mods: {e}")

class InstallerWorker(QObject):
    progress = Signal(int)
    finished = Signal(str)
    error = Signal(str)
    server_added = Signal(str, str)
    log = Signal(str)
    clear_log = Signal()

    def __init__(self, modpack_name, rename_mode):
        super().__init__()
        self.modpack_name = modpack_name
        self.rename_mode = rename_mode

    def run(self):
        self.clear_log.emit()
        try:
            self.progress.emit(0)
            self.log.emit("Переименование/удаление папки mods, если необходимо...")
            
            if self.rename_mode:
                rename_mods_folder(MINECRAFT_PATH)
                self.log.emit("Папка mods переименована")
            else:
                delete_mods_folder(MINECRAFT_PATH)
                self.log.emit("Папка mods удалена")
            
            self.progress.emit(5)
            # Запрос архива
            self.log.emit("Запрос архива модпаков...")
            resp = requests.get(ZIP_URL, headers=HEADERS)
            resp.raise_for_status()
            self.progress.emit(15)

            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                root_folder = None
                for name in z.namelist():
                    if name.endswith('/') and '/' not in name[:-1]:
                        root_folder = name
                        break

                if root_folder is None:
                    self.error.emit("Не удалось определить корневую папку архива.")
                    return

                target_prefix = f"{root_folder}modpacks/{self.modpack_name}/"

                found = False
                existing_worlds = set()
                file_list = [m for m in z.namelist() if m.startswith(target_prefix)]
                total_files = len(file_list)
                processed_files = 0

                # --------------------------------------
                # 1. Сначала собираем список всех имён миров из архива (папок в saves/)
                archive_saves_worlds = set()
                for member in file_list:
                    relative_path = member[len(target_prefix):]
                    if relative_path.startswith("saves/"):
                        parts = relative_path.split("/")
                        if len(parts) > 1:
                            archive_saves_worlds.add(parts[1])

                def format_worlds_list(worlds_set):
                    worlds = [w.strip() for w in worlds_set if w.strip()]
                    return ", ".join(worlds) if worlds else "нет"
                
                def log_worlds_action(log_func, worlds_set, action_singular, action_plural):
                    worlds = [w.strip() for w in worlds_set if w.strip()]
                    if not worlds:
                        return 

                    if len(worlds) == 1:
                        log_func(f"Мир {worlds[0]} {action_singular}")
                    else:
                        log_func(f"Миры {', '.join(worlds)} {action_plural}")

                self.log.emit(f"Текущие миры модпака: {format_worlds_list(archive_saves_worlds)}")

                # 2. Проверяем, какие миры уже есть локально и добавляем их в existing_worlds
                existing_worlds = set()
                for world_name in archive_saves_worlds:
                    local_save_path = os.path.join(MINECRAFT_PATH, "saves", world_name)
                    if os.path.exists(local_save_path):
                        existing_worlds.add(world_name)
                
                if existing_worlds:
                    log_worlds_action(self.log.emit, existing_worlds, "пропущен", "пропущены")

                worlds_to_download = archive_saves_worlds - existing_worlds
                if worlds_to_download:
                    log_worlds_action(self.log.emit, worlds_to_download, "добавлен", "добавлены")

                # --------------------------------------

                for member in file_list:
                    found = True
                    relative_path = member[len(target_prefix):]
                    if not relative_path:
                        continue

                    # Если файл/папка внутри saves/<имя_мира>, который уже есть локально — пропускаем
                    if relative_path.startswith("saves/"):
                        parts = relative_path.split("/")
                        if len(parts) > 1:
                            save_world_name = parts[1]
                            if save_world_name in existing_worlds:
                                continue  # Пропускаем этот файл — мир уже есть локально

                    target_path = os.path.join(MINECRAFT_PATH, relative_path)

                    if member.endswith('/'):
                        os.makedirs(target_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with z.open(member) as source, open(target_path, "wb") as target:
                            target.write(source.read())

                    processed_files += 1
                    if total_files > 0:
                        progress_val = 15 + int((processed_files / total_files) * 55)
                        self.progress.emit(progress_val)

                if existing_worlds:
                    filtered_worlds = [w.strip() for w in existing_worlds if w.strip()]
                    if filtered_worlds:
                        print(f"Текущие существующие миры из сборки: {', '.join(filtered_worlds)}")
                        self.log.emit("Текущие существующие миры из сборки: " + ", ".join(filtered_worlds))

                if not found:
                    self.error.emit(f"Модпак '{self.modpack_name}' не найден в архиве.")
                    return

            self.progress.emit(75)
            versions_path = os.path.join(MINECRAFT_PATH, "versions")
            installer_jar_name = None

            # Ищем jar с "-installer.jar" в названии (в версии)
            jar_files = glob.glob(os.path.join(versions_path, "*.jar"))
            for jar_path in jar_files:
                if jar_path.endswith("-installer.jar"):
                    installer_jar_name = os.path.basename(jar_path)
                    break

            if installer_jar_name:
                # Получаем базовое имя версии (без "-installer.jar")
                version_folder_name = installer_jar_name.replace("-installer.jar", "")
                version_folder_path = os.path.join(versions_path, version_folder_name)

                if os.path.isdir(version_folder_path):
                    # Папка с версией уже есть — запуска не делаем, просто удаляем инсталлятор
                    print(f"Папка версии '{version_folder_name}' найдена, запуска инсталлятора не будет.")
                    self.log.emit(f"Папка версии '{version_folder_name}' найдена, запуска инсталлятора не будет.")
                    try:
                        os.remove(os.path.join(versions_path, installer_jar_name))
                    except Exception as e:
                        print(f"Ошибка удаления инсталлятора: {e}")
                        self.log.emit(f"Ошибка удаления инсталлятора: {e}")
                else:
                    # Папки нет — запускаем инсталлятор
                    jar_path = os.path.join(versions_path, installer_jar_name)
                    try:
                        subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                        self.log.emit(f"Запуск инсталлятора модовой версии '{installer_jar_name}'...")
                        with open(os.devnull, 'w') as devnull:
                            subprocess.run(
                                ["java", "-jar", jar_path],
                                stdout=devnull,
                                stderr=devnull,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                            )
                        # После запуска удаляем инсталлятор
                        os.remove(jar_path)
                    except FileNotFoundError:
                        self.error.emit("Java не установлена или недоступна в переменной среды.")
                        return
                    except Exception as e:
                        print(f"Ошибка при запуске инсталлятора .jar: {e}")
                        self.log.emit(f"Ошибка при запуске инсталлятора .jar: {e}")
            else:
                print("Инсталлятор не найден, запуск пропущен.")
                self.log.emit("Инсталлятор не найден, запуск пропущен.")

            self.progress.emit(90)
            server_txt_path = os.path.join(MINECRAFT_PATH, "server.txt")
            if os.path.exists(server_txt_path):
                try:
                    with open(server_txt_path, "r", encoding="utf-8") as f:
                        lines = f.read().splitlines()
                    name = ""
                    ip = ""
                    for line in lines:
                        if line.startswith("name="):
                            name = line.split("=", 1)[1].strip().strip('"')
                        elif line.startswith("ip="):
                            ip = line.split("=", 1)[1].strip().strip('"')
                    if name and ip:
                        # Вместо прямого вызова add_server_to_list с QMessageBox,
                        # вызываем функцию, которая просто добавляет сервер без UI
                        added = self.add_server_without_message(name, ip)
                        # И эмитим сигнал в главный поток, чтобы там показать сообщение
                        if added:
                            self.server_added.emit(name, ip)
                    else:
                        print("Неверный формат в server.txt")
                        self.log.emit("Неверный формат в server.txt")
                except Exception as e:
                    print(f"Ошибка обработки server.txt: {e}")
                    self.log.emit(f"Ошибка обработки server.txt: {e}")
                finally:
                    os.remove(server_txt_path)

            self.progress.emit(100)
            self.finished.emit(f"Модпак '{self.modpack_name}' установлен в .minecraft.")
            self.log.emit(f"Модпак '{self.modpack_name}' установлен в .minecraft.")

        except Exception as e:
            self.error.emit(str(e))

    def add_server_without_message(self, name, ip):
        MINECRAFT_DIR = os.path.join(os.getenv("APPDATA"), ".minecraft")
        SERVERS_PATH = os.path.join(MINECRAFT_DIR, "servers.dat")

        if not os.path.exists(SERVERS_PATH):
            servers_data = nbtlib.File({
                "servers": tag.List[nbtlib.Compound]()
            })
            root = servers_data.root
        else:
            try:
                servers_data = nbtlib.load(SERVERS_PATH)
                root = getattr(servers_data, "root", servers_data)
            except Exception as e:
                print(f"Ошибка чтения servers.dat: {e}")
                self.log.emit(f"Ошибка чтения servers.dat: {e}")
                return False

        servers = root.get("servers", tag.List())

        for server in servers:
            if server.get("ip") == ip:
                print("Сервер уже существует в списке.")
                self.log.emit(f"Сервер уже существует в списке.")
                return False

        new_server = nbtlib.Compound({
            "acceptTextures": tag.Byte(1),
            "hidden": tag.Byte(0),
            "ip": tag.String(ip),
            "name": tag.String(name)
        })
        servers.append(new_server)
        root["servers"] = servers

        try:
            servers_data.save(SERVERS_PATH)
        except AttributeError:
            with open(SERVERS_PATH, "wb") as f:
                f.write(nbtlib.serialize(servers_data))
        return True

class ModpackInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Установка модпаков")
        self.setFixedSize(600, 350)
        self.setStyleSheet("background-color: #121212; color: white;")

        font_id = QFontDatabase.addApplicationFont(resource_path("fonts/Genshin_Impact.ttf"))
        if font_id == -1:
            QMessageBox.warning(None, "Внимание", "Не удалось загрузить шрифт!")
            self.font_family = "Arial"
        else:
            self.font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            print(self.font_family)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        title_container = QHBoxLayout()

        title_container.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # Центрированная надпись
        title_label = QLabel("Какой модпак вы хотите установить?")
        title_label.setFont(QFont(self.font_family, 13))
        title_label.setStyleSheet("color: white;")
        title_label.setAlignment(Qt.AlignCenter)
        title_container.addWidget(title_label, alignment=Qt.AlignCenter)

        title_container.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.mode_switch = ModeSwitch()
        self.mode_switch.mode_changed.connect(self.on_mode_changed)
        title_container.addWidget(self.mode_switch, alignment=Qt.AlignRight | Qt.AlignVCenter)

        main_layout.addLayout(title_container)
        main_layout.addSpacing(10)

        icon_path = resource_path("icons/icon.ico")
        app.setWindowIcon(QIcon(icon_path))

        self.container = QFrame()
        self.container.setStyleSheet("background-color: #1e1e1e; border-radius: 4px;")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(self.container, stretch=1)

        self.modpacks = fetch_modpack_list()
        if not self.modpacks:
            empty_label = QLabel("Нет доступных модпаков")
            empty_label.setFont(QFont(self.font_family, 4))
            empty_label.setStyleSheet("color: white;")
            empty_label.setAlignment(Qt.AlignCenter)
            container_layout.addWidget(empty_label)
        else:
            columns = 3
            rows = ceil(len(self.modpacks) / columns)

            for i in range(rows):
                row_frame = QFrame()
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(0, 5, 0, 5)
                row_layout.setSpacing(20)
                row_layout.setAlignment(Qt.AlignTop)

                row_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

                remaining = len(self.modpacks) - i * columns
                count_in_row = min(columns, remaining)

                for j in range(count_in_row):
                    idx = i * columns + j
                    name = self.modpacks[idx]

                    btn = QPushButton(name)
                    btn.setFixedWidth(170)
                    btn.setFont(QFont(self.font_family, 8))
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #ff9900;
                            color: #1e1e1e;
                            border-radius: 4px;
                            padding: 6px;
                        }
                        QPushButton:hover {
                            background-color: #e68a00;
                        }
                    """)
                    btn.clicked.connect(lambda checked, n=name: self.start_install(n))
                    row_layout.addWidget(btn)

                row_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

                container_layout.addWidget(row_frame)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e1e1e;
                border-radius: 4px;
                padding: 3px;
            }
            QProgressBar::chunk {
                background-color: #ff9900;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self.progress_bar)

        self.log_panel = QPlainTextEdit()
        self.log_panel.setReadOnly(True)
        # self.log_panel.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.log_panel.setFixedHeight(78.3)  # примерно на 3 строки
        self.log_panel.setVisible(False)

        self.log_panel.setStyleSheet("""
            QPlainTextEdit {
                background-color: #2a2a2a;  /* чуть светлее чем контейнер */
                color: white;
                border-radius: 4px;
                padding: 5px;
                font-family: "Courier New", Courier, monospace;
                font-size: 9pt;
            }
                                     
            QScrollBar:vertical {
                background: #1e1e1e; 
                width: 11.5px;
                margin: 0px 0px 0px 0px;
                border: 2px solid black; 
                border-radius: 8px;
            }

            /* Трек (полоса, по которой движется бегунок) */
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent; 
            }

            /* Сам бегунок (handle) */
            QScrollBar::handle:vertical {
                background: #ff9900;  
                min-height: 30px;
                border-radius: 10px;   
            }

            /* Кнопки вверх и вниз - скрываем */
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                height: 0px;
                width: 0px;
                subcontrol-origin: margin;
                subcontrol-position: top left;
                border: none;
                background: none;
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                width: 0px;
                background: none;
                border: none;
            }
        """)

        main_layout.addWidget(self.log_panel)

        self.thread = None
        self.worker = None

    def start_install(self, modpack_name):
        # 🔒 Проверка имени модпака на запрещённые символы
        if re.search(r'[\/:*?"<>|]', modpack_name):
            QMessageBox.critical(None, "Ошибка", f"Имя модпака '{modpack_name}' содержит недопустимые символы.")
            return

        # ✅ Проверка потока, как и было
        if self.thread is not None:
            if self.thread.isRunning():
                QMessageBox.warning(None, "Внимание", "Установка уже запущена")
                return
            self.thread = None
            self.worker = None

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.thread = QThread()
        self.worker = InstallerWorker(modpack_name, self.mode_switch.active_mode == "r")
        self.worker.clear_log.connect(self.log_panel.clear)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_install_finished)
        self.worker.error.connect(self.on_install_error)
        self.worker.server_added.connect(self.on_server_added)

        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup_thread)

        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
    
    def on_mode_changed(self, mode):
        self.rename_mode = (mode == "r")

    def append_log(self, message):
        self.log_panel.setVisible(True)
        # Получаем текущие строки
        existing = self.log_panel.toPlainText().splitlines()
        existing.append(message)
        # Обновляем текст
        self.log_panel.setPlainText("\n".join(existing))
        # Скроллим вниз к последнему сообщению
        QTimer.singleShot(0, lambda: self.log_panel.verticalScrollBar().setValue(
            self.log_panel.verticalScrollBar().maximum()
        ))

    def on_server_added(self, name, ip):
        QMessageBox.information(None, "Успех", f"Сервер '{name}' по адресу '{ip}' добавлен в список серверов Minecraft.")
        self.log.emit(f"Сервер '{name}' по адресу '{ip}' добавлен в список серверов Minecraft.")
    
    def cleanup_thread(self):
        self.thread = None
        self.worker = None

    def on_install_finished(self, message):
        self.progress_bar.setVisible(False)
        QMessageBox.information(None, "Успех", message)

    def on_install_error(self, error_message):
        self.progress_bar.setVisible(False)
        QMessageBox.critical(None, "Ошибка установки", error_message)

class ModeSwitch(QWidget):
    mode_changed = Signal(str)  # "d" или "r"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 24)  # компактнее
        self.active_mode = "d"

        self.setStyleSheet("""
            border-radius: 8px;
        """)

        # Метки "d" и "r" по краям
        self.label_d = QLabel("d", self)
        self.label_r = QLabel("r", self)
        font_id = QFontDatabase.addApplicationFont(resource_path("fonts/Genshin_Impact.ttf"))
        font_bold = QFontDatabase.applicationFontFamilies(font_id)[0]

        for label in (self.label_d, self.label_r):
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: whitesmoke; background-color: #2a2a2a;")
            label.setFont(QFont(font_bold, 8, QFont.Bold))
            label.setFixedSize(28, 20)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.label_d.move(2, 2)
        self.label_r.move(30, 2)

        # Подвижная оранжевая кнопка
        self.slider = QFrame(self)
        self.slider.setGeometry(2, 2, 28, 20)
        self.slider.setStyleSheet("""
            background-color: orange;
            border: 3.25px solid #2a2a2a;
            border-radius: 8px;
        """)

        self.slider_text = QLabel("d", self.slider)
        self.slider_text.setAlignment(Qt.AlignCenter)
        self.slider_text.setStyleSheet("color: #2a2a2a; font-weight: bold; background: transparent;")
        self.slider_text.setFont(QFont(font_bold, 8, QFont.Bold))
        self.slider_text.setFixedSize(28, 20)
        self.slider_text.move(0, 0)

        self.anim = QPropertyAnimation(self.slider, b"geometry")
        self.anim.setDuration(150)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)

        self.setCursor(Qt.PointingHandCursor)

        self.load_mode()

    def mousePressEvent(self, event):
        if self.active_mode == "d":
            self.set_mode("r")
        else:
            self.set_mode("d")

    def set_mode(self, mode):
        if mode == self.active_mode:
            return
        self.active_mode = mode

        if mode == "d":
            start_rect = QRect(34, 2, 28, 20)
            end_rect = QRect(2, 2, 28, 20)
            self.slider_text.setText("d")
        else:
            start_rect = QRect(2, 2, 28, 20)
            end_rect = QRect(34, 2, 28, 20)
            self.slider_text.setText("r")

        self.anim.stop()
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()

        self.save_mode()
        self.mode_changed.emit(mode)

    def save_mode(self):
        settings = QSettings("EndLinkerio", "ModpackInstaller")
        settings.setValue("active_mode", self.active_mode)

    def load_mode(self):
        settings = QSettings("EndLinkerio", "ModpackInstaller")
        saved_mode = settings.value("active_mode", "d")
        self.active_mode = saved_mode
        
        if saved_mode == "r":
            self.slider.setGeometry(34, 2, 28, 20)
            self.slider_text.setText("r")
        else:
            self.slider.setGeometry(2, 2, 28, 20)
            self.slider_text.setText("d")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(QColor("#2a2a2a"))
        painter.setPen(QPen(QColor("orange"), 1))
        rect = self.rect()
        rect.adjust(1, 1, -1, -1)
        painter.drawRoundedRect(rect, 8, 8)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ModpackInstaller()
    window.show()
    sys.exit(app.exec())
