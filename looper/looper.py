#!/usr/bin/env python
# encoding: utf-8

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

import sys
import os
from gi.repository import Gio, Gtk, GObject, RB, Peas
from string import Template
from LooperConfigureDialog import LooperConfigureDialog


class LooperPlugin(GObject.Object, Peas.Activatable):
    """
    Loops part of the song defined by Start and End Gtk sliders.
    """
    object = GObject.property(type=GObject.Object)

    status_tpl = Template('[Loop Duration: $duration] ' +
                          '[Current time: $time]')

    # Number of seconds that the End slider is less than a song
    # duration. Its needed because in that period Rhythmbox would
    # change to the next song. Thats why we dont go there.
    SEC_BEFORE_END = 3

    # Minimal allowed range in seconds.
    # (1 second is too small for meaningful sound)
    MIN_RANGE = 2

    # Available positions in the RB GUI.
    # They are chosen through user settings.
    POSITIONS = {
        'TOP': RB.ShellUILocation.MAIN_TOP,
        'BOTTOM': RB.ShellUILocation.MAIN_BOTTOM,
        'SIDEBAR': RB.ShellUILocation.SIDEBAR,
        'RIGHT SIDEBAR': RB.ShellUILocation.RIGHT_SIDEBAR,
    }

    UI = """
        <ui>
          <toolbar name="ToolBar">
            <toolitem name="LooperPlugin" action="ActivateLooper"/>
            <separator/>
          </toolbar>
        </ui>
    """
    LOOPER_DIR = os.path.dirname(os.path.abspath(__file__))

    def __init__(self):
        super(LooperPlugin, self).__init__()
        self.settings = Gio.Settings("org.gnome.rhythmbox.plugins.looper")

    def do_activate(self):
        self.shell = self.object
        self.player = self.shell.props.shell_player

        self.create_widgets()
        self.connect_signals()

        # a song COULD be playing, so refresh sliders
        self.refresh_song_duration()
        self.refresh_min_range_button()
        self.refresh_sliders()

        if self.settings['always-show']:
            self.refresh_rb_position_slider()
            self.hbox.show_all()

    def create_widgets(self):
        """Create, show and add looper's GTK widgets to RB's window."""
        # Activation button, part of the main RB toolbar
        self.action = Gtk.ToggleAction('ActivateLooper', 'Looper',
                                       'Loop part of the song', "")
        self.action_group = Gtk.ActionGroup('LooperActionGroup')
        self.action_group.add_action(self.action)
        ICON_PATH = os.path.join(self.LOOPER_DIR, 'looper.png')
        self.icon = Gio.FileIcon.new(Gio.File.new_for_path(ICON_PATH))
        self.action.set_gicon(self.icon)
        self.shell.props.ui_manager.insert_action_group(self.action_group)
        self.ui_id = self.shell.props.ui_manager.add_ui_from_string(self.UI)

        # Main horizontal box
        self.hbox = Gtk.HBox()

        self.min_range_label = Gtk.Label()
        self.min_range_label.set_text('Min range ')
        self.hbox.pack_start(self.min_range_label, False, False, 0)
        adj = Gtk.Adjustment(self.MIN_RANGE, self.MIN_RANGE,
                             self.MIN_RANGE, 1, 10, 0)
        self.min_range = Gtk.SpinButton(adjustment=adj)
        self.hbox.pack_start(self.min_range, False, False, 0)

        # status bar label
        self.label = Gtk.Label()
        self.refresh_status_label()
        self.hbox.pack_start(self.label, True, False, 0)

        # Start slider
        self.start_slider = self.create_slider()
        self.hbox.pack_start(self.start_slider, True, True, 0)

        # End slider
        self.end_slider = self.create_slider()
        self.hbox.pack_start(self.end_slider, True, True, 0)

        # show widget and add it to Rhythmbox
        position = self.POSITIONS[self.settings['position']]
        self.shell.add_widget(self.hbox, position, True, False)

        # Locate position slider in the RB's toolbar
        # rb_toolbar = self.shell.props.ui_manager.get_widget('/ToolBar/')
        rb_toolbar = self.find(self.shell.props.window, 'ToolBar', 'by_name')
        if not rb_toolbar:
            rb_toolbar = self.find(self.shell.props.window,
                                   'main-toolbar', 'by_id')
        self.rb_position_slider = self.find(rb_toolbar, 'GtkScale', 'by_name')

        # We need to disable cross fade while Looper is active. So store
        # RB's xfade widget and user preference for later use.
        # Next line throws error in the Rhythmbox's console. Dont know why.
        prefs = self.shell.props.prefs  # <-- error. Unreleased refs maybe.
        self.cross_fade = self.find(prefs, 'use_xfade_backend', 'by_id')
        self.cross_fade_active = False
        if self.cross_fade and self.cross_fade.get_active():
            self.cross_fade_active = True

    def refresh_status_label(self):
        status_vars = {'duration': '00:00', 'time': '00:00'}
        status_text = self.status_tpl.substitute(status_vars)
        self.label.set_text(status_text)

    def refresh_min_range_button(self):
        current_value = self.min_range.get_value_as_int()
        if self.duration == -1:
            lower_limit = self.MIN_RANGE
            upper_limit = self.MIN_RANGE
            current_value = self.MIN_RANGE
        else:
            lower_limit = self.MIN_RANGE
            upper_limit = self.duration

        if current_value > upper_limit:
            current_value = upper_limit

        adj = self.min_range.get_adjustment()
        adj.set_lower(lower_limit)
        adj.set_upper(upper_limit)
        adj.set_value(current_value)
        self.min_range.set_numeric(True)
        self.min_range.set_update_policy(1)

    def create_slider(self):
        adj = Gtk.Adjustment(0, 0, 0, 1, 1, 0)
        slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                           adjustment=adj)
        slider.set_digits(0)
        return slider

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

    def connect_signals(self):
        # Min range change
        self.min_range_cv = self.min_range.connect(
            'value-changed', self.min_range_changed)
        # Looper activation
        self.activate_sid = self.action.connect(
            'activate', self.looper_toggled, self.shell)
        # Song change
        self.player_psc_id = self.player.connect(
            "playing-song-changed", self.playing_song_changed)

        # start_slider and end_slider movement
        self.start_slider_vc_id = self.start_slider.connect(
            "value-changed", self.slider_moved, 'start')
        self.end_slider_vc_id = self.end_slider.connect(
            "value-changed", self.slider_moved, 'end')

        # Start and End slider values need to be formated from
        # seconds to (MM:SS)
        self.start_slider_fv_id = self.start_slider.connect(
            "format-value", self.format_slider_value)
        self.end_slider_fv_id = self.end_slider.connect(
            "format-value", self.format_slider_value)

    def min_range_changed(self, spinner):
        # simulate slider moved event so sliders obey new min_range value
        self.slider_moved(self.start_slider, 'start')

    def playing_song_changed(self, source, user_data):
        """Refresh sliders and RB's position marks."""
        self.refresh_song_duration()
        self.refresh_min_range_button()
        self.refresh_sliders()
        if self.action.get_active() is True:
            self.refresh_rb_position_slider()

    def refresh_sliders(self):
        """Set the Looper's slider boundries to the current song duration."""
        if self.duration != -1:
            end_slider_max = self.duration
            start_slider_max = end_slider_max - self.MIN_RANGE

            start_adj = self.start_slider.get_adjustment()
            start_adj.set_lower(0)
            start_adj.set_upper(start_slider_max)
            start_adj.set_value(0)

            end_adj = self.end_slider.get_adjustment()
            end_adj.set_lower(self.MIN_RANGE)
            end_adj.set_upper(end_slider_max)
            end_adj.set_value(self.duration)

    def refresh_rb_position_slider(self):
        """
        Add marks to RB's position slider with Looper's start/end time values.
        """
        # Add start and end marks to the position slider
        if self.rb_position_slider and (self.action.get_active() or
                                        self.settings['always-show']):
            self.rb_position_slider.clear_marks()

            start_time = self.seconds_to_time(self.start_slider.get_value())
            end_time = self.seconds_to_time(self.end_slider.get_value())

            self.rb_position_slider.add_mark(self.start_slider.get_value(),
                                             Gtk.PositionType.TOP, start_time)
            self.rb_position_slider.add_mark(self.end_slider.get_value(),
                                             Gtk.PositionType.TOP, end_time)

    def slider_moved(self, slider, moving_slider):
        """Dont let Start slider be greater than End or vice versa."""
        start_value = self.start_slider.get_value()
        end_value = self.end_slider.get_value()
        min_range = self.min_range.get_value_as_int()
        if moving_slider == 'start':
            slider_start_max = end_value - min_range
            if start_value > slider_start_max:
                if self.duration != -1 and end_value >= self.duration:
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

        self.refresh_rb_position_slider()

    def format_slider_value(self, scale, value):
        return self.seconds_to_time(value)

    def seconds_to_time(self, seconds):
        """Converts seconds to time format (MM:SS)."""
        m, s = divmod(int(seconds), 60)
        return "%02d:%02d" % (m, s)

    def looper_toggled(self, button, shell=None):

        if button.get_active():
            # connect elapsed handler/signal to handle the loop
            self.player_sid = self.player.connect("elapsed-changed", self.loop)

            # Disable cross fade. It interferes at the edges of the song ..
            if (self.cross_fade and self.cross_fade.get_active()):
                    self.cross_fade.set_active(False)
            self.refresh_rb_position_slider()
            self.hbox.show_all()
        else:
            # disconnect the elapsed handler from hes duty
            self.player.disconnect(self.player_sid)
            del self.player_sid
            # Restore users crossfade if it was enabled
            if self.cross_fade and self.cross_fade_active:
                self.cross_fade.set_active(True)
            if not self.settings['always-show']:
                self.hbox.hide()
                if hasattr(self, 'rb_position_slider'):
                    self.rb_position_slider.clear_marks()

        self.refresh_status_label()

    def loop(self, player, elapsed):
        """
        Signal handler called every second of the current playing song.
        Forces the song to stay inside Looper's slider limits.
        """
        # Start and End sliders values
        start = int(self.start_slider.get_value())
        end = int(self.end_slider.get_value())

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
                self.player.seek(seek_time)
            except GObject.GError:
                sys.stderr.write('Seek to ' + str(seek_time) + 's failed\n')
        self.update_label(elapsed, start, end)

    def update_label(self, elapsed, start, end):
        """Update label based on current song time and sliders positions."""
        current_loop_seconds = elapsed - start
        loop_duration_seconds = end - start
        if current_loop_seconds > 0 and (current_loop_seconds <=
                                         loop_duration_seconds):
            current_loop_time = self.seconds_to_time(current_loop_seconds)
            loop_duration = self.seconds_to_time(loop_duration_seconds)

            label = self.status_tpl.substitute(duration=loop_duration,
                                               time=current_loop_time)
            self.label.set_text(label)

    def refresh_song_duration(self):
        duration = self.shell.props.shell_player.get_playing_song_duration()
        if duration != -1 and duration >= (self.SEC_BEFORE_END + 2):
            self.duration = duration - self.SEC_BEFORE_END
        else:
            self.duration = -1

    def do_deactivate(self):
        # Restore users crossfade preference
        if self.cross_fade and self.cross_fade_active:
            self.cross_fade.set_active(True)

        self.discconect_signals()
        self.destroy_widgets()
        del self.shell
        del self.player

    def discconect_signals(self):
        self.action.disconnect(self.activate_sid)
        self.player.disconnect(self.player_psc_id)
        if hasattr(self, 'player_sid'):
            self.player.disconnect(self.player_sid)
        self.start_slider.disconnect(self.start_slider_fv_id)
        self.start_slider.disconnect(self.start_slider_vc_id)
        self.end_slider.disconnect(self.end_slider_fv_id)
        self.end_slider.disconnect(self.end_slider_vc_id)

    def destroy_widgets(self):
        self.shell.props.ui_manager.remove_action_group(self.action_group)
        self.shell.props.ui_manager.remove_ui(self.ui_id)
        self.hbox.set_visible(False)
        self.shell.remove_widget(self.hbox, RB.ShellUILocation.MAIN_TOP)
        if hasattr(self, 'rb_position_slider'):
            self.rb_position_slider.clear_marks()
            del self.rb_position_slider
        del self.action
        del self.action_group
        del self.icon
        del self.hbox
        del self.min_range_label
        del self.min_range
        del self.start_slider
        del self.end_slider
        del self.label
        del self.cross_fade
        del self.cross_fade_active
