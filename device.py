from configparser import ConfigParser
from multiprocessing import Queue
import os
from pathlib import Path
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
SONG_FADE_START = SONG_END + 1
LVL2_END = SONG_FADE_START + 1

COMMANDS = [STATE_END, STATE_SONG, STATE_SONG_LOOP, STATE_SONG_THEN_WHITENOISE,
            STATE_WHITENOISE, STATE_WHITENOISE_LVL2]

TRIGGERS = [SONG_END, SONG_FADE_START, LVL2_END]

STR_TO_EVENT_MAP = {
    'END': STATE_END,
    'SONG': STATE_SONG,
    'SONG_LOOP': STATE_SONG_LOOP,
    'SONG_THEN_WHITENOISE': STATE_SONG_THEN_WHITENOISE,
    'WHITENOISE': STATE_WHITENOISE,
    'WHITENOISE_LVL2': STATE_WHITENOISE_LVL2,
    'SONG_END': SONG_END,
    'SONG_FADE_START': SONG_FADE_START,
    'LVL2_END': LVL2_END
}

EVENT_TO_STR_MAP = {STR_TO_EVENT_MAP[key]: key
                    for key
                    in STR_TO_EVENT_MAP}

STOP_FILE='/tmp/nursery_speaker_stop_file'
RESTART_FILE='/tmp/nursery_speaker_restart_file'

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
                    if (STR_TO_EVENT_MAP[event['mode']] == STATE_WHITENOISE and
                            event['level'] == 2):
                        mode = STATE_WHITENOISE_LVL2
                    else:
                        mode = STR_TO_EVENT_MAP[event['mode']]

                    log_debug("Queueing command: %s" % EVENT_TO_STR_MAP[mode])

                    self.change_queue.put(mode)
                else:
                    log_debug("Skipping old event")

            time.sleep(2)

    def stop(self):
        self.end_processing = True


