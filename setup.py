#!/usr/bin/env python
# encoding: utf-8
import os
import shutil

LOOPER_CONF = """[Plugin]
Loader=python
Module=looper
Depends=rb
IAge=2
Name=Looper
Description=Loop part of the song
Authors=Ivan Augustinović <augustinovic.ivan@gmail.com>
Copyright=Copyright © 2013 Ivan Augustinović
Website=https://github.com/kingd/looper
"""

print('Copying Looper folder')
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOOPER_DIR_FROM = os.path.join(SCRIPT_DIR, 'looper')
USER_DIR = os.path.expanduser('~')
PLUGINS_DIR = os.path.join(USER_DIR, '.local', 'share', 'rhythmbox', 'plugins')
LOOPER_DIR_TO = os.path.join(PLUGINS_DIR, 'looper')
if os.path.lexists(LOOPER_DIR_TO):
    raise Exception('Directory "%s" already exists. Remove it and try again.'
                    % LOOPER_DIR_TO)
shutil.copytree(LOOPER_DIR_FROM, LOOPER_DIR_TO)

print('Generating Looper .plugin config')
LOOPER_CONF_PATH = os.path.join(LOOPER_DIR_TO, '.plugin')
with open(LOOPER_CONF_PATH, 'w') as conf:
    conf.write(LOOPER_CONF)

print("Done. Make sure to copy and compile looper's gschema.xml")
