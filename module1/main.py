import sys
import json
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSizePolicy, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog
)
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QPixmap, QTransform
from PyQt6.QtCore import Qt, QSize

# ===== Пути к медиафайлам =====
MEDIA_DIR = r"module1\media"
ICON_TRAFFIC_LIGHT = f"{MEDIA_DIR}\\TLgreen.png"
IMG_CROSS_BOTTOM     = f"{MEDIA_DIR}\\Cbottom.png"
IMG_PEDESTRIAN       = f"{MEDIA_DIR}\\Pedestrain.png"
IMG_BLOCK            = f"{MEDIA_DIR}\\Block.png"
IMG_HORIZONTAL_ZEBRA = f"{MEDIA_DIR}\\Zhorizontal.png"
IMG_TL_YELLOW        = f"{MEDIA_DIR}\\TLyellow.png"
IMG_ROAD_VERTICAL    = f"{MEDIA_DIR}\\Rvertical.png"
IMG_ROAD_CROSS       = f"{MEDIA_DIR}\\Rcrossroads.png"

PLACE_IMAGES = [IMG_CROSS_BOTTOM, IMG_PEDESTRIAN, IMG_BLOCK, IMG_HORIZONTAL_ZEBRA, IMG_TL_YELLOW]
ROAD_IMAGES  = [IMG_ROAD_VERTICAL, IMG_ROAD_CROSS]
FREE_PLACE_ITEMS = {IMG_PEDESTRIAN, IMG_BLOCK}
ROTATABLE_ITEMS  = {IMG_CROSS_BOTTOM, IMG_PEDESTRIAN, IMG_HORIZONTAL_ZEBRA, IMG_TL_YELLOW,
                    IMG_ROAD_VERTICAL, IMG_ROAD_CROSS}
CYCLE_TYPES = {
    IMG_CROSS_BOTTOM: [IMG_CROSS_BOTTOM, f"{MEDIA_DIR}\\BCvertical.png", f"{MEDIA_DIR}\\GCicon.ico"],
    IMG_BLOCK:        [IMG_BLOCK,        f"{MEDIA_DIR}\\Stop.png",       f"{MEDIA_DIR}\\Start.png"],
    IMG_TL_YELLOW:    [IMG_TL_YELLOW,    f"{MEDIA_DIR}\\TLred.png",      f"{MEDIA_DIR}\\TLgreen.png"],
}
CELL_SIZE = 36
COLS = 21
ROWS = 21

def load_pixmap(file_path, angle=0):
    """Загружает QPixmap с возможностью поворота."""
    pix = QPixmap(file_path)
    if angle and not pix.isNull():
        return pix.transformed(QTransform().rotate(angle))
    return pix

