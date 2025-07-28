# CSV Data Analyzer for VenusOS DbusLogger

A Python script that analyzes CSV files containing GPS and electrical data from VenusOS DbusLogger to calculate total distance traveled and engine efficiency.

## Features

- **Distance Calculation**: Calculates total distance traveled using accurate geodesic (great circle) distance formulas
- **Engine Efficiency Analysis**: Computes watts per knot efficiency metrics
- **Data Visualization**: Generates comprehensive plots showing efficiency trends and relationships
- **Batch Processing**: Processes multiple CSV files from a folder automatically
- **Data Cleaning**: Handles invalid GPS coordinates and electrical readings
- **Summary Reports**: Generates detailed analysis reports

## CSV Data Format

The script expects CSV files with the following header format:
```
timestamp,soc,voltage,current,gps_lat,gps_lon,gps_speed
```

Where:
- `timestamp`: Date/time stamp
- `soc`: State of charge (%)
- `voltage`: Electrical voltage (V)
- `current`: Electrical current (A)
- `gps_lat`: GPS latitude (decimal degrees)
- `gps_lon`: GPS longitude (decimal degrees)
- `gps_speed`: GPS speed (m/s)

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
- Progress information during processing
- Summary statistics including total distance and average efficiency

### Files Generated
- `efficiency_analysis.png`: Multi-panel visualization showing:
  - Efficiency over time
  - Efficiency vs speed relationship
  - Power vs speed relationship
  - Efficiency distribution histogram
- `analysis_summary.txt`: Detailed text report with statistics

### Analysis Metrics

- **Total Distance**: Sum of all GPS track segments in kilometers
- **Engine Efficiency**: Power consumption per unit of speed (watts per knot)
- **Speed Statistics**: Average and maximum speeds achieved
- **Power Statistics**: Average and maximum power consumption
- **Efficiency by Speed Range**: Performance analysis across different speed bands

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
