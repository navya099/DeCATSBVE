"""데이터셋 편집기 단독 실행 (수동 확인용): python TEST/dataset_editor_test.py [설계속도]"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dataset_edit import DatasetDocument  # noqa: E402
from gui.dataset_gui import DatasetEditor  # noqa: E402


def main():
    root = tk.Tk()
    root.withdraw()
    speed = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    editor = DatasetEditor(DatasetDocument.from_standard(speed))
    editor.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == '__main__':
    main()
