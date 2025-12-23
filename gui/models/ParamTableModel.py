from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
import Usart_Para_FK as proto

COLS = ['Key','Name','Unit','Min','Max','Precision','Value','Description']

class ParamTableModel(QAbstractTableModel):
    def __init__(self, group: str):
        super().__init__()
        self.group = group
        self.rows = []
        self.reload(group)

    def reload(self, group: str):
        self.beginResetModel()
        self.group = group
        raw = proto.load_mapping(group)
        self.rows = []
        for r in raw:
            def clean(x):
                if x is None:
                    return ''
                s = str(x).strip()
                return '' if s.lower() in ('null','none','nan') else s
            row = {
                'Key': clean(r.get('Key','')),
                'Name': clean(r.get('Name','')),
                'Unit': clean(r.get('Unit','')),
                'Min': clean(r.get('Min','')),
                'Max': clean(r.get('Max','')),
                'Precision': clean(r.get('Precision','2')) or '2',
                'Value': clean(r.get('Default','')),
                'Description': clean(r.get('Description','')),
            }
            self.rows.append(row)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLS)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLS[section]
        return None

    def data(self, index, role):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = COLS[index.column()]
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return row.get(col,'')
        return None

    def flags(self, index):
        base = super().flags(index)
        if COLS[index.column()] == 'Value':
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index, value, role):
        if role != Qt.EditRole:
            return False
        row = self.rows[index.row()]
        if COLS[index.column()] == 'Value':
            try:
                v = float(value)
                mn = float(row['Min']) if row['Min']!='' else None
                mx = float(row['Max']) if row['Max']!='' else None
                if mn is not None and v < mn:
                    return False
                if mx is not None and v > mx:
                    return False
                prec = int(row['Precision']) if row['Precision']!='' else 2
                row['Value'] = f'{v:.{prec}f}'
                self.dataChanged.emit(index, index, [Qt.DisplayRole])
                return True
            except Exception:
                return False
        return False

    def valuesDict(self):
        out = {}
        for r in self.rows:
            k = r.get('Key','')
            if k:
                try:
                    out[k] = float(r.get('Value',''))
                except Exception:
                    pass
        return out

    def updateValues(self, data: dict):
        for i, r in enumerate(self.rows):
            k = r.get('Key','')
            if k in data:
                v = data[k]
                try:
                    prec = int(r.get('Precision','2'))
                except Exception:
                    prec = 2
                r['Value'] = f'{v:.{prec}f}'
        self.dataChanged.emit(self.index(0,0), self.index(self.rowCount()-1, self.columnCount()-1), [Qt.DisplayRole])

    def setAllValuesError(self):
        for r in self.rows:
            r['Value'] = 'Error'
        self.dataChanged.emit(self.index(0,0), self.index(self.rowCount()-1, self.columnCount()-1), [Qt.DisplayRole])
