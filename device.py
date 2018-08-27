from configparser import ConfigParser
from multiprocessing import Queue
import os
import pygame
import queue
import requests
from threading import Thread
import time

DEBUG = False

STATE_END = 1
STATE_SONG = 2
STATE_SONG_LOOP = 3
STATE_SONG_THEN_WHITENOISE = 4
STATE_WHITENOISE = 5
STATE_WHITENOISE_LVL2 = 6

SONG_END = max(pygame.USEREVENT + 1, STATE_WHITENOISE_LVL2 + 1)
LVL2_END = SONG_END + 1

STRING_TO_EVENT_MAP = {
    'END': STATE_END,
    'SONG': STATE_SONG,
    'SONG_LOOP': STATE_SONG_LOOP,
    'SONG_THEN_WHITENOISE': STATE_SONG_THEN_WHITENOISE,
    'WHITENOISE': STATE_WHITENOISE,
    'WHITENOISE_LVL2': STATE_WHITENOISE_LVL2,
    'SONG_END': SONG_END,
    'LVL2_END': LVL2_END
}

EVENT_TO_STRING_MAP = { STRING_TO_EVENT_MAP[key]: key for key in STRING_TO_EVENT_MAP }


def log_debug(msg):
    if DEBUG:
        print(msg)


class ChangeWorker(Thread):

    ONE_MINUTE = 60

    end_processing = False

    def __init__(self, url, username, password, change_queue):
        log_debug("Init ChangeWorker")
        Thread.__init__(self)
        self.username = username
        self.password = password
        self.url = url
        self.change_queue = change_queue

    def get_msg(self):
        response = requests.get(self.url, auth=(self.username, self.password))
        if response.status_code == 200:
            return response.json()
        else:
            return None

    def run(self):
        log_debug("Starting ChangeWorker")
        while not self.end_processing:
            event = self.get_msg()

            if event:
                if event['create_date'] > time.time() - self.ONE_MINUTE:
                    if STRING_TO_EVENT_MAP[event['mode']] == STATE_WHITENOISE and event['level'] == 2:
                        mode = STATE_WHITENOISE_LVL2
                    else:
                        mode = STRING_TO_EVENT_MAP[event['mode']]

                    log_debug("Queueing command: %s" % EVENT_TO_STRING_MAP[mode])

                    self.change_queue.put(mode)
                else:
                    log_debug("Skipping old event")

            time.sleep(1)

    def stop(self):
        self.end_processing = True


