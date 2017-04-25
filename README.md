# Looper - Rhythmbox plugin

Loop only part of the song in Rhythmbox and/or change tempo, pitch or speed of the track.

Requires soundtouch which is in the gstreamer-plugin-bad package.

## Screenshot

![Alt text](looper.png?raw=true "Loop part of the song and change tempo, pitch or speed.")


## Install

Copy looper folder into your local `rhythmbox/plugins` directory. On Debian/Ubuntu 
this is `~/.local/share/rhythmbox/plugins`. Following commands will install for those systems:

* For Rhythmbox 2.96 - 2.99

    ```
    sudo apt-get install git python python-gi gstreamer1.0-plugins-bad
    git clone https://github.com/kingd/looper
    cd looper
    ./install.sh
    ```

* For Rhythmbox 3.0+

    ```
    sudo apt-get install git python3 python3-gi
    git clone https://github.com/kingd/looper
    cd looper
    ./install.sh --rb3
    ```

### Updating from old version

    If you installing a version with soundtouch/tempo support and don't want to lose saved loops copy them to a
    new location in user home directory:

    ```
    cp ~/.local/share/rhythmbox/plugins/looper/loops.json ~/.loops.json
    ```

## Known Issues

`Crossfade between tracks` option changes to next or previous song while the
current time is near the edges of the song. Thats why it will be temporary
disabled when the Looper is in control of the playback. 

Rhythmbox changes to next song if the song is less than 3 seconds before the end.
Therefore those last 3 seconds wont be available for looping.

Tested on Rhythmbox 3.4.1

## TODO

- improve GUI usabillity
- test on older versions
- clean up code
- make a server to serve looper interface to browser
- add guitar tuner popup
- tabs

## Author

[kingd](https://github.com/kingd/)

## Contributors

[fossfreedom](https://github.com/fossfreedom/)
