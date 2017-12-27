# -*- Mode: python; coding: utf-8; tab-width: 4; indent-tabs-mode: nil; -*-
###############################################################################
# Copyright 2013 Ivan Augustinović
#
# This file is part of Looper.
#
# Looper is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# Looper is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# Looper. If not, see http://www.gnu.org/licenses/.
###############################################################################

import os
import sys
import json
import math
import shutil
import hashlib
from string import Template

from gi.repository import Gio, Gtk, GObject, RB, Peas, GLib, Gdk, Gst

import rb
from looper_rb3compat import ActionGroup
from looper_rb3compat import ApplicationShell
from looper_rb3compat import is_rb3

from tuner import Tuner
from LooperConfigureDialog import LooperConfigureDialog


# Minimal allowed range in seconds.
# (1 second is too small for meaningful sound)
MIN_RANGE = 2

ON_LABEL = 'Enabled'

OFF_LABEL = 'Disabled'


def create_slider(*args):
    if not args:
        args = (0, 0, 0, 1, 1, 0)
    adj = Gtk.Adjustment(*args)
    slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                        adjustment=adj)
    slider.set_digits(0)
    return slider


def seconds_to_time(seconds):
    """Converts seconds to time format (MM:SS)."""
    m, s = divmod(int(seconds), 60)
    return "%02d:%02d" % (m, s)


