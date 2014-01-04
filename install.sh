#!/bin/bash

rb_version=""

read -r -d '' LOOPER_CONF <<'EOF'
[Plugin]
Loader=##LOADER##
Module=looper
IAge=2
Name=Looper
Description=Loop part of the song
Authors=Ivan Augustinović <augustinovic.ivan@gmail.com>
Copyright=Copyright © 2013 Ivan Augustinović
Website=https://github.com/kingd/looper
EOF

show_help()
{
    echo "Usage: bash install.sh -v [rb2|rb3]"
}

OPTIND=1 # Reset is necessary if getopts was used previously in the script.
while getopts "v:" opt; do
    case "$opt" in
        v)
            rb_version=$OPTARG
            ;;
        *)
            show_help >&2
            exit 1
            ;;
    esac
done
shift $((OPTIND-1)) # Shift off the options and optional --.

if [ "$rb_version" = "rb2" ]; then
    LOADER="python"
elif [ "$rb_version" = "rb3" ]; then
    LOADER="python3"
else
    show_help
    exit
fi

LOOPER_CONF=${LOOPER_CONF/"##LOADER##"/$LOADER}
SCRIPT_PATH=${0%`basename "$0"`}
PLUGINS_PATH="/home/${USER}/.local/share/rhythmbox/plugins/"
PLUGIN_PATH="${PLUGINS_PATH}looper"

rm -rf $PLUGIN_PATH
mkdir -p $PLUGINS_PATH
cp -r "${SCRIPT_PATH}looper" "$PLUGIN_PATH"
echo "$LOOPER_CONF" > "$PLUGIN_PATH/.plugin"
