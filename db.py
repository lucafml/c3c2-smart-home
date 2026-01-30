import sqlite3
from collections import defaultdict
import time as t

from exceptions import DeviceTypeNotFoundException, DeviceNotFoundException

# DB-Wrapper für die Geräteverwaltung (kleines, simples SQLite-Setup).
# Ich halte es bewusst schlank, damit man es als Azubi schnell versteht.

class DBWrapper:
    def __init__(self, db_name):
        self.db_name = db_name
        self.connection = None
        self.cur = None
        # DB ist am Anfang noch nicht verbunden

    def dict_factory(self, cursor, row):
        """Rows -> dict (column_name: value)"""
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]  # Spaltennamen als Schlüssel
        return d

    def group_by_minute(self, data):
        """Group history entries by minute"""
        history_by_minute = defaultdict(list)
        for row in data:
            minute = row["minute_group"]
            history_by_minute[minute].append(row)
        return dict(history_by_minute)

    def create_db(self):
        """Establish connection (one-time)"""
        # check_same_thread=False, damit wir die Verbindung auch aus Flask-Threads nutzen können
        self.connection = sqlite3.connect(self.db_name, check_same_thread=False)
        self.connection.row_factory = self.dict_factory
        self.cur = self.connection.cursor()
        return self.cur

    def init_tables(self):
        """Create tables if not present and write startup log"""
        start = t.time()
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL,
                code TEXT NOT NULL,
                message TEXT NOT NULL,
                deviceID INTEGER,
                FOREIGN KEY(deviceID) REFERENCES device(id)
            );
        """)

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                deviceID INTEGER,
                state INTEGER,
                FOREIGN KEY(deviceID) REFERENCES device(id)
            );
        """)

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS device_type (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_type TEXT NOT NULL
            );
        """)
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS device (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                devicename TEXT NOT NULL,
                pin INTEGER NOT NULL UNIQUE,
                second_pin INTEGER UNIQUE,
                device_type_id INTEGER NOT NULL,
                roomID INTEGER,
                state INTEGER,
                FOREIGN KEY(device_type_id) REFERENCES device_type(id)
            );
        """)

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                sensor_type TEXT NOT NULL,
                temperature_c REAL,
                humidity REAL,
                pressure_hpa REAL,
                gas_ohms REAL
            );
        """)

        # Default device types (fixed ids): 1=output, 2=input, 3=virt, 4=sensor
        self.cur.executemany("""
            INSERT OR IGNORE INTO device_type (id, device_type) VALUES (?, ?);
        """, [(1, 'output'), (2, 'input'), (3, 'virtual_input'), (4, 'sensor')])
        time_to_build = t.time() - start
        # Startup-Log, damit wir grob sehen ob die DB fix fertig ist
        self.cur.execute("""
            INSERT INTO logs (type, code, message, deviceID)
            VALUES (?, ?, ?, NULL);
        """, ('info', 'startup', f'System initialized in {time_to_build:.2f} secs'))
        self.connection.commit()

    def init_db(self):
        """Convenience: create connection"""
        self.create_db()
        return self.cur

    def write_log(self, msg_type: str, code: str, message: str, device_id=None):
        """Write log entry"""
        self.cur.execute("""
            INSERT INTO logs (type, code, message, deviceID)
            VALUES (?, ?, ?, ?);
        """, (msg_type, code, message, device_id))
        self.connection.commit()

    def add_device(self, device_name: str, pin: int, device_type: int, secondary_pin=None, room_id = 0):
        """Add new device (unique pin). Returns True/False"""
        device_type_obj = self.cur.execute("""
            SELECT id FROM device_type WHERE id = ?;
        """, (device_type,)).fetchone()
        if not device_type_obj:
            raise DeviceTypeNotFoundException(f"Device type not found", device_type)
            
        try:
            if device_type == 1:
                # Output: nur ein Pin
                self.cur.execute("""
                    INSERT INTO device (devicename, pin, device_type_id, roomID)
                    VALUES (?, ?, ?, ?);
                """, (device_name, pin, device_type, room_id))
            elif device_type == 2:
                # Input/Button: hat zusätzlich einen Secondary-Pin
                self.cur.execute("""
                    INSERT INTO device (devicename, pin, secondary_pin, device_type_id, roomID)
                    VALUES (?, ?, ?, ?, ?);
                """, (device_name, pin, secondary_pin, device_type, room_id))
        except sqlite3.IntegrityError:
            return False
        self.write_log("info", "device_added", f"Successfully added device {device_name} of type {device_type} on pin {pin}")
        self.connection.commit()
        return True

    def remove_device(self, pin):
        """Remove device by pin or raise exception"""
        pin_is_in_use = self.cur.execute("""
            SELECT pin FROM device WHERE pin = ?;
        """, (pin,)).fetchone()
        if pin_is_in_use:
            # Gerät entfernen, Pin wird wieder frei
            self.cur.execute("""
                DELETE FROM device WHERE pin = ?;
            """, (pin,))
            self.write_log("info", "device_removed", f"Successfully removed device on pin {pin}")
            self.connection.commit()
        else:
            raise DeviceNotFoundException(f"Device with pin {pin} not found")

    def get_device(self, pin):
        """Get device by pin (or None)"""
        device = self.cur.execute("""
        SELECT * FROM device WHERE pin = ?;
        """, (pin,)).fetchone()
        
        return device
    
    def get_all_devices(self):
        """All devices (list)"""
        all_devices = self.cur.execute("""
        SELECT * FROM device ORDER BY roomID DESC;
        """).fetchall()
        return all_devices
    
    def get_all_devices_for_room(self,room_id: int):
        """Devices in room"""
        all_devices_for_room = self.cur.execute("""
        SELECT * FROM device WHERE roomID = ?;
        """, (room_id,)).fetchall()

        return all_devices_for_room
    
    def get_all_devices_grouped_by_room(self):
        """Devices grouped by room -> dict"""
        all_devices = self.cur.execute("""
        SELECT * FROM device ORDER BY roomID DESC;
        """).fetchall()

        grouped_devices = {}

        for device in all_devices:
            roomID = device["roomID"]
            if roomID not in grouped_devices:
                grouped_devices[roomID] = []
            grouped_devices[roomID].append(device)
        
        return grouped_devices


    def update_device_state_by_pin(self, pin: int, state: int):
        """Persist current state"""
        update = self.cur.execute("""
        UPDATE device SET state = ? WHERE pin = ?;
        """, (state,pin, ))
        self.write_log("INFO", 200 , f"Updated state on pin {pin} to {state}")
        self.connection.commit()

    def get_number_of_rooms(self):
        """List distinct roomIDs"""
        result = self.cur.execute("""
        SELECT DISTINCT roomID FROM device;
        """).fetchall()
        return result
    
    def create_record(self, deviceID, state):
        """Create history record"""
        self.cur.execute("""
            INSERT INTO history (deviceID, state) VALUES (?, ?)
        """, (deviceID, state, ))

        self.connection.commit()
        return True
    
    def get_num_state_updates(self):
        """Number of state changes (COUNT)"""
        row = self.cur.execute("""
            SELECT COUNT(deviceID) AS cnt FROM history;
        """).fetchone()
        return int(row.get('cnt', 0) if isinstance(row, dict) else row[0])
    def get_history(self):
        """History grouped by minute"""
        history_entries = self.cur.execute("""
            SELECT 
                strftime('%Y-%m-%d %H:%M', history.timestamp) AS minute_group,
                device.devicename,
                device.id AS device_id,
                device.roomID,
                history.state
            FROM 
                history
            JOIN 
                device ON history.deviceID = device.id
            GROUP BY 
                minute_group, device.id
            ORDER BY 
                minute_group DESC;
        """)
        grouped_data = self.group_by_minute(history_entries)
        return grouped_data

    def get_all_buttons(self):
        """All button devices (device_type_id=2)"""
        return  self.cur.execute("""
            SELECT * FROM device WHERE device_type_id=2;
        """).fetchall()
        

    def insert_sensor_reading(self, sensor_type: str, reading: dict):
        # Rohwerte vom Sensor in die DB schreiben
        self.cur.execute(
            """
            INSERT INTO sensor_readings (
                sensor_type, temperature_c, humidity, pressure_hpa, gas_ohms
            ) VALUES (?, ?, ?, ?, ?);
            """,
            (
                sensor_type,
                reading.get("temperature_c"),
                reading.get("humidity"),
                reading.get("pressure_hpa"),
                reading.get("gas_ohms"),
            ),
        )
        self.connection.commit()

    def get_latest_sensor_reading(self, sensor_type: str = 'bme680'):
        # Letzten Eintrag holen (timestamp + id, damit es stabil ist)
        return self.cur.execute(
            """
            SELECT * FROM sensor_readings
            WHERE sensor_type = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1;
            """,
            (sensor_type,),
        ).fetchone()

    def get_sensor_history(self, sensor_type: str = 'bme680', limit: int = 300):
        # Historie für Diagramme (als Liste, jüngste Einträge zuerst)
        rows = self.cur.execute(
            """
            SELECT 
                strftime('%s', timestamp) AS ts,
                temperature_c, humidity, pressure_hpa, gas_ohms
            FROM sensor_readings
            WHERE sensor_type = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?;
            """,
            (sensor_type, limit),
        ).fetchall()
        return list(reversed(rows))


    def close(self):
        """Close DB connection"""
        if self.connection:
            self.connection.close()