class LoopControl(Gtk.Grid):
    def __init__(self, looper, index, name, start_slider_value, end_slider_value):
        super(LoopControl, self).__init__()
        self.index = index
        self.name = name
        self.looper = looper
        self.start_slider_value = start_slider_value
        self.end_slider_value = end_slider_value
        self.create_widgets()
        self.connect_signals()

    def create_widgets(self):
        self.loop_name = Gtk.Entry()

        self.stack = Gtk.Stack()

        self.activation_btn = Gtk.Button()
        self.activation_btn.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        self.activation_btn_menu = Gtk.Menu()
        self.rename_item = Gtk.MenuItem('Rename')
        self.delete_item = Gtk.MenuItem('Delete')
        self.activation_btn_menu.append(self.rename_item)
        self.activation_btn_menu.append(self.delete_item)
        self.activation_btn_menu.show_all()

        self.start_slider = self.create_slider(self.start_slider_value,
                                               self.looper.start_slider_min,
                                               self.looper.start_slider_max)
        self.end_slider = self.create_slider(self.end_slider_value,
                                             self.looper.end_slider_min,
                                             self.looper.end_slider_max)

        self.stack.add_named(self.loop_name, 'loop_name')
        self.stack.add_named(self.activation_btn, 'activation_btn')

        self.attach(self.stack, 0, 0, 2, 1)
        self.attach(self.start_slider, 0, 1, 1, 1)
        self.attach(self.end_slider, 1, 1, 1, 1)
        self.show_all()
        self.stack.set_visible_child_name('activation_btn')
        # WEIRD BUG: Have to reset slider values again here as they would only
        # sometimes be set by the `create_slider`. I suppose this works
        # because it is after `show_all`.
        self.start_slider.set_value(self.start_slider_value)
        self.end_slider.set_value(self.end_slider_value)
        self.activation_btn.set_label(self.name)

    def create_slider(self, value, min_value, max_value):
        label = seconds_to_time(value)
        slider = Gtk.ScaleButton(label=label)
        slider.set_orientation(Gtk.Orientation.HORIZONTAL)
        adj = Gtk.Adjustment(value, min_value, max_value, 1, 1, 0)
        slider.set_adjustment(adj)
        return slider

    def connect_signals(self):
        self.rename_done_sigid = self.loop_name.connect('activate', self.on_rename_done)
        self.show_rename_sigid = self.rename_item.connect("activate", self.on_show_rename)
        self.delete_sigid = self.delete_item.connect("activate", self.on_delete)
        self.activation_btn_sigid = self.activation_btn.connect(
            'button-press-event', self.on_activation, self.activation_btn_menu)
        self.start_slider_moved_sigid = self.start_slider.connect(
            'value-changed', self.on_slider_moved, 'start')
        self.end_slider_moved_sigid = self.end_slider.connect(
            'value-changed', self.on_slider_moved, 'end')

    def on_activation(self, button, event, menu):
        is_success, button = event.get_button()
        if is_success:
            # right click
            if button == 3:
                menu.popup(None, None, None, None, button, Gtk.get_current_event_time())
            # left click
            elif button == 1:
                self.set_loop()
        return True

    def on_slider_moved(self, button, value, moving_slider):
        """Dont let Start slider be greater than End or vice versa."""
        start_value = self.start_slider.get_value()
        end_value = self.end_slider.get_value()
        min_range = self.looper.controls.min_range.get_value_as_int()
        if moving_slider == 'start':
            slider_start_max = end_value - min_range
            if start_value > slider_start_max:
                if self.looper.duration and end_value >= self.looper.duration:
                    new_value = end_value - min_range
                    self.start_slider.set_value(new_value)
                else:
                    new_value = start_value + min_range
                    self.end_slider.set_value(new_value)
        else:
            slider_end_min = start_value + min_range
            if end_value < slider_end_min:
                if start_value == 0.0:
                    new_value = start_value + min_range
                    self.end_slider.set_value(new_value)
                else:
                    new_value = end_value - min_range
                    self.start_slider.set_value(new_value)
        self.refresh_slider_label()
        self.update_loop()
        self.looper.save_loops()

    def update_loop(self):
        song_id = self.looper.get_song_id()
        if song_id and song_id in self.looper.loops:
            loop = self.looper.loops[song_id][self.index]
            loop['start'] = self.start_slider.get_value()
            loop['end'] = self.end_slider.get_value()
            loop['name'] = self.name

    def refresh_slider_label(self):
        start_slider_label = seconds_to_time(self.start_slider.get_value())
        self.start_slider.set_label(start_slider_label)

        end_slider_label = seconds_to_time(self.end_slider.get_value())
        self.end_slider.set_label(end_slider_label)

    def set_loop(self):
        self.looper.controls.start_slider.set_value(self.start_slider.get_value())
        self.looper.controls.end_slider.set_value(self.end_slider.get_value())

    def on_show_rename(self, widget):
        self.stack.set_visible_child_name('loop_name')
        self.loop_name.grab_focus()
        self.rename_canceled_sigid = self.loop_name.connect(
            'focus-out-event', self.on_rename_canceled)

    def on_rename_done(self, widget):
        name = widget.get_text()
        self.activation_btn.set_label(name)
        self.name = name
        self.update_loop()
        self.stack.set_visible_child_name('activation_btn')
        self.disconnect_rename_canceled()
        self.looper.save_loops()
        return True

    def on_rename_canceled(self, widget, event):
        self.disconnect_rename_canceled()
        widget.set_text('')
        self.stack.set_visible_child_name('activation_btn')

    def disconnect_rename_canceled(self):
        if self.rename_canceled_sigid:
            self.loop_name.disconnect(self.rename_canceled_sigid)
        self.rename_canceled_sigid = None

    def on_delete(self, widget):
        song_id = self.looper.get_song_id()
        if song_id in self.looper.loops:
            del self.looper.loops[song_id][self.index]
        self.looper.clear_loops()
        self.looper.load_song_loops()
        self.looper.save_loops()

    def destroy_widgets(self):
        del self.loop_name
        del self.stack
        del self.activation_btn
        del self.activation_btn_menu
        del self.rename_item
        del self.delete_item
        del self.start_slider
        del self.end_slider

    def disconnect_signals(self):
        self.loop_name.disconnect(self.rename_done_sigid)
        self.rename_item.disconnect(self.show_rename_sigid)
        self.delete_item.disconnect(self.delete_sigid)
        self.activation_btn.disconnect(self.activation_btn_sigid)
        self.start_slider.disconnect(self.start_slider_moved_sigid)
        self.end_slider.disconnect(self.end_slider_moved_sigid)

    def deactivate(self):
        self.disconnect_signals()
        self.destroy_widgets()


class RbPitchElem(Gtk.Box):
    def __init__(self, label, adj, presets=None, on_preset_clicked_callback=None):
        super(RbPitchElem, self).__init__()
        self.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.slider = create_slider(*adj)
        self.slider.set_value_pos(Gtk.PositionType.LEFT)
        self.label = Gtk.Label('%s (%%): ' % label)
        self.pack_start(self.label, False, False, 0)
        self.pack_start(self.slider, True, True, 0)
        if presets and on_preset_clicked_callback:
            for label, value in presets:
                button = Gtk.Button(label)
                button.value = value
                button.connect('clicked', on_preset_clicked_callback)
                self.pack_start(button, False, False, 2)


