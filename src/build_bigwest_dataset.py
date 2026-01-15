import re
import time
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from rapidfuzz import process, fuzz

print("SCRIPT STARTED (CSV-DRIVEN BIG WEST DATASET BUILDER v2.4 + ANALYSIS)")

# ----------------------------
# Paths
# ----------------------------
THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[1]          # .../BigWestAnalytics
DATA_DIR = PROJECT_ROOT / "data"

SEASON_YEAR = 2025

CSV_NAME = "Big West Individual Data.csv"
PLAYER_CSV_PATH = DATA_DIR / CSV_NAME
OUT_PATH = DATA_DIR / f"bigwest_{SEASON_YEAR}_team_dataset.csv"

# ----------------------------
# Web (standings only)
# ----------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

BIG_WEST_CONF_URL = f"https://www.sports-reference.com/cbb/conferences/big-west/men/{SEASON_YEAR}.html"


def fetch_html(url: str) -> str:
    print(f"Fetching: {url}")
    for attempt in range(3):
        r = requests.get(url, headers=HEADERS, timeout=30)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            time.sleep(1)
            return r.text
        if r.status_code == 404:
            break
        time.sleep(2 + attempt)
    raise RuntimeError(f"Failed to fetch {url}")


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join([str(x).strip() for x in col if str(x).strip() != "nan"]).strip()
            for col in df.columns.values
        ]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    return df


def get_big_west_standings() -> pd.DataFrame:
    html = fetch_html(BIG_WEST_CONF_URL)
    dfs = pd.read_html(StringIO(html))

    target = None
    for d in dfs:
        d = flatten_columns(d.copy())
        cols = [c.lower() for c in d.columns]
        if any("school" in c for c in cols) and "overall w" in cols and "overall l" in cols:
            target = d.copy()
            break

    if target is None:
        raise RuntimeError("Could not locate standings table on Big West page.")

    school_col = [c for c in target.columns if "school" in c.lower()][0]
    out = target[[school_col, "Overall W", "Overall L"]].copy()
    out.columns = ["Team", "W", "L"]

    out = out.dropna(subset=["Team"])
    out["W"] = pd.to_numeric(out["W"], errors="coerce")
    out["L"] = pd.to_numeric(out["L"], errors="coerce")
    out = out.dropna(subset=["W", "L"])

    out["Team"] = out["Team"].astype(str).str.strip()
    out["WinPct"] = out["W"] / (out["W"] + out["L"])

    # Sanity check: WinPct must be in [0, 1]
    bad = ~out["WinPct"].between(0, 1) | out["WinPct"].isna()
    if bad.any():
        raise ValueError(
            "WinPct sanity check failed in standings:\n"
            + out.loc[bad, ["Team", "W", "L", "WinPct"]].to_string(index=False)
        )

    return out.reset_index(drop=True)