class NurseryClient(object):

    CONFIG_FILENAME = 'nursery.ini'

    WHITENOISE_LVL1_FILE = 'Rain.ogg'
    WHITENOISE_LVL2_FILE = 'Strong_Hair_Dryer.ogg'

    CROSSFADE_MSECS = 10000

    state = STATE_END

    song_end_cb = None

    def __init__(self):
        log_debug("Init NurseryClient")

        parser = ConfigParser()
        found = parser.read(self.CONFIG_FILENAME)

        if not found:
            raise IOError('Config file "%s" not found.' % self.CONFIG_FILENAME)

        try:
            self.song_file = parser.get('device', 'song_file')
            self.server_user = parser.get('device', 'server_user')
            self.server_pass = parser.get('device', 'server_pass')
            self.server_url = parser.get('device', 'server_url')
            lvl2_play_secs = parser.getint('device', 'level_two_play_seconds')

            if lvl2_play_secs <= 0:
                raise ValueError('level_two_play_seconds must be an integer larger than 0')
            else:
                self.lvl2_play_msecs = lvl2_play_secs * 1000
        except Exception as e:
            raise ValueError('Definitions missing from config file: %s' % e)

        pygame.init()
        os.putenv('SDL_VIDEODRIVER', 'fbcon')
        pygame.display.init()
        pygame.mixer.init()

        self.lvl1_channel = pygame.mixer.Channel(0)
        self.lvl2_channel = pygame.mixer.Channel(1)

        pygame.mixer.music.set_endevent(SONG_END)

        self.change_queue = Queue()

        self.lvl1_sound = pygame.mixer.Sound(file=self.WHITENOISE_LVL1_FILE)
        self.lvl2_sound = pygame.mixer.Sound(file=self.WHITENOISE_LVL2_FILE)

        log_debug("System Ready")

    def is_state_change(self, event):
        return event in (
            STATE_END, STATE_WHITENOISE, STATE_SONG_THEN_WHITENOISE, STATE_SONG,
            STATE_SONG_LOOP
        )

    def play_song(self):
        log_debug("Playing song")
        pygame.mixer.music.load(self.song_file)
        pygame.mixer.music.play(loops=0)

    def play_whitenoise(self, level_two=False):
        log_debug("Playing whitenoise. Level 2? %s" % level_two)
        if level_two:
            self.lvl2_channel.stop()
            self.lvl2_channel.set_volume(1)
            self.lvl2_channel.play(self.lvl2_sound, loops=-1, fade_ms=self.CROSSFADE_MSECS)
        else:
            self.lvl1_channel.stop()
            self.lvl1_channel.set_volume(1)
            self.lvl1_channel.play(self.lvl1_sound, loops=-1, fade_ms=self.CROSSFADE_MSECS)

    def go_whitenoise(self):
        log_debug("Go Whitenoise")
        self.song_end_cb = None
        self.state = STATE_WHITENOISE
        self.play_whitenoise()

    def go_whitenoise_lvl2(self):
        log_debug("Go Whitenoise lvl2")
        self.song_end_cb = None
        pygame.time.set_timer(LVL2_END, self.lvl2_play_msecs)
        self.state = STATE_WHITENOISE_LVL2
        self.play_whitenoise(level_two=True)

    def go_song_loop(self, start_song=False):
        log_debug("Go Song Loop. Start? %s" % start_song)
        self.song_end_cb = self.play_song
        self.state = STATE_SONG_LOOP
        if start_song:
            self.play_song()

    def go_song(self, start_song=False):
        log_debug("Go Song. Start? %s" % start_song)
        self.song_end_cb = self.go_end
        self.state = STATE_SONG
        if start_song:
            self.play_song()

    def go_song_then_whitenoise(self, start_song=False):
        log_debug("Go Song Then Whitenoise. Start? %s" % start_song)
        self.song_end_cb = self.go_whitenoise
        self.state = STATE_SONG_THEN_WHITENOISE
        if start_song:
            self.play_song()

    def go_end(self):
        log_debug("Go End")
        self.song_end_cb = None
        self.state = STATE_END

    def get_event(self):
        try:
            event = self.change_queue.get_nowait()
            return event
        except queue.Empty:
            events = pygame.event.get()
            if any([event.type == SONG_END for event in events]):
                return SONG_END
            if any([event.type == LVL2_END for event in events]):
                return LVL2_END

            return None

    def handle_event(self, event):
        log_debug("Handling event: %s -> %s" % (EVENT_TO_STRING_MAP[self.state], EVENT_TO_STRING_MAP[event]))

        if event == SONG_END and self.song_end_cb:
            self.song_end_cb()
            return

        if event == LVL2_END:
            event = STATE_WHITENOISE

        if self.state == STATE_END:
            if event == STATE_SONG:
                self.go_song(start_song=True)
            elif event == STATE_SONG_LOOP:
                self.go_song_loop(start_song=True)
            elif event == STATE_SONG_THEN_WHITENOISE:
                self.go_song_then_whitenoise(start_song=True)
            elif event == STATE_WHITENOISE:
                self.go_whitenoise()

        elif self.state in (STATE_SONG, STATE_SONG_LOOP, STATE_SONG_THEN_WHITENOISE):
            if event == STATE_SONG:
                self.go_song(start_song=False)
            elif event == STATE_SONG_LOOP:
                self.go_song_loop(start_song=False)
            elif event == STATE_SONG_THEN_WHITENOISE:
                self.go_song_then_whitenoise(start_song=False)
            elif event == STATE_WHITENOISE:
                self.go_whitenoise()
                pygame.mixer.music.fadeout(self.CROSSFADE_MSECS)
            elif event == STATE_END:
                self.go_end()
                pygame.mixer.music.fadeout(self.CROSSFADE_MSECS)

        elif self.state in (STATE_WHITENOISE, STATE_WHITENOISE_LVL2):
            if (self.is_state_change(event) and
                    self.state == STATE_WHITENOISE_LVL2 and
                    self.state != event):
                log_debug("Reset Level 2 Timer")
                pygame.time.set_timer(LVL2_END, 0)

            if event in (STATE_SONG, STATE_SONG_LOOP, STATE_SONG_THEN_WHITENOISE, STATE_END):
                if self.state == STATE_WHITENOISE:
                    self.lvl1_channel.fadeout(self.CROSSFADE_MSECS)
                else:
                    self.lvl2_channel.fadeout(self.CROSSFADE_MSECS)

                if event == STATE_SONG:
                    self.go_song(True)
                elif event == STATE_SONG_LOOP:
                    self.go_song_loop(True)
                elif event == STATE_SONG_THEN_WHITENOISE:
                    self.go_song_then_whitenoise(True)
                elif event == STATE_END:
                    self.go_end()

            elif event == STATE_WHITENOISE and self.state != event:
                self.lvl2_channel.fadeout(self.CROSSFADE_MSECS)
                self.go_whitenoise()

            elif event == STATE_WHITENOISE_LVL2 and self.state != event:
                self.lvl1_channel.fadeout(self.CROSSFADE_MSECS)
                self.go_whitenoise_lvl2()

    def start_worker(self):
        self.change_worker = ChangeWorker(self.server_url, self.server_user, self.server_pass, self.change_queue)
        self.change_worker.start()

    def run(self):
        self.start_worker()

        log_debug("Starting event loop")

        while True:
            print('.', end='', flush=True)
            event = self.get_event()

            if event:
                self.handle_event(event)
            else:
                time.sleep(0.05)

    @staticmethod
    def startup():
        try:
            log_debug("Client startup")
            client = NurseryClient()
            client.run()
        except Exception as e:
            print("Unable to start client: %s" % e)

NurseryClient.startup()
