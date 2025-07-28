# Sailboat Engine Efficiency Analyzer for VenusOS DbusLogger

A Python script that analyzes CSV files containing GPS and electrical data from VenusOS DbusLogger to calculate sailboat engine efficiency, optimized for realistic sailboat performance parameters.

## Sailboat-Specific Features

- **Realistic Speed Filtering**: Removes data points with speeds over 8 knots (sailboat maximum)
- **Engine Power Limits**: Filters out power readings over 11kW (typical sailboat engine maximum)
- **Current Direction Handling**: 
  - Negative current = engine consumption (kept and converted to positive values)
  - Positive current = battery charging when docked (filtered out)
- **Nautical Mile Measurements**: All distances reported in nautical miles
- **Engine-Only Analysis**: Focuses on motoring efficiency, excludes sailing data

## Features

- **Distance Calculation**: Calculates total distance traveled using accurate geodesic formulas
- **Engine Efficiency Analysis**: Computes watts per knot efficiency metrics for motoring
- **Data Visualization**: Generates sailboat-specific plots with appropriate axis limits
- **Batch Processing**: Processes multiple CSV files from a folder automatically
- **Advanced Filtering**: Removes charging periods, speed outliers, and power anomalies
- **Detailed Reports**: Engine-focused analysis with speed range breakdowns

## CSV Data Format

The script expects CSV files with the following header format:
```
timestamp,soc,voltage,current,gps_lat,gps_lon,gps_speed
```

Where:
- `timestamp`: Date/time stamp
- `soc`: State of charge (%)
- `voltage`: Electrical voltage (V)
- `current`: Electrical current (A) - **NEGATIVE for engine consumption, POSITIVE for battery charging**
- `gps_lat`: GPS latitude (decimal degrees)
- `gps_lon`: GPS longitude (decimal degrees)
- `gps_speed`: GPS speed (m/s)

**Important**: Current values should be negative when the engine is consuming power and positive when batteries are being charged (typically when docked).

## Installation

1. Make sure you have Python 3.7+ installed
2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Place your CSV files in a folder
2. Run the analyzer:
   ```bash
   python csv_analyzer.py
   ```
3. Enter the path to your CSV folder when prompted (or press Enter for current directory)

## Output

The script generates:

### Console Output
- Progress information with filtering statistics
- Summary statistics including total distance in nautical miles and average efficiency
- Engine-specific performance metrics

### Files Generated
- `sailboat_efficiency_analysis.png`: Multi-panel visualization showing:
  - Engine efficiency over time
  - Efficiency vs speed relationship (0-8 knots)
  - Power consumption vs speed (0-11kW limit)
  - Efficiency distribution histogram
- `sailboat_analysis_summary.txt`: Detailed text report with sailboat-specific statistics

### Analysis Metrics

- **Total Distance**: Sum of all GPS track segments in nautical miles
- **Engine Efficiency**: Power consumption per unit of speed (watts per knot)
- **Speed Statistics**: Average and maximum speeds under engine power only
- **Power Statistics**: Average and maximum power consumption (filtered for 11kW limit)
- **Efficiency by Speed Range**: Performance analysis across sailboat speed bands (0-2, 2-4, 4-6, 6-8 knots)

## Data Processing

The script performs several data cleaning and preprocessing steps:

1. **Validation**: Checks for required CSV columns
2. **Timestamp Conversion**: Converts timestamps to datetime objects
3. **GPS Filtering**: Removes invalid coordinates (0,0 or NaN)
4. **Power Calculation**: Computes electrical power (voltage × current)
5. **Unit Conversion**: Converts GPS speed from m/s to knots
6. **Distance Calculation**: Uses geodesic formulas for accurate distance measurement
7. **Efficiency Filtering**: Removes stationary points and extreme outliers

## Technical Details

### Dependencies
- **pandas**: Data manipulation and CSV parsing
- **numpy**: Numerical computations
- **matplotlib**: Plotting and visualization
- **geopy**: GPS distance calculations using geodesic formulas

### Efficiency Calculation
Engine efficiency is calculated as:
```
Efficiency (watts/knot) = Power (watts) / Speed (knots)
```

Where:
- Power = Voltage × Current
- Speed conversion: 1 m/s = 1.94384 knots

### Distance Calculation
Uses the geodesic distance formula to account for Earth's curvature, providing more accurate results than simple Euclidean distance for GPS coordinates.

## Configuration

The script includes several configurable parameters:

- **Minimum Speed Filter**: 0.5 knots (filters out stationary readings)
- **Maximum Efficiency Filter**: 1000 watts/knot (removes extreme outliers)
- **Speed Range Categories**: 
  - Very slow: 0-2 knots
  - Slow: 2-5 knots
  - Medium: 5-8 knots
  - Fast: 8+ knots

## Troubleshooting

### Common Issues

1. **No CSV files found**: Ensure CSV files are in the specified folder
2. **Missing columns**: Verify CSV files have the correct header format
3. **No movement data**: Check that GPS speed values are present and non-zero
4. **Import errors**: Install missing dependencies with `pip install -r requirements.txt`

### Data Quality Tips

- Ensure GPS coordinates are valid (not 0,0)
- Check that electrical readings (voltage/current) are reasonable
- Verify timestamps are in a recognizable format
- Remove or fix corrupted data rows before analysis

## License

This project is open source and available under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.
