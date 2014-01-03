Looper - Rhythmbox plugin
=========================

Loop part of the song in Rhythmbox.

Screenshots
-----------

![](http://image.bayimg.com/c8a2d58cae0089822ea946967a820ebe2a4b4824.jpg)


Install
-------

Copy looper folder into your local `rhythmbox/plugins` directory. On Debian/Ubuntu 
this is `~/.local/share/rhythmbox/plugins`. Following commands will install for those systems:

For RB2
+++++++

    git clone https://github.com/kingd/looper
    cd looper
    bash install.sh -v rb2

For RB3
+++++++

    git clone https://github.com/kingd/looper
    cd looper
    bash install.sh -v rb3

Known Issues
------------

`Crossfade between tracks` option changes to next or previous song while the
current time is near the edges of the song. Thats why it will be temporary
disabled when the Looper is in control of the playback. 

Rhythmbox also changes to next song if the song is less than 3 seconds before the end.
Therefore those last 3 seconds wont be available for looping.

Tested on Rhythmbox 2.97, 2.99.1, 3.0

TODO
----

- add preferences for the position of the Looper in the RB UI
- when the start slider moves, song should follow and when the end slider moves
song should follow minus 2 seconds (so a user can hear where he is in the song)

Author
------

Ivan Augustinović https://github.com/kingd
