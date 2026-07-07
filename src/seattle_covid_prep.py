import pandas as pd

SRC = r"C:\Users\obiel\OneDrive\Documents\Tableau Data Files\Seattle Covid Traffic Infographic\call_data_2019-2021.csv"
OUT = r"C:\Users\obiel\OneDrive\Documents\Tableau Data Files\Seattle Covid Traffic Infographic"
NYT = "https://raw.githubusercontent.com/nytimes/covid-19-data/master/us-counties.csv"
KING_POP = 2_266_789  # 2020 Census

# --- 1. Calls: load only what's needed, dedupe to one row per call ---
cols = ["cadEventNumber", "originalTimeQueued", "eventGroup",
        "initialCallType", "finalCallType", "callTypeReceivedClassification"]
df = pd.read_csv(SRC, usecols=cols)
df["originalTimeQueued"] = pd.to_datetime(df["originalTimeQueued"])
calls = (df.sort_values("originalTimeQueued")
           .groupby("cadEventNumber", as_index=False).first())   # ~1.76 rows/call -> 1

# --- 2. Traffic flag (mirrors the Hyper SQL; STARTSWITH avoids *TRAFFICKING/NARCOTICS) ---
ict = calls["initialCallType"].fillna("").str.upper()
fct = calls["finalCallType"].fillna("").str.upper()

def traffic_ish(s):
    return (s.str.startswith("TRAFFIC") | s.str.contains("MVC")
            | s.str.startswith("DUI") | s.str.contains("ROAD RAGE")
            | s.eq("PARKING VIOLATION (EXCEPT ABANDONED CAR)")
            | s.eq("ABANDONED VEHICLE"))

calls["is_traffic"] = (calls["eventGroup"].eq("Traffic")
                       | traffic_ish(ict) | traffic_ish(fct))

def subcat(row_i, row_f):
    pairs = [("TRAFFIC STOP", "Traffic Stop"), ("MVC", "Collision / Hit & Run"),
             ("COLLISION", "Collision / Hit & Run"), ("PARKING", "Parking / Abandoned"),
             ("ABANDONED", "Parking / Abandoned"), ("D.U.I", "DUI"), ("DUI", "DUI"),
             ("MOVING VIOLATION", "Moving Violation"), ("ROAD RAGE", "Road Rage"),
             ("BLOCKING", "Blocking / Signals Out"), ("BO SIGNALS", "Blocking / Signals Out")]
    for key, label in pairs:
        if key in row_i or key in row_f:
            return label
    return "Other Traffic"

t = calls[calls["is_traffic"]].copy()
t["subcategory"] = [subcat(i, f) for i, f in zip(ict[calls["is_traffic"]], fct[calls["is_traffic"]])]
t["month"] = t["originalTimeQueued"].dt.to_period("M").dt.to_timestamp()
t = t[(t["month"] >= "2019-01-01") & (t["month"] <= "2021-12-01")]

# --- 3. Detail file: month x subcategory x classification (strip + small multiples) ---
detail = (t.groupby(["month", "subcategory", "callTypeReceivedClassification"])
            .size().reset_index(name="calls")
            .rename(columns={"callTypeReceivedClassification": "classification"}))
detail["quarter_start"] = detail["month"].dt.to_period("Q").dt.to_timestamp()
detail.to_csv(f"{OUT}\\traffic_monthly_detail.csv", index=False)

# --- 4. COVID: King County monthly new cases (NYT cumulative -> diff) ---
cv = pd.read_csv(NYT, usecols=["date", "county", "state", "cases"], parse_dates=["date"])
cv = cv[(cv["county"] == "King") & (cv["state"] == "Washington")].sort_values("date")
cv["new_cases"] = cv["cases"].diff().clip(lower=0)          # revisions -> negative diffs
covid = (cv.set_index("date")["new_cases"].resample("MS").sum()
           .loc["2019-01-01":"2021-12-01"].reset_index()
           .rename(columns={"date": "month"}))
covid["cases_per_100k"] = covid["new_cases"] / KING_POP * 100_000
covid.to_csv(f"{OUT}\\covid_king_monthly.csv", index=False)

# --- 5. Wheel file: month totals + COVID merged + path scaffold (0=hub, 1=tip) ---
wheel = t.groupby("month").size().reset_index(name="calls")
wheel = wheel.merge(covid, on="month", how="left").fillna({"new_cases": 0, "cases_per_100k": 0})
wheel["month_index"] = range(1, len(wheel) + 1)              # 1..36
wheel = wheel.loc[wheel.index.repeat(2)].reset_index(drop=True)
wheel["path"] = [0, 1] * (len(wheel) // 2)
wheel.to_csv(f"{OUT}\\wheel_traffic_covid.csv", index=False)
print(detail.shape, covid.shape, wheel.shape)   # sanity: (~700+, 5) (36, 3) (72, 6)