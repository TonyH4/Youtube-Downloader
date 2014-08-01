import pafy
import keyring
from nap.url import Url
from requests.exceptions import HTTPError
import os
from subprocess import Popen as popen
from tempfile import mkstemp
import socket
import string
import random
from urllib.parse import parse_qs, urlparse
import threading
from collections import defaultdict
import webbrowser
import atexit
from googleapicfg import _key, _client_id, _client_secret

__all__ = [ "download_audio", "search", "convert", "login", "make_filename", "get_playlist", "get_my_playlists", "get_playlist_title", "logout", "HTTPError" ]

class YoutubeDataApi(Url):
    def after_request(self, response):
        if response.status_code == 401:
            #Lost authorization, log out
            logout()
        if response.status_code != 200:
            response.raise_for_status()

        return response.json()
    
_api = YoutubeDataApi('https://www.googleapis.com/youtube/v3/')
_oauth_api = Url('https://accounts.google.com/o/oauth2/')
_appname = "yt-downloader-py"

def make_filename(filename: str):
    """Remove any invalid filename characters from `filename`,
    and replace them with `_` (underscore)
    WARNING: DO NOT USE ON FULL PATHS"""
    return ''.join([c if make_filename.invalid_chars.find(c) < 0 else '_' for c in filename])

make_filename.invalid_chars = '/\\:*"?|<>'

def download_audio(videoId: str, filename: str = ""):
    #Throws IOError, ValueError, RuntimeError
    """Download the audio from the youtube video identified by `videoId`
    and save it in the file `filename`.
    If `filename` already exists, the function fails
    If `filename` is not specified, a tmp file is created.
    Returns pair(video title, name of the file written)."""

    if filename == "":
        tmp = mkstemp('.' + download_audio.output_format)
        os.close(tmp[0]); os.remove(tmp[1])
        filename = tmp[1]
    elif os.path.exists(filename):
        raise IOError("the file already exists")

    video = pafy.new(videoId)
    for stream in video.audiostreams:
        if str(stream).find(download_audio.output_format) > 0:
            stream.download(filename, quiet=True)
            return video.title, filename

    raise RuntimeError("No " + download_audio.output_format + " audio found for video " + video.videoid)

download_audio.output_format = 'ogg'

def get_playlist(playlistId: str):
    """Return a list of videoIds containted in the youtube playlist
    identified by `playlistId`.
    Throws HTTPError in case of failure."""

    get_params = {
        'part':'contentDetails',
        'playlistId':playlistId,
        'fields':'items/contentDetails,nextPageToken,pageInfo',
        'maxResults':50,
        'key':_key
    }

    if login.username:
        get_params['access_token'] = login._access_token

    response = _api.get("playlistItems", params=get_params)

    totalResults = response['pageInfo']['totalResults']
    playlist = []
    while 'nextPageToken' in response:
        for item in response['items']:
            playlist.append(item['contentDetails']['videoId'])
        get_params['pageToken'] = response['nextPageToken']
        response = _api.get("playlistItems", params=get_params)
    
    for item in response['items']:
        playlist.append(item['contentDetails']['videoId'])

    assert totalResults == len(playlist)
    return playlist

def get_my_playlists():
    """Return all playlists on the channel of the currently logged in user
    as a list of dictionaries with keys id, title, count, privacy.
    Throws HTTPError in case of failure."""
    if not login.username:
        raise AssertionError('requires authorization')

    get_params = {
        'part':'snippet,contentDetails,status',
        'mine':'true',
        'fields':'pageInfo,nextPageToken,items/id,items/snippet/title,items/contentDetails/itemCount,items/status/privacyStatus',
        'maxResults':50,
        'key':_key,
        'access_token':login._access_token
    }
    
    response = _api.get("playlists", params=get_params)

    totalResults = response['pageInfo']['totalResults']
    playlists = []
    while 'nextPageToken' in response:
        for item in response['items']:
            playlist = dict()
            playlist['id'] = item['id']
            playlist['title'] = item['snippet']['title']
            playlist['privacy'] = item['status']['privacyStatus']
            playlist['count'] = item['contentDetails']['itemCount']
            playlists.append(playlist)
        get_params['pageToken'] = response['nextPageToken']
        response = _api.get("playlists", params=get_params)

    for item in response['items']:
        playlist = dict()
        playlist['id'] = item['id']
        playlist['title'] = item['snippet']['title']
        playlist['privacy'] = item['status']['privacyStatus']
        playlist['count'] = item['contentDetails']['itemCount']
        playlists.append(playlist)

    assert totalResults == len(playlists)
    return playlists

def get_playlist_title(playlistId: str):
    """Return the title of the playlist identified by playlistId.
    Return None in case of failure."""

    get_params = {
        'part':'snippet',
        'id':playlistId,
        'fields':'items/snippet/title',
        'maxResults':1,
        'key':_key
    }

    if login.username:
        get_params['access_token'] = login._access_token

    response = _api.get("playlists", params=get_params)
    if not response:
        return None

    if len(response['items']) > 0:
        return response['items'][0]['snippet']['title']
    else: return ''
    

