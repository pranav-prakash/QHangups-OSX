QHangups-OSX
========

Client for Google Hangouts written in PyQt. Now optimized for OSX!

Changes from QHangups
----------------------

- Updated UI to match browser hangouts client
- Notification support
- Fix menubar icon (option-click to show items, click to hide/show)
- Always on top window to match old panels hangouts chrome extension

Installation
------------

``brew install qt5 --with-qtwebkit``
``brew install PyQt5``
``brew install python3``

``cd [downloaded directory]``
``python3 setup.py build``
``python3 setup.py install``
``easy_install ./dist/QHangups-1.8.1-py3.5.egg`

BONUS:

The ./Application/dist` folder holds a app built with py2applet that launches qhangups after it's been installed through easy_install.


Requirements
------------

- Python >= 3.3
- PyQt >= 5
- Quamash (https://github.com/harvimt/quamash)
- hangups (https://github.com/tdryer/hangups)
- appdirs (https://github.com/ActiveState/appdirs)
- asyncio (https://pypi.python.org/pypi/asyncio) for Python < 3.4

Usage
-----

Run ``qhangups --help`` to see all available options.
Start QHangups by running ``qhangups``.

The first time you start QHangups, you will be prompted to log into your
Google account. Your credentials will only be sent to Google, and only
OAuth 2 refresh token will be stored locally.

Help
----
::

    usage: qhangups [-h] [-d] [--log LOG] [--token TOKEN]
    
    optional arguments:
      -h, --help     show this help message and exit
      -d, --debug    log detailed debugging messages (default: False)
      --log LOG      log file path (default:
                     ~/.local/share/QHangups/hangups.log)
      --token TOKEN  OAuth refresh token storage path (default:
                     ~/.local/share/QHangups/refresh_token.txt)
