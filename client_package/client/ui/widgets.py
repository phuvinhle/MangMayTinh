from PyQt5.QtWidgets import QTableWidgetItem

class NumericItem(QTableWidgetItem):
    """Custom table item for proper numerical sorting using raw data."""
    def __init__(self, text, sort_val):
        super().__init__(text)
        self.sort_val = sort_val
    def __lt__(self, other):
        if isinstance(other, NumericItem): return self.sort_val < other.sort_val
        return super().__lt__(other)
