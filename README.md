# Looper - Rhythmbox plugin

Loop only part of the song in Rhythmbox.

## Screenshots

![](http://image.bayimg.com/e30f16f05611d85b2b160d4b91e7c9ff0304b59c.jpg)


## Install

Copy looper folder into your local `rhythmbox/plugins` directory. On Debian/Ubuntu 
this is `~/.local/share/rhythmbox/plugins`. Following commands will install for those systems:

* For Rhythmbox 2.96 - 2.99

    ```
    sudo apt-get install git python python-gi
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

## Known Issues

`Crossfade between tracks` option changes to next or previous song while the
current time is near the edges of the song. Thats why it will be temporary
disabled when the Looper is in control of the playback. 

Rhythmbox changes to next song if the song is less than 3 seconds before the end.
Therefore those last 3 seconds wont be available for looping.

Tested on Rhythmbox 2.97

## TODO

- test on 2.99.1, 3.0 versions

## Author

[kingd](https://github.com/kingd/)

## Contributors

[fossfreedom](https://github.com/fossfreedom/)