# ----------------------------
# Team-name normalization
# ----------------------------
def canon_team(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.lower().strip()
    s = s.replace("&", "and")
    s = re.sub(r"[.\u00a0]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    s = s.replace("cal st ", "cal state ")
    s = s.replace("cal st", "cal state")
    s = s.replace("csu ", "cal state ")

    s = s.replace("ucsb", "uc santa barbara")
    s = s.replace("ucsd", "uc san diego")
    s = s.replace("uci", "uc irvine")
    s = s.replace("ucd", "uc davis")
    s = s.replace("ucr", "uc riverside")

    if "long beach" in s and "state" not in s:
        s = "long beach state"

    s = re.sub(r"\s+", " ", s).strip()
    return s


# ----------------------------
# CSV cleaning
# ----------------------------
CLASS_VALUES = {"fr", "so", "jr", "sr", "gr"}


def is_dateish(x: str) -> bool:
    if not isinstance(x, str):
        return False
    x = x.strip()
    return bool(re.match(r"^\d{1,2}-[A-Za-z]{3}$", x) or re.match(r"^[A-Za-z]{3}-\d{2}$", x))


def parse_made_attempts(x):
    """
    For fields like:
      - "18-49" -> attempts = 49
      - "145" -> 145
      - other weird strings -> NaN
    """
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)

    s = str(x).strip()
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", s)
    if m:
        return float(int(m.group(2)))

    s = s.replace(",", "").replace("%", "")
    return pd.to_numeric(s, errors="coerce")


def load_and_clean_player_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"Could not find CSV at: {path}")

    df = pd.read_csv(path, dtype=str)
    df = df.dropna(axis=1, how="all")

    if "Team" not in df.columns:
        raise RuntimeError(f"CSV missing 'Team'. Columns seen: {list(df.columns)}")

    # Fix misaligned Player fields:
    # Player column might contain class ("Sr"), next col is date-ish ("7-Jun"), next col is real player name
    if "Player" in df.columns:
        sample = df["Player"].dropna().astype(str).head(30).str.lower().str.strip()
        class_like = (sample.isin(CLASS_VALUES)).mean() > 0.6

        cols = list(df.columns)
        p_idx = cols.index("Player")
        col_after_1 = cols[p_idx + 1] if p_idx + 1 < len(cols) else None
        col_after_2 = cols[p_idx + 2] if p_idx + 2 < len(cols) else None

        if class_like and col_after_1 and col_after_2:
            mid_sample = df[col_after_1].dropna().astype(str).head(30)
            if (mid_sample.apply(is_dateish).mean() > 0.5):
                df = df.rename(columns={"Player": "Class", col_after_1: "DateCol", col_after_2: "Player"})

    df["Team"] = df["Team"].astype(str).str.strip()

    wanted = [
        "Player", "Team", "Role", "Min%", "Usg", "D-PRPG", "D-Rtg",
        "OR", "DR", "Blk", "Stl", "FTR", "FTA"
    ]
    keep = [c for c in wanted if c in df.columns]
    df = df[keep].copy()

    # Convert numeric-ish columns
    numeric_cols = ["Min%", "Usg", "D-PRPG", "D-Rtg", "OR", "DR", "Blk", "Stl", "FTR"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "", regex=False), errors="coerce")

    # FTA is a season total in your table; keep as attempts (numeric)
    df["FTA_att"] = df["FTA"].apply(parse_made_attempts) if "FTA" in df.columns else np.nan

    if "Min%" not in df.columns:
        raise RuntimeError("CSV must include 'Min%' for minutes-weighting.")

    df["Min%"] = pd.to_numeric(df["Min%"], errors="coerce").clip(lower=0)
    df = df.dropna(subset=["Team", "Min%"])
    return df


# ----------------------------
# Aggregation (minutes-weighted)
# ----------------------------
def weighted_avg(series: pd.Series, weights: pd.Series) -> float:
    m = series.notna() & weights.notna()
    if m.sum() == 0:
        return np.nan
    s = series[m].astype(float)
    w = weights[m].astype(float)
    if w.sum() == 0:
        return np.nan
    return float(np.average(s, weights=w))


def aggregate_to_team_level(players: pd.DataFrame) -> pd.DataFrame:
    """
    Team metrics:
      - Defense: minutes-weighted
      - Foul pressure: usage-involvement weighted FTR (Min% * Usg)
      - Keep minutes-weighted FTR as a comparison column
    """
    df = players.copy()
    df["TeamCanon"] = df["Team"].apply(canon_team)

    # Ensure columns exist
    for c in ["OR", "D-Rtg", "Usg", "D-PRPG", "DR", "Blk", "Stl", "FTR", "FTA_att"]:
        if c not in df.columns:
            df[c] = np.nan

    out_rows = []
    for tcanon, g in df.groupby("TeamCanon", dropna=False):
        w_min = g["Min%"]
        w_usage = g["Min%"] * g["Usg"]  # "offensive involvement" weight

        row = {
            "TeamCanon": tcanon,
            "players_in_csv": int(len(g)),
            "sum_MinPct": float(g["Min%"].sum(skipna=True)),

            # Defense (minutes-weighted)
            "w_D_Rtg": weighted_avg(g["D-Rtg"], w_min),
            "w_D_PRPG": weighted_avg(g["D-PRPG"], w_min),
            "w_DefBox": (
                weighted_avg(g["DR"], w_min)
                + weighted_avg(g["Blk"], w_min)
                + weighted_avg(g["Stl"], w_min)
            ),

            # Offense / roster context
            "w_Usg": weighted_avg(g["Usg"], w_min),
            "w_OR": weighted_avg(g["OR"], w_min),

            # Foul pressure
            "w_FoulPressure": weighted_avg(g["FTR"], w_usage),  # PRIMARY
            "w_FTR_minwt": weighted_avg(g["FTR"], w_min),       # comparison
            "w_FTA_att": weighted_avg(g["FTA_att"], w_min),     # volume context
        }

        # Top roles by minutes (optional)
        if "Role" in g.columns:
            role_minutes = (
                g.dropna(subset=["Role"])
                .groupby("Role")["Min%"]
                .sum()
                .sort_values(ascending=False)
            )
            top = role_minutes.head(3)
            row["TopRoles"] = "; ".join([f"{idx}:{val:.1f}" for idx, val in top.items()])
        else:
            row["TopRoles"] = ""

        out_rows.append(row)

    return pd.DataFrame(out_rows)


