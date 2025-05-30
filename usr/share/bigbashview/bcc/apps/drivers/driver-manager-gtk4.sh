#!/bin/bash
# GTK4 version of the BigLinux Driver Manager launcher

# Ensure we're in the correct directory
cd "$(dirname "$0")"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not found."
    exit 1
fi

# Check if GTK4 and libadwaita are available
if ! python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); from gi.repository import Gtk, Adw" &> /dev/null; then
    echo "Error: GTK4 and libadwaita Python bindings are required but not found."
    exit 1
fi

# Launch the application
python3 driver_manager.py "$@"
