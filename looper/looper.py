###############################################################################
# Copyright 2013 Ivan Augustinovic
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

from gi.repository import Gtk, GObject, RB, Peas
from string import Template
import sys

class LooperPlugin (GObject.Object, Peas.Activatable):
    """
    Loops part of the song defined by Start and End Gtk sliders
    """
    object = GObject.property(type=GObject.Object)

    status_tpl = Template('[Loop Duration: $duration] ' +
                              '[Current time: $time]')

    """
    Number of seconds that the End slider is less than a song
    duration. Its needed because in that period Rhythmbox would
    change to the next song. Thats why we dont go there.
    """
    SEC_BEFORE_END = 3

    """
    Minimal slider difference in seconds.
    0 seconds is too small for a meaningful sound, set to 2 seconds
    """
    MIN_RANGE = 2


    def __init__(self):
        super(LooperPlugin, self).__init__()

    def do_activate(self):
        self.shell  = self.object
        self.player = self.shell.props.shell_player
        self.create_widgets()
        self.connect_signals()
        # a song COULD be playing, so refresh sliders
        self.refresh_sliders()


    def do_deactivate(self):
        # Restore users crossfade preference
        if self.cross_fade_checkbox and self.cross_fade_active:
            self.cross_fade_checkbox.set_active(True)

        self.discconect_signals()
        if hasattr(self, 'rb_position_slider'):
            self.rb_position_slider.clear_marks()
            del self.rb_position_slider
        self.destroy_widgets()
        del self.shell
        del self.player

    def create_widgets(self):
        """ Create, show and add looper's GTK widgets to RB's window """
        # looper's main horizontal box
        self.hbox = Gtk.HBox()

        # activation button
        self.button = Gtk.CheckButton('Activate Looper')
        self.hbox.pack_start(self.button, True, False, 0)

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
        self.hbox.show_all()
        self.shell.add_widget(self.hbox, RB.ShellUILocation.MAIN_TOP, True, False)

        # Locate position slider in the RB's toolbar
        rb_toolbar = self.shell.props.ui_manager.get_widget('/ToolBar/')
        self.rb_position_slider = self.find(rb_toolbar, 'GtkScale', 'by_name')

        # We need to disable cross fade while Looper is active. So store
        # RB's xfade widget and user preference for later use.
        # Next line throws error in the Rhythmbox's console. Dont know why.
        prefs = self.shell.props.prefs # <-- error. Unreleased refs maybe.
        self.cross_fade_checkbox = self.find(prefs, 'use_xfade_backend', 'by_id')
        self.cross_fade_active = False
        if self.cross_fade_checkbox and self.cross_fade_checkbox.get_active():
            self.cross_fade_active = True

    def refresh_status_label(self):
        status_vars = {'duration': '00:00', 'time':'00:00'}
        status_text = LooperPlugin.status_tpl.substitute(status_vars)
        self.label.set_text(status_text)

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

    def destroy_widgets(self):
        self.hbox.set_visible(False)
        self.shell.remove_widget(self.hbox, RB.ShellUILocation.MAIN_TOP)
        del self.hbox
        del self.start_slider
        del self.end_slider
        del self.label
        del self.button
        del self.cross_fade_checkbox
        del self.cross_fade_active

    def connect_signals(self):
        self.player_psc_id = self.player.connect("playing-song-changed",
                                                 self.playing_song_changed)

        self.start_slider_vc_id = self.start_slider.connect("value-changed", self.slider_moved, 'start')
        self.end_slider_vc_id   = self.end_slider.connect("value-changed", self.slider_moved, 'end')

        # Start and End values need to be formated from seconds to (MM:SS)
        self.start_slider_fv_id = self.start_slider.connect("format-value", self.format_slider_value)
        self.end_slider_fv_id   = self.end_slider.connect("format-value", self.format_slider_value)

        self.button_t_id = self.button.connect('toggled', self.looper_toggled)

    def playing_song_changed(self, source, user_data):
        """ Refresh sliders and RB's position marks """
        self.refresh_sliders()
        self.refresh_rb_position_slider()

    def refresh_sliders(self):
        """ Set the Looper's slider boundries to the current song duration """
        # song duration in seconds
        duration = self.shell.props.shell_player.get_playing_song_duration()

        if duration != -1:
            # Set the MAX value of the End slider `SEC_BEFORE_END` seconds less
            # than song duration, so the rhythmbox doesn't go to the next song
            end_slider_max = duration - LooperPlugin.SEC_BEFORE_END

            # Start slider's MAX is less by MIN_RANGE from End_slider_max
            start_slider_max = end_slider_max - LooperPlugin.MIN_RANGE

            # set sliders adjustments
            start_adj = Gtk.Adjustment(0, 0, start_slider_max, 1, 1, 0)
            self.start_slider.set_adjustment(start_adj)

            end_adj = Gtk.Adjustment(duration, LooperPlugin.MIN_RANGE, end_slider_max, 1, 1, 0)
            self.end_slider.set_adjustment(end_adj)

    def refresh_rb_position_slider(self):
        """
        Add marks to RB's position slider with Looper's start/end time values
        """
        # Add start and end marks to the position slider
        if self.rb_position_slider:
            self.rb_position_slider.clear_marks()

            start_time   = self.seconds_to_time(self.start_slider.get_value())
            end_time     = self.seconds_to_time(self.end_slider.get_value())

            self.rb_position_slider.add_mark(self.start_slider.get_value(),
                                             Gtk.PositionType.TOP, start_time)
            self.rb_position_slider.add_mark(self.end_slider.get_value(),
                                             Gtk.PositionType.TOP, end_time)
    
    def slider_moved(self, slider, moving_slider):
        """ Dont let Start slider be greater than End or vice versa """
        if moving_slider == 'start':
            slider_start_max = self.end_slider.get_value() - self.MIN_RANGE
            if self.start_slider.get_value() > slider_start_max:
                new_value = self.start_slider.get_value() + self.MIN_RANGE
                self.end_slider.set_value(new_value)
        else:
            slider_end_min = self.start_slider.get_value() + self.MIN_RANGE
            if self.end_slider.get_value() < slider_end_min:
                new_value = self.end_slider.get_value() - self.MIN_RANGE
                self.start_slider.set_value(new_value)

        self.refresh_rb_position_slider()

    def format_slider_value(self, scale, value):
        return self.seconds_to_time(value)

    def seconds_to_time(self, seconds):
        """ Converts seconds to time format (MM:SS) """
        m, s = divmod(int(seconds), 60)
        return "%02d:%02d" % (m, s)

    def looper_toggled(self, button):

        if button.get_active():
            # connect elapsed handler/signal to handle the loop
            self.player_ec_id = self.player.connect("elapsed-changed", self.loop)

            # Disable cross fade. It interferes at the edges of the song ..
            if self.cross_fade_checkbox and self.cross_fade_checkbox.get_active():
                self.cross_fade_checkbox.set_active(False)
        else:
            # disconnect the elapsed handler from hes duty
            self.player.disconnect(self.player_ec_id)
            del self.player_ec_id
            # Restore users crossfade if it was enabled
            if self.cross_fade_checkbox and self.cross_fade_active:
                self.cross_fade_checkbox.set_active(True)

        self.refresh_status_label()

    def loop(self, player, elapsed):
        """
        Signal handler called every second of the current playing song.
        Forces the song to stay inside Looper's slider limits.
        """
        # Start and End sliders values
        start   = int(self.start_slider.get_value())
        end     = int(self.end_slider.get_value())

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
        """ Update label based on current song time and sliders positions """
        current_loop_time = self.seconds_to_time(elapsed - start)
        loop_duration     = self.seconds_to_time(end - start)

        label = self.status_tpl.substitute(duration=loop_duration,
                                               time=current_loop_time)
        self.label.set_text(label)

    def discconect_signals(self):
        self.player.disconnect(self.player_psc_id)
        if hasattr(self, 'player_ec_id'):
            self.player.disconnect(self.player_ec_id)
        self.start_slider.disconnect(self.start_slider_fv_id)
        self.start_slider.disconnect(self.start_slider_vc_id)
        self.end_slider.disconnect(self.end_slider_fv_id)
        self.end_slider.disconnect(self.end_slider_vc_id)
        self.button.disconnect(self.button_t_id)
