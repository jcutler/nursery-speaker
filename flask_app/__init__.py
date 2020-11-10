from flask import Flask
from flaskext.mysql import MySQL
from configparser import ConfigParser
from pymysql import cursors


CONFIG_FILENAME = '/srv/nursery.cutler.is/nursery.ini'

app = Flask(__name__)

parser = ConfigParser()
found = parser.read(CONFIG_FILENAME)
if not found:
  raise IOError('Config file "%s" not found.' % CONFIG_FILENAME)

try:
  app.config['MYSQL_DATABASE_USER'] = parser.get('server', 'db_user')
  app.config['MYSQL_DATABASE_PASSWORD'] = parser.get('server', 'db_pass')
  app.config['MYSQL_DATABASE_DB'] = parser.get('server', 'db_name')
except Exception as e:
  raise ValueError('Definitions missing from config file: %s' %e)

mysql = MySQL(cursorclass=cursors.DictCursor)
mysql.init_app(app)

from flask_app import routes
