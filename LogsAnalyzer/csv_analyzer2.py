#!/usr/bin/env python3
"""
Sailboat Engine Efficiency Analyzer for VenusOS DbusLogger
Parses CSV files containing GPS and electrical data to calculate:
- Total dista        print("Engine data breakdown:")
        print(f"  Moving periods (>=0.5 knots): {len(moving_data)} data points")
        print(f"  Idle periods (<0.5 knots): {len(idle_data)} data points") traveled (in nautical miles)
- Engine efficiency (watts per knot)
- Generates efficiency plots with sailboat-specific filtering

Sailboat-specific filtering:
- Removes speeds over 8 knots (sailboat maximum realistic speed)
- Filters out positive currents (battery charging when docked)
- Converts negative currents to positive consumption values
- Removes power readings over 11kW (engine maximum)
- Distance measured in nautical miles

CSV Format Expected:
timestamp,soc,voltage,current,gps_lat,gps_lon,gps_speed

Where current is negative for engine consumption, positive for battery charging.
"""

import logging
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from geopy.distance import geodesic
from datetime import datetime
import glob
from typing import List, Tuple, Dict

# Constants
ENGINE_POWER_MAX = 11000  # Maximum engine power in watts (11kW)
ENGINE_IDLE_CURRENT = -0.5  # Current threshold for engine consumption (in Amperes), 0.4 is a common idle current
MAX_TIME_GAP = pd.Timedelta(seconds=61)  # Maximum time gap between data points to consider them consecutive
SPEED_MAX = 12.0  # Maximum speed in knots (sailboat realistic)
VOLTAGE_MIN = 45  # Minimum voltage for valid readings
VOLTAGE_MAX = 70  # Maximum voltage for valid readings
CURRENT_MIN = -300  # Minimum current for valid readings
CURRENT_MAX = 300  # Maximum current for valid readings