class RbPitch(Gtk.Box):
    DEFAULT_ADJUSTMENT = (100, 10, 1000, 1, 1, 0)
    TEMPO_PRESETS = [
        ('x0.5', 50),
        ('x0.6', 60),
        ('x0.7', 70),
        ('x0.75', 75),
        ('x0.8', 80),
        ('x0.9', 90),
        ('x1.5', 150),
        ('x2', 200),
        ('reset', 100),
    ]
    PITCH_PRESETS = TEMPO_PRESETS
    RATE_PRESETS = TEMPO_PRESETS
    def __init__(self, looper):
        super(RbPitch, self).__init__()
        self.looper = looper
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.tempo_val = 100
        self.pitch_val = 100
        self.rate_val = 100

        self.tempo = RbPitchElem('Tempo', self.DEFAULT_ADJUSTMENT, self.TEMPO_PRESETS, self.on_tempo_preset)
        self.pitch = RbPitchElem('Pitch', self.DEFAULT_ADJUSTMENT, self.PITCH_PRESETS, self.on_pitch_preset)
        self.rate = RbPitchElem('Rate', self.DEFAULT_ADJUSTMENT, self.RATE_PRESETS, self.on_rate_preset)

        self.gst_pitch = Gst.ElementFactory.make('pitch', None)
        if not self.gst_pitch:
            self.pack_start(Gtk.Label('pitch missing'), True, True, 0)

        self.pack_start(self.tempo, True, True, 0)
        self.pack_start(self.pitch, True, True, 0)
        self.pack_start(self.rate, True, True, 0)

        self.tempo_slider_sigid = self.tempo.slider.connect("value-changed", self.on_tempo_change)
        self.pitch_slider_sigid = self.pitch.slider.connect("value-changed", self.on_pitch_change)
        self.rate_slider_sigid = self.rate.slider.connect("value-changed", self.on_rate_change)

    def on_tempo_preset(self, button):
        self.tempo.slider.set_value(button.value)

    def on_pitch_preset(self, button):
        self.pitch.slider.set_value(button.value)

    def on_rate_preset(self, button):
        self.rate.slider.set_value(button.value)

    def on_tempo_change(self, slider):
        if self.gst_pitch:
            tempo = slider.get_value()
            self.gst_pitch.set_property('tempo', tempo / 100)

    def on_pitch_change(self, slider):
        if self.gst_pitch:
            pitch = slider.get_value()
            self.gst_pitch.set_property('pitch', pitch / 100)

    def on_rate_change(self, slider):
        if self.gst_pitch:
            rate = slider.get_value()
            self.gst_pitch.set_property('rate', rate / 100)

    def destroy_widgets(self):
        self.tempo.slider.disconnect(self.tempo_slider_sigid)
        self.pitch.slider.disconnect(self.pitch_slider_sigid)
        self.rate.slider.disconnect(self.rate_slider_sigid)
        if self.gst_pitch:
            self.looper.player.remove_filter(self.gst_pitch)
        del self.tempo
        del self.pitch
        del self.rate
        del self.looper
        del self.gst_pitch


