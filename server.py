#!env/bin/python

import cgi
from ConfigParser import SafeConfigParser
from datetime import timezone
import json
import os
import pymysql.cursors

class NurseryServer(object):

    CONFIG_FILENAME = 'nursery.ini'

    VALID_MODES = [
        'END', 'SONG', 'SONG_LOOP', 'SONG_THEN_WHITENOISE', 'WHITENOISE'
    ]

    def __init__(self):
        parser = SafeConfigParser()
        found = parser.read(self.CONFIG_FILENAME)

        if not found:
            raise IOError('Config file "%s" not found.' % self.CONFIG_FILENAME)

        self.db_name = parser.get('server', 'db_name', None)
        self.username = parser.get('server', 'db_user', None)
        self.password = parser.get('server', 'db_pass', None)

        if not self.db_name or not self.username or not self.password:
            raise ValueError('Definitions missing from config file.')

    @staticmethod
    def send_response(status, data):
        print("Content-Type: application/json")
        print("Status: %d" % status)
        print("")
        print(json.dumps(data))

    def validate(self, input):
        errors = []
        data = {}

        mode = input.getfirst('mode', None)
        if mode:
            data['mode'] = mode.upper()

        level_input = input.getfirst('level', None)

        if 'mode' not in input:
            errors.append("Field 'mode' is missing")
        elif input.getfirst('mode').upper() not in self.VALID_MODES:
            errors.append("Value '%s' is not an acceptable mode" % input.getfirst('mode').upper())

        if level_input:
            if data['mode'] != 'WHITENOISE':
                errors.append("Level specified on a mode other than WHITENOISE")
            else:
                try:
                    data['level'] = int(level_input)
                    if data['level'] < 1 or data['level'] > 2:
                        errors.append("Unexpected level given: %d" % data['level'])
                except ValueError:
                    errors.append("Unexpected level given: %s" % level_input)
        elif data['mode'] == 'WHITENOISE':
            data['level'] = 1

        if not errors:
            return True, data
        else:
            return False, errors

    def connect(self):
        if not hasattr(self, 'connection'):
            self.connection = pymysql.connect(
                host='localhost',
                user=self.username,
                password=self.password,
                db=self.db_name,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )

    def disconnect(self):
        self.connection.close()

    def insert(self, data):
        self.connect()
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO `nursery_sounds` (`mode`, `level`) VALUES (%(mode)s, %(level)s)",
                    data
                )
                self.connection.commit()
        finally:
            self.disconnect()

    def get_and_ack(self):
        self.connect()
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT `id`, `mode`, `level`, `ack`, `create_date` FROM `nursery_sounds` ORDER BY `create_date` DESC LIMIT 1"
                )
                result = cursor.fetchone()

                if result and not result['ack']:
                    result['create_date'] = result['create_date'].replace(tzinfo=timezone.utc).timestamp()
                    cursor.execute(
                        "UPDATE `nursery_sounds` SET `ack` = TRUE WHERE `id` = %s",
                        (result['id'])
                    )
                    self.connection.commit()

                    return result
                else:
                    return None
        finally:
            self.disconnect()

    def handle(self, input):

        if os.environ['REQUEST_METHOD'] == 'POST':
            validated, result = self.validate(input)

            if not validated:
                NurseryServer.send_response(
                    status=400,
                    data={
                        'errors': result
                    }
                )
                return False

            else:
                self.insert(result)
                NurseryServer.send_response(201, result)
                return True

        elif os.environ['REQUEST_METHOD'] == 'GET':
            result = self.get_and_ack()

            if result:
                NurseryServer.send_response(200, result)
            else:
                NurseryServer.send_response(404, None)
            return True

        else:
            NurseryServer.send_response(400, {'error': "Invalid HTTP method specified"})
            return False

    @staticmethod
    def startup(input):
        try:
            server = NurseryServer()
        except Exception as e:
            NurseryServer.send_response(500, {'error': "Unable to start server: %s" % e})

        server.handle(input)


NurseryServer.startup(cgi.FieldStorage())
