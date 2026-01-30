from flask import Flask, render_template, redirect, request, url_for, render_template_string, flash, abort, jsonify
import threading
import time as _time
import os
import led as LEDC
import file_access as FA
import requests
import json
import urllib.parse
import configparser
import run_on_start as setup2
from db import DBWrapper
from buttons.press_button import PressButton
from buttons.switch_button import SwitchButton
from sensors.bme680_sensor import read_bme680

# Zentraler Flask-Server für das Mini-Smart-Home.
# Ich habe hier alles in einer Datei gelassen, damit man es schnell findet.
# Kernfeatures: Devices verwalten, Buttons, Remote-API, Historie.

buttons = []  # Liste der Button-Objekte (bleibt im Speicher)

from exceptions import DeviceTypeNotFoundException  # eigene Exception für falsche Device-Typen

app = Flask(__name__)  # Flask-Instanz

config = configparser.ConfigParser()
config.read('.conf')  # Lokale Konfiguration laden (.conf liegt im Repo)

# Secret-Key ist nötig für Flask-Flash-Nachrichten
if config['SYSTEM']['secret_key'].strip('"') != " ":
    app.secret_key = config['SYSTEM']['secret_key'].strip('"')  # vorhandenen Key nutzen
else:
    secret_key = str(setup2.generate.token())  # sonst neuen Token bauen
    app.secret_key = secret_key
    config.set('SYSTEM', 'secret_key', f'"{secret_key}"')

# System-ID wird für API-Identifikation verwendet
if config['SYSTEM']['system_id'].strip('"') != " ":
    system_id = config['SYSTEM']['system_id'].strip('"')
else:
    system_id = str(setup2.generate.system_id())
    config.set('SYSTEM', 'system_id', f'"{system_id}"')

global api_active
global api_token
global api_list
api_active = bool(config['DEFAULT']['api_active'].strip('"'))  # API-Feature an/aus

api_config = configparser.ConfigParser()
api_config.read('api.conf')  # Liste der externen APIs

api_list = []  # verlinkte externe Systeme
for api_group in api_config:
    if api_group != "DEFAULT":
        api_list += [{"url": api_config[api_group]['url'].strip('"'), "token": api_config[api_group]['token'].strip('"')}]

global connect2api
global access_url
connect2api = config['SYSTEM']['connect2api']
access_token = config['DEFAULT']['access_token'].strip('"')  # Anführungszeichen weg

# Access-URL: entweder aus Config oder dynamisch bauen
if config['DEFAULT']['access_url'].strip('"') != "":
    access_url = config['DEFAULT']['access_url'].strip('"')
else:
    access_url = "http://" + setup2.get.ip() + ":" + config['DEFAULT']['port'].strip('"')
access_url = urllib.parse.quote(access_url)  # URL-encoding fürs Weiterreichen

with open('.conf', 'w') as configfile:
    config.write(configfile)  # Änderungen (z.B. neue IDs) zurückschreiben

def create_record(deviceID, state):
    """Persist state change"""
    db.create_record(deviceID, state)  # History-Entry schreiben

def switch(pin):
    """Toggle physical device and persist state"""
    device = db.get_device(pin)
    if device is None:
        return redirect(url_for('error'))
    LEDC.set.switch(pin)  # Hardware umschalten
    state = LEDC.get.led(pin)  # neuen Zustand abfragen
    db.update_device_state_by_pin(pin, state)
    create_record(int(device["id"]), state)

def call_api_info():
    """Init: fetch system IDs of linked APIs"""
    for api in api_list:
        print()
        url = api['url'] + f'/api/info?code=' + api['token']
        response = requests.get(url)
        response = json.loads(response.text)[0]
        api['system_id'] = str(response['system_id'])

def get_api(api_id):
    """Hilfsfunktion: API-Objekt anhand System-ID finden"""
    for api in api_list:
        if api['system_id'] == api_id:
            return api
    return "[{ 'response': 'error'}]"

db = DBWrapper(config["DEFAULT"]["db_name"])  # SQLite-Wrapper
db.init_db()
db.init_tables()

# -------------------------- Web views --------------------------
@app.route('/')
def home():
    """Overview: devices grouped by room"""
    devices = db.get_all_devices()
    num_rooms = db.get_number_of_rooms()
    grouped_devices = db.get_all_devices_grouped_by_room()
    all_buttons = db.get_all_buttons()
    # Sensor: aktuellen Wert lesen und abspeichern, falls verfügbar
    current_reading = read_bme680()
    latest_sensor = None
    if current_reading.get('available'):
        try:
            db.insert_sensor_reading('bme680', current_reading)
            latest_sensor = current_reading
        except Exception:
            latest_sensor = current_reading
    else:
        try:
            latest_sensor = db.get_latest_sensor_reading('bme680')  # fallback auf letzten Wert
        except Exception:
            latest_sensor = None

    if config['SYSTEM']['connect2api'].strip('"') == "true":
        # Externe Systeme einbinden (wenn aktiviert)
        for response in call_all_apis("json"):
            devices += response

    return render_template('index.html', devices_by_room=grouped_devices, all_devices=devices, all_button_devices=all_buttons, latest_sensor=latest_sensor)