class Controls(Gtk.Grid):
    def __init__(self, looper):
        super(Controls, self).__init__()
        self.looper = looper
        self.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.set_row_spacing(5)
        self.set_column_spacing(2)
        self.set_column_homogeneous(True)
        self.set_row_homogeneous(True)

        self.save_loop_btn = Gtk.Button(label='Save loop')

        self.tuner_btn = Gtk.Button('Tuner')
        self.tuner_sigid = self.tuner_btn.connect('clicked', self.on_tuner_btn_clicked)

        self.audiokaraoke = Gst.ElementFactory.make('audiokaraoke', None)
        self.audiokaraoke_btn = Gtk.ToggleButton('Filter out speech')
        self.audiokaraoke_sigid = self.audiokaraoke_btn.connect('clicked', self.on_audiokaraoke_toggle)

        self.rbpitch_btn = Gtk.ToggleButton('T/P/R')
        self.rbpitch_sigid = self.rbpitch_btn.connect('clicked', self.on_rbpitch_toggle)

        self.min_range_label = Gtk.Label()
        self.min_range_label.set_text('Min range ')
        adj = Gtk.Adjustment(MIN_RANGE, MIN_RANGE, MIN_RANGE, 1, 10, 0)
        self.min_range = Gtk.SpinButton(adjustment=adj)

        if is_rb3(looper.shell):
            self.activation_btn = Gtk.Button(OFF_LABEL)
        else:
            self.activation_btn = Gtk.CheckButton()
            self.activation_btn.set_related_action(self.action.action)

        self.status_label = Gtk.ProgressBar()
        self.status_label.set_show_text(True)

        self.start_slider = create_slider()
        self.start_slider.set_property('margin-left', 5)
        self.end_slider = create_slider()
        self.end_slider.set_property('margin-right', 5)

        self.attach(self.start_slider, 0, 0, 7, 2)
        self.attach(self.end_slider, 7, 0, 7, 2)

        self.attach(self.status_label, 0, 2, 14, 2)

        self.attach(self.tuner_btn, 0, 4, 2, 2)
        self.attach(self.audiokaraoke_btn, 2, 4, 2, 2)
        self.attach(self.rbpitch_btn, 4, 4, 2, 2)
        self.attach(self.min_range_label, 6, 4, 2, 2)
        self.attach(self.min_range, 8, 4, 1, 2)
        self.attach(self.save_loop_btn, 10, 4, 2, 2)
        self.attach(self.activation_btn, 12, 4, 2, 2)

        if is_rb3(looper.shell):
            # In RB3 plugins cannot be activated from custom buttons so
            # we need to hack it with dummy button that will emit activation
            # on click. If Looper is activated through Rhythmbox just change
            # activation_btn label else if Looper is activated through
            # our button, change the button label and emit a signal for
            # Rhythmbox.
            self.action_sigid = looper.action.connect(
                'change-state', self.on_rb_activation, '')
            self.activation_btn_sigid = self.activation_btn.connect(
                'clicked', self.on_btn_activation)

        self.min_range_sigid = self.min_range.connect(
            'value-changed', self.on_min_range_changed)

        self.start_slider_changed_sigid = self.start_slider.connect(
            "value-changed", self.on_slider_moved, 'start')
        self.end_slider_changed_sigid = self.end_slider.connect(
            "value-changed", self.on_slider_moved, 'end')

        # Start and End slider values need to be formated from
        # seconds to (MM:SS)
        self.start_slider_value_sigid = self.start_slider.connect(
            "format-value", self.on_format_slider_value)
        self.end_slider_value_sigid = self.end_slider.connect(
            "format-value", self.on_format_slider_value)

        self.save_loop_btn_sigid = self.save_loop_btn.connect(
            'clicked', looper.on_save_loop)

    def on_rb_activation(self, action, state, data):
        """
        Change our custom activation button label as appropriate for the
        current activation state.
        """
        if state:
            self.activation_btn.set_label(ON_LABEL)
            self.activation_btn.get_style_context().add_class('looper_active')
        else:
            self.activation_btn.set_label(OFF_LABEL)
            self.activation_btn.get_style_context().remove_class('looper_active')

    def on_btn_activation(self, button):
        """
        Change our custom activation button label as appropriate for the
        next activation state and send a signal to Rhythmbox to change
        the active state.
        """
        label = self.activation_btn.get_label()
        # It seems that the value of state parameter (True/False) has no
        # effect on self.action.action.emit('activate', state) result, But
        # it's required.
        if label == ON_LABEL:
            state = GLib.Variant('b', False)
            label = OFF_LABEL
        else:
            state = GLib.Variant('b', True)
            label = ON_LABEL
        self.looper.action.action.emit('activate', state)

    def on_min_range_changed(self, spinner):
        # simulate slider moved event so sliders obey new min_range value
        self.on_slider_moved(self.start_slider, 'start')

    def on_slider_moved(self, slider, moving_slider):
        """Dont let Start slider be greater than End or vice versa."""
        start_value = self.start_slider.get_value()
        end_value = self.end_slider.get_value()
        min_range = self.min_range.get_value_as_int()
        if moving_slider == 'start':
            slider_start_max = end_value - min_range
            if start_value > slider_start_max:
                if self.looper.duration and end_value >= self.looper.duration:
                    new_value = end_value - min_range
                    self.start_slider.set_value(new_value)
                else:
                    new_value = start_value + min_range
                    self.end_slider.set_value(new_value)
        else:
            slider_end_min = start_value + min_range
            if end_value < slider_end_min:
                if start_value == 0.0:
                    new_value = start_value + min_range
                    self.end_slider.set_value(new_value)
                else:
                    new_value = end_value - min_range
                    self.start_slider.set_value(new_value)

        self.looper.refresh_rb_position_slider()

    def on_format_slider_value(self, scale, value):
        return seconds_to_time(value)

    def refresh_min_range_button(self):
        current_value = self.min_range.get_value_as_int()
        if self.looper.duration is None:
            lower_limit = MIN_RANGE
            upper_limit = MIN_RANGE
            current_value = MIN_RANGE
        else:
            lower_limit = MIN_RANGE
            upper_limit = self.looper.duration

        if current_value > upper_limit:
            current_value = upper_limit

        adj = self.min_range.get_adjustment()
        adj.set_lower(lower_limit)
        adj.set_upper(upper_limit)
        adj.set_value(current_value)
        self.min_range.set_numeric(True)
        self.min_range.set_update_policy(1)

    def refresh_sliders(self):
        """Set the Looper's slider boundries to the current song duration."""
        if self.looper.duration:
            start_adj = self.start_slider.get_adjustment()
            start_adj.set_lower(self.looper.start_slider_min)
            start_adj.set_upper(self.looper.start_slider_max)
            start_adj.set_value(0)

            end_adj = self.end_slider.get_adjustment()
            end_adj.set_lower(self.looper.end_slider_min)
            end_adj.set_upper(self.looper.end_slider_max)
            end_adj.set_value(self.looper.duration)

    def on_audiokaraoke_toggle(self, button):
        if self.audiokaraoke:
            if button.get_active() is True:
                self.looper.player.add_filter(self.audiokaraoke)
            else:
                self.looper.player.remove_filter(self.audiokaraoke)
        else:
            self.audiokaraoke_btn.set_label('audiokaraoke missing')

    def on_tuner_btn_clicked(self, button):
        tuner = Tuner([16, 21, 26, 31, 35, 40])
        tuner.run()
        tuner.destroy()

    def on_rbpitch_toggle(self, button):
        if self.looper.rbpitch.gst_pitch:
            if button.get_active() is True:
                self.looper.player.add_filter(self.looper.rbpitch.gst_pitch)
            else:
                self.looper.player.remove_filter(self.looper.rbpitch.gst_pitch)
        else:
            self.rbpitch_btn.set_label('pitch missing')

    def destroy_widgets(self):
        if is_rb3(self.looper.shell):
            self.activation_btn.disconnect(self.activation_btn_sigid)
        self.min_range.disconnect(self.min_range_sigid)
        self.start_slider.disconnect(self.start_slider_changed_sigid)
        self.start_slider.disconnect(self.start_slider_value_sigid)
        self.end_slider.disconnect(self.end_slider_changed_sigid)
        self.end_slider.disconnect(self.end_slider_value_sigid)
        self.save_loop_btn.disconnect(self.save_loop_btn_sigid)
        self.tuner_btn.disconnect(self.tuner_sigid)
        self.audiokaraoke_btn.disconnect(self.audiokaraoke_sigid)
        self.rbpitch_btn.disconnect(self.rbpitch_sigid)
        del self.looper
        del self.save_loop_btn
        del self.min_range_label
        del self.min_range
        del self.activation_btn
        del self.status_label
        del self.start_slider
        del self.end_slider
        del self.tuner_btn
        del self.rbpitch_btn
        del self.audiokaraoke_btn
        del self.audiokaraoke


