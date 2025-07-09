#!/usr/bin/env python3
"""
GPS Map Viewer for VenusOS D-Bus Logger
Displays GPS positions from logged CSV files on an interactive map
"""

import os
import sys
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import webbrowser
import tempfile
from datetime import datetime
from typing import Set, Tuple, List
import glob

try:
    import folium
    import pandas as pd
    from folium import plugins
except ImportError as e:
    print("Required packages not installed. Please install with:")
    print("pip install folium pandas")
    sys.exit(1)

class GPSMapViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("VenusOS GPS Map Viewer")
        self.root.geometry("800x600")
        
        # Data storage
        self.gps_positions = []
        self.unique_positions = set()
        self.logs_directory = "logs"
        
        # GUI setup
        self.setup_gui()
        
        # Check for logs directory
        if os.path.exists(self.logs_directory):
            self.logs_path_var.set(self.logs_directory)
    
    def setup_gui(self):
        """Create the GUI interface"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="VenusOS GPS Map Viewer", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Logs directory selection
        ttk.Label(main_frame, text="Logs Directory:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.logs_path_var = tk.StringVar()
        logs_entry = ttk.Entry(main_frame, textvariable=self.logs_path_var, width=50)
        logs_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)
        
        browse_btn = ttk.Button(main_frame, text="Browse", command=self.browse_directory)
        browse_btn.grid(row=1, column=2, padx=(5, 0), pady=5)
        
        # File filters
        filter_frame = ttk.LabelFrame(main_frame, text="File Filters", padding="10")
        filter_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        filter_frame.columnconfigure(1, weight=1)
        
        # Date range filters
        ttk.Label(filter_frame, text="From Date (YYYYMMDD):").grid(row=0, column=0, sticky=tk.W)
        self.from_date_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.from_date_var, width=20).grid(row=0, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(filter_frame, text="To Date (YYYYMMDD):").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        self.to_date_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.to_date_var, width=20).grid(row=0, column=3, sticky=tk.W, padx=10)
        
        # Map options
        options_frame = ttk.LabelFrame(main_frame, text="Map Options", padding="10")
        options_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        self.show_track_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Show track line", variable=self.show_track_var).grid(row=0, column=0, sticky=tk.W)
        
        self.show_markers_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Show position markers", variable=self.show_markers_var).grid(row=0, column=1, sticky=tk.W, padx=20)
        
        self.cluster_markers_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Cluster nearby markers", variable=self.cluster_markers_var).grid(row=0, column=2, sticky=tk.W, padx=20)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.grid(row=5, column=0, columnspan=3, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=20)
        
        load_btn = ttk.Button(button_frame, text="Load GPS Data", command=self.load_gps_data)
        load_btn.pack(side=tk.LEFT, padx=5)
        
        self.generate_btn = ttk.Button(button_frame, text="Generate Map", 
                                     command=self.generate_map, state="disabled")
        self.generate_btn.pack(side=tk.LEFT, padx=5)
        
        clear_btn = ttk.Button(button_frame, text="Clear Data", command=self.clear_data)
        clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Statistics frame
        stats_frame = ttk.LabelFrame(main_frame, text="Statistics", padding="10")
        stats_frame.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        self.stats_var = tk.StringVar(value="No data loaded")
        stats_label = ttk.Label(stats_frame, textvariable=self.stats_var)
        stats_label.pack()
    
    def browse_directory(self):
        """Browse for logs directory"""
        directory = filedialog.askdirectory(title="Select Logs Directory")
        if directory:
            self.logs_path_var.set(directory)
    
    def load_gps_data(self):
        """Load GPS data from CSV files in a separate thread"""
        logs_dir = self.logs_path_var.get()
        if not logs_dir or not os.path.exists(logs_dir):
            messagebox.showerror("Error", "Please select a valid logs directory")
            return
        
        # Disable buttons during loading
        self.generate_btn.config(state="disabled")
        
        # Start loading in separate thread
        threading.Thread(target=self._load_gps_data_thread, args=(logs_dir,), daemon=True).start()
    
    def _load_gps_data_thread(self, logs_dir):
        """Load GPS data in background thread"""
        try:
            self.root.after(0, lambda: self.status_var.set("Loading GPS data..."))
            self.root.after(0, lambda: self.progress_var.set(0))
            
            # Find all CSV files
            csv_files = glob.glob(os.path.join(logs_dir, "*.csv"))
            csv_files = [f for f in csv_files if "sensor_log" in os.path.basename(f) or "dbus_log" in os.path.basename(f)]
            
            if not csv_files:
                self.root.after(0, lambda: messagebox.showerror("Error", "No log files found in directory"))
                return
            
            # Filter files by date if specified
            from_date = self.from_date_var.get().strip()
            to_date = self.to_date_var.get().strip()
            
            if from_date or to_date:
                csv_files = self._filter_files_by_date(csv_files, from_date, to_date)
            
            # Reset data
            self.gps_positions = []
            self.unique_positions = set()
            
            total_files = len(csv_files)
            processed_files = 0
            total_positions = 0
            unique_positions = 0
            
            for csv_file in csv_files:
                self._process_csv_file(csv_file)
                processed_files += 1
                progress = (processed_files / total_files) * 100
                self.root.after(0, lambda p=progress: self.progress_var.set(p))
                
                # Update status
                total_positions = len(self.gps_positions)
                unique_positions = len(self.unique_positions)
                status = f"Processed {processed_files}/{total_files} files - {total_positions} positions ({unique_positions} unique)"
                self.root.after(0, lambda s=status: self.status_var.set(s))
            
            # Final statistics
            stats_text = f"Loaded {total_positions} GPS positions ({unique_positions} unique) from {total_files} files"
            self.root.after(0, lambda: self.stats_var.set(stats_text))
            self.root.after(0, lambda: self.status_var.set("GPS data loaded successfully"))
            
            # Enable generate button if we have data
            if self.gps_positions:
                self.root.after(0, lambda: self.generate_btn.config(state="normal"))
            
        except Exception as e:
            error_msg = f"Error loading GPS data: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.root.after(0, lambda: self.status_var.set("Error loading data"))
    
    def _filter_files_by_date(self, csv_files, from_date, to_date):
        """Filter CSV files by date range"""
        filtered_files = []
        
        for csv_file in csv_files:
            filename = os.path.basename(csv_file)
            # Extract date from filename (assuming format: sensor_log_YYYYMMDD.csv or dbus_log_YYYYMMDD.csv)
            try:
                if "sensor_log_" in filename:
                    date_str = filename.replace("sensor_log_", "").replace(".csv", "")
                elif "dbus_log_" in filename:
                    date_str = filename.replace("dbus_log_", "").replace(".csv", "")
                else:
                    continue
                
                if len(date_str) == 8 and date_str.isdigit():
                    if from_date and date_str < from_date:
                        continue
                    if to_date and date_str > to_date:
                        continue
                    filtered_files.append(csv_file)
            except:
                # If we can't parse the date, include the file
                filtered_files.append(csv_file)
        
        return filtered_files
    
    def _process_csv_file(self, csv_file):
        """Process a single CSV file for GPS data"""
        try:
            with open(csv_file, 'r', newline='', encoding='utf-8') as file:
                # Try to detect if file has header
                sample = file.read(1024)
                file.seek(0)
                has_header = 'timestamp' in sample.lower() or 'gps_lat' in sample.lower()
                
                reader = csv.DictReader(file) if has_header else csv.reader(file)
                
                for row in reader:
                    try:
                        if has_header:
                            # Dictionary reader
                            lat = row.get('gps_lat', '').strip()
                            lon = row.get('gps_lon', '').strip()
                            timestamp = row.get('timestamp', '').strip()
                            speed = row.get('gps_speed', '').strip()
                        else:
                            # Assume CSV format: timestamp,soc,current,voltage,gps_lat,gps_lon,gps_speed
                            if len(row) >= 6:
                                timestamp = row[0].strip()
                                lat = row[4].strip()
                                lon = row[5].strip()
                                speed = row[6].strip() if len(row) > 6 else ''
                            else:
                                continue
                        
                        # Validate and convert coordinates
                        if lat and lon and lat != 'None' and lon != 'None':
                            try:
                                lat_float = float(lat)
                                lon_float = float(lon)
                                
                                # Basic coordinate validation
                                if -90 <= lat_float <= 90 and -180 <= lon_float <= 180:
                                    # Round to reduce duplicates (approximately 11m precision)
                                    lat_rounded = round(lat_float, 4)
                                    lon_rounded = round(lon_float, 4)
                                    position_key = (lat_rounded, lon_rounded)
                                    
                                    # Only add if not duplicate
                                    if position_key not in self.unique_positions:
                                        self.unique_positions.add(position_key)
                                        
                                        # Parse speed
                                        speed_float = None
                                        if speed and speed != 'None':
                                            try:
                                                speed_float = float(speed)
                                            except:
                                                pass
                                        
                                        self.gps_positions.append({
                                            'lat': lat_float,
                                            'lon': lon_float,
                                            'timestamp': timestamp,
                                            'speed': speed_float
                                        })
                            except ValueError:
                                continue
                    except Exception:
                        continue
                        
        except Exception as e:
            print(f"Error processing file {csv_file}: {e}")
    
    def generate_map(self):
        """Generate the interactive map"""
        if not self.gps_positions:
            messagebox.showwarning("Warning", "No GPS data loaded")
            return
        
        # Disable button during generation
        self.generate_btn.config(state="disabled")
        
        # Start map generation in separate thread
        threading.Thread(target=self._generate_map_thread, daemon=True).start()
    
    def _generate_map_thread(self):
        """Generate map in background thread"""
        try:
            self.root.after(0, lambda: self.status_var.set("Generating map..."))
            self.root.after(0, lambda: self.progress_var.set(0))
            
            # Calculate map center
            lats = [pos['lat'] for pos in self.gps_positions]
            lons = [pos['lon'] for pos in self.gps_positions]
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
            
            # Create map
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=12,
                tiles='OpenStreetMap'
            )
            
            # Add alternative tile layers with proper attributions
            folium.TileLayer(
                tiles='https://stamen-tiles-{s}.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg',
                attr='Map tiles by <a href="http://stamen.com">Stamen Design</a>, under <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>. Data by <a href="http://openstreetmap.org">OpenStreetMap</a>, under <a href="http://www.openstreetmap.org/copyright">ODbL</a>.',
                name='Stamen Terrain',
                overlay=False,
                control=True
            ).add_to(m)
            
            folium.TileLayer(
                tiles='https://stamen-tiles-{s}.a.ssl.fastly.net/toner/{z}/{x}/{y}.png',
                attr='Map tiles by <a href="http://stamen.com">Stamen Design</a>, under <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>. Data by <a href="http://openstreetmap.org">OpenStreetMap</a>, under <a href="http://www.openstreetmap.org/copyright">ODbL</a>.',
                name='Stamen Toner',
                overlay=False,
                control=True
            ).add_to(m)
            
            folium.TileLayer(
                tiles='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
                attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                name='CartoDB Positron',
                overlay=False,
                control=True
            ).add_to(m)
            
            # Sort positions by timestamp for track line
            sorted_positions = sorted(self.gps_positions, key=lambda x: x['timestamp'])
            
            self.root.after(0, lambda: self.progress_var.set(25))
            
            # Add track line if enabled
            if self.show_track_var.get():
                track_coords = [[pos['lat'], pos['lon']] for pos in sorted_positions]
                folium.PolyLine(
                    track_coords,
                    color='blue',
                    weight=3,
                    opacity=0.8,
                    popup="GPS Track"
                ).add_to(m)
            
            self.root.after(0, lambda: self.progress_var.set(50))
            
            # Add markers if enabled
            if self.show_markers_var.get():
                if self.cluster_markers_var.get() and len(self.gps_positions) > 100:
                    # Use marker clustering for large datasets
                    marker_cluster = plugins.MarkerCluster().add_to(m)
                    
                    for i, pos in enumerate(sorted_positions):
                        if i % max(1, len(sorted_positions) // 1000) == 0:  # Sample for performance
                            popup_text = f"Time: {pos['timestamp']}<br>Lat: {pos['lat']:.4f}<br>Lon: {pos['lon']:.4f}"
                            if pos['speed'] is not None:
                                popup_text += f"<br>Speed: {pos['speed']:.1f} knots"
                            
                            folium.Marker(
                                [pos['lat'], pos['lon']],
                                popup=popup_text,
                                icon=folium.Icon(color='red', icon='info-sign')
                            ).add_to(marker_cluster)
                else:
                    # Add individual markers
                    sample_rate = max(1, len(sorted_positions) // 500)  # Limit to ~500 markers
                    for i, pos in enumerate(sorted_positions[::sample_rate]):
                        popup_text = f"Time: {pos['timestamp']}<br>Lat: {pos['lat']:.4f}<br>Lon: {pos['lon']:.4f}"
                        if pos['speed'] is not None:
                            popup_text += f"<br>Speed: {pos['speed']:.1f} knots"
                        
                        folium.Marker(
                            [pos['lat'], pos['lon']],
                            popup=popup_text,
                            icon=folium.Icon(color='red', icon='info-sign')
                        ).add_to(m)
            
            self.root.after(0, lambda: self.progress_var.set(75))
            
            # Add start/end markers
            if len(sorted_positions) > 1:
                start_pos = sorted_positions[0]
                end_pos = sorted_positions[-1]
                
                folium.Marker(
                    [start_pos['lat'], start_pos['lon']],
                    popup=f"Start: {start_pos['timestamp']}",
                    icon=folium.Icon(color='green', icon='play')
                ).add_to(m)
                
                folium.Marker(
                    [end_pos['lat'], end_pos['lon']],
                    popup=f"End: {end_pos['timestamp']}",
                    icon=folium.Icon(color='red', icon='stop')
                ).add_to(m)
            
            # Add layer control
            folium.LayerControl().add_to(m)
            
            # Save map to temporary file and open
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False)
            m.save(temp_file.name)
            temp_file.close()
            
            self.root.after(0, lambda: self.progress_var.set(100))
            self.root.after(0, lambda: self.status_var.set("Map generated successfully"))
            
            # Open in browser
            webbrowser.open(f'file://{temp_file.name}')
            
            # Re-enable button
            self.root.after(0, lambda: self.generate_btn.config(state="normal"))
            
        except Exception as e:
            error_msg = f"Error generating map: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.root.after(0, lambda: self.status_var.set("Error generating map"))
            self.root.after(0, lambda: self.generate_btn.config(state="normal"))
    
    def clear_data(self):
        """Clear loaded GPS data"""
        self.gps_positions = []
        self.unique_positions = set()
        self.stats_var.set("No data loaded")
        self.status_var.set("Data cleared")
        self.progress_var.set(0)
        self.generate_btn.config(state="disabled")

def main():
    """Main function"""
    root = tk.Tk()
    app = GPSMapViewer(root)
    root.mainloop()

if __name__ == "__main__":
    main()
