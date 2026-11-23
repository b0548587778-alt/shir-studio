"""חלון המחרוזת: בוחרים שירים, מסדרים אותם, ומחברים לקובץ אחד."""
import os

from PySide6.QtCore import Qt, QStandardPaths
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QCheckBox,
                               QDoubleSpinBox, QFileDialog)

from .trimview import CSS

FILTER = "קבצי שיר (*.mp3 *.wav *.flac *.ogg)"


class MedleyDialog(QDialog):
    def __init__(self, parent, style_name=""):
        super().__init__(parent)
        self.setWindowTitle("מחרוזת - כמה שירים בקובץ אחד")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(CSS)
        v = QVBoxLayout(self)
        lab = QLabel("הוסף את השירים וסדר אותם לפי הסדר שבו יושמעו. בין שיר לשיר יהיה מעבר חלק.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        row = QHBoxLayout()
        self.list = QListWidget()
        row.addWidget(self.list, 1)
        col = QVBoxLayout()
        for text, fn in (("➕  הוסף שירים", self.add_files), ("▲  למעלה", lambda: self.move(-1)),
                         ("▼  למטה", lambda: self.move(1)), ("✖  הסר", self.remove)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            col.addWidget(b)
        col.addStretch()
        row.addLayout(col)
        v.addLayout(row, 1)
        self.process = QCheckBox(f"הקבצים הם שירה בלי ליווי - קודם להכין לכל אחד שיר מלא"
                                 + (f" (סגנון: {style_name})" if style_name else ""))
        v.addWidget(self.process)
        h = QHBoxLayout()
        h.addWidget(QLabel("אורך המעבר בין שיר לשיר:"))
        self.cross = QDoubleSpinBox()
        self.cross.setRange(0.0, 8.0)
        self.cross.setSingleStep(0.5)
        self.cross.setValue(2.0)
        self.cross.setSuffix(" שניות")
        h.addWidget(self.cross); h.addStretch()
        v.addLayout(h)
        h = QHBoxLayout()
        self.ok = QPushButton("🎼  צור מחרוזת")
        self.ok.setStyleSheet("background:#2c7a3f; color:white; font-weight:bold;")
        self.ok.setEnabled(False)
        self.ok.clicked.connect(self.accept)
        cancel = QPushButton("ביטול")
        cancel.clicked.connect(self.reject)
        h.addWidget(self.ok, 2); h.addWidget(cancel, 1)
        v.addLayout(h)
        self._paths = []
        self.resize(760, 520)

    def add_paths(self, paths):
        for p in paths:
            self._paths.append(p)
            self.list.addItem(os.path.basename(p))
        self.ok.setEnabled(len(self._paths) >= 2)

    def add_files(self):
        start = QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
        paths, _ = QFileDialog.getOpenFileNames(self, "בחר שירים למחרוזת", start, FILTER)
        self.add_paths(paths)

    def move(self, d):
        i = self.list.currentRow()
        j = i + d
        if i < 0 or not 0 <= j < len(self._paths):
            return
        self._paths[i], self._paths[j] = self._paths[j], self._paths[i]
        self.list.insertItem(j, self.list.takeItem(i))
        self.list.setCurrentRow(j)

    def remove(self):
        i = self.list.currentRow()
        if i >= 0:
            self.list.takeItem(i)
            del self._paths[i]
        self.ok.setEnabled(len(self._paths) >= 2)

    def paths(self):
        return list(self._paths)
