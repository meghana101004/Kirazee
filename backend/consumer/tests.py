import pandas as pd
import os

# Path to your CSV file (update if needed)
csv_file = "F:\\menu_Items.csv"

# Path to save SQL file in Downloads folder
downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
sql_file = os.path.join(downloads_folder, "menu_items.sql")

# Load CSV
df = pd.read_csv(csv_file)

# Function to escape SQL values
def escape_sql(value):
    if pd.isna(value):
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)

# Build SQL INSERT statements
table_name = "kirazee.menuItems"
insert_statements = []
for _, row in df.iterrows():
    values = [escape_sql(v) for v in row]
    sql = f"INSERT INTO {table_name} ({', '.join(df.columns)}) VALUES ({', '.join(values)});"
    insert_statements.append(sql)

# Save to file
with open(sql_file, "w", encoding="utf-8") as f:
    f.write("\n".join(insert_statements))

print(f"✅ SQL file saved to: {sql_file}")