@app.route('/device/<pin>/')
def device(pin):
    """Device detail view"""
    pin = int(pin)
    device = db.get_device(pin)
    if device is None:
        return redirect(url_for('error'))
    try:
        state = int(device["state"])  # state kann None sein -> try/except
    except:
        db.update_device_state_by_pin(pin, 0)
    return render_template('device.html', device=device)

@app.route('/switch/<pin>/')
def device_switch(pin):
    """UI: toggle device"""
    pin = int(pin)
    switch(pin)  # toggeln und Status speichern
    return redirect(f'/device/{pin}')

@app.route('/unset/<pin>/')
def unset_pin(pin):
    """Remove device and free pin"""
    pin = int(pin)
    device = db.get_device(pin)
    if device is None:
        return redirect(url_for('error'))
    db.remove_device(pin)
    LEDC.clear_led(pin)  # GPIO freigeben
    
    flash(f'Pin "{pin}" is now unset and cleand.', 'success')
    return redirect('/')

@app.route('/add-device', methods=['POST'])
def add_device():
    """Add new output device"""
    device_name = request.form.get('deviceName')
    pin = int(request.form.get('pin'))
    device_type = request.form.get('deviceType')
    roomID = int(request.form.get('roomID'))
    if not db.get_device(pin):
        db.add_device(device_name, pin, device_type, roomID)  # DB-Eintrag
    else:
        flash(f'Error: Pin "{pin}" is already in use.', 'error')
        return redirect(url_for('home'))
    try:
        if device_type == 'output':
            if LEDC.setup_led(pin):
                flash(f'Device "{device_name}" added successfully.', 'success')
                pass
            else:
                db.remove_device(pin)
                flash(f'Error by pin setup "{device_name}" are not created.', 'error')
        else:
            flash("Not implemented yet! Use Add Button to add button devices!")
            pass
    except:
        FA.remove(pin)  # falls GPIO Setup klemmt, löschen wir das Gerät wieder
        flash(f'Error "{device_name}" are not created.', 'error')

    return redirect("/")

@app.route("/add-button", methods=['POST'])
def add_button():
    """Create button (input -> output)"""
    device_name = request.form.get('deviceName')
    input_pin = int(request.form.get('inputPin'))  # Input GPIO
    output_pin = int(request.form.get('outputPin'))
    button_type = int(request.form.get('buttonType'))
    device_type = 2
    try:
        if not db.get_device(input_pin):
            # Raum 1000 ist bei uns "virtuell", damit Buttons nicht bei normalen Räumen stören
            db.add_device(device_name, input_pin, device_type, secondary_pin=output_pin, room_id=1000)
        else:
            flash(f'Error: Pin "{input_pin}" is already in use.', 'error')
            return redirect(url_for('home'))
    except DeviceTypeNotFoundException:
        flash(f"Device type with id {device_type} does not exist", 'error')
        return redirect(url_for('home'))

    if button_type == 1:
            btn = SwitchButton(input_pin, output_pin)
            buttons.append(btn)  # switch = toggeln
    elif button_type == 2:
            btn = PressButton(input_pin, output_pin)
            buttons.append(btn)  # press = kurzer HIGH
    else:
        flash("Button Type does not exist!")
        redirect(url_for('home'))
    flash(f"Added button {device_name} successfully on pin {input_pin}")
    return redirect("/")


   
    



@app.route("/room/<roomID>")
def room_toggle(roomID):
    """Toggle all devices in room"""
    roomID = int(roomID)
    devices_in_room = db.get_all_devices_for_room(roomID)
    for device in devices_in_room:
        switch(int(device['pin']))  # jedes Device einzeln toggeln
    
    return redirect("/")

@app.route('/stats')
def stats():
    """Statistics / history"""
    stats = db.get_num_state_updates()
    history = db.get_history()
    return render_template("stats.html", stats=stats, history_by_minute=history, api_code=access_token)

@app.route('/sensors')
def sensors_view():
    # Nur Template rendern, Daten kommen per JS
    return render_template('sensors.html', api_code=access_token)


@app.route('/<all>')
def catch(all = None):
    return render_template('error.html')  # Catch-all, falls Route nicht gefunden

@app.route('/error')
def error():
    return render_template('error.html')  # Standard-Fehlerseite

#--------------------------------------------------------------
# call_api's

def call_all_apis(url_part):
    """Query all connected APIs (GET)"""
    if api_active == True:
        full_response = []
        for api in api_list:
            try:
                url = api['url'] + f'/api/get/{url_part}?code=' + api['token']
                response = requests.get(url)
                if str(response) == "<Response [401]>":
                    flash( '"'+ api['url'] +'" Authorisation failed', 'error')
                else:
                    full_response += [json.loads(response.text)]  # API liefert JSON als String
            except:
                flash(api['url'] + ' is not available', 'error')
                pass
            
        return full_response
    
def call_api(url_part, use_api):
    """Single API request"""
    if api_active == True:
        url = use_api['url'] + f'/api/{url_part}?code=' + use_api['token']
        response = json.loads(requests.get(url).text)[0]
        return response

