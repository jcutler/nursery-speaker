from configparser import ConfigParser
from multiprocessing import SimpleQueue
import pygame
import queue
import requests
from threading import Thread
import time

DEBUG = True

STATE_END = 0
STATE_SONG = 1
STATE_SONG_LOOP = 2
STATE_SONG_THEN_WHITENOISE = 3
STATE_WHITENOISE = 4
STATE_WHITENOISE_LVL2 = 5

SONG_END = pygame.USEREVENT + 1


def log_debug(msg):
    if DEBUG:
        print(msg)


class ChangeWorker(Thread):

    FIVE_MINUTES = 60 * 60 * 24 * 5

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
        while not self.end_processing:
            event = self.get_msg()

            if event and event['create_date'] < time.time() - self.FIVE_MINUTES:
                if event['mode'] == STATE_WHITENOISE and event['level'] == 2:
                    mode = STATE_WHITENOISE_LVL2
                else:
                    mode = event['mode']

                log_debug("Queueing command: %s" % mode)

                self.change_queue.put()

            time.sleep(1)

    def stop(self):
        self.end_processing = True


class NurseryClient(object):

    CONFIG_FILENAME = 'nursery.ini'

    WHITENOISE_LVL1_FILE = 'Rain.mp3'
    WHITENOISE_LVL2_FILE = 'Strong_Hair_Dryer.mp3'

    FADEOUT_MSECS = 5000
    LEVEL2_PLAY_SECS = 7 * 60
    LEVEL2_FULL_SECS = 8 * 60

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
        except Exception as e:
            raise ValueError('Definitions missing from config file: %s' % e)

        pygame.mixer.init()
        pygame.mixer.music.set_endevent(SONG_END)
        self.change_queue = SimpleQueue()

    def play_song(self):
        log_debug("Playing song")
        pygame.mixer.music.load(self.song_file)
        pygame.mixer.music.play(loops=0, start=378) # remove this start change

    def play_whitenoise(self, level_two=False):
        log_debug("Playing whitenoise. Level 2? %s" % level_two)
        if level_two:
            pygame.mixer.music.load(self.WHITENOISE_LVL2_FILE)
            pygame.mixer.music.play(loops=0, start=self.LEVEL2_FULL_SECS-self.LEVEL2_PLAY_SECS)
        else:
            pygame.mixer.music.load(self.WHITENOISE_LVL1_FILE)
            pygame.mixer.music.play(loops=-1)

    def go_whitenoise(self):
        log_debug("Go Whitenoise")
        self.song_end_cb = None
        self.state = STATE_WHITENOISE
        self.play_whitenoise()

    def go_whitenoise_lvl2(self):
        log_debug("Go Whitenoise Lvl2")
        self.song_end_cb = self.go_whitenoise
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
        self.song_end_cb = None
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
        self.state = SONG_END

    def fadeout_then_do(self, func, arg):
        log_debug("Fadeout, then... %s(%s)" % (func, arg))
        pygame.mixer.music.fadeout(self.FADEOUT_MSECS)
        while not any([event.type == SONG_END for event in pygame.event.get()]):
            pass
        func(self, arg)

    def get_event(self):
        try:
            event = self.change_queue.get()
            return event
        except queue.Empty:
            if any([event.type == SONG_END for event in pygame.event.get()]):
                return SONG_END
            return None

    def handle_event(self, event):
        log_debug("Handling event: %s -> %s" % (self.state, event))

        if event == SONG_END and self.song_end_cb:
            self.song_end_cb(self)

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
                self.go_song_then_whitenoise(start_song=False)
                pygame.mixer.music.fadeout(self.FADEOUT_MSECS)
            elif event == STATE_END:
                self.go_end()
                pygame.mixer.music.fadeout(self.FADEOUT_MSECS)

        elif self.state in (STATE_WHITENOISE, STATE_WHITENOISE_LVL2):
            if event == STATE_SONG:
                self.fadeout_then_do(self.go_song, True)
            elif event == STATE_SONG_LOOP:
                self.fadeout_then_do(self.go_song_loop, True)
            elif event == STATE_SONG_THEN_WHITENOISE:
                self.fadeout_then_do(self.go_song_then_whitenoise, True)
            elif event == STATE_WHITENOISE and self.state != event:
                self.go_whitenoise()
            elif event == STATE_WHITENOISE_LVL2 and self.state != event:
                self.go_whitenoise_lvl2()

    def start_worker(self):
        self.change_worker = ChangeWorker(self.server_url, self.server_user, self.server_pass, self.change_queue)
        self.change_worker.start()

    def run(self):
        self.start_worker()
        while True:
            print('.', end='')
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
