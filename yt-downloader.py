import youtube
from multiprocessing.pool import ThreadPool
from os import remove
import functools
import shutil
import os.path
from threading import Lock
import sys
import argparse

pool = ThreadPool()


def menu(prompt: str, options: "list of pairs(string, function); "
                               "string should contain exactly one '&' preceding the key letter"):
    switch = dict()
    if prompt:
        prompt += '\n'
    else:
        prompt = ''

    for (string, func) in options:
        amp = string.find('&')
        if amp < 0 or amp >= len(string) - 1:
            raise RuntimeError("option string must contain a '&' character denoting its key letter")

        if not callable(func):
            raise TypeError("option function must be callable")

        if string[amp + 1].lower() in switch:
            raise RuntimeError("key letter " + string[amp + 1] + " found in multiple options")

        switch[string[amp + 1].lower()] = func
        prompt += string[:amp] + '[' + string[amp + 1] + ']' + string[amp + 2:] + ' | '

    prompt += '[Enter] - Cancel : '
    choice = ''
    while choice not in switch:
        choice = input(prompt)
        choice = choice[0].lower() if choice else ''
        if not choice:
            return False

    # noinspection PyCallingNonCallable
    switch[choice]()
    return True


def work_on_song(videoId: str, filename: str, target_format):
    song = None
    try:
        song = youtube.download_audio(videoId)
        target_filename = filename.replace('*', youtube.make_filename(song[0]))
        if song[2] == target_format:
            shutil.move(song[1], target_filename)
        else:
            youtube.convert(song[1], target_filename)
        if not os.path.isfile(target_filename):
            raise IOError('failed to write target file')
        with work_on_song.lock:
            print(target_filename)
            work_on_song.success_count += 1
    except (IOError, RuntimeError, ValueError, OSError, shutil.Error) as e:
        print("WARNING: failed to download " + song[0] + ": " + str(e))
    finally:
        if song:
            try:
                remove(song[1])
            except (OSError, IOError):
                pass
    return


work_on_song.lock = Lock()
work_on_song.success_count = 0


def dl_video(videoId: str=None, filename: str=None):
    vidParam = not not videoId
    fnameParam = not not filename
    while True:
        if not videoId:
            videoId = input("Video URL | [Enter] - Cancel\n")
            if not videoId:
                return False

        song = None
        try:
            print("Downloading...")
            song = youtube.download_audio(videoId)
            print("Video title: " + song[0])

            if not filename:
                print("Supported formats: " + str(youtube.convert.supported))
                print("Target filename (must have extension matching a supported format)\n"
                      "Use * to expand to video title (e.g 'D:\\*.mp3') | Use [Enter] to cancel")
            while True:
                if not filename:
                    filename = input("Filename: ")
                    if not filename:
                        return False

                filename = filename.replace('*', youtube.make_filename(song[0]))
                try:
                    print("Converting...")
                    youtube.convert(song[1], filename)
                    print("Done")
                    return True
                except (IOError, RuntimeError) as e:
                    if str(e) == 'the file already exists' or str(e) == 'unsupported format':
                        print(e)
                        if fnameParam:
                            return False
                    else:
                        raise
        except ValueError:
            print("Invalid video ID or URL")
            if vidParam:
                return False
        except (IOError, RuntimeError) as e:
            print(e)
            return False
        finally:
            if song:
                remove(song[1])
    return False