@app.route('/api/device/<pin>/', methods=['GET'])
def call_api_device(pin):
    """Device detail (external system)"""
    api_id = request.args.get('system_id')
    api_call = get_api(api_id)
    response = call_api(f"get/device/{pin}", api_call)
    return render_template('device.html', device=response)
    

@app.route('/api/switch/<pin>/', methods=['GET'])
def call_api_device_switch(pin):
    """Remote: toggle device"""
    api_id = request.args.get('system_id')
    api_call = get_api(api_id)
    response = call_api(f"set/switch/{pin}", api_call)
    return redirect("/api/device/{pin}?system_id={sid}".format(pin=response["pin"], sid=response["system_id"]))

@app.route('/api/unset/<pin>/', methods=['GET'])
def call_unset_device(pin):
    """Remote: remove device"""
    api_id = request.args.get('system_id')
    api_call = get_api(api_id)
    pin = int(pin)
    if call_api(f"set/unset/{pin}", api_call)['response'] == 'success':
        flash(f'Pin "{pin}" removed successfully.', 'success')
    else:
        flash(f'Pin "{pin}" could not be removed.', 'error')

    return redirect('/')

#--------------------------------------------------------------
# api response

@app.route('/api/info/')
def info():
    # Kleine Info für andere Systeme
    return '[{ "system_id": "' + system_id + '", "version": "0.0.1", "allow_connection": "' + str(api_active) + '"}]'

def auth_check(code):
    """Token validation"""
    if code == access_token:
        return True
    else:
        return False

@app.route('/api/get/json/')
def home_json():
    """API: all devices (JSON)"""
    code = request.args.get('code')
    if auth_check(code):
        devices = FA.get_devices()
        for device in devices:
            try:
                device['state'] = LEDC.state(device['pin'])  # GPIO-State mitgeben
            except:
                device['state'] = False
            device['system_id'] = system_id
        return devices
    else:
        abort(401)

@app.route('/api/get/device/<pin>/')
def api_device(pin):
    """API: single device status"""
    code = request.args.get('code')
    if auth_check(code):
        pin = int(pin)
        if LEDC.get.led(pin):
            return '[{ "devicename": "API", "pin": '+str(pin)+', "device_type": "output", "state": true, "system_id": "'+system_id+'" }]'
        else:
            return '[{ "devicename": "API", "pin": '+str(pin)+', "device_type": "output", "state": false, "system_id": "'+system_id+'" }]'
    abort(401)

@app.route('/api/set/switch/<pin>/')
def api_device_switch(pin):
    """API: toggle device"""
    code = request.args.get('code')
    if auth_check(code):
        pin = int(pin)
        device = db.get_device(pin)
        if device is None:
            return '[{ "state": false}]'
        LEDC.set.switch(pin)  # Hardware toggeln
        return '[{ "pin": '+str(pin)+', "system_id": "'+system_id+'" }]'
    return "[{ 'error': 'Authorisation failed' }]"

@app.route('/api/sensors/bme680')
def api_sensor_bme680():
    code = request.args.get('code')
    if not auth_check(code):
        abort(401)
    reading = read_bme680()
    if reading.get('available'):
        try:
            db.insert_sensor_reading('bme680', reading)
        except Exception:
            pass
    return jsonify(reading)

@app.route('/api/sensors/bme680/history')
def api_sensor_bme680_history():
    code = request.args.get('code')
    if not auth_check(code):
        abort(401)
    try:
        limit = int(request.args.get('limit', 300))
    except Exception:
        limit = 300
    items = db.get_sensor_history('bme680', limit)
    return jsonify(items)

_sensor_thread_started = False

def _sensor_sampler_loop(interval_sec: int = 10):
    while True:
        try:
            reading = read_bme680()
            if reading.get('available'):
                db.insert_sensor_reading('bme680', reading)
        except Exception:
            pass
        _time.sleep(interval_sec)  # Pause zwischen den Messungen

def _maybe_start_sampler():
    global _sensor_thread_started
    if _sensor_thread_started:
        return  # läuft schon
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return  # verhindert doppelten Thread im Debug-Reload
    try:
        interval = int(config['DEFAULT'].get('sensor_interval', '10').strip('"') or 10)
    except Exception:
        interval = 10
    th = threading.Thread(target=_sensor_sampler_loop, args=(interval,), daemon=True)
    th.start()
    _sensor_thread_started = True

@app.route('/api/set/unset/<pin>')
def api_set_unset_device(pin):
    """API: remove device"""
    code = request.args.get('code')
    if auth_check(code):
        pin = int(pin)
        call_url = request.args.get('url')
        try:
            LEDC.clear_led(pin)
            FA.remove_device(pin)  # remove aus JSON (legacy)
            return [{"response": "success"}]
        except:
            return [{"response": "error"}]
    return "[{ 'error': 'Authorisation failed' }]"

#--------------------------------------------------------------

call_api_info()

def start():
    """Start Flask (externally callable)"""
    _maybe_start_sampler()
    app.run(debug=True, port=config['DEFAULT']['port'].strip('"'), host='0.0.0.0')

start()  # direkt starten, wenn Datei ausgeführt/importiert wird
