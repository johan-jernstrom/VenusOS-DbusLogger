#!/usr/bin/env python3
"""
CSV Data Analyzer for VenusOS DbusLogger
Parses CSV files containing GPS and electrical data to calculate:
- Total distance traveled
- Engine efficiency (watts per knot)
- Generates efficiency plots

CSV Format Expected:
timestamp,soc,voltage,current,gps_lat,gps_lon,gps_speed
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
        self.total_distance_km = 0
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
        
        # Convert timestamp to datetime
        self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])
        
        # Remove rows with invalid GPS coordinates (0,0 or NaN)
        initial_rows = len(self.data)
        self.data = self.data.dropna(subset=['gps_lat', 'gps_lon', 'gps_speed'])
        self.data = self.data[(self.data['gps_lat'] != 0) | (self.data['gps_lon'] != 0)]
        
        # Remove rows with invalid electrical data
        self.data = self.data.dropna(subset=['voltage', 'current'])
        
        # Calculate power in watts
        self.data['power_watts'] = self.data['voltage'] * self.data['current']
        
        # Convert GPS speed from m/s to knots (1 m/s = 1.94384 knots)
        self.data['speed_knots'] = self.data['gps_speed'] * 1.94384
        
        # Sort by timestamp
        self.data = self.data.sort_values('timestamp').reset_index(drop=True)
        
        print(f"Preprocessed data: {len(self.data)} rows (removed {initial_rows - len(self.data)} invalid rows)")
        
    def calculate_distances(self) -> None:
        """Calculate distances between consecutive GPS points."""
        print("Calculating distances...")
        
        distances = []
        
        for i in range(1, len(self.data)):
            # Get consecutive GPS coordinates
            lat1, lon1 = self.data.iloc[i-1]['gps_lat'], self.data.iloc[i-1]['gps_lon']
            lat2, lon2 = self.data.iloc[i]['gps_lat'], self.data.iloc[i]['gps_lon']
            
            # Calculate distance using geodesic (great circle) distance
            distance_km = geodesic((lat1, lon1), (lat2, lon2)).kilometers
            distances.append(distance_km)
        
        # First row has no previous point, so distance is 0
        distances.insert(0, 0)
        
        self.data['distance_km'] = distances
        self.total_distance_km = sum(distances)
        
        print(f"Total distance traveled: {self.total_distance_km:.2f} km")
        
    def calculate_efficiency(self) -> None:
        """Calculate engine efficiency (watts per knot)."""
        print("Calculating engine efficiency...")
        
        # Filter out stationary points (speed < 0.5 knots)
        moving_data = self.data[self.data['speed_knots'] >= 0.5].copy()
        
        if len(moving_data) == 0:
            print("Warning: No movement data found (all speeds < 0.5 knots)")
            return
        
        # Calculate efficiency (watts per knot)
        moving_data['efficiency_watts_per_knot'] = moving_data['power_watts'] / moving_data['speed_knots']
        
        # Remove extreme outliers (efficiency > 1000 watts/knot)
        moving_data = moving_data[moving_data['efficiency_watts_per_knot'] <= 1000]
        
        self.efficiency_data = moving_data
        
        if len(self.efficiency_data) > 0:
            avg_efficiency = self.efficiency_data['efficiency_watts_per_knot'].mean()
            print(f"Average efficiency: {avg_efficiency:.2f} watts per knot")
        else:
            print("Warning: No valid efficiency data calculated")
            
    def plot_efficiency(self) -> None:
        """Create plots for engine efficiency analysis."""
        if len(self.efficiency_data) == 0:
            print("No efficiency data to plot")
            return
            
        print("Generating efficiency plots...")
        
        # Create subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Engine Efficiency Analysis', fontsize=16)
        
        # Plot 1: Efficiency over time
        ax1.plot(self.efficiency_data['timestamp'], 
                self.efficiency_data['efficiency_watts_per_knot'], 
                alpha=0.7, linewidth=0.5)
        ax1.set_title('Efficiency Over Time')
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Watts per Knot')
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(axis='x', rotation=45)
        
        # Plot 2: Efficiency vs Speed
        ax2.scatter(self.efficiency_data['speed_knots'], 
                   self.efficiency_data['efficiency_watts_per_knot'], 
                   alpha=0.6, s=1)
        ax2.set_title('Efficiency vs Speed')
        ax2.set_xlabel('Speed (knots)')
        ax2.set_ylabel('Watts per Knot')
        ax2.grid(True, alpha=0.3)
        
        # Plot 3: Power vs Speed
        ax3.scatter(self.efficiency_data['speed_knots'], 
                   self.efficiency_data['power_watts'], 
                   alpha=0.6, s=1, c='green')
        ax3.set_title('Power vs Speed')
        ax3.set_xlabel('Speed (knots)')
        ax3.set_ylabel('Power (watts)')
        ax3.grid(True, alpha=0.3)
        
        # Plot 4: Efficiency histogram
        ax4.hist(self.efficiency_data['efficiency_watts_per_knot'], 
                bins=50, alpha=0.7, edgecolor='black')
        ax4.set_title('Efficiency Distribution')
        ax4.set_xlabel('Watts per Knot')
        ax4.set_ylabel('Frequency')
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save the plot
        output_file = os.path.join(self.folder_path, 'efficiency_analysis.png')
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Plot saved as: {output_file}")
        
        plt.show()
        
    def generate_summary_report(self) -> None:
        """Generate a summary report of the analysis."""
        print("\n" + "="*50)
        print("ANALYSIS SUMMARY REPORT")
        print("="*50)
        
        if len(self.data) > 0:
            print(f"Total data points: {len(self.data)}")
            print(f"Time period: {self.data['timestamp'].min()} to {self.data['timestamp'].max()}")
            print(f"Total distance traveled: {self.total_distance_km:.2f} km")
            
            if len(self.efficiency_data) > 0:
                avg_speed = self.efficiency_data['speed_knots'].mean()
                max_speed = self.efficiency_data['speed_knots'].max()
                avg_power = self.efficiency_data['power_watts'].mean()
                max_power = self.efficiency_data['power_watts'].max()
                avg_efficiency = self.efficiency_data['efficiency_watts_per_knot'].mean()
                
                print(f"\nSpeed Statistics:")
                print(f"  Average speed: {avg_speed:.2f} knots")
                print(f"  Maximum speed: {max_speed:.2f} knots")
                
                print(f"\nPower Statistics:")
                print(f"  Average power: {avg_power:.2f} watts")
                print(f"  Maximum power: {max_power:.2f} watts")
                
                print(f"\nEfficiency Statistics:")
                print(f"  Average efficiency: {avg_efficiency:.2f} watts per knot")
                
                # Calculate efficiency at different speed ranges
                speed_ranges = [
                    (0, 2, "Very slow (0-2 knots)"),
                    (2, 5, "Slow (2-5 knots)"),
                    (5, 8, "Medium (5-8 knots)"),
                    (8, float('inf'), "Fast (8+ knots)")
                ]
                
                print(f"\nEfficiency by Speed Range:")
                for min_speed, max_speed, label in speed_ranges:
                    mask = (self.efficiency_data['speed_knots'] >= min_speed) & \
                           (self.efficiency_data['speed_knots'] < max_speed)
                    range_data = self.efficiency_data[mask]
                    
                    if len(range_data) > 0:
                        range_efficiency = range_data['efficiency_watts_per_knot'].mean()
                        print(f"  {label}: {range_efficiency:.2f} watts/knot ({len(range_data)} points)")
            
        print("="*50)
        
        # Save summary to file
        summary_file = os.path.join(self.folder_path, 'analysis_summary.txt')
        with open(summary_file, 'w') as f:
            f.write("ANALYSIS SUMMARY REPORT\n")
            f.write("="*50 + "\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            if len(self.data) > 0:
                f.write(f"Total data points: {len(self.data)}\n")
                f.write(f"Time period: {self.data['timestamp'].min()} to {self.data['timestamp'].max()}\n")
                f.write(f"Total distance traveled: {self.total_distance_km:.2f} km\n")
                
                if len(self.efficiency_data) > 0:
                    f.write(f"Average efficiency: {self.efficiency_data['efficiency_watts_per_knot'].mean():.2f} watts per knot\n")
        
        print(f"Summary saved to: {summary_file}")


def main():
    """Main function to run the CSV analysis."""
    # Get folder path from user or use current directory
    folder_path = input("Enter the path to the folder containing CSV files (or press Enter for current directory): ").strip()
    
    if not folder_path:
        folder_path = "."
    
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
