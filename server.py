#!/home/ciw/env/bin/python

import cgi
from configparser import ConfigParser
import json
import os
import pymysql.cursors
import pytz


class NurseryServer(object):

    CONFIG_FILENAME = 'nursery.ini'

    VALID_MODES = [
        'END', 'SONG', 'SONG_LOOP', 'SONG_THEN_WHITENOISE', 'WHITENOISE', 'RESTART'
    ]

    def load_config(self):
        parser = ConfigParser()
        found = parser.read(self.CONFIG_FILENAME)

        if not found:
            raise IOError('Config file "%s" not found.' % self.CONFIG_FILENAME)

        try:
            self.db_name = parser.get('server', 'db_name')
            self.username = parser.get('server', 'db_user')
            self.password = parser.get('server', 'db_pass')
        except Exception as e:
            raise ValueError('Definitions missing from config file: %s' % e)

    def __init__(self):
        self.load_config()

    @staticmethod
    def send_response(status, data):
        print("Content-Type: application/json")
        print("Status: %d" % status)
        print("")
        print(json.dumps(data))

    def validate(self, params):
        errors = []
        data = {}

        if 'mode' in params:
            mode = params.getfirst('mode').upper()
            if mode not in self.VALID_MODES:
                errors.append("Value '%s' is not an acceptable mode" % mode)
                return False, errors
            else:
                data['mode'] = mode
        else:
            errors.append("Field 'mode' is missing")
            return False, errors

        if 'level' in params:
            if data['mode'] != 'WHITENOISE':
                errors.append("Level specified on a mode other than WHITENOISE")
            else:
                level_input = params.getfirst('level')
                try:
                    data['level'] = int(level_input)

                    if data['level'] < 1 or data['level'] > 2:
                        errors.append("Unexpected level given: %d" % data['level'])
                except ValueError:
                    errors.append("Unexpected level given: %s" % level_input)
        elif data['mode'] == 'WHITENOISE':
            data['level'] = 1

        if 'level' not in data:
            data['level'] = None

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
                    result['create_date'] = result['create_date'].replace(tzinfo=pytz.utc).timestamp()
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

    def handle(self, params):

        if os.environ['REQUEST_METHOD'] == 'POST':
            validated, result = self.validate(params)

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
    def startup(params):
        try:
            server = NurseryServer()
            server.handle(params)
        except Exception as e:
            NurseryServer.send_response(500, {'error': "Unable to start server: %s" % e})


NurseryServer.startup(cgi.FieldStorage())