# ===== Класс основной сетки =====
class CellGrid(QWidget):
    def __init__(self, side_panel):
        super().__init__()
        self.setFixedSize(COLS * CELL_SIZE, ROWS * CELL_SIZE)
        self.side_panel = side_panel
        self.road_cells = {}
        self.object_cells = {}
        self.active_mode = None
        self.selected_item = None
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        col = int(event.position().x() // CELL_SIZE)
        row = int(event.position().y() // CELL_SIZE)
        if 0 <= col < COLS and 0 <= row < ROWS:
            self.setToolTip(f"x:{col} y:{row}")
        else:
            self.setToolTip("")

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(235, 235, 235))

        for layer in (self.road_cells, self.object_cells):
            for (cx, cy), item_data in layer.items():
                img = load_pixmap(item_data["path"], item_data["rot"])
                if not img.isNull():
                    painter.drawPixmap(cx * CELL_SIZE, cy * CELL_SIZE, CELL_SIZE, CELL_SIZE, img)

        painter.setPen(QPen(QColor(0, 0, 0, 50)))
        for i in range(COLS + 1):
            painter.drawLine(i * CELL_SIZE, 0, i * CELL_SIZE, ROWS * CELL_SIZE)
        for i in range(ROWS + 1):
            painter.drawLine(0, i * CELL_SIZE, COLS * CELL_SIZE, i * CELL_SIZE)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        col = int(event.position().x() // CELL_SIZE)
        row = int(event.position().y() // CELL_SIZE)
        if not (0 <= col < COLS and 0 <= row < ROWS):
            return
        cell_pos = (col, row)

        if self.active_mode == 'road' and self.selected_item:
            self.road_cells[cell_pos] = {"path": self.selected_item, "base": self.selected_item, "rot": 0}
        elif self.active_mode == 'place' and self.selected_item:
            if cell_pos in self.road_cells or self.selected_item in FREE_PLACE_ITEMS:
                self.object_cells[cell_pos] = {"path": self.selected_item, "base": self.selected_item, "rot": 0, "speed": 0}
        else:
            obj = self.object_cells.get(cell_pos) or self.road_cells.get(cell_pos)
            if obj:
                self.side_panel.show_props(cell_pos, obj, self)
        self.update()

    def save_to_file(self, file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            data = {
                "roads": {f"{k[0]},{k[1]}": v for k, v in self.road_cells.items()},
                "objs":  {f"{k[0]},{k[1]}": v for k, v in self.object_cells.items()}
            }
            json.dump(data, f, indent=2)

    def load_from_file(self, file_path):
        try:
            with open(file_path, encoding="utf-8") as f:
                raw_data = json.load(f)
            def parse_dict(d):
                return {tuple(map(int, key.split(","))): val for key, val in d.items()}
            self.road_cells = parse_dict(raw_data.get("roads", {}))
            self.object_cells = parse_dict(raw_data.get("objs", {}))
            self.update()
        except Exception:
            pass

# ===== Боковая панель =====
class SidePanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(140)  # немного расширим для комфорта
        self.grid_widget = None
        self.all_buttons = []    # кнопки выбора объектов

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        self.place_section = self._create_button_section(PLACE_IMAGES)
        self.road_section  = self._create_button_section(ROAD_IMAGES)
        self.props_panel = QWidget()
        self.props_layout = QVBoxLayout(self.props_panel)
        self.props_layout.setContentsMargins(0, 0, 0, 0)
        self.props_layout.setSpacing(4)

        for w in (self.place_section, self.road_section, self.props_panel):
            w.hide()
            main_layout.addWidget(w)

        main_layout.addStretch()  # прижимаем управляющие кнопки к низу

        # Контейнер для управляющих кнопок (всегда видим)
        self.control_container = QWidget()
        self.control_layout = QVBoxLayout(self.control_container)
        self.control_layout.setContentsMargins(0, 0, 0, 0)
        self.control_layout.setSpacing(4)
        main_layout.addWidget(self.control_container)

    def _create_button_section(self, image_paths):
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        for img_path in image_paths:
            btn = QPushButton()
            btn.setFixedSize(100, 100)
            btn.setCheckable(True)
            btn.setProperty("image_path", img_path)
            pix = load_pixmap(img_path)
            if not pix.isNull():
                btn.setIcon(QIcon(pix))
                btn.setIconSize(QSize(88, 88))
            else:
                btn.setText(os.path.basename(img_path)[:8])
            btn.clicked.connect(self._on_button_clicked)
            vbox.addWidget(btn)
            self.all_buttons.append(btn)
        return container

    def _on_button_clicked(self):
        sender = self.sender()
        for btn in self.all_buttons:
            if btn is not sender:
                btn.setChecked(False)
        if self.grid_widget:
            self.grid_widget.selected_item = sender.property("image_path") if sender.isChecked() else None

    def switch_mode(self, place_active=False, road_active=False):
        for btn in self.all_buttons:
            btn.setChecked(False)
        if self.grid_widget:
            self.grid_widget.selected_item = None
            if place_active:
                self.grid_widget.active_mode = 'place'
            elif road_active:
                self.grid_widget.active_mode = 'road'
            else:
                self.grid_widget.active_mode = None
        self.props_panel.hide()
        self.place_section.setVisible(place_active)
        self.road_section.setVisible(road_active)

    def setup_control_buttons(self, on_place_toggled, on_road_toggled, on_save, on_load):
        """Создаёт кнопки управления на боковой панели и подключает их."""
        self.btn_place = QPushButton("Добавить объекты")
        self.btn_place.setCheckable(True)
        self.btn_place.setFixedHeight(36)
        self.btn_place.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.control_layout.addWidget(self.btn_place)

        self.btn_road = QPushButton("Редактор дороги")
        self.btn_road.setCheckable(True)
        self.btn_road.setFixedHeight(36)
        self.btn_road.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.control_layout.addWidget(self.btn_road)

        # Разделитель
        line = QWidget()
        line.setFixedHeight(10)
        self.control_layout.addWidget(line)

        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setFixedHeight(36)
        self.btn_save.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.control_layout.addWidget(self.btn_save)

        self.btn_load = QPushButton("Загрузить")
        self.btn_load.setFixedHeight(36)
        self.btn_load.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.control_layout.addWidget(self.btn_load)

        # Подключаем сигналы
        self.btn_place.toggled.connect(on_place_toggled)
        self.btn_road.toggled.connect(on_road_toggled)
        self.btn_save.clicked.connect(on_save)
        self.btn_load.clicked.connect(on_load)

    def update_control_buttons_state(self, place_checked, road_checked):
        """Обновляет состояние кнопок (чтобы избежать зацикливания сигналов)."""
        self.btn_place.blockSignals(True)
        self.btn_road.blockSignals(True)
        self.btn_place.setChecked(place_checked)
        self.btn_road.setChecked(road_checked)
        self.btn_place.blockSignals(False)
        self.btn_road.blockSignals(False)

    def show_props(self, cell_pos, obj_data, grid_ref):
        while self.props_layout.count():
            w = self.props_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        self.props_panel.show()
        base_item = obj_data["base"]
        self.props_layout.addWidget(QLabel(f"<b>{os.path.basename(base_item)}</b>"))

        if base_item in ROTATABLE_ITEMS:
            rotate_btn = QPushButton("Повернуть")
            rotate_btn.clicked.connect(
                lambda: (obj_data.update(rot=(obj_data["rot"] + 90) % 360), grid_ref.update())
            )
            self.props_layout.addWidget(rotate_btn)

        if base_item in CYCLE_TYPES:
            cycle_btn = QPushButton("Изменить тип")
            cycle_list = CYCLE_TYPES[base_item]
            def cycle_type(_, obj=obj_data, cyc=cycle_list):
                idx = cyc.index(obj["path"]) if obj["path"] in cyc else 0
                obj["path"] = cyc[(idx + 1) % len(cyc)]
                grid_ref.update()
            cycle_btn.clicked.connect(cycle_type)
            self.props_layout.addWidget(cycle_btn)

        if base_item == IMG_PEDESTRIAN:
            speed_label = QLabel(f"Скорость: {obj_data.get('speed', 0)} сек")
            self.props_layout.addWidget(speed_label)
            for step_txt, delta in (("+1", 1), ("-1", -1)):
                step_btn = QPushButton(step_txt)
                def change_speed(_, obj=obj_data, dv=delta, lbl=speed_label):
                    obj["speed"] = obj.get("speed", 0) + dv
                    lbl.setText(f"Скорость: {obj['speed']} сек")
                step_btn.clicked.connect(change_speed)
                self.props_layout.addWidget(step_btn)

        delete_btn = QPushButton("Удалить")
        delete_btn.setStyleSheet("color:red;")
        def remove_item(_, pos=cell_pos, g=grid_ref):
            g.object_cells.pop(pos, None)
            g.road_cells.pop(pos, None)
            g.update()
            self.props_panel.hide()
        delete_btn.clicked.connect(remove_item)
        self.props_layout.addWidget(delete_btn)


# ===== Главное окно =====
class MainApplication(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Интеллектуальная Дорожная Система")
        icon_pix = QPixmap(ICON_TRAFFIC_LIGHT)
        if not icon_pix.isNull():
            self.setWindowIcon(QIcon(icon_pix))

        self.side_panel = SidePanel()
        self.grid_view = CellGrid(self.side_panel)
        self.side_panel.grid_widget = self.grid_view

        # Настраиваем управляющие кнопки на боковой панели
        self.side_panel.setup_control_buttons(
            on_place_toggled=self._on_place_toggled,
            on_road_toggled=self._on_road_toggled,
            on_save=self._save_grid,
            on_load=self._load_grid
        )

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addWidget(self.side_panel)
        hbox.addWidget(self.grid_view)
        root_layout.addLayout(hbox)

        self.adjustSize()

    def _on_place_toggled(self, checked):
        if checked:
            # Выключаем режим дороги, включаем режим объектов
            self.side_panel.update_control_buttons_state(place_checked=True, road_checked=False)
            self.side_panel.switch_mode(place_active=True)
        else:
            self.side_panel.update_control_buttons_state(place_checked=False, road_checked=False)
            self.side_panel.switch_mode()

    def _on_road_toggled(self, checked):
        if checked:
            self.side_panel.update_control_buttons_state(place_checked=False, road_checked=True)
            self.side_panel.switch_mode(road_active=True)
        else:
            self.side_panel.update_control_buttons_state(place_checked=False, road_checked=False)
            self.side_panel.switch_mode()

    def _save_grid(self):
        fname, _ = QFileDialog.getSaveFileName(self, "", "", "JSON (*.json)")
        if fname:
            self.grid_view.save_to_file(fname)

    def _load_grid(self):
        fname, _ = QFileDialog.getOpenFileName(self, "", "", "JSON (*.json)")
        if fname:
            self.grid_view.load_from_file(fname)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApplication()
    window.show()
    sys.exit(app.exec())