# Eigene Exceptions, damit wir Fehler sauber unterscheiden können.
# (Ich fand es übersichtlicher als überall nur Exception zu werfen.)

class DeviceTypeNotFoundException(Exception):
    # Device type ID does not exist
    def __init__(self, message, errors):
        super().__init__(message)
    
class DeviceNotFoundException(Exception):
    # Device (pin) not found
    def __init__(self, message, errors):
        super().__init__(message)
    