def merge_team_metrics(standings: pd.DataFrame, team_metrics: pd.DataFrame) -> pd.DataFrame:
    s = standings.copy()
    s["TeamCanon"] = s["Team"].apply(canon_team)

    m = team_metrics.copy()
    out = s.merge(m, on="TeamCanon", how="left")

    # Fuzzy fill remaining misses
    missing = out["players_in_csv"].isna()
    if missing.any():
        metric_keys = m["TeamCanon"].tolist()
        metric_map = {k: row for k, row in m.set_index("TeamCanon").iterrows()}

        for idx in out[missing].index:
            key = out.at[idx, "TeamCanon"]
            match = process.extractOne(key, metric_keys, scorer=fuzz.WRatio)
            if match and match[1] >= 80:
                row = metric_map[match[0]]
                for col in m.columns:
                    if col == "TeamCanon":
                        continue
                    out.at[idx, col] = row[col]

    return out


# ----------------------------
# Analysis helpers
# ----------------------------
def corr_table(df: pd.DataFrame, y: str, xs: list[str]) -> pd.DataFrame:
    rows = []
    for x in xs:
        if x not in df.columns:
            continue
        sub = df[[y, x]].dropna()
        if len(sub) < 5:
            rows.append((x, np.nan, len(sub)))
            continue
        rows.append((x, float(sub[y].corr(sub[x])), len(sub)))
    return pd.DataFrame(rows, columns=["Metric", "PearsonCorr", "N"]).sort_values("PearsonCorr", ascending=False)


def simple_ols(df: pd.DataFrame, y: str, x: str):
    sub = df[[y, x]].dropna()
    n = len(sub)
    if n < 5:
        return (x, np.nan, np.nan, np.nan, n)

    X = sub[x].astype(float).values
    Y = sub[y].astype(float).values

    X1 = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(X1, Y, rcond=None)
    intercept, slope = beta[0], beta[1]

    yhat = X1 @ beta
    ss_res = np.sum((Y - yhat) ** 2)
    ss_tot = np.sum((Y - Y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else np.nan
    return (x, float(slope), float(intercept), float(r2), n)


# ----------------------------
# Main
# ----------------------------
def main():
    print("MAIN STARTED")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    standings = get_big_west_standings()
    print(f"Standings teams found: {len(standings)}")

    print(f"Loading player CSV: {PLAYER_CSV_PATH}")
    players = load_and_clean_player_csv(PLAYER_CSV_PATH)
    print(f"Player rows loaded: {len(players)}")

    print("Aggregating to team level (minutes-weighted)...")
    team_metrics = aggregate_to_team_level(players)

    df = merge_team_metrics(standings, team_metrics)

    # Sanity check (post-merge)
    if not df["WinPct"].between(0, 1).all():
        raise ValueError("WinPct outside [0,1] after merge — unexpected.")

    df.to_csv(OUT_PATH, index=False)
    print(f"Saved: {OUT_PATH}")

    # Preview table (ordered, clean)
    show_cols = [
        "Team", "W", "L", "WinPct",
        "players_in_csv", "sum_MinPct",
        "w_D_Rtg", "w_D_PRPG",
        "w_FoulPressure", "w_FTR_minwt", "w_FTA_att",
        "w_DefBox", "w_Usg", "w_OR",
    ]
    show_cols = [c for c in show_cols if c in df.columns]
    pd.set_option("display.width", 200)
    print(df.sort_values("WinPct", ascending=False)[show_cols].to_string(index=False))

    # Print TopRoles cleanly
    if "TopRoles" in df.columns:
        print("\nTopRoles (clean):")
        tr = df.sort_values("WinPct", ascending=False)[["Team", "TopRoles"]].copy()
        for _, r in tr.iterrows():
            print(f"  {r['Team']}: {r['TopRoles']}")

    # Analysis: correlations + simple regressions vs WinPct
    metrics = [
        "w_D_PRPG", "w_D_Rtg",
        "w_FoulPressure", "w_FTR_minwt", "w_FTA_att",
        "w_DefBox", "w_Usg", "w_OR",
    ]

    print("\nCorrelation with WinPct:")
    print(corr_table(df, "WinPct", metrics).to_string(index=False))

    print("\nSimple OLS (WinPct ~ metric):")
    ols_rows = [simple_ols(df, "WinPct", m) for m in metrics if m in df.columns]
    ols_df = (
        pd.DataFrame(ols_rows, columns=["Metric", "Slope", "Intercept", "R2", "N"])
        .sort_values("R2", ascending=False)
    )
    print(ols_df.to_string(index=False))


if __name__ == "__main__":
    main()
