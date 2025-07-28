<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

# CSV Data Analyzer Project Instructions

This project analyzes CSV files from VenusOS DbusLogger containing GPS and electrical data.

## Project Context
- **Purpose**: Parse CSV files to calculate total distance traveled and engine efficiency (watts per knot)
- **Data Format**: CSV files with columns: timestamp, soc, voltage, current, gps_lat, gps_lon, gps_speed
- **Key Calculations**: 
  - Distance calculation using geodesic formulas
  - Power calculation (voltage × current)
  - Efficiency calculation (watts per knot)
  - Speed conversion from m/s to knots

## Code Guidelines
- Use pandas for data manipulation and CSV parsing
- Use geopy for accurate GPS distance calculations  
- Use matplotlib for plotting and visualization
- Handle missing/invalid GPS coordinates (0,0 or NaN values)
- Filter out stationary points (speed < 0.5 knots) for efficiency calculations
- Remove efficiency outliers (> 1000 watts/knot)
- Always include error handling for file I/O operations
- Provide informative console output during processing
- Save analysis results and plots to files

## Data Processing Best Practices
- Validate CSV column headers before processing
- Convert timestamps to datetime objects for proper sorting
- Clean data by removing invalid GPS coordinates and electrical readings
- Sort data chronologically before distance calculations
- Use appropriate units (km for distance, knots for speed, watts for power)

## Visualization Requirements
- Create multi-panel plots showing efficiency trends
- Include efficiency over time, efficiency vs speed, power vs speed, and distribution plots
- Save plots as high-resolution PNG files
- Use appropriate alpha values for scatter plots with many points
