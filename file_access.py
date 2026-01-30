import json

# Simple JSON file storage (device.json) – Übergangslösung neben SQLite
# Ich nutze das hier für die API-Responses, falls die DB gerade nicht greift.

def get_devices():
    """Load all devices or empty list"""
    try:
        # JSON-Datei mit den Devices lesen
        with open('device.json', 'r') as file:
            devices = json.load(file)
    except FileNotFoundError:
        print("device.json file not found. Starting with an empty list.")
        devices = []
    except json.JSONDecodeError:
        print("device.json file is empty or corrupted. Starting with an empty list.")
        devices = []
    return devices

# Write the updated devices back to the JSON file
def _save_devices(devices):
    """Write entire list back"""
    # Speichern wir die komplette Liste zurück
    with open('device.json', 'w') as file:
        json.dump(devices, file, indent=4)

# Check if a pin is already in use
def check_pin(pin):
    """True if pin already in use"""
    devices = get_devices()
    for device in devices:
        if device["pin"] == pin:
            return True
    return False

# Remove a device by its pin
def remove(pin):
    """Remove device by pin"""
    devices = get_devices()
    updated_devices = [device for device in devices if device["pin"] != pin]

    # Check if any device was removed
    if len(devices) == len(updated_devices):
        print(f"No device found on pin {pin}.")
    else:
        # Liste nur speichern, wenn sich was geändert hat
        _save_devices(updated_devices)
        print(f"Device on pin {pin} has been removed.")

# Add a new device to the JSON file
def add_device(devicename, pin, device_type):
    """Add new device (lightweight validation)"""
    devices = get_devices()

    # Check if the pin is already in use
    if check_pin(pin) == True:
        return False

    # Create a new device dictionary
    new_device = {
        "devicename": devicename,
        "pin": pin,
        "device_type": device_type
    }

    # Add the new device to the list
    devices.append(new_device)

    # Save the updated device list back to the JSON file
    _save_devices(devices)
    print(f"Device '{devicename}' added successfully on pin {pin}.")
    return True
