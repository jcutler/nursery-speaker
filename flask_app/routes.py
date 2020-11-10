from flask import abort, jsonify, render_template, request
import pytz

from flask_app import app, mysql

VALID_MODES = [
    'END', 'SONG', 'SONG_LOOP', 'SONG_THEN_WHITENOISE', 'WHITENOISE', 'RESTART'
]

def validate(params):
    errors = []
    data = {}

    if 'mode' in params:
        mode = params.get('mode').upper()
        if mode not in VALID_MODES:
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
            level_input = params.get('level')
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

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/server", methods=['GET', 'POST'])
def server():
    if request.method == 'POST':
        validated, result = validate(request.form)

        if not validated:
            return jsonify(errors=result), 400
        else:
            conn = mysql.connect()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO `nursery_sounds` (`mode`, `level`) VALUES (%(mode)s, %(level)s)",
                        result
                    )
                    conn.commit()
                
                    return jsonify(result), 201
            finally:
                conn.close()

    else:
        conn = mysql.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT `id`, `mode`, `level`, `actor_ip`, `ack`, `create_date` FROM `nursery_sounds` ORDER BY `create_date` DESC LIMIT 1"
                )
                result = cursor.fetchone()

                if result and not result['ack']:
                    result['create_date'] = result['create_date'].replace(tzinfo=pytz.utc).timestamp()
                    cursor.execute(
                        "UPDATE `nursery_sounds` SET `ack` = TRUE WHERE `id` = %s",
                        (result['id'])
                    )
                    conn.commit()

                    del result['actor_ip']

                    return jsonify(result)
                else:
                    abort(404)
        finally:
            conn.close()

