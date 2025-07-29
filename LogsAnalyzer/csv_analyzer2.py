#!/usr/bin/env python3
"""
Sailboat Engine Efficiency Analyzer for VenusOS DbusLogger
Parses CSV files containing GPS and electrical data to calculate:
- Total distance traveled (in nautical miles)
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
BATTERY_CAPACITY = 300.0  # Battery capacity in Ampere-hours (Ah), adjust as needed

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
        
    def _validate_data_bounds(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and clean data within acceptable bounds."""
        # Create boolean masks for valid data
        valid_voltage = (df['voltage'] >= VOLTAGE_MIN) & (df['voltage'] <= VOLTAGE_MAX)
        valid_current = (df['current'] >= CURRENT_MIN) & (df['current'] <= CURRENT_MAX)
        valid_gps = (df['gps_lat'] != 0.0) & (df['gps_lon'] != 0.0) & \
                   (~pd.isna(df['gps_lat'])) & (~pd.isna(df['gps_lon']))
        
        # Log invalid data counts
        invalid_voltage_count = (~valid_voltage).sum()
        invalid_current_count = (~valid_current).sum()
        invalid_gps_count = (~valid_gps).sum()
        
        if invalid_voltage_count > 0:
            self.logger.warning(f"Found {invalid_voltage_count} rows with invalid voltage readings")
        if invalid_current_count > 0:
            self.logger.warning(f"Found {invalid_current_count} rows with invalid current readings")
        if invalid_gps_count > 0:
            self.logger.warning(f"Found {invalid_gps_count} rows with invalid GPS coordinates")
            
        return df, valid_voltage, valid_current, valid_gps

    def load_csv_files(self) -> None:
        """Load and combine all CSV files from the specified folder."""
        csv_files = glob.glob(os.path.join(self.log_folder, "*.csv"))
        
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in {self.log_folder}")

        self.logger.info(f"Found {len(csv_files)} CSV files")

        dataframes = []
        for file in csv_files:
            try:
                # Use efficient data types to reduce memory usage
                dtype_dict = {
                    'soc': 'float32',
                    'voltage': 'float32', 
                    'current': 'float32',
                    'gps_lat': 'float64',  # Keep high precision for GPS
                    'gps_lon': 'float64',
                    'gps_speed': 'float32'
                }
                
                df = pd.read_csv(file, dtype=dtype_dict)
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

        # Initialize calculated columns with appropriate data types
        self.data['distance_nm'] = pd.Series(0.0, dtype='float32')
        self.data['cumulative_distance_nm'] = pd.Series(0.0, dtype='float32')
        self.data['speed_knots'] = pd.Series(np.nan, dtype='float32')

        # Validate data bounds
        self.data, self.valid_voltage, self.valid_current, self.valid_gps = self._validate_data_bounds(self.data)

        self.logger.info(f"Final preprocessed data: {len(self.data)} rows")

    def calculate_distances(self) -> None:
        """Calculate distances between consecutive GPS points in nautical miles using vectorized operations."""
        self.logger.info("Calculating distances...")
        
        # Create boolean mask for valid GPS data
        valid_coords = self.valid_gps
        
        if valid_coords.sum() < 2:
            self.logger.warning("Insufficient valid GPS coordinates for distance calculation")
            return
            
        # Get arrays of valid coordinates
        valid_data = self.data[valid_coords].copy()
        
        # Calculate distances using vectorized operations where possible
        lat1 = valid_data['gps_lat'].shift(1)
        lon1 = valid_data['gps_lon'].shift(1)
        lat2 = valid_data['gps_lat']
        lon2 = valid_data['gps_lon']
        
        # Remove first row (no previous point)
        mask = ~pd.isna(lat1)
        
        distances = []
        cumulative_distance = 0.0
        
        # Use tqdm for progress tracking on large datasets
        if len(valid_data) > 10000:
            try:
                from tqdm import tqdm
                iterator = tqdm(range(len(valid_data)), desc="Calculating distances")
            except ImportError:
                iterator = range(len(valid_data))
        else:
            iterator = range(len(valid_data))
            
        for i in iterator:
            if i == 0 or pd.isna(lat1.iloc[i]):
                distances.append(0.0)
                continue
                
            distance_nm = geodesic(
                (lat1.iloc[i], lon1.iloc[i]), 
                (lat2.iloc[i], lon2.iloc[i])
            ).nm
            
            # Apply distance validation
            if distance_nm < 0 or distance_nm > 0.1:
                distance_nm = 0.0
                
            distances.append(distance_nm)
            cumulative_distance += distance_nm
            
        # Map distances back to original dataframe with explicit float32 casting
        valid_data['distance_nm'] = pd.Series(distances, dtype='float32')
        valid_data['cumulative_distance_nm'] = pd.Series(np.cumsum(distances), dtype='float32')
        
        # Update main dataframe with explicit casting
        self.data.loc[valid_coords, 'distance_nm'] = valid_data['distance_nm'].astype('float32')
        self.data.loc[valid_coords, 'cumulative_distance_nm'] = valid_data['cumulative_distance_nm'].astype('float32')
        
        # Forward fill cumulative distances for invalid GPS points using modern syntax
        self.data['cumulative_distance_nm'] = self.data['cumulative_distance_nm'].ffill().fillna(0.0)
        
        total_distance_nm = self.data['cumulative_distance_nm'].max()
        self.logger.info(f"Distance calculation complete: {total_distance_nm:.2f} nautical miles")

    def calculate_speed_in_knots(self) -> None:
        """Calculate speeds based on GPS data using vectorized operations."""
        self.logger.info("Calculating speeds...")

        # Vectorized speed calculation
        speed_mask = (self.data['gps_speed'] > 0.0) & (~pd.isna(self.data['gps_speed']))
        self.data.loc[speed_mask, 'speed_knots'] = self.data.loc[speed_mask, 'gps_speed'] * 1.94384
        
        # Filter out unrealistic speeds
        speed_too_high = self.data['speed_knots'] > SPEED_MAX
        if speed_too_high.sum() > 0:
            self.logger.warning(f"Found {speed_too_high.sum()} rows with unrealistic speeds, setting to NaN")
            self.data.loc[speed_too_high, 'speed_knots'] = np.nan

    def _calculate_engine_power_vectorized(self) -> None:
        """Calculate engine power using vectorized operations."""
        # Engine is on when current is negative
        engine_on_mask = (self.data['current'] < 0) & self.valid_voltage & self.valid_current
        
        # Calculate power for engine-on periods
        self.data.loc[engine_on_mask, 'engine_watts'] = np.abs(
            self.data.loc[engine_on_mask, 'voltage'] * self.data.loc[engine_on_mask, 'current']
        )
        self.data.loc[engine_on_mask, 'engine_current'] = -self.data.loc[engine_on_mask, 'current']
        
        # Filter out excessive power readings
        power_too_high = self.data['engine_watts'] > ENGINE_POWER_MAX
        if power_too_high.sum() > 0:
            self.logger.warning(f"Found {power_too_high.sum()} rows with excessive power, setting to 0")
            self.data.loc[power_too_high, ['engine_watts', 'engine_current']] = 0.0
            
        # Determine idling status
        idling_mask = engine_on_mask & (self.data['current'] >= ENGINE_IDLE_CURRENT)
        self.data.loc[idling_mask, 'engine_idling'] = 1

    def calculate_engine_metrics(self) -> None:
        """Calculate engine metrics based on current consumption."""
        self.logger.info("Calculating engine metrics...")

        # Initialize columns with appropriate data types
        self.data['engine_watts'] = pd.Series(0.0, dtype='float32')
        self.data['engine_current'] = pd.Series(0.0, dtype='float32')
        self.data['engine_idling'] = pd.Series(0, dtype='int8')
        self.data['engine_seconds'] = pd.Series(0.0, dtype='float32')
        self.data['engine_hours'] = pd.Series(0.0, dtype='float32')
        self.data['engine_idling_seconds'] = pd.Series(0.0, dtype='float32')
        self.data['engine_idling_hours'] = pd.Series(0.0, dtype='float32')
        self.data['engine_efficiency'] = pd.Series(np.nan, dtype='float32')

        # Calculate power using vectorized operations
        self._calculate_engine_power_vectorized()
        
        # Calculate efficiency for non-idling periods with valid speed
        # Engine must be running (watts > 0), not idling, and have valid speed
        efficiency_mask = (self.data['engine_watts'] > 0) & \
                         (self.data['engine_idling'] != 1.0) & \
                         (~pd.isna(self.data['speed_knots'])) & \
                         (self.data['speed_knots'] > 0)
        
        # Log how many efficiency calculations we're making
        efficiency_count = efficiency_mask.sum()
        self.logger.info(f"Calculating efficiency for {efficiency_count} data points")
        
        if efficiency_count > 0:
            self.data.loc[efficiency_mask, 'engine_efficiency'] = (
                self.data.loc[efficiency_mask, 'engine_watts'] / 
                self.data.loc[efficiency_mask, 'speed_knots']
            )
            
            # Log efficiency statistics
            eff_values = self.data.loc[efficiency_mask, 'engine_efficiency']
            self.logger.info(f"Engine efficiency - Mean: {eff_values.mean():.1f} W/knot, "
                           f"Min: {eff_values.min():.1f} W/knot, Max: {eff_values.max():.1f} W/knot")
        else:
            self.logger.warning("No valid data points found for engine efficiency calculation")
        
        # Calculate cumulative times (this still needs iteration due to time dependencies)
        self._calculate_cumulative_times()

    def _calculate_cumulative_times(self) -> None:
        """Calculate cumulative engine and idling times."""
        total_engine_seconds = 0.0
        total_idling_seconds = 0.0
        prev_timestamp = None
        prev_engine_on = False
        prev_idling = False
        
        # Use batch processing for better performance
        batch_size = 10000
        for start_idx in range(0, len(self.data), batch_size):
            end_idx = min(start_idx + batch_size, len(self.data))
            batch = self.data.iloc[start_idx:end_idx]
            
            for i in range(len(batch)):
                actual_idx = start_idx + i
                current = batch.iloc[i]['current']
                timestamp = batch.iloc[i]['timestamp']
                
                # Skip invalid data
                if not (self.valid_voltage.iloc[actual_idx] and self.valid_current.iloc[actual_idx]):
                    self.data.at[actual_idx, 'engine_seconds'] = total_engine_seconds
                    self.data.at[actual_idx, 'engine_hours'] = total_engine_seconds / 3600.0
                    self.data.at[actual_idx, 'engine_idling_seconds'] = total_idling_seconds
                    self.data.at[actual_idx, 'engine_idling_hours'] = total_idling_seconds / 3600.0
                    prev_timestamp = timestamp
                    prev_engine_on = False
                    prev_idling = False
                    continue

                engine_on = current < 0
                is_idling = engine_on and current >= ENGINE_IDLE_CURRENT
                
                # Calculate time differences
                if prev_timestamp is not None and prev_engine_on and engine_on:
                    time_diff = (timestamp - prev_timestamp).total_seconds()
                    
                    if 0 < time_diff <= MAX_TIME_GAP.total_seconds():
                        total_engine_seconds += time_diff
                        
                        if prev_idling and is_idling:
                            total_idling_seconds += time_diff

                # Store cumulative times
                self.data.at[actual_idx, 'engine_seconds'] = total_engine_seconds
                self.data.at[actual_idx, 'engine_hours'] = total_engine_seconds / 3600.0
                self.data.at[actual_idx, 'engine_idling_seconds'] = total_idling_seconds
                self.data.at[actual_idx, 'engine_idling_hours'] = total_idling_seconds / 3600.0

                prev_timestamp = timestamp
                prev_engine_on = engine_on
                prev_idling = is_idling

        max_engine_hours = self.data['engine_hours'].max()
        max_idling_hours = self.data['engine_idling_hours'].max()
        self.logger.info(f"Engine metrics calculated: {max_engine_hours:.1f} hours total, "
                        f"of which {max_idling_hours:.1f} hours were idling")

    def get_summary_stats(self) -> Dict[str, float]:
        """Return summary statistics for the analysis."""
        engine_data = self.data[self.data['engine_watts'] > 0]
        efficiency_data = self.data[~pd.isna(self.data['engine_efficiency'])]
        
        return {
            'total_distance_nm': float(self.data['cumulative_distance_nm'].max() or 0),
            'total_engine_hours': float(self.data['engine_hours'].max() or 0),
            'total_idling_hours': float(self.data['engine_idling_hours'].max() or 0),
            'avg_engine_efficiency': float(efficiency_data['engine_efficiency'].mean() or 0),
            'max_speed_knots': float(self.data['speed_knots'].max() or 0),
            'avg_engine_power': float(engine_data['engine_watts'].mean() or 0),
            'max_engine_power': float(engine_data['engine_watts'].max() or 0),
            'data_points': len(self.data),
            'valid_gps_points': int(self.valid_gps.sum()),
            'efficiency_data_points': len(efficiency_data)
        }

    def export_processed_data(self) -> None:
        """Export processed data to a CSV file in the log folder."""
        if not os.path.exists(os.path.join(self.log_folder, "processed_data")):
            os.makedirs(os.path.join(self.log_folder, "processed_data"))
        output_path = os.path.join(self.log_folder, "processed_data", "processed_data.csv")
        self.data.to_csv(output_path, index=False)
        self.logger.info(f"Processed data saved to {output_path}")

    def plot_efficiency(self) -> None:
        """Plot engine efficiency with focus on engine efficency measured as watts per knot as a function of speed in knots.
        Make a graph showing mean efficiency per speed bin, with error bars for standard deviation.
        Also show total range in nautical miles for each speed bin using a constant speed.
        1 knot = 1 nautical mile per hour.
        """
        self.logger.info("Plotting engine efficiency...")
        
        # Filter out invalid data
        valid_efficiency = self.data[~pd.isna(self.data['engine_efficiency']) & 
                                     (self.data['engine_efficiency'] > 0) & 
                                     (self.data['speed_knots'] > 0) &
                                     (self.data['engine_watts'] > 0)]
        
        if valid_efficiency.empty:
            self.logger.warning("No valid efficiency data to plot")
            return
        
        # Create bins for speed
        speed_bins = np.arange(0, SPEED_MAX + 1, 1.0)
        bin_labels = [f"{i}-{i+1}" for i in speed_bins[:-1]]
        
        # Calculate mean and std deviation of efficiency per speed bin
        binned_data = pd.cut(valid_efficiency['speed_knots'], bins=speed_bins, labels=bin_labels)
        efficiency_summary = valid_efficiency.groupby(binned_data).agg({
            'engine_efficiency': ['mean', 'std', 'count'],
            'engine_watts': 'mean',
            'voltage': 'mean'
        }).reset_index()
        
        # Flatten column names
        efficiency_summary.columns = ['speed_bin', 'efficiency_mean', 'efficiency_std', 'count', 'power_mean', 'voltage_mean']
        
        # Calculate theoretical range for each speed bin
        # Range = (Battery Capacity [Ah] * Average Voltage [V]) / Average Power [W]
        # This gives hours of operation, multiply by speed to get nautical miles
        speed_centers = np.arange(0.5, SPEED_MAX, 1.0)  # Center of each bin
        efficiency_summary['theoretical_range_nm'] = (
            (BATTERY_CAPACITY * efficiency_summary['voltage_mean']) / 
            efficiency_summary['power_mean']
        ) * speed_centers[:len(efficiency_summary)]
        
        # Remove rows with insufficient data
        efficiency_summary = efficiency_summary[efficiency_summary['count'] >= 3]
        
        if efficiency_summary.empty:
            self.logger.warning("Insufficient data points per speed bin for plotting")
            return
        
        # Create figure with two y-axes
        fig, ax1 = plt.subplots(figsize=(14, 8))
        
        # Plot efficiency on primary y-axis
        color = 'tab:blue'
        ax1.set_xlabel('Speed Bin (knots)')
        ax1.set_ylabel('Efficiency (W/knot)', color=color)
        ax1.errorbar(range(len(efficiency_summary)), efficiency_summary['efficiency_mean'], 
                     yerr=efficiency_summary['efficiency_std'], fmt='o-', capsize=5, 
                     color=color, label='Mean Efficiency ± Std Dev')
        ax1.tick_params(axis='y', labelcolor=color)
        ax1.grid(True, alpha=0.3)
        
        # Create secondary y-axis for theoretical range
        ax2 = ax1.twinx()
        color = 'tab:red'
        ax2.set_ylabel('Theoretical Range (nautical miles)', color=color)
        ax2.bar(range(len(efficiency_summary)), efficiency_summary['theoretical_range_nm'], 
                alpha=0.6, color=color, label='Theoretical Range')
        ax2.tick_params(axis='y', labelcolor=color)
        
        # Set x-axis labels
        ax1.set_xticks(range(len(efficiency_summary)))
        ax1.set_xticklabels(efficiency_summary['speed_bin'], rotation=45)
        
        # Add title and legends
        plt.title('Engine Efficiency and Theoretical Range vs Speed\n' + 
                 f'Battery Capacity: {BATTERY_CAPACITY} Ah', fontsize=14)
        
        # Combine legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
        
        # Add data point counts as text annotations
        for i, (idx, row) in enumerate(efficiency_summary.iterrows()):
            ax1.annotate(f'n={int(row["count"])}', 
                        (i, row['efficiency_mean']), 
                        textcoords="offset points", 
                        xytext=(0,10), ha='center', fontsize=8)
        
        plt.tight_layout()
        
        # Save plot
        if not os.path.exists(os.path.join(self.log_folder, "processed_data")):
            os.makedirs(os.path.join(self.log_folder, "processed_data"))
        output_path = os.path.join(self.log_folder, "processed_data", "engine_efficiency_plot.png")
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        self.logger.info(f"Efficiency plot saved to {output_path}")
        
        # Log summary statistics
        self.logger.info("Efficiency and Range Summary by Speed Bin:")
        for _, row in efficiency_summary.iterrows():
            self.logger.info(f"  {row['speed_bin']} knots: "
                           f"Efficiency {row['efficiency_mean']:.1f}±{row['efficiency_std']:.1f} W/knot, "
                           f"Range {row['theoretical_range_nm']:.1f} nm, "
                           f"Data points: {int(row['count'])}")
        
        # Display the plot
        plt.show()

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
        analyzer.export_processed_data()
        analyzer.plot_efficiency()
        # analyzer.generate_summary_report()

        summary_stats = analyzer.get_summary_stats()
        print("\nSummary Statistics:")
        for key, value in summary_stats.items():
            print(f"{key}: {value:.2f}" if isinstance(value, float) else f"{key}: {value}")
        
        print("\nAnalysis completed successfully!")
        
    except Exception as e:
        print(f"Error during analysis: {e}")
        return

if __name__ == "__main__":
    main()