def dl_playlist(playlistId: str='', filename: str=None):
    url = False
    fnameParam = not not filename
    while True:
        if not playlistId:
            while not url:
                playlistId = input("Playlist URL (must be logged in if playlist is private) | [Enter] - Cancel\n")
                if not playlistId:
                    return False

                try:
                    playlistId = youtube.parsePlaylistId(playlistId)
                    url = True
                except ValueError as e:
                    print(e)
                    continue

        print("Downloading playlist...")
        playlist = youtube.get_playlist(playlistId)
        playlistTitle = youtube.get_playlist_title(playlistId)
        if playlist is None or playlistTitle is None:
            if not url:
                return False
            else:
                print("Invalid playlist URL")
                playlistId = ''
                continue
        print("Playlist title: {0} ({1} songs)".format(playlistTitle, len(playlist)))
        playlistTitle = youtube.make_filename(playlistTitle)
        if not filename:
            print("Target filename (must have extension matching a supported format)\n"
                  "Use * to expand to video title (e.g 'D:\\*.mp3')\n"
                  "Use ? to expand to playlist title (e.g. 'D:\\?\\*.mp3 to save every song \n"
                  "with its video title in a new folder with the playlist's name) | [Enter] - Cancel")
        while True:
            if not filename:
                filename = input("Filename: ")
                if not filename:
                    break

            target_format = ''
            for fmt in youtube.convert.supported:
                if filename.endswith('.' + fmt):
                    target_format = fmt

            if not target_format:
                print("unsupported format")
                if not fnameParam:
                    continue
                else:
                    break

            filename = filename.replace('?', playlistTitle)
            print("Downloading songs...")
            pool.map(functools.partial(work_on_song, filename=filename, target_format=target_format), playlist)
            print("Done. {0}/{1} succeeded".format(work_on_song.success_count, len(playlist)))
            return True

    return False


def choose_from_my():
    if youtube.login.username:
        print("Choose a playlist from the list (by number):")
        playlists = youtube.get_my_playlists()
        if not playlists:
            print("Unknown error. Sorry :(")
            return False

        for (i, playlist) in enumerate(playlists):
            print(
                "{0}. : {1}({2} songs) - {3}".format(i + 1, playlist['title'], playlist['count'], playlist['privacy']))

        if len(playlists) > 0:
            while True:
                in_str = input("Playlist #[1-{0}] : ".format(len(playlists)))
                if not in_str:
                    return False

                try:
                    p = int(in_str)
                    if 0 < p <= len(playlists):
                        if not dl_playlist(playlists[p - 1]['id']):
                            print("Unknown error. Sorry :(")
                        return True
                except ValueError:
                    continue
        else:
            print("No playlists")
            return True

    return False


def download():
    menu("What do you want to download?", [("&Song", dl_video),
                                           ("&Playlist", functools.partial(menu, None, [
                                               ("Youtube &Playlist URL", dl_playlist),
                                               # ("M3&U Playlist",)
                                               ("&My youtube playlists [" + youtube.login.username + "]",
                                                choose_from_my) if youtube.login.username else
                                               ("&My youtube playlists [requires login]", prompt_login)]))])
    return


def convert():
    return


def login():
    if youtube.login():
        print("Successfully authenticated as " + youtube.login.username)
    else:
        print("Access was denied. Not logged in")
    return


def prompt_login():
    yn = input("Login is required. Do you want to log in? [Y/N]: ")[:1].lower()
    while yn != 'y' and yn != 'n':
        yn = input("Login is required. Do you want to log in? [Y/N]: ")[:1].lower()
    if yn == 'y':
        login()
    return


def main():
    try:
        if len(sys.argv) == 1:
            print("Youtube Downloader - v1.0.0 - Python 3")
            print("Not logged in" if not youtube.login.username else "Logged in as " + youtube.login.username)
            while menu("What do you want to do?", [("&Download", download),
                                                   # ("&Convert", convert),
                                                   ("&Logout [logged in as " + youtube.login.username + "]",
                                                    youtube.logout) if youtube.login.username else
                                                   ("&Login", login)]): pass
            return 0

        else:
            parser = argparse.ArgumentParser(description='Download a video')
            parser.add_argument(dest='url', type=str,
                                help='url of video to download')
            parser.add_argument(dest='path', type=str,
                                help="path to save the video into\n"
                                     "Target filename (must have extension matching a supported format)\n"
                                     "Use * to expand to video title (e.g 'D:\\*.mp3')\n"
                                     "Use ? to expand to playlist title (e.g. 'D:\\?\\*.mp3 to save every song \n"
                                     "with its video title in a new folder with the playlist's name) | [Enter] - Cancel"
                                )

            args = parser.parse_args()
            try:
                videoId = youtube.parseVideoId(args.url)
            except ValueError as e:
                print(e)
                return 1

            print(args)
            return 0 if dl_video(videoId, args.path) else 1
    finally:
        youtube.__end__()


if __name__ == "__main__":
    exit(main())
