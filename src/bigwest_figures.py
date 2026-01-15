from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SEASON_YEAR = 2025

THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[1]
DATA_DIR = PROJECT_ROOT / "data"
FIG_DIR = DATA_DIR / "figures"

DATA_PATH = DATA_DIR / f"bigwest_{SEASON_YEAR}_team_dataset.csv"


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def add_regression_line(ax, x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 2:
        return
    b, a = np.polyfit(x[m], y[m], 1)  # y = a + b x
    xs = np.linspace(x[m].min(), x[m].max(), 200)
    ys = a + b * xs
    ax.plot(xs, ys, linewidth=2)


def corr(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 3:
        return np.nan
    return float(np.corrcoef(x[m], y[m])[0, 1])


def annotate_teams(ax, df, x_col, y_col):
    for _, row in df.iterrows():
        ax.annotate(
            row["Team"],
            (float(row[x_col]), float(row[y_col])),
            fontsize=8,
            xytext=(4, 4),
            textcoords="offset points",
        )


def style_axes(ax):
    # Small “clean + smooth” style without extra deps
    ax.grid(True, alpha=0.25, linewidth=0.8)
    ax.set_axisbelow(True)


def add_r_label(ax, r):
    ax.text(
        0.02, 0.98,
        f"Pearson r = {r:.3f}" if np.isfinite(r) else "Pearson r = n/a",
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.25", alpha=0.15, linewidth=0),
    )


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found at: {DATA_PATH}. Run build_bigwest_dataset.py first.")

    ensure_dir(FIG_DIR)

    df = pd.read_csv(DATA_PATH).sort_values("WinPct", ascending=False).reset_index(drop=True)

    # ----------------------------
    # 1) Scatter: WinPct vs Defensive Rating (invert x-axis: lower is better)
    # ----------------------------
    x = df["w_D_Rtg"].astype(float).values
    y = df["WinPct"].astype(float).values
    r = corr(x, y)

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(x, y, s=55, alpha=0.85)
    add_regression_line(ax, x, y)
    style_axes(ax)
    ax.set_xlabel("Minutes-weighted Defensive Rating (w_D_Rtg) — lower is better")
    ax.set_ylabel("Win Percentage (WinPct)")
    ax.set_title("Big West 2024–25: WinPct vs Defensive Rating")
    add_r_label(ax, r)
    annotate_teams(ax, df, "w_D_Rtg", "WinPct")
    ax.invert_xaxis()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "01_winpct_vs_def_rating.png", dpi=220)
    plt.close(fig)

    # ----------------------------
    # 2) Scatter: WinPct vs D-PRPG
    # ----------------------------
    x = df["w_D_PRPG"].astype(float).values
    y = df["WinPct"].astype(float).values
    r = corr(x, y)

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(x, y, s=55, alpha=0.85)
    add_regression_line(ax, x, y)
    style_axes(ax)
    ax.set_xlabel("Minutes-weighted D-PRPG (w_D_PRPG) — higher = more defensive impact")
    ax.set_ylabel("Win Percentage (WinPct)")
    ax.set_title("Big West 2024–25: WinPct vs D-PRPG")
    add_r_label(ax, r)
    annotate_teams(ax, df, "w_D_PRPG", "WinPct")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "02_winpct_vs_dprpg.png", dpi=220)
    plt.close(fig)

    # ----------------------------
    # 3) Bar: Teams sorted by WinPct
    # ----------------------------
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(df["Team"], df["WinPct"], alpha=0.9)
    style_axes(ax)
    ax.set_xlabel("Team")
    ax.set_ylabel("Win Percentage (WinPct)")
    ax.set_title("Big West 2024–25: WinPct by Team")
    ax.tick_params(axis="x", rotation=45)
    plt.setp(ax.get_xticklabels(), ha="right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "03_winpct_by_team.png", dpi=220)
    plt.close(fig)

    # ----------------------------
    # 4) Correlation bar chart
    # ----------------------------
    metrics = ["w_D_PRPG", "w_D_Rtg", "w_FoulPressure", "w_FTA_att", "w_DefBox", "w_Usg", "w_OR", "w_FTR_minwt"]
    rows = []
    for m in metrics:
        if m in df.columns:
            sub = df[["WinPct", m]].dropna()
            rows.append((m, float(sub["WinPct"].corr(sub[m])) if len(sub) >= 5 else np.nan))

    cor_df = pd.DataFrame(rows, columns=["Metric", "PearsonCorr"]).sort_values("PearsonCorr", ascending=False)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(cor_df["Metric"], cor_df["PearsonCorr"], alpha=0.9)
    style_axes(ax)
    ax.set_xlabel("Metric")
    ax.set_ylabel("Pearson correlation with WinPct")
    ax.set_title("Big West 2024–25: Correlation with WinPct (Team-level)")
    ax.tick_params(axis="x", rotation=45)
    plt.setp(ax.get_xticklabels(), ha="right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "04_correlation_bar.png", dpi=220)
    plt.close(fig)

    # ----------------------------
    # 5) Scatter: WinPct vs Foul Pressure (PRIMARY)
    # ----------------------------
    # Prefer w_FoulPressure (usage-weighted FTR). Fall back gracefully if missing.
    foul_col = "w_FoulPressure" if "w_FoulPressure" in df.columns else ("w_FTR_minwt" if "w_FTR_minwt" in df.columns else None)

    if foul_col is not None:
        x = df[foul_col].astype(float).values
        y = df["WinPct"].astype(float).values
        r = corr(x, y)

        fig, ax = plt.subplots(figsize=(9, 6))
        ax.scatter(x, y, s=55, alpha=0.85)
        add_regression_line(ax, x, y)
        style_axes(ax)

        if foul_col == "w_FoulPressure":
            ax.set_xlabel("Foul Pressure (usage-weighted FTR: Min% × Usg weights) — higher = more pressure")
            ax.set_title("Big West 2024–25: WinPct vs Foul Pressure (Usage-weighted)")
        else:
            ax.set_xlabel("Foul Pressure (minutes-weighted FTR) — higher = more pressure")
            ax.set_title("Big West 2024–25: WinPct vs Foul Pressure (Minutes-weighted)")

        ax.set_ylabel("Win Percentage (WinPct)")
        add_r_label(ax, r)
        annotate_teams(ax, df, foul_col, "WinPct")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "05_winpct_vs_foul_pressure.png", dpi=220)
        plt.close(fig)

    print(f"Saved figures to: {FIG_DIR}")


if __name__ == "__main__":
    main()