def convert(filename: str, output: str, start_time: "seconds" = 0, duration: "seconds" = -1):
    #Throws IOError, RuntimeError
    """Transcode the audio from file `filename` into the file `output`,
    whose extension must specify a valid audio format.
    The format to use for decoding `filename` is deduced from its headers
    See convert.supported"""

    CREATE_NO_WINDOW = 0x08000000

    path = max(output.rfind('\\'), output.rfind('/'))
    if path >= 0:
        try:
            os.makedirs(output[:path])
        except OSError as e:
            if e.errno != os.errno.EEXIST:
                raise
        
    if os.path.exists(output):
        raise IOError("the file already exists")
    
    for fmt in convert.supported:
        if output.endswith('.' + fmt):
            p = popen(convert._command.format(filename, fmt, output, start_time, ('-t ' + str(duration) if duration >= 0 else '')),
                      creationflags=CREATE_NO_WINDOW);
            p.wait()
            if p.returncode != 0:
                raise RuntimeError("ffmpeg failed with code " + str(p.returncode))
            else: return

    raise RuntimeError("unsupported format")
    
convert.supported = '3gp aiff amr au flac mmf mp3 opus wav wv rm oga ogg'.split(' ')
convert._command = 'ffmpeg -loglevel quiet -n -i "{0}" -ss {3} {4} -f {1} "{2}"'

def parseVideoId(url: str):
    parse = urlparse(url)
    if not parse.netloc.endswith('youtube.com') or parse.path != '/watch':
        raise ValueError('invalid video URL')

    params = parse_qs(parse.query)
    if 'v' not in params:
        raise ValueError('invalid video URL')

    return params['v'][0]

def parsePlaylistId(url: str):
    parse = urlparse(url)
    if not parse.netloc.endswith('youtube.com') or (parse.path != '/watch' and parse.path != '/playlist'):
        raise ValueError('invalid playlist URL')

    params = parse_qs(parse.query)
    if 'list' not in params:
        raise ValueError('invalid playlist URL')

    return params['list'][0]


def __gen_request_id(size):
    return ''.join(random.choice(string.ascii_lowercase + string.ascii_uppercase + string.digits) for _ in range(size))

def _refresh_token():
    if not login.username:
        return False

    login.access_token = ""
    refresh_token = keyring.get_password(_appname, login.username)
    if not refresh_token:
        logout()
        return False
    
    response = _oauth_api.post("token", data={
        'refresh_token':refresh_token,
        'client_id':_client_id,
        'client_secret':_client_secret,
        'grant_type':'refresh_token'})

    if response.status_code != 200:
        try:
            keyring.delete_password(_appname, login.username)
        except keyring.errors.PasswordDeleteError:
            pass
        logout()
        return False

    token = response.json()
    with login._lock:
        login._access_token = token['access_token']
        login._access_token_refresh_timer = threading.Timer(token['expires_in'] * 0.95, _refresh_token)
        login._access_token_refresh_timer.start()
    return True

def login(privileges: "space delimited string of privileges" = 'youtube.readonly'):
    #Send an OAuth2 request to google's servers
    #The result is returned to the local webserver on the specified port
    #See __runserver and __serveclient

    #Uniquely identify this request in order to process it in __serveclient
    auth_request_id = __gen_request_id(12)
    while auth_request_id in login._token_code:
        auth_request_id = __gen_request_id(12)

    
    redirect_uri = 'http://localhost:' + str(login.server.getsockname()[1])
    response = _oauth_api.get("auth", params={
	'client_id':_client_id,
	'redirect_uri':redirect_uri,
        'access_type':'offline',
	'response_type':'code',
	'scope':' '.join(['https://www.googleapis.com/auth/' + privilege for privilege in privileges.split(' ')]),
        'state':auth_request_id})

    if response.status_code != 200:
        return False
    
    if webbrowser.open(response.url, new=1, autoraise=True):
        print("Switch to your browser in order to authenticate")
    else:
        print("Failed to open browser window. Go to " + response.url + " to authenticate")

    #After sending the request, the user must grant the requested privileges
    #__serveclient will handle the response, and will notify us when it's ready
    with login._token_code_condvar[auth_request_id]:
        login._token_code_condvar[auth_request_id].wait()
        code = login._token_code[auth_request_id]
        login._token_code[auth_request_id] = None
        
    if not code or code == 'access_denied':
        return False

    #Exchange the token code for an access token and a refresh token
    response = _oauth_api.post("token", data={
        'code':code,
        'client_id':_client_id,
        'client_secret':_client_secret,
        'redirect_uri':redirect_uri,
        'grant_type':'authorization_code'})
    
    if response.status_code != 200:
        return False
    
    token = response.json()
    try:
        response = _api.get("channels", params={
            'part':'snippet',
            'mine':'true',
            'key':_key,
            'access_token':token['access_token']})
        if not response:
            return False
        
        with login._lock:
            logout()
            #The access token is used to authorize requests
            #The refresh token is used to get new access tokens as they expire
            login.username = response['items'][0]['snippet']['title']
            keyring.set_password(_appname, login.username, token['refresh_token'])
            keyring.set_password(_appname, "", login.username)
            login._access_token = token['access_token']
            login._access_token_refresh_timer = threading.Timer(token['expires_in'] * 0.95, _refresh_token)
            login._access_token_refresh_timer.start()
    except HTTPError:
        return False
    
    return True

