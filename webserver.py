from flask import Flask, render_template, redirect, request, url_for, render_template_string, flash, abort, jsonify
import led as LEDC
import file_access as FA
import requests
import json
import urllib.parse
import configparser
import run_on_start as setup2
import secrets
from db import DBWrapper
from buttons.press_button import PressButton
from buttons.switch_button import SwitchButton

# Central Flask app for smart-home mini system
# Core features: device management, buttons, remote API, history

buttons = []

from exceptions import DeviceTypeNotFoundException

app = Flask(__name__)

config = configparser.ConfigParser()
config.read('.conf')

REQUEST_TIMEOUT = 5

def parse_bool(raw_value, default=False):
    if raw_value is None:
        return default
    normalized = str(raw_value).strip().strip('"').lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default

if config['SYSTEM']['secret_key'].strip('"') != " ":
    app.secret_key = config['SYSTEM']['secret_key'].strip('"')  # Needed for flashing messages
else:
    secret_key = str(setup2.generate.token())
    app.secret_key = secret_key
    config.set('SYSTEM', 'secret_key', f'"{secret_key}"')

if config['SYSTEM']['system_id'].strip('"') != " ":
    system_id = config['SYSTEM']['system_id'].strip('"')  # Needed for flashing messages
else:
    system_id = str(setup2.generate.system_id())
    config.set('SYSTEM', 'system_id', f'"{system_id}"')

global api_active
global api_token
global api_list
api_active = parse_bool(config['DEFAULT'].get('api_active', '"false"'))

api_config = configparser.ConfigParser()
api_config.read('api.conf')

api_list = []  # Linked external systems
for api_group in api_config:
    if api_group != "DEFAULT":
        api_list += [{ "url": api_config[api_group]['url'].strip('"'), "token": api_config[api_group]['token'].strip('"')}]

global connect2api
global access_url
connect2api =  config['SYSTEM']['connect2api']
access_token = config['DEFAULT']['access_token'].strip('"')  # Remove quotes

if config['DEFAULT']['access_url'].strip('"') != "":
    access_url = config['DEFAULT']['access_url'].strip('"')  # Remove quotes
else:
    access_url = "http://" +setup2.get.ip() + ":" + config['DEFAULT']['port'].strip('"')
access_url = urllib.parse.quote(access_url)  # URL encode

with open('.conf', 'w') as configfile:
    config.write(configfile)

def create_record(deviceID, state):
    """Persist state change"""
    db.create_record(deviceID, state)

def switch(pin):
    """Toggle physical device and persist state"""
    device = db.get_device(pin)
    if device is None:
        return redirect(url_for('error'))
    LEDC.set.switch(pin)
    state = LEDC.get.led(pin)
    db.update_device_state_by_pin(pin, state)
    create_record(int(device["id"]), state)

def call_api_info():
    """Init: fetch system IDs of linked APIs"""
    for api in api_list:
        url = api['url'] + f'/api/info?code='+ api['token']
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response = response.json()[0]
            api['system_id'] = str(response['system_id'])
        except (requests.RequestException, ValueError, KeyError):
            app.logger.warning("Failed to load API info from %s", api["url"])

def get_api(api_id):
    for api in api_list:
        if api['system_id'] == api_id:
            return api
    return "[{ 'response': 'error'}]"

db = DBWrapper(config["DEFAULT"]["db_name"])  # SQLite instance
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

    if config['SYSTEM']['connect2api'].strip('"') == "true":
        for response in call_all_apis("json"):
            devices += response

    return render_template('index.html', devices_by_room=grouped_devices, all_devices=devices, all_button_devices=all_buttons)

@app.route('/device/<pin>/')
def device(pin):
    """Device detail view"""
    pin = int(pin)
    device = db.get_device(pin)
    if device is None:
        return redirect(url_for('error'))
    try:
        state = int(device["state"])
    except:
        db.update_device_state_by_pin(pin, 0)
    return render_template('device.html', device=device)

@app.route('/switch/<pin>/')
def device_switch(pin):
    """UI: toggle device"""
    pin = int(pin)
    switch(pin)
    return redirect(f'/device/{pin}')

@app.route('/unset/<pin>/')
def unset_pin(pin):
    """Remove device and free pin"""
    pin = int(pin)
    device = db.get_device(pin)
    if device is None:
        return redirect(url_for('error'))
    db.remove_device(pin)
    LEDC.clear_led(pin)
    
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
        db.add_device(device_name, pin, device_type, roomID)
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
        FA.remove(pin)
        flash(f'Error "{device_name}" are not created.', 'error')

    return redirect("/")

