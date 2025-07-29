import pandas as pd
import glob

# Analyze current consumption patterns across multiple files
csv_files = glob.glob('logs/*.csv')
total_engine_consumption = 0
total_rows = 0

for i, file in enumerate(csv_files[:5]):  # Check first 5 files
    try:
        df = pd.read_csv(file)
        
        print(f'\nFile {i+1}: {file.split("/")[-1] if "/" in file else file.split("\\")[-1]}')
        print(f'  Total rows: {len(df)}')
        print(f'  Current range: {df["current"].min():.2f}A to {df["current"].max():.2f}A')
        
        negative_current = df[df['current'] < 0]
        print(f'  Negative current: {len(negative_current)} rows ({len(negative_current)/len(df)*100:.1f}%)')
        
        # Engine-level consumption (likely > 2A draw)
        engine_consumption = negative_current[negative_current['current'] <= -2.0]
        
        if len(engine_consumption) > 0:
            print(f'  Engine-level (<-2A): {len(engine_consumption)} rows')
            print(f'  Engine range: {engine_consumption["current"].min():.2f}A to {engine_consumption["current"].max():.2f}A')
            total_engine_consumption += len(engine_consumption)
        
        total_rows += len(df)
        
    except Exception as e:
        print(f'Error with {file}: {e}')

print(f'\nSummary:')
print(f'Total rows checked: {total_rows}')
print(f'Total engine-level consumption rows: {total_engine_consumption}')
print(f'Engine consumption percentage: {total_engine_consumption/total_rows*100:.1f}%')