def logout():
    with login._lock:
        try:
            if login.username:
                keyring.delete_password(_appname, login.username)
        except keyring.errors.PasswordDeleteError:
            pass
        try:
            keyring.delete_password(_appname, "")
        except keyring.errors.PasswordDeleteError:
            pass
        login.username = None
        if login._access_token_refresh_timer:
            login._access_token_refresh_timer.cancel()
            login._access_token_refresh_timer = None

    return

def __serveclient(sock):
    #Serve GET requests to extract ouath2 request results
    #The first line of a request must be the resource line
    #Read at most 1024 bytes, until a CRLF is found

    try:
        left = 1024
        buffer = bytearray(1024)
        view = memoryview(buffer)
        while left > 0 and buffer.find(b'\r\n') < 0:
            read = sock.recv_into(view, left)
            if read <= 0:
                return

            view = view[read:]
            left -= read
            
        end = buffer.find(b'\r\n')
        if end < 0:
            return

        resource_line = buffer[0:end].decode().split()
        #We are only serving GET requests
        #A get request must be of the form 'GET resource-uri HTTP/version'
        if len(resource_line) != 3 or resource_line[0] != "GET":
            return

        resource = urlparse(resource_line[1])
        #Expecting a request of the form 'GET /?state=asd48thdfbF&code=uebehbes-st4yhZT-Dbfberh'
        #OR 'GET /' as a result of being redirected by a request of the previous type
        #OR 'GET /denied' as a result of being redirected after the user refused to give access

        if resource.path == '/' and len(resource.query) > 0:
            #Assume request is of the first form
            try:
                params = parse_qs(resource.query)
                if 'state' in params and params['state'][0] not in login._token_code:
                    req_id = params['state'][0]
                    with login._token_code_condvar[req_id]:
                        if 'code' in params and 'error' not in params:
                            login._token_code[req_id] = params['code'][0]
                            
                            #The request was good. Redirect the browser to /
                            sock.send(b'HTTP/1.0 302 Found\r\n'
                                      b'Location: /\r\n\r\n')
                            
                        elif 'error' in params and 'code' not in params:
                            login._token_code[req_id] = params['error'][0]
                            
                            #The user rejected the auth request. Redirect the browser to /denied
                            sock.send(b'HTTP/1.0 302 Found\r\n'
                                      b'Location: /denied\r\n\r\n')
                            
                        else: raise RuntimeException('bad get request')

                        login._token_code_condvar[req_id].notifyAll()
                        return
                    
            except RuntimeError as e:
                if str(e) == 'bad get request':
                    return
                else: raise
            except (KeyError, IndexError):
                return

        elif resource.path == '/':
            #Assume request is a result of redirection from previous step. Display success message.
            sock.send(b'HTTP/1.0 200 OK\r\n\r\n'
                      b'<html><head><title>Success</title></head><body><h1>Succesfully authenticated.</h1><br/><p>You may now close this page.</p></body></html>\r\n')
            return
        elif resource.path == '/denied':
            #Assume request is a result of redirection from previous step. Display error message.
            sock.send(b'HTTP/1.0 200 OK\r\n\r\n'
                      b'<html><head><title>Aww :(</title></head><body><h1>You denied the access request.</h1>'
                      b'<br/><p>The related functionality will not be enabled.</p></body></html>\r\n')
            return
        
    finally:
        sock.close()

#Run a local webserver to handle oauth responses
def __runserver():
    login.server = socket.socket()
    login.server.bind(('0.0.0.0', 0))
    login.server.listen(5)
    try:
        client = login.server.accept()
        while client:
            threading.Thread(target=__serveclient, args=(client[0],)).start()
            client = login.server.accept()
    except OSError:
        pass

threading.Thread(target=__runserver).start()

#A dictionary of access token codes received as responses from oauth requests
#keys are random strings used to identify access token requests
login._token_code = dict()
login._token_code_condvar = defaultdict(threading.Condition)

#Access token used to authenticate some requests
#Obtained from login method
login._access_token = ""

#Timer used to refresh access token
login._access_token_refresh_timer = None
login._lock = threading.RLock()
login.username = keyring.get_password(_appname, "")

#If we have a refresh token stored, refresh the access token now
if login.username:
    _refresh_token()

def __end__():
    try:
        if login._access_token_refresh_timer:
            login._access_token_refresh_timer.cancel()
            login._access_token_refresh_timer = None
    except:
        pass
    try: login.server.close()
    except: pass
    return

atexit.register(__end__)






    
    


       