class CSVAnalyzer:
    def __init__(self, log_folder: str):
        """
        Initialize the CSV analyzer with a folder path containing CSV files.
        
        Args:
            log_folder (str): Path to folder containing CSV files
        """
        self.logger = logging.getLogger(__name__)
        self.log_folder = log_folder
        self.data = pd.DataFrame()
        
    def load_csv_files(self) -> None:
        """Load and combine all CSV files from the specified folder."""
        csv_files = glob.glob(os.path.join(self.log_folder, "*.csv"))
        
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in {self.log_folder}")

        self.logger.info(f"Found {len(csv_files)} CSV files")

        dataframes = []
        for file in csv_files:
            try:
                df = pd.read_csv(file)
                # Ensure required columns exist
                required_columns = ['timestamp', 'soc', 'voltage', 'current', 
                                  'gps_lat', 'gps_lon', 'gps_speed']
                
                if not all(col in df.columns for col in required_columns):
                    self.logger.warning(f"{file} missing required columns, skipping...")
                    continue
                
                df['source_file'] = os.path.basename(file)
                dataframes.append(df)
                self.logger.info(f"Loaded {len(df)} rows from {os.path.basename(file)}")
                
            except Exception as e:
                self.logger.error(f"Error loading {file}: {e}")

        if not dataframes:
            raise ValueError("No valid CSV files could be loaded")
        
        self.data = pd.concat(dataframes, ignore_index=True)
        self.logger.info(f"Total rows loaded: {len(self.data)}")
        
    def preprocess_data(self) -> None:
        """Clean and preprocess the loaded data."""
        self.logger.info("Preprocessing data...")

        # Convert timestamp to datetime with flexible parsing
        try:
            self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])
        except Exception as e:
            self.logger.warning(f"Timestamp parsing issue, using mixed format: {e}")
            self.data['timestamp'] = pd.to_datetime(self.data['timestamp'], format='mixed')

        # Sort by timestamp
        self.data = self.data.sort_values('timestamp').reset_index(drop=True)

        self.logger.info(f"Final preprocessed data: {len(self.data)} rows")

    def calculate_distances(self) -> None:
        """Calculate distances between consecutive GPS points in nautical miles."""
        self.logger.info("Calculating distances...")

        distance_nm = 0
        prev_lat, prev_lon = None, None
        
        for i in range(len(self.data)):
            # skip if GPS coordinates are missing or 0.0
            if pd.isna(self.data.iloc[i]['gps_lat']) or pd.isna(self.data.iloc[i]['gps_lon']) or \
               self.data.iloc[i]['gps_lat'] == 0.0 or self.data.iloc[i]['gps_lon'] == 0.0:
                continue

            # skip if previous point is None
            if prev_lat is None or prev_lon is None:
                prev_lat = self.data.iloc[i]['gps_lat']
                prev_lon = self.data.iloc[i]['gps_lon']
                continue

            # Get consecutive GPS coordinates
            lat1, lon1 = prev_lat, prev_lon
            lat2, lon2 = self.data.iloc[i]['gps_lat'], self.data.iloc[i]['gps_lon']
            
            # Calculate distance using geodesic (great circle) distance in kilometers
            distance_nm = geodesic((lat1, lon1), (lat2, lon2)).nm
            prev_lat, prev_lon = lat2, lon2

            # skip if distance is zero
            if distance_nm == 0:
                continue

            #skip if distance is negative
            if distance_nm < 0:
                self.logger.warning(f"Skipping row {i} due to negative distance: {distance_nm:.2f} nm")
                continue
                
            # Warn if unusually large distance
            if distance_nm > 0.01:  # 0.01 nm is about 18.5 meters
                self.logger.warning(f"Skipping row {i} due to unrealistic distance: {distance_nm:.2f} nm")
                continue

            # Store instant distance and cumulative distance
            self.data.at[i, 'distance_nm'] = distance_nm
            self.data.at[i, 'cumulative_distance_nm'] = self.data['distance_nm'].cumsum().iloc[i]
            
        self.total_distance_nm = self.data['cumulative_distance_nm'].max()
        self.logger.info(f"Distance calculation complete: {self.total_distance_nm:.2f} nautical miles")

    def calculate_speed_in_knots(self) -> None:
        """Calculate speeds based on GPS data."""
        self.logger.info("Calculating speeds...")

        for i in range(len(self.data)):
            # skip if gps speed is missing or less than or equal to 0.0
            if pd.isna(self.data.iloc[i]['gps_speed']) or self.data.iloc[i]['gps_speed'] <= 0.0:
                continue
            # Calculate speed in knots
            speed_knots = self.data.iloc[i]['gps_speed'] * 1.94384

            # skip if speed is greater than maximum speed
            if speed_knots > SPEED_MAX:
                self.logger.warning(f"Skipping row {i} due to unrealistic speed: {speed_knots:.2f} knots")
                continue
            self.data.at[i, 'speed_knots'] = speed_knots

    def calculate_engine_metrics(self) -> None:
        """Calculate engine metrics based on current consumption."""
        self.logger.info("Calculating engine metrics...")

        # Initialize columns to avoid KeyError
        self.data['engine_watts'] = 0.0
        self.data['engine_current'] = 0.0
        self.data['engine_idling'] = 0
        self.data['engine_seconds'] = 0.0
        self.data['engine_hours'] = 0.0
        self.data['engine_idling_seconds'] = 0.0
        self.data['engine_idling_hours'] = 0.0
        
        total_engine_seconds = 0.0
        total_idling_seconds = 0.0
        prev_timestamp = None
        prev_engine_on = False
        prev_idling = False
        
        for i in range(len(self.data)):
            current = self.data.iloc[i]['current']
            voltage = self.data.iloc[i]['voltage']
            timestamp = self.data.iloc[i]['timestamp']

            # Skip if voltage or current is NaN or out of bounds
            if pd.isna(current) or pd.isna(voltage) or \
               current < CURRENT_MIN or current > CURRENT_MAX or \
               voltage < VOLTAGE_MIN or voltage > VOLTAGE_MAX:
                # Still update cumulative times for this row
                self.data.at[i, 'engine_seconds'] = total_engine_seconds
                self.data.at[i, 'engine_hours'] = total_engine_seconds / 3600.0
                self.data.at[i, 'engine_idling_seconds'] = total_idling_seconds
                self.data.at[i, 'engine_idling_hours'] = total_idling_seconds / 3600.0
                prev_timestamp = timestamp
                prev_engine_on = False
                prev_idling = False
                continue

            # Determine if engine is currently running
            engine_on = current < 0
            
            # Set current row values if engine is on
            if engine_on:
                # Calculate power (Watts) = Voltage (Volts) * Current (Amps)
                power = abs(voltage * current)

                # Skip if power exceeds maximum engine power
                if power > ENGINE_POWER_MAX:
                    self.logger.warning(f"Skipping row {i} due to excessive power: {power:.2f}W")
                    # Still update cumulative times
                    self.data.at[i, 'engine_seconds'] = total_engine_seconds
                    self.data.at[i, 'engine_hours'] = total_engine_seconds / 3600.0
                    self.data.at[i, 'engine_idling_seconds'] = total_idling_seconds
                    self.data.at[i, 'engine_idling_hours'] = total_idling_seconds / 3600.0
                    continue

                self.data.at[i, 'engine_watts'] = power
                self.data.at[i, 'engine_current'] = -current
                
                # Determine if idling (current closer to 0 means idling)
                is_idling = current >= ENGINE_IDLE_CURRENT
                self.data.at[i, 'engine_idling'] = 1 if is_idling else 0
                
                # Calculate engine efficiency (watts per knot) if above idle current and speed available
                if not is_idling and 'speed_knots' in self.data.columns and \
                   not pd.isna(self.data.iloc[i]['speed_knots']) and self.data.iloc[i]['speed_knots'] > 0:
                    efficiency = power / self.data.iloc[i]['speed_knots']
                    self.data.at[i, 'engine_efficiency'] = efficiency
                
                # Calculate time difference and accumulate if previous readings show engine on
                if prev_timestamp is not None and prev_engine_on:
                    time_diff = (timestamp - prev_timestamp).total_seconds()
                    
                    # Only add time if within reasonable gap (avoid inflating hours from data gaps)
                    if 0 < time_diff <= MAX_TIME_GAP.total_seconds():
                        total_engine_seconds += time_diff
                        
                        # Add to idling time if both previous and current readings were idling
                        if prev_idling and is_idling:
                            total_idling_seconds += time_diff
                    elif time_diff > MAX_TIME_GAP.total_seconds():
                        self.logger.warning(f"Large time gap detected: {time_diff:.0f} seconds, not adding to engine hours")

                # Update for next iteration
                prev_idling = is_idling
            else:
                # Engine is off
                prev_idling = False

            # Store cumulative times for this row
            self.data.at[i, 'engine_seconds'] = total_engine_seconds
            self.data.at[i, 'engine_hours'] = total_engine_seconds / 3600.0
            self.data.at[i, 'engine_idling_seconds'] = total_idling_seconds
            self.data.at[i, 'engine_idling_hours'] = total_idling_seconds / 3600.0

            # Update for next iteration
            prev_timestamp = timestamp
            prev_engine_on = engine_on

        max_engine_hours = self.data['engine_hours'].max()
        max_idling_hours = self.data['engine_idling_hours'].max()
        self.logger.info(f"Engine metrics calculated: {max_engine_hours:.1f} hours total, "
                        f"of which {max_idling_hours:.1f} hours were idling")

    def save_output(self) -> None:
        """Save processed data to a CSV file in the log folder."""
        # save processed data to a CSV in a subfolder to the log folder
        if not os.path.exists(os.path.join(self.log_folder, "processed_data")):
            os.makedirs(os.path.join(self.log_folder, "processed_data"))
        output_path = os.path.join(self.log_folder, "processed_data", "processed_data.csv")
        self.data.to_csv(output_path, index=False)
        self.logger.info(f"Processed data saved to {output_path}")

def main():
    
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Analyzes logs from D-Bus Logger for VenusOS')
    parser.add_argument('--log-folder', type=str, default='./logs', 
                        help='Path to folder containing CSV files to analyze')
    parser.add_argument('--log-level', type=str, default='INFO', 
                        help='Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')

    args = parser.parse_args()
    log_folder = args.log_folder
    log_level = args.log_level
    logging.basicConfig(level=log_level.upper(), format='%(asctime)s - %(levelname)s - %(message)s')

    print(f"Analyzing CSV files in folder: {log_folder}")
    
    if not os.path.exists(log_folder):
        print(f"Error: Folder '{log_folder}' does not exist")
        return
    
    try:
        # Create analyzer instance
        analyzer = CSVAnalyzer(log_folder)
        
        # Run analysis
        analyzer.load_csv_files()
        analyzer.preprocess_data()
        analyzer.calculate_distances()
        analyzer.calculate_speed_in_knots()
        analyzer.calculate_engine_metrics()
        # analyzer.plot_efficiency()
        # analyzer.generate_summary_report()
        analyzer.save_output()
        
        print("\nAnalysis completed successfully!")
        
    except Exception as e:
        print(f"Error during analysis: {e}")
        return


if __name__ == "__main__":
    main()
