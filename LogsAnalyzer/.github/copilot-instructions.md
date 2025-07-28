<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

# Sailboat Engine Efficiency Analyzer Instructions

This project analyzes CSV files from VenusOS DbusLogger containing GPS and electrical data, specifically optimized for sailboat engine performance analysis.

## Project Context
- **Purpose**: Analyze sailboat engine efficiency and distance traveled under engine power
- **Data Format**: CSV files with columns: timestamp, soc, voltage, current, gps_lat, gps_lon, gps_speed
- **Key Focus**: Engine-only analysis with realistic sailboat performance parameters

## Sailboat-Specific Filtering
- **Speed Limit**: Remove data points with speeds > 8 knots (sailboat maximum realistic speed)
- **Power Limit**: Filter out power readings > 11kW (typical sailboat engine maximum)
- **Current Direction**: 
  - Negative current = engine consumption (keep and convert to positive)
  - Positive current = battery charging when docked (filter out)
- **Distance Units**: Use nautical miles for all distance measurements
- **Efficiency Focus**: Analyze only motoring periods, exclude sailing data

## Key Calculations
- Distance calculation using geodesic formulas, converted to nautical miles
- Power calculation using absolute value of negative current (engine consumption)
- Efficiency calculation (watts per knot) for engine-only operation
- Speed conversion from m/s to knots (1 m/s = 1.94384 knots)
- Distance conversion from km to nautical miles (1 km = 0.539957 nm)

## Code Guidelines
- Use pandas for data manipulation and CSV parsing
- Use geopy for accurate GPS distance calculations  
- Use matplotlib for plotting with sailboat-appropriate axis limits (0-8 knots, 0-11kW)
- Handle current sign properly (negative = consumption, positive = charging)
- Filter out charging periods and speed/power outliers early in preprocessing
- Always include informative console output showing filtering statistics
- Save analysis results with sailboat-specific filenames
- Provide speed range analysis appropriate for sailboat performance (0-2, 2-4, 4-6, 6-8 knots)

## Data Processing Best Practices
- Validate CSV column headers before processing
- Apply sailboat-specific filtering in preprocessing phase
- Sort data chronologically before distance calculations
- Use appropriate units (nautical miles, knots, watts)
- Show filtering statistics to user (rows removed for each filter)
- Focus analysis on engine-only periods (negative current values)
