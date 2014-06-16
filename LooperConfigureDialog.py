#!/usr/bin/env python
# encoding: utf-8
import os
import rb
from gi.repository import Gtk, Gio, GObject, PeasGtk


class LooperConfigureDialog(GObject.Object, PeasGtk.Configurable):
    __gtype_name__ = 'LooperConfigureDialog'
    object = GObject.property(type=GObject.Object)

    positions = ['TOP', 'BOTTOM', 'SIDEBAR', 'RIGHT SIDEBAR']
    LOOPER_DIR = os.path.dirname(os.path.abspath(__file__))

    def __init__(self):
        GObject.Object.__init__(self)
        self.settings = Gio.Settings("org.gnome.rhythmbox.plugins.looper")

    def do_create_configure_widget(self):
        def set_looper_position(spiner):
            self.settings['position'] = self.positions[spiner.get_active()]

        def set_looper_always_show(button):
            self.settings['always-show'] = button.get_active()

        self.configure_callback_dic = {
            "rb_looper_position_changed": set_looper_position,
            "rb_looper_always_show_changed": set_looper_always_show,
        }
        builder = Gtk.Builder()
        PREFS_PATH = rb.find_plugin_file(self, 'ui/looper-prefs.ui')
        builder.add_from_file(PREFS_PATH)

        self.config = builder.get_object("config")

        active_position = self.positions.index(self.settings['position'])
        builder.get_object("rb_looper_position").set_active(active_position)
        always_show = self.settings['always-show']
        builder.get_object("rb_looper_always_show").set_active(always_show)
        builder.connect_signals(self.configure_callback_dic)
        return self.config
