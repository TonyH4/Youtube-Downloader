Youtube-Downloader
==================

Command line interface for downloading audio from youtube videos.


Dependencies
============

https://pypi.python.org/pypi/Pafy
https://github.com/kennethreitz/requests
https://pypi.python.org/pypi/nap
https://pypi.python.org/pypi/keyring

Configuration
=============

You need to create a file named googleapicfg.py, containing 3 variables:

_key = 'GOOGLE_API_KEY'
_client_id = 'GOOGLE_API_CLIENT_ID'
_client_secret = 'GOOGLE_API_CLIENT_SECRET'


You can get these values by registering an application for the youtube data api on https://console.developers.google.com/
