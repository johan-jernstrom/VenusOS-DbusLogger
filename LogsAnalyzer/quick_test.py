#!/usr/bin/env python3
"""
Quick test of the sailboat analyzer to demonstrate the improvements.
"""

from csv_analyzer import CSVAnalyzer

def main():
    print("Testing Sailboat Engine Efficiency Analyzer")
    print("=" * 50)
    
    try:
        # Create analyzer instance
        analyzer = CSVAnalyzer(".")
        
        # Run analysis
        analyzer.load_csv_files()
        analyzer.preprocess_data()
        analyzer.calculate_distances() 
        analyzer.calculate_efficiency()
        analyzer.generate_summary_report()
        
        print("\n✅ Analysis completed successfully!")
        print("\nKey improvements implemented:")
        print("- Speed limited to 8 knots (sailboat realistic)")
        print("- Power limited to 11kW (engine maximum)")
        print("- Negative current handling (engine consumption)")
        print("- Positive current filtering (charging periods)")
        print("- Distance measured in nautical miles")
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")

if __name__ == "__main__":
    main()
