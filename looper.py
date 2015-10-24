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
from string import Template
import shutil
import hashlib
from pprint import pprint as pp

from gi.repository import Gio, Gtk, GObject, RB, Peas, GLib, Gdk
from LooperConfigureDialog import LooperConfigureDialog
from looper_rb3compat import ActionGroup
from looper_rb3compat import ApplicationShell
from looper_rb3compat import is_rb3

import rb


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

    # Minimal allowed range in seconds.
    # (1 second is too small for meaningful sound)
    MIN_RANGE = 2

    LOOPS_FILENAME = 'loops.json'

    LOOPS_PER_ROW = 8

    MAX_LOOPS_NUM = 32

    ON_LABEL = 'Enabled'

    OFF_LABEL = 'Disabled'

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
        self.settings = Gio.Settings("org.gnome.rhythmbox.plugins.looper")
        # old value will be needed when removing/adding(moving) GUI
        self.gui_position = self.POSITIONS[self.settings['position']]
        self.shell = self.object
        self.player = self.shell.props.shell_player
        self.db = self.shell.props.db

        self.create_widgets()
        self.create_main_action()
        self.rb_slider = self.find_rb_slider()
        self.pack_widgets()
        self.save_crossfade_settings()
        self.connect_signals()

        # a song COULD be playing, so refresh sliders
        self.refresh_widgets()
        self.refresh_status_label()

        if self.settings['always-show']:
            self.refresh_rb_position_slider()
            self.main_box.show_all()

        self.load_loops_conf()
        self.loops_box.hide()
        # srv = LooperServer(self)
        # srv.daemon = True
        # srv.start()
        # GObject.threads_init()

    def create_widgets(self):
        """Create Looper's GTK widgets."""
        self.appshell = ApplicationShell(self.shell)
        self.main_box = Gtk.VBox()
        self.controls_box = Gtk.HBox()

        self.loops_box = Gtk.Grid()
        self.loops_box.set_row_spacing(2)
        self.loops_box.set_column_spacing(2)
        self.loops_box.set_column_homogeneous(True)
        self.loops_box.set_row_homogeneous(True)
        self.loops_box.set_border_width(0)

        self.save_loop_btn = Gtk.Button(label='Save loop')

        self.min_range_label = Gtk.Label()
        self.min_range_label.set_text('Min range ')
        adj = Gtk.Adjustment(self.MIN_RANGE, self.MIN_RANGE,
                             self.MIN_RANGE, 1, 10, 0)
        self.min_range = Gtk.SpinButton(adjustment=adj)

        if is_rb3(self.shell):
            self.activation_btn = Gtk.Button(self.OFF_LABEL)
        else:
            self.activation_btn = Gtk.CheckButton()
            self.activation_btn.set_related_action(self.action.action)

        self.status_label = Gtk.Label()

        self.start_slider = self.create_slider()
        self.end_slider = self.create_slider()

    def on_activation(self, *args):
        action = self.actions.get_action('ActivateLooper')
        if action.get_active():
            # connect elapsed handler/signal to handle the loop
            self.elapsed_changed_sigid = self.player.connect(
                "elapsed-changed", self.loop)

            # Disable cross fade. It interferes at the edges of the song ..
            if (self.crossfade and self.crossfade.get_active()):
                    self.crossfade.set_active(False)
            self.refresh_rb_position_slider()
            self.main_box.show_all()
            self.loops_box.show_all()
        else:
            # disconnect the elapsed handler from hes duty
            self.player.disconnect(self.elapsed_changed_sigid)
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

    def create_slider(self):
        adj = Gtk.Adjustment(0, 0, 0, 1, 1, 0)
        slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                           adjustment=adj)
        slider.set_digits(0)
        return slider

    def create_main_action(self):
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

    def pack_widgets(self):
        """Pack Looper's widgets and add Looper to Rhythmbox."""
        self.controls_box.pack_start(self.min_range_label, False, False, 5)
        self.controls_box.pack_start(self.min_range, False, False, 0)
        self.controls_box.pack_start(self.status_label, True, False, 0)
        self.controls_box.pack_start(self.start_slider, True, True, 0)
        self.controls_box.pack_start(self.end_slider, True, True, 0)
        self.controls_box.pack_start(self.save_loop_btn, True, True, 5)
        self.controls_box.pack_start(self.activation_btn, True, True, 0)
        self.main_box.pack_start(self.controls_box, True, True, 0)
        self.main_box.pack_start(self.loops_box, True, True, 0)
        position = self.POSITIONS[self.settings['position']]
        self.shell.add_widget(self.main_box, position, True, False)

    def save_crossfade_settings(self):
        # We need to disable cross fade while Looper is active. So store
        # RB's xfade widget and user preference for later use.
        # Next line throws error in the Rhythmbox's console. Dont know why.
        prefs = self.shell.props.prefs  # <-- error. Unreleased refs maybe.
        self.crossfade = self.find(prefs, 'use_xfade_backend', 'by_id')
        self.was_crossfade_active = False
        if self.crossfade and self.crossfade.get_active():
            self.was_crossfade_active = True

    def connect_signals(self):
        """Connects all needed GTK signals."""
        self.settings_changed_sigid = self.settings.connect(
            'changed', self.on_settings_changed)

        if is_rb3(self.shell):
            # In RB3 plugins cannot be activated from custom buttons so
            # we need to hack it with dummy button that will emit activation
            # on click. If Looper is activated through Rhythmbox just change
            # activation_btn label else if Looper is activated through
            # our button, change the button label and emit a signal for
            # Rhythmbox.
            self.action_sigid = self.action.connect(
                'change-state', self.on_rb_activation, '')
            self.activation_btn_sigid = self.activation_btn.connect(
                'clicked', self.on_btn_activation)

        self.min_range_sigid = self.min_range.connect(
            'value-changed', self.on_min_range_changed)

        self.song_changed_sigid = self.player.connect(
            "playing-song-changed", self.on_playing_song_changed)

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
            'clicked', self.on_save_loop)

    def on_settings_changed(self, settings, setting):
        """Handles changes to settings."""
        if setting == 'position':
            self.shell.remove_widget(self.main_box, self.gui_position)
            position = self.POSITIONS[self.settings['position']]
            self.shell.add_widget(self.main_box, position, True, False)
            self.gui_position = self.POSITIONS[self.settings['position']]
        elif setting == 'always-show':
            if settings['always-show']:
                self.main_box.show_all()
            else:
                action = self.actions.get_action('ActivateLooper')
                if action.get_active() is not True:
                    self.main_box.hide()

    def on_rb_activation(self, action, state, data):
        """
        Change our custom activation button label as appropriate for the
        current activation state.
        """
        if state:
            self.activation_btn.set_label(self.ON_LABEL)
        else:
            self.activation_btn.set_label(self.OFF_LABEL)

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
        if label == self.ON_LABEL:
            state = GLib.Variant('b', False)
            label = self.OFF_LABEL
        else:
            state = GLib.Variant('b', True)
            label = self.ON_LABEL
        self.action.action.emit('activate', state)

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
                if self.duration and end_value >= self.duration:
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
        duration = self.player.get_playing_song_duration()
        if duration != -1 and duration >= (self.SEC_BEFORE_END + 2):
            self.duration = duration - self.SEC_BEFORE_END
        else:
            self.duration = None

    def refresh_min_range_button(self):
        current_value = self.min_range.get_value_as_int()
        if self.duration is None:
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

    def refresh_sliders(self):
        """Set the Looper's slider boundries to the current song duration."""
        if self.duration:
            start_adj = self.start_slider.get_adjustment()
            start_adj.set_lower(self.start_slider_min)
            start_adj.set_upper(self.start_slider_max)
            start_adj.set_value(0)

            end_adj = self.end_slider.get_adjustment()
            end_adj.set_lower(self.end_slider_min)
            end_adj.set_upper(self.end_slider_max)
            end_adj.set_value(self.duration)

    def refresh_rb_position_slider(self):
        """
        Add marks to RB's position slider with Looper's start/end time values.
        """
        # Add start and end marks to the position slider
        action = self.actions.get_action('ActivateLooper')
        if self.rb_slider and (action.get_active() or self.settings['always-show']):
            self.rb_slider.clear_marks()

            start_time = self.seconds_to_time(self.start_slider.get_value())
            end_time = self.seconds_to_time(self.end_slider.get_value())

            self.rb_slider.add_mark(self.start_slider.get_value(),
                                             Gtk.PositionType.TOP, start_time)
            self.rb_slider.add_mark(self.end_slider.get_value(),
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

    def on_format_slider_value(self, scale, value):
        return self.seconds_to_time(value)

    def seconds_to_time(self, seconds):
        """Converts seconds to time format (MM:SS)."""
        m, s = divmod(int(seconds), 60)
        return "%02d:%02d" % (m, s)

    def on_save_loop(self, button):
        song_id = self.get_song_id()
        if song_id:
            if song_id not in self.loops:
                self.loops[song_id] = []
            if len(self.loops[song_id]) >= self.MAX_LOOPS_NUM:
                return
            name = '{} - {}'.format(
                self.seconds_to_time(self.start_slider.get_value()),
                self.seconds_to_time(self.end_slider.get_value()),
            )
            loop = {
                'end': self.end_slider.get_value(),
                'start': self.start_slider.get_value(),
                'name': name
            }
            self.loops[song_id].append(loop)
            self.save_loops()
            self.clear_loops()
            self.load_loops(self.loops[song_id])

    def refresh_status_label(self):
        status_vars = {'duration': '00:00', 'time': '00:00'}
        status_text = self.STATUS_TPL.substitute(status_vars)
        self.status_label.set_text(status_text)

    def refresh_widgets(self):
        self.refresh_song_duration()
        self.refresh_min_range_button()
        self.refresh_sliders()

    def load_loops_conf(self):
        self.loops = {}
        loops_file = self.get_loops_file()
        if loops_file:
            with open(loops_file, 'r') as f:
                try:
                    self.loops = json.loads(f.read())
                except ValueError as e:
                    sys.stderr.write('Error on loading %s: %s\n' % (
                        loops_file, e))

    def get_loops_file(self):
        loops_file = rb.find_plugin_file(self, self.LOOPS_FILENAME)
        if loops_file is None:
            loops_file = os.path.join(rb.find_plugin_file(self, ''), self.LOOPS_FILENAME)
            with open(loops_file, 'w') as f:
                data = {}
                f.write(json.dumps(data))
        return rb.find_plugin_file(self, self.LOOPS_FILENAME)

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
        return self.player.get_playing_entry()

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
        loops_file = rb.find_plugin_file(self, self.LOOPS_FILENAME)
        with open(loops_file, 'w') as f:
            f.write(json.dumps(self.loops))

    @property
    def start_slider_max(self):
        if self.duration:
            return self.duration - self.MIN_RANGE
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
            return self.MIN_RANGE
        return 0

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

            label = self.STATUS_TPL.substitute(duration=loop_duration,
                                               time=current_loop_time)
            self.status_label.set_text(label)

    def do_deactivate(self):
        self.save_loops_to_file()
        # Restore users crossfade preference
        if self.crossfade and self.was_crossfade_active:
            self.crossfade.set_active(True)

        self.disconnect_signals()
        self.destroy_widgets()
        del self.shell
        del self.player

    def disconnect_signals(self):
        self.settings.disconnect(self.settings_changed_sigid)
        self.activation_btn.disconnect(self.activation_btn_sigid)
        self.min_range.disconnect(self.min_range_sigid)
        self.player.disconnect(self.song_changed_sigid)
        if hasattr(self, 'elapsed_changed_sigid'):
            self.player.disconnect(self.elapsed_changed_sigid)
        self.start_slider.disconnect(self.start_slider_changed_sigid)
        self.start_slider.disconnect(self.start_slider_value_sigid)
        self.end_slider.disconnect(self.end_slider_changed_sigid)
        self.end_slider.disconnect(self.end_slider_value_sigid)

    def destroy_widgets(self):
        self.appshell.cleanup()
        self.main_box.set_visible(False)
        self.shell.remove_widget(self.main_box, RB.ShellUILocation.MAIN_TOP)
        if hasattr(self, 'rb_slider'):
            self.rb_slider.clear_marks()
            del self.rb_slider
        del self.main_box
        del self.controls_box
        del self.loops_box
        del self.save_loop_btn
        del self.min_range_label
        del self.min_range
        del self.start_slider
        del self.end_slider
        del self.status_label
        del self.activation_btn
        del self.crossfade
        del self.was_crossfade_active

    def log(self, *args):
        output = ', '.join([str(arg) for arg in args]) + '\n'
        sys.stdout.write(output)


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
        label = self.looper.seconds_to_time(value)
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
        min_range = self.looper.min_range.get_value_as_int()
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
        start_slider_label = self.looper.seconds_to_time(self.start_slider.get_value())
        self.start_slider.set_label(start_slider_label)

        end_slider_label = self.looper.seconds_to_time(self.end_slider.get_value())
        self.end_slider.set_label(end_slider_label)

    def set_loop(self):
        self.looper.start_slider.set_value(self.start_slider.get_value())
        self.looper.end_slider.set_value(self.end_slider.get_value())

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