class LooperPlugin(GObject.Object, Peas.Activatable):
    """
    Loops part of the song defined by Start and End Gtk sliders.
    """
    object = GObject.property(type=GObject.Object)

    # Available positions in the RB GUI.
    # They are chosen through user settings.
    POSITIONS = {
        'TOP': RB.ShellUILocation.MAIN_TOP,
        'BOTTOM': RB.ShellUILocation.MAIN_BOTTOM,
        'SIDEBAR': RB.ShellUILocation.SIDEBAR,
        'RIGHT SIDEBAR': RB.ShellUILocation.RIGHT_SIDEBAR,
    }

    STATUS_TPL = Template('[Loop Duration: $duration] ' +
                          '[Current time: $time]')

    # Number of seconds that the End slider is less than a song
    # duration. Its needed because in that period Rhythmbox would
    # change to the next song. Thats why we dont go there.
    SEC_BEFORE_END = 3

    LOOPS_FILENAME = '.loops.json'

    LOOPS_PER_ROW = 8

    MAX_LOOPS_NUM = 32

    UI = """
    <ui>
        <menubar name="MenuBar">
            <menu name="ViewMenu" action="View">
                <menuitem name="LooperPlugin" action="ActivateLooper" />
            </menu>
        </menubar>
    </ui>
    """

    def __init__(self):
        super(LooperPlugin, self).__init__()

    def do_activate(self):
        self.load_css()
        self.settings = Gio.Settings("org.gnome.rhythmbox.plugins.looper")
        # old value will be needed when removing/adding(moving) GUI
        self.gui_position = self.POSITIONS[self.settings['position']]
        self.shell = self.object
        self.shell_player = self.shell.props.shell_player
        self.player = self.shell_player.props.player
        self.db = self.shell.props.db

        self.appshell = ApplicationShell(self.shell)
        self.main_box = Gtk.Box()
        self.main_box.set_orientation(Gtk.Orientation.VERTICAL)

        self.controls_box = Gtk.Box()
        self.controls_box.set_orientation(Gtk.Orientation.VERTICAL)

        self._create_main_action()

        self.controls = Controls(self)
        controls_frame = Gtk.Frame()
        controls_frame.add(self.controls)
        controls_frame.set_property('margin-left', 2)
        controls_frame.set_property('margin-right', 2)
        self.rbpitch = RbPitch(self)
        rbpitch_frame = Gtk.Frame()
        rbpitch_frame.add(self.rbpitch)
        rbpitch_frame.set_property('margin-left', 2)
        rbpitch_frame.set_property('margin-right', 2)
        self.controls_box.pack_start(rbpitch_frame, True, True, 5)
        self.controls_box.pack_start(controls_frame, True, True, 5)

        self.loops_box = Gtk.Grid()
        self.loops_box.set_row_spacing(2)
        self.loops_box.set_column_spacing(2)
        self.loops_box.set_column_homogeneous(True)
        self.loops_box.set_row_homogeneous(True)
        self.loops_box.set_border_width(0)

        self.rb_slider = self.find_rb_slider()

        self.main_box.pack_start(self.controls_box, True, True, 10)
        self.main_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), True, True, 0)
        self.main_box.pack_start(self.loops_box, True, True, 10)

        # position = self.POSITIONS[self.settings['position']]
        self.shell.add_widget(self.main_box, self.gui_position, True, False)

        self.rbpitch.tempo.slider.set_value(self.rbpitch.tempo_val)
        self.rbpitch.pitch.slider.set_value(self.rbpitch.pitch_val)
        self.rbpitch.rate.slider.set_value(self.rbpitch.rate_val)

        self.save_crossfade_settings()

        self.settings_changed_sigid = self.settings.connect(
            'changed', self.on_settings_changed)

        self.song_changed_sigid = self.shell_player.connect(
            "playing-song-changed", self.on_playing_song_changed)

        # a song COULD be playing, so refresh sliders
        self.refresh_widgets()
        self.refresh_status_label()

        if self.settings['always-show']:
            self.refresh_rb_position_slider()
            self.main_box.show_all()

        self.loops = {}
        self.load_loops_file()
        self.loops_box.hide()

    def load_css(self):
        cssProvider = Gtk.CssProvider()
        css_path = rb.find_plugin_file(self, 'looper.css')
        cssProvider.load_from_path(css_path)
        screen = Gdk.Screen.get_default()
        styleContext = Gtk.StyleContext()
        styleContext.add_provider_for_screen(screen, cssProvider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def on_activation(self, *args):
        action = self.actions.get_action('ActivateLooper')
        if action.get_active():
            # connect elapsed handler/signal to handle the loop
            self.elapsed_changed_sigid = self.shell_player.connect(
                "elapsed-changed", self.loop)

            # Disable cross fade. It interferes at the edges of the song ..
            if (self.crossfade and self.crossfade.get_active()):
                    self.crossfade.set_active(False)
            self.refresh_rb_position_slider()
            self.controls_box.show_all()
            if self.shell_player.get_playing_song_duration() > -1:
                self.loops_box.show_all()
        else:
            # disconnect the elapsed handler from hes duty
            self.shell_player.disconnect(self.elapsed_changed_sigid)
            del self.elapsed_changed_sigid
            # Restore users crossfade if it was enabled
            if self.crossfade and self.was_crossfade_active:
                self.crossfade.set_active(True)
            if not self.settings['always-show']:
                self.main_box.hide()
                if hasattr(self, 'rb_slider'):
                    self.rb_slider.clear_marks()
            self.loops_box.hide()

        self.refresh_status_label()

    def _create_main_action(self):
        self.actions = ActionGroup(self.shell, 'LooperActionGroup')
        self.actions.add_action(func=self.on_activation,
                                action_name='ActivateLooper',
                                label=_("Looper"),
                                action_state=ActionGroup.TOGGLE,
                                action_type='app', accel="<Ctrl>e",
                                tooltip=_("Loop part of the song"))
        self.appshell.insert_action_group(self.actions)
        self.appshell.add_app_menuitems(self.UI, 'LooperActionGroup', 'view')
        self.action = self.appshell.lookup_action('LooperActionGroup',
                                                  'ActivateLooper', 'app')

    def find_rb_slider(self):
        rb_toolbar = self.find(self.shell.props.window, 'ToolBar', 'by_name')
        if not rb_toolbar:
            rb_toolbar = self.find(self.shell.props.window,
                                   'main-toolbar', 'by_id')
        return self.find(rb_toolbar, 'GtkScale', 'by_name')

    # Couldn't find better way to find widgets than loop through them
    def find(self, node, search_id, search_type):
        if isinstance(node, Gtk.Buildable):
            if search_type == 'by_id':
                if Gtk.Buildable.get_name(node) == search_id:
                    return node
            elif search_type == 'by_name':
                if node.get_name() == search_id:
                    return node

        if isinstance(node, Gtk.Container):
            for child in node.get_children():
                ret = self.find(child, search_id, search_type)
                if ret:
                    return ret
        return None

    def save_crossfade_settings(self):
        # We need to disable cross fade while Looper is active. So store
        # RB's xfade widget and user preference for later use.
        # Next line throws error in the Rhythmbox's console. Dont know why.
        prefs = self.shell.props.prefs  # <-- error. Unreleased refs maybe.
        self.crossfade = self.find(prefs, 'use_xfade_backend', 'by_id')
        self.was_crossfade_active = False
        if self.crossfade and self.crossfade.get_active():
            self.was_crossfade_active = True

    def on_settings_changed(self, settings, setting):
        """Handles changes to settings."""
        if setting == 'position':
            self.shell.remove_widget(self.main_box, self.gui_position)
            new_gui_position = self.POSITIONS[self.settings['position']]
            self.shell.add_widget(self.main_box, new_gui_position, True, False)
            self.gui_position = new_gui_position
        elif setting == 'always-show':
            action = self.actions.get_action('ActivateLooper')
            if settings['always-show']:
                self.main_box.show_all()
                if action.get_active() is not True:
                    self.loops_box.hide()
            else:
                if action.get_active() is not True:
                    self.main_box.hide()

    def on_playing_song_changed(self, source, user_data):
        """Refresh sliders and RB's position marks."""
        self.refresh_widgets()
        self.clear_loops()
        self.load_song_loops()
        action = self.actions.get_action('ActivateLooper')
        if action.get_active() is True:
            self.refresh_rb_position_slider()
            self.loops_box.show_all()
        else:
            self.loops_box.hide()

    def refresh_song_duration(self):
        duration = self.shell_player.get_playing_song_duration()
        if duration != -1 and duration >= (self.SEC_BEFORE_END + 2):
            self.duration = duration - self.SEC_BEFORE_END
        else:
            self.duration = None

    def refresh_rb_position_slider(self):
        """
        Add marks to RB's position slider with Looper's start/end time values.
        """
        # Add start and end marks to the position slider
        action = self.actions.get_action('ActivateLooper')
        if self.rb_slider and (action.get_active() or self.settings['always-show']):
            self.rb_slider.clear_marks()

            start_time = seconds_to_time(self.controls.start_slider.get_value())
            end_time = seconds_to_time(self.controls.end_slider.get_value())

            self.rb_slider.add_mark(self.controls.start_slider.get_value(),
                                             Gtk.PositionType.TOP, start_time)
            self.rb_slider.add_mark(self.controls.end_slider.get_value(),
                                             Gtk.PositionType.TOP, end_time)

    def clear_loops(self):
        for child in self.loops_box.get_children():
            child.deactivate()
            self.loops_box.remove(child)

    def load_song_loops(self):
        song_id = self.get_song_id()
        if song_id:
            if song_id and song_id in self.loops:
                self.load_loops(self.loops[song_id])

    def on_save_loop(self, button):
        song_id = self.get_song_id()
        if song_id:
            if song_id not in self.loops:
                self.loops[song_id] = []
            if len(self.loops[song_id]) >= self.MAX_LOOPS_NUM:
                return
            name = '{} - {}'.format(
                seconds_to_time(self.controls.start_slider.get_value()),
                seconds_to_time(self.controls.end_slider.get_value()),
            )
            loop = {
                'end': self.controls.end_slider.get_value(),
                'start': self.controls.start_slider.get_value(),
                'name': name
            }
            self.loops[song_id].append(loop)
            self.save_loops()
            self.clear_loops()
            self.load_loops(self.loops[song_id])

    def refresh_status_label(self):
        status_vars = {'duration': '00:00', 'time': '00:00'}
        status_text = self.STATUS_TPL.substitute(status_vars)
        self.controls.status_label.set_text(status_text)
        self.controls.status_label.set_fraction(0)

    def refresh_widgets(self):
        self.refresh_song_duration()
        self.controls.refresh_min_range_button()
        self.controls.refresh_sliders()

    def load_loops_file(self):
        loops_file = self.get_loops_file_path()
        if loops_file:
            with open(loops_file, 'r') as f:
                try:
                    self.loops = json.loads(f.read())
                except ValueError as e:
                    sys.stderr.write('Error on loading %s: %s\n' % (
                        loops_file, e))

    def get_loops_file_path(self):
        home = os.path.expanduser('~')
        loops_file = os.path.join(home, self.LOOPS_FILENAME)
        if not os.path.isfile(loops_file):
            with open(loops_file, 'w') as f:
                data = {}
                f.write(json.dumps(data))
        return loops_file

    def get_grid_column_and_row(self):
        number_of_children = len(self.loops_box.get_children())
        row, column  = divmod(number_of_children, self.LOOPS_PER_ROW)
        return column, row

    def get_song_id(self):
        if not self.entry:
            return None
        song_id = u'{0}-{1}'.format(self.song_artist, self.song_title)
        if not song_id:
            song_id =  self.entry.get_playback_uri()
        return hashlib.md5(song_id.encode('utf8')).hexdigest()

    @property
    def entry(self):
        return self.shell_player.get_playing_entry()

    @property
    def song_title(self):
        if self.entry:
            return self.entry.get_string(RB.RhythmDBPropType.TITLE)
        return ''

    @property
    def song_artist(self):
        if self.entry:
            return self.entry.get_string(RB.RhythmDBPropType.ARTIST)
        return ''

    @property
    def song_path(self):
        if self.entry:
            return self.entry.get_string(RB.RhythmDBPropType.LOCATION)
        return ''

    def load_loops(self, loops):
        for index, loop in enumerate(loops):
            loop = loops[index]
            loop_control = LoopControl(self, index, loop['name'], loop['start'], loop['end'])
            # TODO:
            # Use ScrolledWindow instead of limited numbers of loops per grid row.
            # For now we will use limited number of loops per row as the
            # Gtk.ScrolledWindow is not working for some reason.
            row, column = self.get_grid_column_and_row()
            self.loops_box.attach(loop_control, row, column, 1, 1)
        action = self.actions.get_action('ActivateLooper')
        if action.get_active():
            self.loops_box.show_all()

    def save_loops(self):
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self.save_loops_to_file)

    def save_loops_to_file(self):
        if self.loops:
            loops_file = self.get_loops_file_path()
            with open(loops_file, 'w') as f:
                f.write(json.dumps(self.loops))

    @property
    def start_slider_max(self):
        if self.duration:
            return self.duration - MIN_RANGE
        return 0

    @property
    def start_slider_min(self):
        return 0

    @property
    def end_slider_max(self):
        if self.duration:
            return self.duration
        return 0

    @property
    def end_slider_min(self):
        if self.duration:
            return MIN_RANGE
        return 0

    def loop(self, player, elapsed):
        """
        Signal handler called every second of the current playing song.
        Forces the song to stay inside Looper's slider limits.
        """
        # Start and End sliders values
        start = int(self.controls.start_slider.get_value())
        end = int(self.controls.end_slider.get_value())

        if self.rbpitch.gst_pitch and self.controls.rbpitch_btn.get_active() is True:
            tempo = self.rbpitch.tempo.slider.get_value()
            rate = self.rbpitch.rate.slider.get_value()
            start = math.floor(start / (tempo / 100) / (rate / 100))
            end = math.ceil(end / (tempo / 100) / (rate / 100))

        if elapsed < start:
            # current time is bellow Start slider so fast forward
            seek_time = start - elapsed
        elif elapsed >= end:
            # current time is above End slider so rewind
            seek_time = start - elapsed
        else:
            # current position is within sliders, so chill
            seek_time = False

        # Sometimes song change event interferes with seeking. Therefore
        # dont do anything if elapsed time is 0 (less than 1).
        if seek_time and elapsed > 0:
            try:
                self.shell_player.seek(seek_time)
            except GObject.GError:
                sys.stderr.write('Seek to ' + str(seek_time) + 's failed\n')
        self.update_label(elapsed, start, end)

    def update_label(self, elapsed, start, end):
        """Update label based on current song time and sliders positions."""
        current_loop_seconds = elapsed - start
        loop_duration_seconds = end - start
        if current_loop_seconds > 0 and (current_loop_seconds <=
                                         loop_duration_seconds):
            current_loop_time = seconds_to_time(current_loop_seconds)
            loop_duration = seconds_to_time(loop_duration_seconds)

            label = self.STATUS_TPL.substitute(duration=loop_duration,
                                               time=current_loop_time)
            self.controls.status_label.set_text(label)
            fraction = current_loop_seconds / loop_duration_seconds
            self.controls.status_label.set_fraction(fraction)

    def do_deactivate(self):
        self.save_loops_to_file()

        self.controls.destroy_widgets()
        self.rbpitch.destroy_widgets()

        # Restore users crossfade preference
        if self.crossfade and self.was_crossfade_active:
            self.crossfade.set_active(True)

        self.settings.disconnect(self.settings_changed_sigid)
        self.shell_player.disconnect(self.song_changed_sigid)
        if hasattr(self, 'elapsed_changed_sigid'):
            self.shell_player.disconnect(self.elapsed_changed_sigid)

        self.appshell.cleanup()

        self.main_box.set_visible(False)
        self.shell.remove_widget(self.main_box, RB.ShellUILocation.MAIN_TOP)

        if hasattr(self, 'rb_slider'):
            self.rb_slider.clear_marks()
            del self.rb_slider

        del self.controls
        del self.loops_box
        del self.crossfade
        del self.was_crossfade_active
        del self.shell_player
        del self.shell
        del self.player
        del self.db
        del self.appshell
        del self.main_box
        del self.controls_box
        del self.rbpitch
        del self.actions
        del self.action

    def log(self, *args):
        output = ', '.join([str(arg) for arg in args]) + '\n'
        sys.stdout.write(output)
