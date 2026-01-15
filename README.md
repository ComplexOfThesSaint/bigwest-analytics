# Big West Men’s Basketball Analytics (2024–25)

This project analyzes **team-level winning in Big West men’s basketball** by aggregating
player-level metrics into minutes-weighted team indicators and examining their
respective relationship with win percentage.

The focus is on **defensive impact**, **foul pressure**, and how these different forms of
player contribution scale to team success within Big West basketball.

---

## Key Questions
- Which team-level defensive indicators correlate most strongly with winning?
- Does defensive impact measured at the player level scale meaningfully to team success?
- How does *foul pressure* (drawing fouls / getting to the line) relate to win percentage?

---

## Data Sources
- **Team records**: Sports-Reference (Big West conference page, 2024–25)
- **Player metrics**: Exported Big West player table (minutes %, defensive impact, usage, fouls, etc.)

---

## Methodology
- Normalize team names across data sources
- Convert player metrics into **minutes-weighted team averages**
- Construct team-level indicators:
  - Defensive Rating (w_D_Rtg)
  - Defensive Points Reduced per Game (w_D_PRPG)
  - Defensive Box Score proxy (rebounds + blocks + steals)
  - Foul Pressure (minutes-weighted FTR and FTA)
  - Usage and offensive rebounding
- Evaluate relationships with:
  - Pearson correlations
  - Simple OLS regressions vs win percentage
- Generate publication-ready visualizations

---
## Results & Visualizations

### Defensive Rating vs Win Percentage
Lower defensive rating (better defense) is strongly associated with higher win percentage.

![WinPct vs Defensive Rating](data/figures/01_winpct_vs_def_rating.png)

### Defensive Impact (D-PRPG) vs Win Percentage
Minutes-weighted defensive points prevented per game shows a strong positive relationship with winning.

![WinPct vs D-PRPG](data/figures/02_winpct_vs_dprpg.png)

### Win Percentage by Team
Distribution of conference win percentage across Big West teams.

![WinPct by Team](data/figures/03_winpct_by_team.png)

### Correlation Summary
Comparison of team-level metrics by Pearson correlation with win percentage.

![Correlation Bar Chart](data/figures/04_correlation_bar.png)

---

## Outputs
- **Final dataset**:  
  `data/bigwest_2025_team_dataset.csv`

- **Figures** (auto-generated):  
  `data/figures/`
  - WinPct vs Defensive Rating  
  - WinPct vs D-PRPG  
  - WinPct by Team  
  - Correlation summary

---

## How to Run
```bash
python src/build_bigwest_dataset.py
python src/bigwest_figures.py
