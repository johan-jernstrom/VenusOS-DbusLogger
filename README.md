# VenusOS D-Bus Logger

A Python-based data logger for Victron Energy VenusOS systems that captures and logs sensor data from various systems including battery monitoring, GPS, and power consumption metrics.

## Purpose

This logger is designed to collect comprehensive data from VenusOS D-Bus services to enable advanced analysis and monitoring capabilities. The primary goals include:

### Current Functionality
- **Real-time Data Logging**: Captures battery state of charge (SOC), voltage, current, and GPS position data
- **Event-driven Architecture**: Uses D-Bus callbacks to efficiently log data only when values change
- **Smart Buffering**: Implements configurable buffering to optimize disk I/O and prevent data loss
- **Automatic Log Rotation**: Creates daily log files with automatic cleanup of old files
- **Robust Error Handling**: Gracefully handles D-Bus connection issues and sensor unavailability

### Future Development Goals

#### 1. Engine Efficiency Analysis
The logged data will be enhanced to calculate **engine efficiency in watts per knot** at different speeds:
- **Power Consumption Tracking**: Monitor total system power draw and engine output
- **Speed Correlation**: Cross-reference GPS speed data with power consumption
- **Efficiency Curves**: Generate performance charts showing optimal operating speeds
- **Battery Consumption Modeling**: Estimate energy efficiency based on power output curves
- **Weather Impact Analysis**: Factor in wind and sea conditions for accurate efficiency calculations

#### 2. Automatic Logbook
Transform the logger into a comprehensive automatic maritime logbook:
- **Journey Tracking**: Automatic start/stop detection based on movement and engine state
- **Route Recording**: GPS track logging with waypoint detection
- **Time at Sea**: Accurate engine hours and sailing time tracking
- **Weather Integration**: Log weather conditions, wind speed, and sea state
- **Track Engine usage**: Track engine hours

## Technical Features

### Data Sources
Currently logging from these D-Bus services:
- `com.victronenergy.battery.ttyUSB1` - Battery SOC, voltage and current
- `com.victronenergy.gps.ve_ttyACM0` - GPS position and speed

### Configuration Options
- **Buffer Size**: Configurable number of entries to buffer before writing to disk
- **Log Intervals**: Minimum and maximum intervals for data logging
- **Log Directory**: Customizable storage location for log files
- **Log Retention**: Automatic cleanup of files older than specified days

### Data Format
Logs are stored in CSV format with the following fields:
```csv
timestamp,soc,current,voltage,gps_lat,gps_lon,gps_speed
```

## Installation and Usage

### Prerequisites
- VenusOS system (Victron Energy GX device)
- Tested on Raspberry Pi 3b
- Python 3.x with the following dependencies:
  - `dbus-python`
  - `gi` (GObject Introspection)
  - Standard Python libraries: `csv`, `logging`, `threading`, `datetime`

### Setup
1. Copy folder contents to your VenusOS device, eg /data/VenusOS-DbusLogger
2. Run the script:
```bash
bash install.sh
```

### Configuration
Edit the main section of the script to adjust:
```python
dbusLogger = DbusLogger(
    buffer_size=10,              # Buffer size before disk write
    min_log_interval=1.0,        # Minimum seconds between logs
    max_log_interval=60.0        # Maximum seconds between logs
)
```

## Log File Example
```csv
timestamp,soc,current,voltage,gps_lat,gps_lon,gps_speed
2025-07-08T16:14:41.920676,100.0,0.0,55.65,60.1638,22.0598,
2025-07-08T16:17:09.124781,100.0,0.0,55.63,60.1638,22.0598,
```

## License
[Add your chosen license here]
