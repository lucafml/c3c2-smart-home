import RPi.GPIO as GPIO

from .button import GenericButtonHandler


class SwitchButton(GenericButtonHandler):
    def trigger(self, pin):
        # Toggle output state (wie Lichtschalter)
        print(f"triggered switch button on {self.input_pin}")
        print(GPIO.input(self.input_pin))
        print("Input is HIGH")
        current_state = GPIO.input(self.output_pin)
        print(f"Current state is {current_state} ")
        GPIO.output(self.output_pin, not current_state)