@app.route("/add-button", methods=['POST'])
def add_button():
    """Create button (input -> output)"""
    device_name = request.form.get('deviceName')
    input_pin = int(request.form.get('inputPin')) #24
    output_pin = int(request.form.get('outputPin'))
    button_type = int(request.form.get('buttonType'))
    device_type = 2
    try:
        if not db.get_device(input_pin):
            db.add_device(device_name, input_pin, device_type , secondary_pin=output_pin,room_id=1000)
        else:
            flash(f'Error: Pin "{input_pin}" is already in use.', 'error')
            return redirect(url_for('home'))
    except DeviceTypeNotFoundException:
        flash(f"Device type with id {device_type} does not exist", 'error')
        return redirect(url_for('home'))

    if button_type == 1:
            btn = SwitchButton(input_pin,output_pin)
            buttons.append(btn)
    elif button_type == 2:
            btn = PressButton(input_pin, output_pin)
            buttons.append(btn)
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
        switch(int(device['pin']))
    
    return redirect("/")

@app.route('/stats')
def stats():
    """Statistics / history"""
    stats = db.get_num_state_updates()
    history = db.get_history()
    return render_template("stats.html", stats=stats, history_by_minute=history)


@app.route('/<all>')
def catch(all = None):
    return render_template('error.html')

@app.route('/error')
def error():
    return render_template('error.html')

#--------------------------------------------------------------
# call_api's

def call_all_apis(url_part):
    """Query all connected APIs (GET)"""
    if api_active is True:
        full_response = []
        for api in api_list:
            try:
                url = api['url'] + f'/api/get/{url_part}?code='+ api['token']
                response = requests.get(url, timeout=REQUEST_TIMEOUT)
                if response.status_code == 401:
                    flash(f'"{api["url"]}" Authorisation failed', 'error')
                else:
                    full_response.append(response.json())
            except (requests.RequestException, ValueError):
                flash(api['url'] + ' is not available', 'error')

        return full_response
    return []
    
def call_api(url_part, use_api):
    """Single API request"""
    if api_active is True:
        try:
            url = use_api['url'] + f'/api/{url_part}?code='+use_api['token']
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()[0]
        except (requests.RequestException, ValueError, KeyError):
            return {"response": "error"}
    return {"response": "error"}

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
    if response.get("response") == "error":
        flash("Remote switch failed.", "error")
        return redirect(url_for('home'))
    return redirect(url_for('call_api_device', pin=response['pin'], system_id=response['system_id']))

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
    return jsonify([{"system_id": system_id, "version": "0.0.1", "allow_connection": str(api_active)}])

def auth_check(code):
    """Token validation"""
    if code is None:
        return False
    return secrets.compare_digest(code, access_token)

@app.route('/api/get/json/')
def home_json():
    """API: all devices (JSON)"""
    code = request.args.get('code')
    if auth_check(code):
        devices = FA.get_devices()
        for device in devices:
            try:
                device['state'] = LEDC.get.led(device['pin'])
            except Exception:
                device['state'] = False
            device['system_id'] = system_id
        return jsonify(devices)
    else:
        abort(401)

@app.route('/api/get/device/<pin>/')
def api_device(pin):
    """API: single device status"""
    code = request.args.get('code')
    if auth_check(code):
        pin = int(pin)
        if LEDC.get.led(pin):
            state = True
        else:
            state = False
        return jsonify([{"devicename": "API", "pin": pin, "device_type": "output", "state": state, "system_id": system_id}])
    abort(401)

@app.route('/api/set/switch/<pin>/')
def api_device_switch(pin):
    """API: toggle device"""
    code = request.args.get('code')
    if auth_check(code):
        pin = int(pin)
        device = db.get_device(pin)
        if device is None:
            return jsonify([{"state": False}])
        LEDC.set.switch(pin)
        return jsonify([{"pin": pin, "system_id": system_id}])
    return jsonify([{"error": "Authorisation failed"}]), 401

@app.route('/api/set/unset/<pin>')
def api_set_unset_device(pin):
    """API: remove device"""
    code = request.args.get('code')
    if auth_check(code):
        pin = int(pin)
        try:
            LEDC.clear_led(pin)
            FA.remove(pin)
            return jsonify([{"response": "success"}])
        except Exception:
            return jsonify([{"response": "error"}]), 500
    return jsonify([{"error": "Authorisation failed"}]), 401

#--------------------------------------------------------------

call_api_info()

def start():
    """Start Flask (externally callable)"""
    app.run(debug=False, port=config['DEFAULT']['port'].strip('"'), host='0.0.0.0')

if __name__ == "__main__":
    start()
