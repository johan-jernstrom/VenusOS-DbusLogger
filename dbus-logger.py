#!/usr/bin/env python3
"""
Venus OS D-Bus Logger
This script is designed to run on Venus OS systems, such as those used in Victron Energy products.
This service periodically logs D-Bus values from Venus OS system to CSV files.
It uses the built-in DbusMonitor class for automatic service discovery and robust monitoring.

"""

import os
import sys
import csv
import logging
import time
import signal
import threading
from datetime import datetime
from collections import deque

# Import victron packages, use locally downloaded copy of latest version of DbusMonitor that supports ignoreServices: https://github.com/victronenergy/velib_python/blob/master/dbusmonitor.py
from velib_python.dbusmonitor import DbusMonitor

# Import GLib for mainloop
try:
    from gi.repository import GLib
    from dbus.mainloop.glib import DBusGMainLoop
except ImportError:
    try:
        import gobject as GLib
        from dbus.mainloop.glib import DBusGMainLoop
    except ImportError:
        # Fallback for older systems
        import gobject as GLib
        from dbus.mainloop.glib import DBusGMainLoop as DBusGMainLoop

LOG_FILE_PREFIX = 'dbus_log_'

class DbusLogger:
    def __init__(self, log_dir="/data/VenusOS-DbusLogger/logs", buffer_size=60, min_log_interval=1.0, max_log_interval=60.0, log_level=logging.INFO):
        # Validate intervals
        if min_log_interval <= 0.1:
            raise ValueError("min_log_interval must be greater than 0.1")
        if max_log_interval <= min_log_interval:
            raise ValueError("max_log_interval must be greater than min_log_interval")
        if max_log_interval > 600:  # 10 minutes
            raise ValueError("max_log_interval should not exceed 600 seconds (10 minutes)")
        
        self.log_dir = log_dir
        self.buffer_size = buffer_size
        self.min_log_interval = min_log_interval  # Minimum interval to log data, to prevent flooding
        self.max_log_interval = max_log_interval  # Maximum interval to log data, to prevent no logging at all
        self.data_buffer = deque(maxlen=buffer_size * 2)  # Double buffer for safety
        self.running = True
        
        # Set up logger for this instance with specified log level
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(log_level)
        
        # Define what services and paths to monitor using DbusMonitor format
        # The structure is: {'service_class': {'/path': {'code': None, 'whenToLog': 'always'}}}
        self.monitor_list = {
            'com.victronenergy.battery': {
                '/Soc': {'code': 'soc', 'whenToLog': 'always'},
                '/Dc/0/Voltage': {'code': 'voltage', 'whenToLog': 'always'},
                '/Dc/0/Current': {'code': 'current', 'whenToLog': 'always'}
            },
            'com.victronenergy.gps': {
                '/Position/Latitude': {'code': 'gps_lat', 'whenToLog': 'always'},
                '/Position/Longitude': {'code': 'gps_lon', 'whenToLog': 'always'},
                '/Speed': {'code': 'gps_speed', 'whenToLog': 'always'}
            }
        }
        
        # Ignore the following service since we only want to monitor the 48v battery service connected to ttyUSB1
        self.ignored_services = ['com.victronenergy.battery.ttyUSB0']

        # Cache for sensor data
        self.sensor_data = {}
        
        # Thread lock for sensor data
        self.data_lock = threading.Lock()
        
        # Performance tracking
        self.last_log_time = 0
        self.data_changed = False
        
        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)
        
        # D-Bus monitor will be initialized later
        self.dbusMonitor = None
        
        # Init logging thread
        self.log_thread = threading.Thread(target=self._log_worker)
        self.log_thread.daemon = True

    def start_logging(self):
        """Initialize D-Bus monitor and start the logging thread"""
        try:
            # Initialize DbusMonitor with our monitor list and callbacks
            self.dbusMonitor = DbusMonitor(
                dbusTree=self.monitor_list,
                valueChangedCallback=self._on_value_changed,
                deviceAddedCallback=self._on_device_added,
                deviceRemovedCallback=self._on_device_removed,
                namespace="com.victronenergy", 
                ignoreServices=self.ignored_services
            )
            
            self.logger.info("DbusMonitor initialized successfully for services: " + ', '.join(self.monitor_list.keys()))
            
            # Initialize sensor data cache with current values
            self._initialize_sensor_cache()
            
        except Exception as e:
            self.logger.error(f"Error initializing DbusMonitor: {e}")
            raise
        
        # Start the logging thread
        if not self.log_thread.is_alive():
            try:
                # Create new thread if the old one has stopped
                if not self.log_thread.is_alive() and self.log_thread.ident is not None:
                    self.log_thread = threading.Thread(target=self._log_worker)
                    self.log_thread.daemon = True
                    
                self.log_thread.start()
                self.logger.info("Logging thread started")
            except Exception as e:
                self.logger.error(f"Error starting logging thread: {e}")
                raise

    def _initialize_sensor_cache(self):
        """Initialize sensor data cache with current values from DbusMonitor"""
        if not self.dbusMonitor:
            self.logger.error("DbusMonitor is not initialized, cannot initialize sensor cache")
            return
            
        with self.data_lock:
            current_time = time.time()
            
            # Initialize all expected sensor keys
            for service_class, paths in self.monitor_list.items():
                for path, config in paths.items():
                    sensor_key = config['code']
                    
                    # Try to get current value from any matching service
                    value = None
                    for service_name in self.dbusMonitor.get_service_list(service_class):
                        value = self.dbusMonitor.get_value(service_name, path)
                        if value is not None:
                            break
                    
                    self.sensor_data[sensor_key] = {
                        'value': value,
                        'timestamp': current_time
                    }

                    self.logger.debug(f"Initialized sensor {sensor_key} with value: {value} at {datetime.fromtimestamp(current_time).isoformat()}")
            
            self.data_changed = True
            self.logger.debug(f"Initialized sensor cache with {len(self.sensor_data)} sensors: {list(self.sensor_data.keys())}")


    def _on_device_added(self, service_name, device_instance):
        """Callback when a new device is added to the bus"""
        try:
            self.logger.info(f"Device added: {service_name} (instance: {device_instance})")
            # Update our cache with values from the new device
            self._update_cache_from_service(service_name)
        except Exception as e:
            self.logger.error(f"Error in _on_device_added callback: {e}")

    def _on_device_removed(self, service_name, device_instance):
        """Callback when a device is removed from the bus"""
        try:
            self.logger.info(f"Device removed: {service_name} (instance: {device_instance})")
        except Exception as e:
            self.logger.error(f"Error in _on_device_removed callback: {e}")

    def _update_cache_from_service(self, service_name):
        """Update cache with values from a specific service"""
        if not self.dbusMonitor:
            return
            
        try:
            service_parts = service_name.split('.')
            if len(service_parts) >= 3:
                service_class = '.'.join(service_parts[0:3])
            else:
                service_class = service_name
            
            paths = self.monitor_list.get(service_class, {})
            
            with self.data_lock:
                current_time = time.time()
                for path, config in paths.items():
                    sensor_key = config['code']
                    value = self.dbusMonitor.get_value(service_name, path)
                    
                    if value is not None:
                        self.sensor_data[sensor_key] = {
                            'value': value,
                            'timestamp': current_time
                        }
                        self.data_changed = True
        except Exception as e:
            self.logger.error(f"Error updating cache from service {service_name}: {e}")

    def _on_value_changed(self, service_name, path, options, changes, device_instance):
        """Callback when a monitored value changes"""
        try:
            if 'Value' not in changes:
                return
                
            sensor_key = options.get('code')
            if not sensor_key:
                return
                
            value = changes['Value']
            current_time = time.time()
            
            with self.data_lock:
                self.sensor_data[sensor_key] = {
                    'value': value,
                    'timestamp': current_time
                }
                self.data_changed = True
                
            self.logger.debug(f"Value changed for {sensor_key}: {value}")
        except Exception as e:
            self.logger.error(f"Error in _on_value_changed callback: {e}")
    
    def get_sensor_data(self):
        """Get current sensor values from cache"""
        with self.data_lock:
            # Create data dictionary with current values
            data = {}
            for sensor_key, sensor_info in self.sensor_data.items():
                value = sensor_info.get('value')
                data[sensor_key] = value if value is not None else float('nan')
            
            # Add timestamp for current reading
            data['timestamp'] = datetime.now().isoformat()
            
            # Ensure all expected sensors are present
            expected_sensors = set()
            for service_class, paths in self.monitor_list.items():
                for path, config in paths.items():
                    expected_sensors.add(config['code'])
            
            for sensor_key in expected_sensors:
                if sensor_key not in data:
                    data[sensor_key] = float('nan')
                    
        return data
    
    def _log_worker(self):
        """Worker thread that logs data """
        while self.running:
            current_time = time.time()

            with self.data_lock:
                data_changed = self.data_changed
            
            # Only log if data has changed or the maximum interval has passed
            if data_changed or (current_time - self.last_log_time) >= self.max_log_interval:
                log_entry = self.get_sensor_data()
                
                # Add to buffer
                self.data_buffer.append(log_entry)
                
                self.logger.debug(f"Buffered data: {log_entry}")

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
        """Write buffered data to CSV file"""
        if not self.data_buffer:
            self.logger.debug("Data buffer is empty, nothing to write")
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
                # Determine fieldnames from monitor list
                fieldnames = ['timestamp']
                for service_class, paths in self.monitor_list.items():
                    for path, config in paths.items():
                        fieldnames.append(config['code'])
                
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
            # Prevent infinite buffer growth - clear buffer if it gets too large
            if len(self.data_buffer) > self.buffer_size * 5:  # 5x normal buffer size
                self.logger.warning(f"Buffer overflow detected, clearing {len(self.data_buffer)} entries")
                self.data_buffer.clear()
    
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
        
        # Fix: Wait for worker thread to finish current processing
        if self.log_thread.is_alive():
            self.log_thread.join(timeout=5)
        
        # Final cleanup and flush
        self._write_buffer_to_disk()
        self._cleanup_old_logs()

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger = logging.getLogger('DbusLogger')
    logger.info("Shutting down logger...")
    global dbusLogger
    if 'dbusLogger' in globals():
        dbusLogger.stop()
    sys.exit(0)

if __name__ == "__main__":
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='D-Bus Logger for VenusOS')
    parser.add_argument('--log-level', type=str, default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the logging level (default: INFO)')
    parser.add_argument('--buffer-size', type=int, default=30,
                        help='Maximum number of entries to buffer before writing to disk (default: 30)')
    parser.add_argument('--min-log-interval', type=float, default=1.0,
                        help='Minimum interval to log data, to prevent flooding (default: 1.0)')
    parser.add_argument('--max-log-interval', type=float, default=60.0,
                        help='Maximum interval to log data, to prevent no logging at all (default: 60.0)')
    
    args = parser.parse_args()
    
    # Convert log level string to logging constant
    log_level = getattr(logging, args.log_level.upper())
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logging.basicConfig(level=log_level, format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s")

    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)
    mainloop = GLib.MainLoop()
    
    dbusLogger = DbusLogger(
        buffer_size=args.buffer_size,
        min_log_interval=args.min_log_interval,
        max_log_interval=args.max_log_interval,
        log_level=log_level
    )
    
    
    # Initialize D-Bus and start logging
    dbusLogger.start_logging()

    logging.info('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')
    mainloop.run()
    
    logging.info("Mainloop stopped, cleaning up...")
    dbusLogger.stop()
