"""
Custom widgets for the hardware info page.
"""
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

class CategoryRow(Adw.ActionRow):
    """
    Custom row class for the category list that can store the category ID.
    """
    
    def __init__(self, title: str, category_id: str, icon_name: str = None):
        """
        Initialize a new category row.
        
        Args:
            title: The display title for the row
            category_id: The category ID to store with this row
            icon_name: Optional icon name to display in the row
        """
        super().__init__()
        self.set_title(title)
        self.category_id = category_id
        
        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            self.add_prefix(icon)
