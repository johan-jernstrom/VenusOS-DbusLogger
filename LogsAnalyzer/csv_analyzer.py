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

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from geopy.distance import geodesic
from datetime import datetime
import glob
from typing import List, Tuple, Dict


class CSVAnalyzer:
    def __init__(self, folder_path: str):
        """
        Initialize the CSV analyzer with a folder path containing CSV files.
        
        Args:
            folder_path (str): Path to folder containing CSV files
        """
        self.folder_path = folder_path
        self.data = pd.DataFrame()
        self.total_distance_nm = 0  # Distance in nautical miles
        self.efficiency_data = []
        
    def load_csv_files(self) -> None:
        """Load and combine all CSV files from the specified folder."""
        csv_files = glob.glob(os.path.join(self.folder_path, "*.csv"))
        
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in {self.folder_path}")
        
        print(f"Found {len(csv_files)} CSV files")
        
        dataframes = []
        for file in csv_files:
            try:
                df = pd.read_csv(file)
                # Ensure required columns exist
                required_columns = ['timestamp', 'soc', 'voltage', 'current', 
                                  'gps_lat', 'gps_lon', 'gps_speed']
                
                if not all(col in df.columns for col in required_columns):
                    print(f"Warning: {file} missing required columns, skipping...")
                    continue
                
                df['source_file'] = os.path.basename(file)
                dataframes.append(df)
                print(f"Loaded {len(df)} rows from {os.path.basename(file)}")
                
            except Exception as e:
                print(f"Error loading {file}: {e}")
        
        if not dataframes:
            raise ValueError("No valid CSV files could be loaded")
        
        self.data = pd.concat(dataframes, ignore_index=True)
        print(f"Total rows loaded: {len(self.data)}")
        
    def preprocess_data(self) -> None:
        """Clean and preprocess the loaded data."""
        print("Preprocessing data...")
        
        # Convert timestamp to datetime with flexible parsing
        try:
            self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])
        except Exception as e:
            print(f"Warning: Timestamp parsing issue, using mixed format: {e}")
            self.data['timestamp'] = pd.to_datetime(self.data['timestamp'], format='mixed')
        
        # Remove rows with invalid GPS coordinates (0,0 or NaN)
        initial_rows = len(self.data)
        self.data = self.data.dropna(subset=['gps_lat', 'gps_lon', 'gps_speed'])
        self.data = self.data[(self.data['gps_lat'] != 0) | (self.data['gps_lon'] != 0)]
        
        print(f"Removed {initial_rows - len(self.data)} rows with invalid GPS data")

        # Remove rows with invalid electrical data
        initial_rows = len(self.data)
        self.data = self.data.dropna(subset=['voltage', 'current'])
        print(f"Removed {initial_rows - len(self.data)} rows with invalid electrical data")

        # Convert GPS speed from m/s to knots (1 m/s = 1.94384 knots)
        self.data['speed_knots'] = self.data['gps_speed'] * 1.94384
        
        # SAILBOAT SPECIFIC FILTERING:
        
        # 1. Remove speeds over 8 knots (sailboat maximum realistic speed)
        speed_filtered = self.data[self.data['speed_knots'] <= 8.0]
        print(f"Removed {len(self.data) - len(speed_filtered)} rows with speed > 8 knots")
        self.data = speed_filtered
        
        # 2. Filter out positive currents (battery charging - happens when docked/stationary)
        # Keep only negative currents (engine consumption) and convert to positive values
        # Also filter out zero or near-zero currents (no actual consumption)
        
        charging_rows = len(self.data[self.data['current'] >= 0])
        if charging_rows > 0:
            print(f"Removed {charging_rows} rows with positive current (battery charging)")
        
        # Filter for actual engine consumption: current must be significantly negative
        # This excludes zero current, NaN values, and very low house loads
        engine_threshold = -0.3  # Minimum 0.3A consumption to be considered engine operation
        self.data = self.data[self.data['current'] <= engine_threshold].copy()
        
        zero_current_rows = charging_rows  # Approximate count of non-engine rows
        print(f"Applied engine threshold: keeping only current <= {engine_threshold}A")
        
        if len(self.data) == 0:
            print("Warning: No engine operation data found after filtering")
            return
        
        # Convert negative current to positive consumption values
        self.data['current_consumption'] = abs(self.data['current'])
        
        # 3. Calculate power consumption in watts (now always positive)
        self.data['power_watts'] = self.data['voltage'] * self.data['current_consumption']
        
        # 4. Remove power readings over 11kW (11000W) - engine maximum
        power_filtered = self.data[self.data['power_watts'] <= 11000]
        print(f"Removed {len(self.data) - len(power_filtered)} rows with power > 11kW")
        self.data = power_filtered
        
        # Sort by timestamp
        self.data = self.data.sort_values('timestamp').reset_index(drop=True)
        
        print(f"Final preprocessed data: {len(self.data)} rows (removed {initial_rows - len(self.data)} total invalid/outlier rows)")
        
    def calculate_distances(self) -> None:
        """Calculate distances between consecutive GPS points in nautical miles."""
        print("Calculating distances...")
        
        distances = []
        
        for i in range(1, len(self.data)):
            # Get consecutive GPS coordinates
            lat1, lon1 = self.data.iloc[i-1]['gps_lat'], self.data.iloc[i-1]['gps_lon']
            lat2, lon2 = self.data.iloc[i]['gps_lat'], self.data.iloc[i]['gps_lon']
            
            # Calculate distance using geodesic (great circle) distance in kilometers
            distance_km = geodesic((lat1, lon1), (lat2, lon2)).nm
            
            # Convert kilometers to nautical miles (1 km = 0.539957 nautical miles)
            distance_nm = distance_km * 0.539957
            distances.append(distance_nm)
        
        # First row has no previous point, so distance is 0
        distances.insert(0, 0)
        
        self.data['distance_nm'] = distances
        self.total_distance_nm = sum(distances)
        
        print(f"Total distance traveled: {self.total_distance_nm:.2f} nautical miles")
        
    def calculate_efficiency(self) -> None:
        """Calculate engine efficiency (watts per knot)."""
        print("Calculating engine efficiency...")
        
        # All negative current data represents engine operation (including idle)
        # The data is already filtered to only include negative currents (engine consumption)
        engine_data = self.data.copy()
        
        # Separate moving and stationary (idle) engine periods
        moving_data = engine_data[engine_data['speed_knots'] >= 0.5].copy()
        idle_data = engine_data[engine_data['speed_knots'] < 0.5].copy()
        
        print(f"Engine data breakdown:")
        print(f"  Moving periods (≥0.5 knots): {len(moving_data)} data points")
        print(f"  Idle periods (<0.5 knots): {len(idle_data)} data points")
        print(f"  Total engine operation: {len(engine_data)} data points")
        
        if len(moving_data) == 0:
            print("Warning: No movement data found (all speeds < 0.5 knots)")
            # Still use all engine data for time calculations, but no efficiency metrics
            self.efficiency_data = engine_data
            return
        
        # Calculate efficiency (watts per knot) only for moving periods
        moving_data['efficiency_watts_per_knot'] = moving_data['power_watts'] / moving_data['speed_knots']
        
        # Remove any remaining extreme outliers (efficiency > 2000 watts/knot)
        moving_data = moving_data[moving_data['efficiency_watts_per_knot'] <= 2000]
        
        # For time calculations, use ALL engine data (moving + idle)
        # For efficiency calculations, use only moving data
        self.efficiency_data = engine_data  # All engine operation for time calculations
        self.moving_efficiency_data = moving_data  # Only moving periods for efficiency metrics
        
        if len(moving_data) > 0:
            avg_efficiency = moving_data['efficiency_watts_per_knot'].mean()
            print(f"Average engine efficiency (moving only): {avg_efficiency:.2f} watts per knot")
            print(f"Moving efficiency data points: {len(moving_data)}")
        else:
            print("Warning: No valid moving efficiency data calculated")
            self.moving_efficiency_data = pd.DataFrame()  # Empty dataframe if no moving data
            
    def plot_efficiency(self) -> None:
        """Create plots for engine efficiency analysis."""
        if len(self.efficiency_data) == 0:
            print("No efficiency data to plot")
            return
            
        # Use moving data for efficiency plots if available
        plot_data = getattr(self, 'moving_efficiency_data', self.efficiency_data)
        if len(plot_data) == 0:
            print("No moving efficiency data to plot")
            return
            
        print("Generating efficiency plots...")
        
        # Create subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Sailboat Engine Efficiency Analysis (Moving Periods)', fontsize=16)
        
        # Plot 1: Efficiency over time
        ax1.plot(plot_data['timestamp'], 
                plot_data['efficiency_watts_per_knot'], 
                alpha=0.7, linewidth=0.8, color='blue')
        ax1.set_title('Engine Efficiency Over Time')
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Watts per Knot')
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(axis='x', rotation=45)
        
        # Plot 2: Efficiency vs Speed
        ax2.scatter(plot_data['speed_knots'], 
                   plot_data['efficiency_watts_per_knot'], 
                   alpha=0.6, s=2, color='red')
        ax2.set_title('Engine Efficiency vs Speed')
        ax2.set_xlabel('Speed (knots)')
        ax2.set_ylabel('Watts per Knot')
        ax2.set_xlim(0, 8)  # Sailboat speed limit
        ax2.grid(True, alpha=0.3)
        
        # Plot 3: Power Consumption vs Speed (use ALL engine data including idle)
        ax3.scatter(self.efficiency_data['speed_knots'], 
                   self.efficiency_data['power_watts'], 
                   alpha=0.6, s=2, color='green')
        ax3.set_title('Power Consumption vs Speed (All Engine Operation)')
        ax3.set_xlabel('Speed (knots)')
        ax3.set_ylabel('Power Consumption (watts)')
        ax3.set_xlim(-0.5, 8)  # Include idle at 0 knots
        ax3.set_ylim(0, 11000)  # Engine power limit
        ax3.grid(True, alpha=0.3)
        
        # Plot 4: Efficiency histogram (moving periods only)
        ax4.hist(plot_data['efficiency_watts_per_knot'], 
                bins=50, alpha=0.7, edgecolor='black', color='orange')
        ax4.set_title('Engine Efficiency Distribution (Moving Only)')
        ax4.set_xlabel('Watts per Knot')
        ax4.set_ylabel('Frequency')
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save the plot
        output_file = os.path.join(self.folder_path, 'sailboat_efficiency_analysis.png')
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Plot saved as: {output_file}")
        
        plt.show()
        
    def generate_summary_report(self) -> None:
        """Generate a summary report of the analysis."""
        print("\n" + "="*60)
        print("SAILBOAT ENGINE EFFICIENCY ANALYSIS SUMMARY")
        print("="*60)
        
        if len(self.data) > 0:
            print(f"Total valid data points: {len(self.data)}")
            print(f"Time period: {self.data['timestamp'].min()} to {self.data['timestamp'].max()}")
            print(f"Total distance traveled: {self.total_distance_nm:.2f} nautical miles")
            
            if len(self.efficiency_data) > 0:
                # Overall engine statistics (including idle)
                avg_power_all = self.efficiency_data['power_watts'].mean()
                max_power_all = self.efficiency_data['power_watts'].max()
                
                print(f"\nEngine Power Statistics (All Operation):")
                print(f"  Average power consumption: {avg_power_all:.0f} watts ({avg_power_all/1000:.1f} kW)")
                print(f"  Maximum power consumption: {max_power_all:.0f} watts ({max_power_all/1000:.1f} kW)")
                
                # Moving periods statistics
                if hasattr(self, 'moving_efficiency_data') and len(self.moving_efficiency_data) > 0:
                    avg_speed = self.moving_efficiency_data['speed_knots'].mean()
                    max_speed = self.moving_efficiency_data['speed_knots'].max()
                    avg_efficiency = self.moving_efficiency_data['efficiency_watts_per_knot'].mean()
                    
                    print(f"\nSpeed Statistics (Moving Periods Only):")
                    print(f"  Average speed under engine: {avg_speed:.2f} knots")
                    print(f"  Maximum speed under engine: {max_speed:.2f} knots")
                    
                    print(f"\nEngine Efficiency (Moving Periods Only):")
                    print(f"  Average efficiency: {avg_efficiency:.1f} watts per knot")
                    
                    # Calculate efficiency at different speed ranges (sailboat specific)
                    speed_ranges = [
                        (0, 2, "Very slow motoring (0-2 knots)"),
                        (2, 4, "Slow motoring (2-4 knots)"),
                        (4, 6, "Medium motoring (4-6 knots)"),
                        (6, 8, "Fast motoring (6-8 knots)")
                    ]
                    
                    print(f"\nEfficiency by Speed Range (Moving Only):")
                    for min_speed, max_speed, label in speed_ranges:
                        mask = (self.moving_efficiency_data['speed_knots'] >= min_speed) & \
                               (self.moving_efficiency_data['speed_knots'] < max_speed)
                        range_data = self.moving_efficiency_data[mask]
                        
                        if len(range_data) > 0:
                            range_efficiency = range_data['efficiency_watts_per_knot'].mean()
                            range_power = range_data['power_watts'].mean()
                            print(f"  {label}:")
                            print(f"    Efficiency: {range_efficiency:.1f} watts/knot")
                            print(f"    Avg Power: {range_power:.0f}W ({range_power/1000:.1f}kW)")
                            print(f"    Data points: {len(range_data)}")
                
                # Idle vs moving breakdown
                idle_data = self.efficiency_data[self.efficiency_data['speed_knots'] < 0.5]
                moving_data = self.efficiency_data[self.efficiency_data['speed_knots'] >= 0.5]
                
                print(f"\nEngine Operation Breakdown:")
                print(f"  Total engine data points: {len(self.efficiency_data)}")
                print(f"  Idle periods (<0.5 knots): {len(idle_data)} points")
                print(f"  Moving periods (>=0.5 knots): {len(moving_data)} points")
                
                if len(idle_data) > 0:
                    avg_idle_power = idle_data['power_watts'].mean()
                    print(f"  Average idle power: {avg_idle_power:.0f}W ({avg_idle_power/24:.1f}A at 24V)")
                
                # Calculate total engine hours (more accurate calculation with gap detection)
                if len(self.efficiency_data) > 1:
                    # Sort by timestamp to ensure correct order
                    sorted_data = self.efficiency_data.sort_values('timestamp')
                    
                    # Calculate time differences between consecutive readings
                    time_diffs = []
                    large_gaps = 0
                    max_gap_minutes = 5  # Consider gaps > 5 minutes as data interruptions
                    
                    for i in range(1, len(sorted_data)):
                        time_diff = (sorted_data.iloc[i]['timestamp'] - sorted_data.iloc[i-1]['timestamp']).total_seconds()
                        
                        # Only count time differences that are reasonable (< 5 minutes)
                        # This prevents counting long periods where logging was stopped
                        if time_diff <= max_gap_minutes * 60:  # 5 minutes in seconds
                            time_diffs.append(time_diff)
                        else:
                            large_gaps += 1
                    
                    # Sum all reasonable time differences to get total engine time
                    total_seconds = sum(time_diffs)
                    total_hours = total_seconds / 3600
                    
                    engine_distance = self.efficiency_data['distance_nm'].sum()
                    
                    print(f"\nEngine Usage:")
                    print(f"  Total engine time: {total_hours:.1f} hours ({total_seconds:.0f} seconds)")
                    print(f"  Distance under engine: {engine_distance:.1f} nautical miles")
                    print(f"  Large data gaps detected: {large_gaps} (>{max_gap_minutes} min)")
                    if total_hours > 0 and engine_distance > 0:
                        avg_engine_speed = engine_distance / total_hours
                        print(f"  Average engine speed: {avg_engine_speed:.1f} knots")
                    
                    # Additional useful metrics
                    if len(time_diffs) > 0:
                        avg_sampling_interval = sum(time_diffs) / len(time_diffs)
                        print(f"  Average sampling interval: ~{avg_sampling_interval:.1f} seconds per reading")
                    if total_hours > 0:
                        avg_power_consumption = self.efficiency_data['power_watts'].mean()
                        total_energy_kwh = (avg_power_consumption * total_hours) / 1000
                        print(f"  Estimated energy consumption: {total_energy_kwh:.2f} kWh")
            
        print("="*60)
        
        # Save complete summary to file
        summary_file = os.path.join(self.folder_path, 'sailboat_analysis_summary.txt')
        with open(summary_file, 'w') as f:
            f.write("SAILBOAT ENGINE EFFICIENCY ANALYSIS SUMMARY\n")
            f.write("="*60 + "\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            if len(self.data) > 0:
                f.write(f"Total valid data points: {len(self.data)}\n")
                f.write(f"Time period: {self.data['timestamp'].min()} to {self.data['timestamp'].max()}\n")
                f.write(f"Total distance traveled: {self.total_distance_nm:.2f} nautical miles\n")
                
                if len(self.efficiency_data) > 0:
                    # Overall engine statistics (including idle)
                    avg_power_all = self.efficiency_data['power_watts'].mean()
                    max_power_all = self.efficiency_data['power_watts'].max()
                    
                    f.write(f"\nEngine Power Statistics (All Operation):\n")
                    f.write(f"  Average power consumption: {avg_power_all:.0f} watts ({avg_power_all/1000:.1f} kW)\n")
                    f.write(f"  Maximum power consumption: {max_power_all:.0f} watts ({max_power_all/1000:.1f} kW)\n")
                    
                    # Moving periods statistics
                    if hasattr(self, 'moving_efficiency_data') and len(self.moving_efficiency_data) > 0:
                        avg_speed = self.moving_efficiency_data['speed_knots'].mean()
                        max_speed = self.moving_efficiency_data['speed_knots'].max()
                        avg_efficiency = self.moving_efficiency_data['efficiency_watts_per_knot'].mean()
                        
                        f.write(f"\nSpeed Statistics (Moving Periods Only):\n")
                        f.write(f"  Average speed under engine: {avg_speed:.2f} knots\n")
                        f.write(f"  Maximum speed under engine: {max_speed:.2f} knots\n")
                        
                        f.write(f"\nEngine Efficiency (Moving Periods Only):\n")
                        f.write(f"  Average efficiency: {avg_efficiency:.1f} watts per knot\n")
                        
                        # Calculate efficiency at different speed ranges (sailboat specific)
                        speed_ranges = [
                            (0, 2, "Very slow motoring (0-2 knots)"),
                            (2, 4, "Slow motoring (2-4 knots)"),
                            (4, 6, "Medium motoring (4-6 knots)"),
                            (6, 8, "Fast motoring (6-8 knots)")
                        ]
                        
                        f.write(f"\nEfficiency by Speed Range (Moving Only):\n")
                        for min_speed, max_speed, label in speed_ranges:
                            mask = (self.moving_efficiency_data['speed_knots'] >= min_speed) & \
                                   (self.moving_efficiency_data['speed_knots'] < max_speed)
                            range_data = self.moving_efficiency_data[mask]
                            
                            if len(range_data) > 0:
                                range_efficiency = range_data['efficiency_watts_per_knot'].mean()
                                range_power = range_data['power_watts'].mean()
                                f.write(f"  {label}:\n")
                                f.write(f"    Efficiency: {range_efficiency:.1f} watts/knot\n")
                                f.write(f"    Avg Power: {range_power:.0f}W ({range_power/1000:.1f}kW)\n")
                                f.write(f"    Data points: {len(range_data)}\n")
                    
                    # Idle vs moving breakdown
                    idle_data = self.efficiency_data[self.efficiency_data['speed_knots'] < 0.5]
                    moving_data = self.efficiency_data[self.efficiency_data['speed_knots'] >= 0.5]
                    
                    f.write(f"\nEngine Operation Breakdown:\n")
                    f.write(f"  Total engine data points: {len(self.efficiency_data)}\n")
                    f.write(f"  Idle periods (<0.5 knots): {len(idle_data)} points\n")
                    f.write(f"  Moving periods (>=0.5 knots): {len(moving_data)} points\n")
                    
                    if len(idle_data) > 0:
                        avg_idle_power = idle_data['power_watts'].mean()
                        f.write(f"  Average idle power: {avg_idle_power:.0f}W ({avg_idle_power/24:.1f}A at 24V)\n")
                    
                    # Calculate total engine hours (more accurate calculation with gap detection)
                    if len(self.efficiency_data) > 1:
                        # Sort by timestamp to ensure correct order
                        sorted_data = self.efficiency_data.sort_values('timestamp')
                        
                        # Calculate time differences between consecutive readings
                        time_diffs = []
                        large_gaps = 0
                        max_gap_minutes = 5  # Consider gaps > 5 minutes as data interruptions
                        
                        for i in range(1, len(sorted_data)):
                            time_diff = (sorted_data.iloc[i]['timestamp'] - sorted_data.iloc[i-1]['timestamp']).total_seconds()
                            
                            # Only count time differences that are reasonable (< 5 minutes)
                            # This prevents counting long periods where logging was stopped
                            if time_diff <= max_gap_minutes * 60:  # 5 minutes in seconds
                                time_diffs.append(time_diff)
                            else:
                                large_gaps += 1
                        
                        # Sum all reasonable time differences to get total engine time
                        total_seconds = sum(time_diffs)
                        total_hours = total_seconds / 3600
                        
                        engine_distance = self.efficiency_data['distance_nm'].sum()
                        
                        f.write(f"\nEngine Usage:\n")
                        f.write(f"  Total engine time: {total_hours:.1f} hours ({total_seconds:.0f} seconds)\n")
                        f.write(f"  Distance under engine: {engine_distance:.1f} nautical miles\n")
                        f.write(f"  Large data gaps detected: {large_gaps} (>{max_gap_minutes} min)\n")
                        if total_hours > 0 and engine_distance > 0:
                            avg_engine_speed = engine_distance / total_hours
                            f.write(f"  Average engine speed: {avg_engine_speed:.1f} knots\n")
                        
                        # Additional useful metrics
                        if len(time_diffs) > 0:
                            avg_sampling_interval = sum(time_diffs) / len(time_diffs)
                            f.write(f"  Average sampling interval: ~{avg_sampling_interval:.1f} seconds per reading\n")
                        if total_hours > 0:
                            avg_power_consumption = self.efficiency_data['power_watts'].mean()
                            total_energy_kwh = (avg_power_consumption * total_hours) / 1000
                            f.write(f"  Estimated energy consumption: {total_energy_kwh:.2f} kWh\n")
            
            f.write("\n" + "="*60 + "\n")
        
        print(f"Complete summary saved to: {summary_file}")


def main():
    """Main function to run the CSV analysis."""
    # Default to logs folder in current directory
    default_folder = "logs"
    folder_path = default_folder
    
    # Check if logs folder exists and contains CSV files
    if not os.path.exists(default_folder):
        print(f"Default folder '{default_folder}' does not exist.")
        folder_path = input("Enter the path to the folder containing CSV files (or press Enter for current directory): ").strip()
        if not folder_path:
            folder_path = "."
    else:
        # Check if logs folder contains any CSV files
        import glob
        csv_files = glob.glob(os.path.join(default_folder, "*.csv"))
        if not csv_files:
            print(f"Default folder '{default_folder}' contains no CSV files.")
            folder_path = input("Enter the path to the folder containing CSV files (or press Enter for current directory): ").strip()
            if not folder_path:
                folder_path = "."
        else:
            print(f"Using default folder: {default_folder}")
    
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist")
        return
    
    try:
        # Create analyzer instance
        analyzer = CSVAnalyzer(folder_path)
        
        # Run analysis
        analyzer.load_csv_files()
        analyzer.preprocess_data()
        analyzer.calculate_distances()
        analyzer.calculate_efficiency()
        analyzer.plot_efficiency()
        analyzer.generate_summary_report()
        
        print("\nAnalysis completed successfully!")
        
    except Exception as e:
        print(f"Error during analysis: {e}")
        return


if __name__ == "__main__":
    main()
