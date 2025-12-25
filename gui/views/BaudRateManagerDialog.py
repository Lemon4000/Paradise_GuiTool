# -*- coding: utf-8 -*-
"""
Baud Rate Manager Dialog
Used to add custom baud rates, remove custom baud rates, and set default baud rate
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QLineEdit, QMessageBox, QGroupBox
)


class BaudRateManagerDialog(QDialog):
    """Baud Rate Manager Dialog"""
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Baud Rate Manager")
        self.setModal(True)
        self.resize(500, 450)
        
        self._init_ui()
        self._load_baud_rates()
    
    def _init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        
        # Current baud rate list group
        list_group = QGroupBox("Current Baud Rate List")
        list_layout = QVBoxLayout(list_group)
        
        self.baud_list = QListWidget()
        self.baud_list.setSelectionMode(QListWidget.SingleSelection)
        list_layout.addWidget(self.baud_list)
        
        # List operation buttons
        list_btn_layout = QHBoxLayout()
        self.btn_set_default = QPushButton("Set as Default")
        self.btn_set_default.setToolTip("Set selected baud rate as default")
        self.btn_delete = QPushButton("Delete Custom")
        self.btn_delete.setToolTip("Delete selected custom baud rate (built-in rates cannot be deleted)")
        list_btn_layout.addWidget(self.btn_set_default)
        list_btn_layout.addWidget(self.btn_delete)
        list_btn_layout.addStretch()
        list_layout.addLayout(list_btn_layout)
        
        layout.addWidget(list_group)
        
        # Add new baud rate group
        add_group = QGroupBox("Add Custom Baud Rate")
        add_layout = QVBoxLayout(add_group)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Baud Rate:"))
        self.input_baud = QLineEdit()
        self.input_baud.setPlaceholderText("Enter value between 300-3000000")
        self.input_baud.setValidator(QIntValidator(300, 3000000))
        input_layout.addWidget(self.input_baud)
        self.btn_add = QPushButton("Add")
        self.btn_add.setMinimumWidth(80)
        input_layout.addWidget(self.btn_add)
        add_layout.addLayout(input_layout)
        
        layout.addWidget(add_group)
        
        # Bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.setMinimumWidth(100)
        bottom_layout.addWidget(self.btn_close)
        layout.addLayout(bottom_layout)
        
        # Connect signals
        self.btn_add.clicked.connect(self._on_add_clicked)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_set_default.clicked.connect(self._on_set_default_clicked)
        self.btn_close.clicked.connect(self.accept)
        self.baud_list.itemSelectionChanged.connect(self._on_selection_changed)
    
    def _load_baud_rates(self):
        """Load baud rate list"""
        self.baud_list.clear()
        baud_rates = self.config_manager.get_baud_rates()
        default_baud = self.config_manager.get_default_baud_rate()
        
        for baud in baud_rates:
            is_custom = self.config_manager.is_custom_baud_rate(baud)
            is_default = (baud == default_baud)
            
            # Build display text
            text = f"{baud}"
            if is_default:
                text += " [Default]"
            if is_custom:
                text += " [Custom]"
            
            self.baud_list.addItem(text)
        
        self._on_selection_changed()
    
    def _on_selection_changed(self):
        """Update button state when selection changes"""
        has_selection = len(self.baud_list.selectedItems()) > 0
        self.btn_set_default.setEnabled(has_selection)
        
        # Only custom baud rates can be deleted
        can_delete = False
        if has_selection:
            selected_text = self.baud_list.selectedItems()[0].text()
            can_delete = "[Custom]" in selected_text
        
        self.btn_delete.setEnabled(can_delete)
    
    def _get_selected_baud_rate(self):
        """Get selected baud rate value"""
        if not self.baud_list.selectedItems():
            return None
        
        text = self.baud_list.selectedItems()[0].text()
        # Extract numeric part
        try:
            baud_str = text.split()[0]
            return int(baud_str)
        except:
            return None
    
    def _on_add_clicked(self):
        """Add button clicked"""
        text = self.input_baud.text().strip()
        if not text:
            QMessageBox.warning(self, "Error", "Please enter baud rate value")
            return
        
        try:
            baud = int(text)
            if baud < 300 or baud > 3000000:
                QMessageBox.warning(self, "Error", "Baud rate must be between 300-3000000")
                return
            
            if self.config_manager.add_custom_baud_rate(baud):
                QMessageBox.information(self, "Success", f"Added baud rate: {baud}")
                self.input_baud.clear()
                self._load_baud_rates()
            else:
                QMessageBox.information(self, "Info", "Baud rate already exists")
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter valid number")
    
    def _on_delete_clicked(self):
        """Delete button clicked"""
        baud = self._get_selected_baud_rate()
        if baud is None:
            return
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete custom baud rate {baud}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.config_manager.remove_custom_baud_rate(baud):
                QMessageBox.information(self, "Success", f"Deleted baud rate: {baud}")
                self._load_baud_rates()
            else:
                QMessageBox.warning(self, "Error", "Delete failed, this baud rate may not be custom")
    
    def _on_set_default_clicked(self):
        """Set as default button clicked"""
        baud = self._get_selected_baud_rate()
        if baud is None:
            return
        
        self.config_manager.set_default_baud_rate(baud)
        QMessageBox.information(self, "Success", f"Set {baud} as default baud rate")
        self._load_baud_rates()
