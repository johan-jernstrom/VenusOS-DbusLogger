#!/usr/bin/env python3
"""
Test script to verify the CSV analyzer setup and dependencies.
"""

import sys
import os

def test_imports():
    """Test that all required packages can be imported."""
    print("Testing package imports...")
    
    try:
        import pandas as pd
        print(f"✓ pandas {pd.__version__}")
    except ImportError as e:
        print(f"✗ pandas: {e}")
        return False
    
    try:
        import numpy as np
        print(f"✓ numpy {np.__version__}")
    except ImportError as e:
        print(f"✗ numpy: {e}")
        return False
    
    try:
        import matplotlib
        print(f"✓ matplotlib {matplotlib.__version__}")
    except ImportError as e:
        print(f"✗ matplotlib: {e}")
        return False
    
    try:
        import geopy
        print(f"✓ geopy {geopy.__version__}")
    except ImportError as e:
        print(f"✗ geopy: {e}")
        return False
    
    return True

def test_sample_data():
    """Test that sample data can be loaded and processed."""
    print("\nTesting sample data loading...")
    
    try:
        import pandas as pd
        
        # Check if sample data exists
        sample_file = "sample_data.csv"
        if not os.path.exists(sample_file):
            print(f"✗ Sample data file '{sample_file}' not found")
            return False
        
        # Try to load sample data
        df = pd.read_csv(sample_file)
        print(f"✓ Sample data loaded: {len(df)} rows")
        
        # Check required columns
        required_columns = ['timestamp', 'soc', 'voltage', 'current', 'gps_lat', 'gps_lon', 'gps_speed']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"✗ Missing columns: {missing_columns}")
            return False
        
        print("✓ All required columns present")
        
        # Show data preview
        print("\nData preview:")
        print(df.head(3).to_string(index=False))
        
        return True
        
    except Exception as e:
        print(f"✗ Error loading sample data: {e}")
        return False

def main():
    """Run all tests."""
    print("CSV Analyzer Setup Test")
    print("=" * 40)
    
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print()
    
    # Test imports
    imports_ok = test_imports()
    
    # Test sample data
    data_ok = test_sample_data()
    
    print("\n" + "=" * 40)
    if imports_ok and data_ok:
        print("✓ All tests passed! The CSV analyzer is ready to use.")
        print("\nTo run the main analyzer:")
        print("python csv_analyzer.py")
    else:
        print("✗ Some tests failed. Please check the setup.")
    
    return imports_ok and data_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
