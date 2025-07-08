#!/usr/bin/env python3
import os
import sys
import dbus
import csv
import logging
import time
import signal
import threading
from datetime import datetime
from collections import deque

# Import victron package for updating dbus (using lib from built in service)
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-modem'))
from vedbus import VeDbusItemImport

# Import GLib for mainloop
try:
    from gi.repository import GLib
    from dbus.mainloop.glib import DBusGMainLoop
except ImportError:
    import gobject as GLib
    from dbus.mainloop.glib import DBusGMainLoop

LOG_FILE_PREFIX = 'dbus_log_'

class DbusLogger:
    def __init__(self, log_dir="/data/VenusOS-DbusLogger/logs", buffer_size=60, min_log_interval=1.0, max_log_interval=60.0):
        self.log_dir = log_dir
        self.buffer_size = buffer_size
        self.min_log_interval = min_log_interval  # Minimum interval to log data, to prevent flooding
        self.max_log_interval = max_log_interval  # Maximum interval to log data, to prevent no logging at all
        self.data_buffer = deque(maxlen=buffer_size * 2)  # Double buffer for safety
        self.running = True
        
        # Set up logger for this instance
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Current sensor data cache with timestamps for change detection
        self.sensor_data = {
            'soc': {'value': None, 'timestamp': 0},
            'current': {'value': None, 'timestamp': 0},
            'voltage': {'value': None, 'timestamp': 0},
            'gps_lat': {'value': None, 'timestamp': 0},
            'gps_lon': {'value': None, 'timestamp': 0},
            'gps_speed': {'value': None, 'timestamp': 0}
        }
        
        # Thread lock for sensor data
        self.data_lock = threading.Lock()
        
        # Performance tracking
        self.last_log_time = 0
        self.data_changed = False
        
        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)
        
        # D-Bus connection and items will be initialized later after main loop setup
        self.dbusConn = None
        self.dbus_items_initialized = False
        
        # Init logging thread
        self.log_thread = threading.Thread(target=self._log_worker)
        self.log_thread.daemon = True
        # self.log_thread.start() # don't start immediately, let the user call start_logging() to control it

    def start_logging(self):
        """Initialize D-Bus connection and start the logging thread"""
        # First initialize D-Bus if not already done
        if not self.dbus_items_initialized:
            try:
                # Connect to the sessionbus. Note that on ccgx we use systembus instead.
                self.dbusConn = dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()
                
                # Initialize D-Bus item imports
                self._setup_dbus_items()
                self.dbus_items_initialized = True
                self.logger.info("D-Bus connection and items initialized successfully")
                
            except Exception as e:
                self.logger.error(f"Error initializing D-Bus: {e}")
        
        # Then start the logging thread
        if not self.log_thread.is_alive():
            self.log_thread.start()
            self.logger.info("Logging thread started")

        
    def _setup_dbus_items(self):
        """Set up VeDbusItemImport objects for all sensors with event callbacks"""
        if not self.dbusConn:
            self.logger.error("D-Bus connection not established")
            return
            
        try:
            # Battery SOC
            self.soc_item = VeDbusItemImport(
                bus=self.dbusConn,
                serviceName="com.victronenergy.battery.ttyUSB1",
                path="/Soc",
                eventCallback=self._on_value_changed('soc'),
                createsignal=True
            )
            
            # Battery voltage
            self.voltage_item = VeDbusItemImport(
                bus=self.dbusConn,
                serviceName="com.victronenergy.battery.ttyUSB1",
                path="/Dc/0/Voltage",
                eventCallback=self._on_value_changed('voltage'),
                createsignal=True
            )
            
            # Battery current
            self.current_item = VeDbusItemImport(
                bus=self.dbusConn,
                serviceName="com.victronenergy.battery.ttyUSB1",
                path="/Dc/0/Current",
                eventCallback=self._on_value_changed('current'),
                createsignal=True
            )
            
            # GPS Position (latitude)
            self.gps_lat_item = VeDbusItemImport(
                bus=self.dbusConn,
                serviceName="com.victronenergy.gps.ve_ttyACM0",
                path="/Position/Latitude",
                eventCallback=self._on_value_changed('gps_lat'),
                createsignal=True
            )
            
            # GPS Position (longitude)
            self.gps_lon_item = VeDbusItemImport(
                bus=self.dbusConn,
                serviceName="com.victronenergy.gps.ve_ttyACM0",
                path="/Position/Longitude",
                eventCallback=self._on_value_changed('gps_lon'),
                createsignal=True
            )
            
            # GPS Speed
            self.gps_speed_item = VeDbusItemImport(
                bus=self.dbusConn,
                serviceName="com.victronenergy.gps.ve_ttyACM0",
                path="/Speed",
                eventCallback=self._on_value_changed('gps_speed'),
                createsignal=True
            )
            
            # Read initial values for all sensors
            self._read_initial_values()
            
        except Exception as e:
            self.logger.error(f"Error setting up D-Bus items: {e}")
    
    def _read_initial_values(self):
        """Read initial values from all D-Bus items"""
        current_time = time.time()
        dbus_items = [
            ('soc', self.soc_item),
            ('voltage', self.voltage_item),
            ('current', self.current_item),
            ('gps_lat', self.gps_lat_item),
            ('gps_lon', self.gps_lon_item),
            ('gps_speed', self.gps_speed_item)
        ]
        
        for sensor_key, dbus_item in dbus_items:
            try:
                if dbus_item is not None:
                    initial_value = dbus_item.get_value()
                    if initial_value is not None:
                        with self.data_lock:
                            self.sensor_data[sensor_key] = {'value': initial_value, 'timestamp': current_time}
                            self.data_changed = True
                        self.logger.debug(f"Read initial value for {sensor_key}: {initial_value}")
                    else:
                        self.logger.debug(f"No initial value available for {sensor_key}")
            except Exception as e:
                self.logger.warning(f"Could not read initial value for {sensor_key}: {e}")

    def _on_value_changed(self, sensor_key):
        """Generic callback factory for sensor value changes"""
        def callback(serviceName, objectPath, changes):
            logging.debug(f"Value changed for {sensor_key}: {changes}")
            value = changes.get('Value')
            if value is not None:
                current_time = time.time()
                with self.data_lock:
                    self.sensor_data[sensor_key] = {'value': value, 'timestamp': current_time}
                    self.data_changed = True
        return callback
    
    def get_sensor_data(self):
        """Get current sensor values from cache - optimized for speed"""
        if not self.dbus_items_initialized:
            # Return empty data if D-Bus not initialized yet
            return {
                'timestamp': datetime.now().isoformat(),
                'soc': None,
                'current': None,
                'voltage': None,
                'gps_lat': None,
                'gps_lon': None,
                'gps_speed': None
            }
            
        with self.data_lock:
            # Use dictionary comprehension for better performance
            data = {
                'timestamp': datetime.now().isoformat(),
                'soc': float(self.sensor_data['soc']['value']) if self.sensor_data['soc']['value'] is not None else None,
                'current': float(self.sensor_data['current']['value']) if self.sensor_data['current']['value'] is not None else None,
                'voltage': float(self.sensor_data['voltage']['value']) if self.sensor_data['voltage']['value'] is not None else None,
                'gps_lat': float(self.sensor_data['gps_lat']['value']) if self.sensor_data['gps_lat']['value'] is not None else None,
                'gps_lon': float(self.sensor_data['gps_lon']['value']) if self.sensor_data['gps_lon']['value'] is not None else None,
                'gps_speed': float(self.sensor_data['gps_speed']['value']) if self.sensor_data['gps_speed']['value'] is not None else None
            }
        return data
    
    def _log_worker(self):
        """Worker thread that logs data - optimized for performance"""
        while self.running:
            current_time = time.time()
            
            # Only log if data has changed or the maximum interval has passed
            if self.data_changed or (current_time - self.last_log_time) >= self.max_log_interval:
                log_entry = self.get_sensor_data()
                
                # Add to buffer
                self.data_buffer.append(log_entry)
                
                # Write buffer to disk when full or every max_log_interval seconds
                if (len(self.data_buffer) >= self.buffer_size or 
                    (current_time - self.last_log_time) >= self.max_log_interval):
                    self._write_buffer_to_disk()
                
                with self.data_lock:
                    self.data_changed = False
                self.last_log_time = current_time
            
            # Sleep for the configured minimum interval to prevent flooding
            time.sleep(self.min_log_interval)
    
    def _write_buffer_to_disk(self):
        """Write buffered data to CSV file - optimized for performance"""
        if not self.data_buffer:
            return
        
        buffer_size = len(self.data_buffer)
        
        # Generate filename based on current date
        filename = f"{LOG_FILE_PREFIX}{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = os.path.join(self.log_dir, filename)
        
        # Check if file exists to write headers
        file_exists = os.path.exists(filepath)
        
        try:
            # Use larger buffer size for file I/O
            with open(filepath, 'a', newline='', buffering=8192) as csvfile:
                fieldnames = ['timestamp', 'soc', 'current', 'voltage', 
                            'gps_lat', 'gps_lon', 'gps_speed']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                
                # Write all buffered data in one go
                writer.writerows(self.data_buffer)
                
                # Force flush to disk
                csvfile.flush()
                os.fsync(csvfile.fileno())
            
            # Clear buffer after successful write
            self.data_buffer.clear()
            self.logger.debug(f"Logged {buffer_size} entries to {filename}")
            
        except Exception as e:
            self.logger.error(f"Error writing to log file: {e}")
            # Don't clear buffer on error - try again next time
    
    def _cleanup_old_logs(self, days_to_keep=30):
        """Clean up old log files to save disk space"""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
            for filename in os.listdir(self.log_dir):
                if filename.startswith(LOG_FILE_PREFIX) and filename.endswith('.csv'):
                    filepath = os.path.join(self.log_dir, filename)
                    if os.path.getmtime(filepath) < cutoff_time:
                        os.remove(filepath)
                        self.logger.info(f"Removed old log file: {filename}")
        except Exception as e:
            self.logger.error(f"Error cleaning up old logs: {e}")
    
    def stop(self):
        """Stop the logger and flush remaining data"""
        self.running = False
        
        # Final cleanup and flush
        self._write_buffer_to_disk()
        self._cleanup_old_logs()
        
        if self.log_thread.is_alive():
            self.log_thread.join(timeout=5)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger = logging.getLogger('DbusLogger')
    logger.info("Shutting down logger...")
    global dbusLogger
    if 'dbusLogger' in globals():
        dbusLogger.stop()
    sys.exit(0)

if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s")

    dbusLogger = DbusLogger(
        buffer_size=10,  # Maximum number of entries to buffer before writing to disk
        min_log_interval=1.0,  # Minimum interval to log data, to prevent flooding
        max_log_interval=60.0  # Maximum interval to log data, to prevent no logging at all
    )
    
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)
    mainloop = GLib.MainLoop()

    # Initialize D-Bus and start logging
    dbusLogger.start_logging()

    logging.info('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')
    mainloop.run()
    
    logging.info("Mainloop stopped, cleaning up...")
    dbusLogger.stop()
