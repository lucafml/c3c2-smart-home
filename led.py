import RPi.GPIO as GPIO

# GPIO-Hilfsfunktionen für LED/Relais-Output.
# Ich hab die API etwas "klassisch" gelassen (get/set Klassen), ist aber simpel zu lesen.


def setup_led(pin):
    """Configure pin as OUTPUT"""
    GPIO.setmode(GPIO.BCM)  # BCM ist die normale GPIO-Nummerierung
    GPIO.setup(pin, GPIO.OUT)
    return True

def clear_led(pin):
    """Release pin"""
    GPIO.cleanup(pin)  # Pin freigeben, sonst "hängt" er ggf. noch

class get:
    # Read operations
    def led(pin):
        try:
            if GPIO.input(pin) == GPIO.HIGH:
                return True
            else:
                return False
        except:
            return False
        
class set:
    # Write operations
    def led_on(pin, repeat=False):
        try:
            GPIO.output(pin, GPIO.HIGH)
            return True

        except RuntimeError as e:
            if repeat:
                return False
            else:
                setup_led(pin)  # GPIO nochmal initialisieren
                set.led_on(pin, True)

    def led_off(pin, repeat=False):
        try:
            GPIO.output(pin, GPIO.LOW)
            return True

        except RuntimeError as e:
            if repeat:
                return False
            else:
                setup_led(pin)  # falls pin noch nicht als Output steht
                set.led_off(pin, True)
                print('x')

    def led(pin, state):
        """Set LED based on bool/keyword"""
        if isinstance(state, bool):
            if state:
                set.led_on(pin)
            else:
                set.led_off(pin)
        elif state.upper() in ["ON", "HIGH"]:
            set.led_on(pin)
        elif state.upper() in ["OFF", "LOW"]:
            set.led_off(pin)
        else:
            raise False
        
    def switch(pin):
        """Toggle state"""
        if get.led(pin):
            set.led_off(pin)
            return False
        else:
            set.led_on(pin)
            return True

class Cleanup:
    def __del__(self):
        # Fallback clean-up on GC
        GPIO.cleanup()  # wenn Python beendet wird, räumen wir GPIO auf

cleanup_instance = Cleanup()
