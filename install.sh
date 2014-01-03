#!/bin/bash
# Initialize our own variables:
rb_version=""

show_help()
{
    echo "Usage: bash install.sh -v [rb2|rb3]"
}

OPTIND=1 # Reset is necessary if getopts was used previously in the script.  It is a good idea to make this local in a function.
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

SCRIPT_PATH=${0%`basename "$0"`}

if [ "$rb_version" = "rb2" ]; then
    CONF_PATH="${SCRIPT_PATH}conf/plugin2"
elif [ "$rb_version" = "rb3" ]; then
    CONF_PATH="${SCRIPT_PATH}conf/plugin3"
else
    show_help
    exit
fi

PLUGINS_PATH="/home/${USER}/.local/share/rhythmbox/plugins/"
PLUGIN_PATH="${PLUGINS_PATH}looper"

rm -rf $PLUGIN_PATH
mkdir -p $PLUGINS_PATH
cp -r "${SCRIPT_PATH}looper" "$PLUGIN_PATH"
cp "${CONF_PATH}" "$PLUGIN_PATH/.plugin"
