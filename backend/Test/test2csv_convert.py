import pandas as pd

# 1. Load the Excel file
df = pd.read_excel("IP_List.xlsx")

# 2. Clean up column names (optional)
df.columns = [col.strip() for col in df.columns]

# 3. Ensure expected columns are present
if "Branch/Sub-Branch Name" not in df.columns or "IP List" not in df.columns:
    raise ValueError("Excel must have 'Branch Name' and 'IP Address' columns")

# 4. Extract subnet from IP address (e.g., 172.19.100.25 → 172.19.100.0/24)
df["Subnet"] = df["IP List"].apply(lambda ip: ".".join(str(ip).split('.')[:3]) + ".0/24")

# 5. Filter unique branch-subnet pairs
result = df[["Branch/Sub-Branch Name", "Subnet"]].drop_duplicates()

# 6. Print the result
print(result)

# Optional: save to CSV
result.to_csv("Branch_Subnet_List.csv", index=False)