class NurseryClient(object):

    SCRIPT_HOME = os.path.dirname(os.path.realpath(__file__))

    CONFIG_FILENAME = SCRIPT_HOME + '/nursery.ini'

    WHITENOISE_LVL1_FILE = SCRIPT_HOME + '/Rain.ogg'
    WHITENOISE_LVL2_FILE = SCRIPT_HOME + '/Strong_Hair_Dryer.ogg'
    TONE_FILE = SCRIPT_HOME + '/Tone.ogg'

    CROSSFADE_MSECS = 10000

    state = STATE_END

    song_end_cb = None
    song_fade_start_cb = None

    fade_start_timer_running = False
    lvl2_timer_running = False

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
            self.song_length = parser.getint('device', 'song_length_seconds')

            self.song_file = self.SCRIPT_HOME + '/' + self.song_file

            if self.song_length <= 0:
                raise ValueError('Song length must be longer than 0 seconds')

            self.song_fade_start_msecs = (self.song_length * 1000 -
                                          self.CROSSFADE_MSECS)

            lvl2_play_secs = parser.getint('device', 'level_two_play_seconds')

            if lvl2_play_secs <= 0:
                raise ValueError('level_two_play_seconds must be an integer larger than 0')
            else:
                self.lvl2_play_msecs = lvl2_play_secs * 1000

        except Exception as e:
            raise ValueError(
                'Definitions missing/incorrect in config file: %s' % e
            )

        pygame.init()
        pygame.mixer.init()

        self.whitenoises = {
            1: {
                'channel': pygame.mixer.Channel(0),
                'sound': pygame.mixer.Sound(file=self.WHITENOISE_LVL1_FILE),
                'volume': 1.0
            },
            2: {
                'channel': pygame.mixer.Channel(1),
                'sound': pygame.mixer.Sound(file=self.WHITENOISE_LVL2_FILE),
                'volume': 0.3
            }
        }

        for level in self.whitenoises:
            self.whitenoises[level]['sound'].set_volume(self.whitenoises[level]['volume'])

        pygame.mixer.music.set_endevent(SONG_END)

        self.change_queue = Queue()

        tone = pygame.mixer.Sound(file=self.TONE_FILE)
        tone.set_volume(0.2)
        tone.play()

        log_debug("System Ready")

    def whitenoise_level_from_state(self, state):
        if state == STATE_WHITENOISE:
            return 1
        elif state == STATE_WHITENOISE_LVL2:
            return 2
        else:
            raise ValueError("Non-whitenoise state given: %s" % state)

    def is_event_state_change(self, event):
        return event in COMMANDS

    def is_event_trigger(self, event):
        return event in TRIGGERS

    # Start the song fade timer
    def start_fade_start_timer(self):
        log_debug("Start song fade timer")
        self.fade_start_timer_running = True
        pygame.time.set_timer(SONG_FADE_START, self.song_fade_start_msecs)

    # Stop the song fade timer if it is running
    def stop_fade_start_timer(self):
        if self.fade_start_timer_running == True:
            log_debug("Clear song fade timer")
            self.fade_start_timer_running = False
            pygame.time.set_timer(SONG_FADE_START, 0)
        else:
            log_debug("Skip clearing song fade timer because it isn't running")

    def handle_song_fade_start(self):
        self.stop_fade_start_timer()
        if self.song_fade_start_cb:
            self.song_fade_start_cb()

    def handle_song_end(self):
        if self.song_end_cb:
            if not pygame.mixer.music.get_busy():
                self.song_end_cb()
            else:
                log_debug("Skip handling song end because it is playing again")

    def start_lvl2_timer(self):
        if self.lvl2_timer_running:
            log_debug("Reset lvl2 timer")
        else:
            log_debug("Start lvl2 timer")
        self.lvl2_timer_running = True
        pygame.time.set_timer(LVL2_END, self.lvl2_play_msecs)

    def stop_lvl2_timer(self):
        if self.lvl2_timer_running == True:
            log_debug("Clear lvl2 timer")
            self.lvl2_timer_running = False
            pygame.time.set_timer(LVL2_END, 0)

    def play_song(self):
        log_debug("Playing song")
        pygame.mixer.music.set_volume(0.7)
        pygame.mixer.music.load(self.song_file)
        pygame.mixer.music.play(loops=0)
        self.start_fade_start_timer()

    def fadeout_song(self):
        log_debug("Fadeout song")
        self.stop_fade_start_timer()
        pygame.mixer.music.fadeout(self.CROSSFADE_MSECS)

    def play_whitenoise(self, level=1):
        log_debug("Playing whitenoise. Level? %s" % level)

        if level not in self.whitenoises:
            log_debug('Invalid whitenoise given: %s' % level)
            return

        self.whitenoises[level]['channel'].stop()
        self.whitenoises[level]['channel'].set_volume(1)
        self.whitenoises[level]['channel'].play(self.whitenoises[level]['sound'],
                                                loops=-1,
                                                fade_ms=self.CROSSFADE_MSECS)

    def fadeout_channel(self, level):
        if level not in self.whitenoises:
            log_debug("Invalid channel to fadeout: %d" % level)
            return

        if self.whitenoises[level]['channel'].get_busy():
            self.whitenoises[level]['channel'].fadeout(self.CROSSFADE_MSECS)
        else:
            log_debug("Attempting to fadeout non-active channel: %s" % level)

    def go_whitenoise(self, level=1, start_sound=True):
        log_debug("Go Whitenoise. Level? %d" % level)

        if level not in self.whitenoises:
            log_debug("Invalid whitenoise level")
            return

        self.song_end_cb = None
        self.song_fade_start_cb = None

        if level == 1:
            self.state = STATE_WHITENOISE
        elif level == 2:
            self.state = STATE_WHITENOISE_LVL2
            self.start_lvl2_timer()

        if start_sound:
            self.play_whitenoise(level=level)

    def go_song_loop(self, start_song=False):
        log_debug("Go Song Loop. Start? %s" % start_song)
        self.song_end_cb = self.play_song
        self.song_fade_start_cb = None
        self.state = STATE_SONG_LOOP
        if start_song:
            self.play_song()

    def go_song(self, start_song=False):
        log_debug("Go Song. Start? %s" % start_song)
        self.song_end_cb = self.go_end
        self.song_fade_start_cb = None
        self.state = STATE_SONG
        if start_song:
            self.play_song()

    def go_song_then_whitenoise(self, start_song=False):
        log_debug("Go Song Then Whitenoise. Start? %s" % start_song)
        self.song_end_cb = None
        self.song_fade_start_cb = self.go_whitenoise
        self.state = STATE_SONG_THEN_WHITENOISE
        if start_song:
            self.play_song()

    def go_end(self):
        log_debug("Go End")
        self.song_end_cb = None
        self.song_fade_start_cb = None
        self.state = STATE_END

    def get_event(self):
        try:
            event = self.change_queue.get_nowait()
            return event
        except queue.Empty:
            if pygame.event.get(SONG_END):
                return SONG_END
            elif pygame.event.get(LVL2_END):
                return LVL2_END
            elif pygame.event.get(SONG_FADE_START):
                return SONG_FADE_START

            return None

    def handle_event(self, event):
        log_debug("Handling event: %s -> %s" % (EVENT_TO_STR_MAP[self.state],
                                                EVENT_TO_STR_MAP[event]))

        if event == SONG_END:
            self.handle_song_end()
            return

        if event == SONG_FADE_START:
            self.handle_song_fade_start()
            return

        if self.state == STATE_END:
            if event == STATE_SONG:
                self.go_song(start_song=True)
            elif event == STATE_SONG_LOOP:
                self.go_song_loop(start_song=True)
            elif event == STATE_SONG_THEN_WHITENOISE:
                self.go_song_then_whitenoise(start_song=True)
            elif event == STATE_WHITENOISE:
                self.go_whitenoise(level=1, start_sound=True)

        elif self.state in (STATE_SONG, STATE_SONG_LOOP,
                            STATE_SONG_THEN_WHITENOISE):
            if event == STATE_SONG:
                self.go_song(start_song=False)
            elif event == STATE_SONG_LOOP:
                self.go_song_loop(start_song=False)
            elif event == STATE_SONG_THEN_WHITENOISE:
                if self.fade_start_timer_running:
                    self.go_song_then_whitenoise(start_song=False)
                else:
                    log_debug("Fade timer already done, going to whitenoise")
                    self.go_whitenoise(level=1, start_sound=True)
                    self.fadeout_song()
            elif event == STATE_WHITENOISE:
                self.go_whitenoise(level=1, start_sound=True)
                self.fadeout_song()
            elif event == STATE_END:
                self.go_end()
                self.fadeout_song()

        elif self.state in (STATE_WHITENOISE, STATE_WHITENOISE_LVL2):

            # do this first so that the check later will stop the lvl2 timer
            if self.state == STATE_WHITENOISE_LVL2 and event == LVL2_END:
                event = STATE_WHITENOISE

            prev_level = self.whitenoise_level_from_state(self.state)

            if (self.is_event_state_change(event) and
                    self.state == STATE_WHITENOISE_LVL2 and
                    self.state != event):
                self.stop_lvl2_timer()

            if event in (STATE_SONG, STATE_SONG_LOOP,
                         STATE_SONG_THEN_WHITENOISE, STATE_END):
                self.fadeout_channel(prev_level)

                if event == STATE_SONG:
                    self.go_song(True)
                elif event == STATE_SONG_LOOP:
                    self.go_song_loop(True)
                elif event == STATE_SONG_THEN_WHITENOISE:
                    self.go_song_then_whitenoise(True)
                elif event == STATE_END:
                    self.go_end()

            elif event in (STATE_WHITENOISE, STATE_WHITENOISE_LVL2):
                # Following line is why we have to allow processing for an
                # event matching the current state. Doing this will reset the
                # level 2 timer so you can extend play on level 2 whitenoise
                new_level = self.whitenoise_level_from_state(event)
                if new_level != prev_level:
                    self.fadeout_channel(level=prev_level)
                self.go_whitenoise(level=new_level, start_sound=(event != self.state))

    def check_for_stop_or_restart(self):
        restart_file = Path(RESTART_FILE)
        if restart_file.is_file():
            log_debug("Found restart file. Exiting for restart.")
            restart_file.unlink()
            return True

        stop_file = Path(STOP_FILE)
        if stop_file.is_file():
            log_debug("Found stop file. Exiting.")
            return True

        return False

    def start_worker(self):
        self.change_worker = ChangeWorker(self.server_url, self.server_user,
                                          self.server_pass, self.change_queue)
        self.change_worker.daemon = True
        self.change_worker.start()

    def run(self):
        self.start_worker()

        run = True

        log_debug("Starting event loop")

        while run:
            if DEBUG:
                print('.', end='', flush=True)

            event = self.get_event()

            if event:
                self.handle_event(event)

            run = not self.check_for_stop_or_restart()

            time.sleep(1)

    @staticmethod
    def startup():
        try:
            log_debug("Client startup")
            client = NurseryClient()
            client.run()
        except Exception as e:
            print("Unable to start client: %s" % e)

NurseryClient.startup()
