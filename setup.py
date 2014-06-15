#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

LOOPER_DIR_FROM = os.path.join(SCRIPT_DIR, 'looper')
USER_DIR = os.path.expanduser('~')
PLUGINS_DIR = os.path.join(USER_DIR, '.local', 'share', 'rhythmbox', 'plugins')
LOOPER_DIR_TO = os.path.join(PLUGINS_DIR, 'looper')
if os.path.lexists(LOOPER_DIR_TO):
    raise Exception('Directory "%s" already exists. Remove it and try again.'
                    % LOOPER_DIR_TO)
print('Copying Looper folder')
shutil.copytree(LOOPER_DIR_FROM, LOOPER_DIR_TO)
LOOPER_CONF_FROM = os.path.join(SCRIPT_DIR, 'conf', 'plugin2')
LOOPER_CONF_TO = os.path.join(LOOPER_DIR_TO, '.plugin')
print('Copying Looper .plugin config')
shutil.copy(LOOPER_CONF_FROM, LOOPER_CONF_TO)
print("Done. Make sure to copy and compile looper's gschema.xml")
