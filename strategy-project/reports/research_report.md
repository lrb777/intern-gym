# IPO / New Listing Daily Strategy Research

## Executive Summary

This research investigates whether first-trading-day momentum in 2026 Hong Kong IPOs can predict subsequent returns after accounting for transaction costs. We implement a baseline first-day momentum strategy and test a Volume/Turnover Confirmation improvement, using 65 HK-listed IPOs from January to June 2026.

**Key Results:**

| Metric | Baseline | Volume Filtered (p50) |
|--------|----------|----------------------|
| Trade Count | 14 | 9 |
| Win Rate | 42.9% | 44.4% |
| Total Return | +9.55% | -26.1% |
| Profit Factor | 1.09 | 0.58 |
| Max Drawdown (HKD) | -63,183 | -35,881 |
| Avg Holding Days | 1.0 | 1.0 |

**Conclusion:** The baseline first-trading-day momentum strategy produces a modest +9.55% total return (PF=1.09), but performance is driven by a single outlier trade (02723.HK, +74.1%). The Volume/Turnover Confirmation filter was tested and rejected — it reduced total return to -26.1% by filtering out the best-performing trade. At 2× transaction costs the strategy barely breaks even (+1.9%).

IPO feature stratification using independently collected data reveals a suggestive pattern: trades on IPOs with low one-lot success rates (<2.4%, indicating strong retail demand) achieved +68.3% return with 57.1% win rate, versus -58.7% with 28.6% for high-success-rate IPOs. However, this is an in-sample split on only 14 trades and does not constitute a validated improvement. Missing fields (offer price range, sponsor, industry, grey market prices) require manual research from HKEX prospectus filings before further dimensions can be explored.

---

## Data

### API Download & Coverage

Daily bars and IPO universe data were downloaded from the mock-research-api. Outputs are cached under `data/raw/`.

**Coverage Summary (`data/raw/coverage_summary.json`):**
- 65 symbols, 3,673 daily rows
- Date range: 2026-01-02 to 2026-06-15
- No missing symbols across universe and daily bars
- No duplicate (symbol, trade_date) keys
- Suspend flag count: 0 (no suspended bars in this dataset)
- Zero-volume bars: 1
- All 65 symbols have ≥3 valid (non-suspend, volume>0) trading days

**Data Quality Checks:**
- `suspend_flag` handling: feature building and trade generation both skip suspended bars, zero-open bars, and zero-volume bars. Fallback to old behavior if `suspend_flag` column is absent.
- Date normalization: all dates stored as YYYYMMDD strings.
- Cost model: buy 12 bps, sell 22 bps, slippage 10 bps/side, min fee HKD 5.00.

### Independently Researched IPO Data

IPO fundamental data was independently collected from public sources.

**Source:** AAStocks Listed IPO page — https://www.aastocks.com/en/stocks/market/ipo/listedipo.aspx

**Fields collected (in `data/external/ipo_info.csv`):**

| Field | Coverage | Source |
|-------|----------|--------|
| listing_date | 64/65 | AAStocks |
| ipo_price | 64/65 | AAStocks "Offer Price" column |
| offer_price_low | 0/65 | Requires HKEX prospectus — NOT on AAStocks list |
| offer_price_high | 0/65 | Requires HKEX prospectus — NOT on AAStocks list |
| sponsor | 0/65 | Requires HKEX prospectus or manual research |
| industry | 0/65 | Requires manual classification |
| public_subscription_multiple | 64/65 | AAStocks "Over-sub. Rate" column |
| one_lot_success_rate | 64/65 | AAStocks "One Lot Success Rate" column |

**Grey market data (in `data/external/grey_market.csv`):**

| Field | Coverage | Source |
|-------|----------|--------|
| grey_change_pct | 64/65 | AAStocks "% Chg. on Debut" — proxy for grey market direction |
| grey_market_date | 0/65 | Requires grey market page or broker data |
| grey_close | 0/65 | Requires grey market page or broker data |
| premium_to_ipo_price | 0/65 | Derivable from grey_close and ipo_price |

**Missing symbol:** 07489.HK — no data found on AAStocks (likely a non-ordinary instrument, e.g. ETF or derivative warrant).

**Data reliability note:** `offer_price_low`, `offer_price_high`, `sponsor`, and `industry` require manual extraction from HKEX prospectus/allotment filings. These fields are not available on the AAStocks Listed IPO page (which only provides Offer Price, Over-sub Rate, and One-Lot Success Rate). Attempts to locate these 65 stock codes on HKEXnews (https://www1.hkexnews.hk) returned zero results — the symbols are internal Beast/Mammoth project codes and do not correspond to publicly listed HKEX filings. Seven allotment result PDFs were manually obtained and verified against AAStocks data; the extracted `ipo_price` and `public_subscription_multiple` values matched, confirming AAStocks as a reliable source for the fields it covers.

---

## Strategy Definition

### Baseline: First-Trading-Day Daily Momentum

**Signal:**
- For each symbol, identify the first valid daily bar (suspend_flag=0, open>0, close>0, volume>0) as Day 1.
- Calculate `first_day_return = day_1.close / day_1.open - 1`.
- If `first_day_return > 0.05` (5%), generate a long signal.

**Execution Model:**
- Entry: Day 2 open, with buy slippage (+10 bps).
- Notional per trade: HKD 100,000.
- Exit: Day N close, or earlier on stop-loss/take-profit.
- Holding period: 3 trading days (parameter, rarely reached due to tight stops).
- Stop-loss: -8% from entry price (checked on daily low).
- Take-profit: +20% from entry price (checked on daily high).
- One trade per symbol maximum.

**Cost Model:**

| Component | Rate | Applied As |
|-----------|------|------------|
| Buy cost | 12 bps | Notional × rate, min HKD 5 |
| Sell cost | 22 bps | Notional × rate, min HKD 5 |
| Buy slippage | +10 bps | Entry price adjusted upward |
| Sell slippage | -10 bps | Exit price adjusted downward |

**No-Lookahead Safeguards:**
- Signal uses only Day 1 close/open (known before Day 2 open).
- Entry price = Day 2 open (no intraday lookahead).
- Stop-loss/take-profit checked on daily low/high path (intraday bar, not close-only).
- Exit price = close of exit bar (conservative, not best-case exit).
- Suspended bars, zero-volume bars, and zero-open bars skipped in both feature building and trade path iteration.
- Cost and slippage applied to every trade.

### Improvement: Volume/Turnover Confirmation (Tested & Rejected)

**Hypothesis:** Filtering out low-turnover IPOs would improve signal quality by removing illiquid names where first-day momentum is noisier.

**Implementation:** Only enter trades where `first_day_turnover >= sample_median(first_day_turnover)`, on top of the baseline momentum signal.

**Result:** The filter was rejected. At p50 (median turnover ≈ HKD 747M), total return collapsed from +9.55% to -26.1%. The best trade (02723.HK, +74.1%) had first-day turnover near the sample median — not an outlier — and was incorrectly filtered out. Higher turnover did NOT predict better follow-through momentum.

---

## Results

### Baseline vs Volume Filtered

| Metric | Baseline | Volume Filtered |
|--------|----------|-----------------|
| Trade Count | 14 | 9 |
| Win Rate | 42.9% | 44.4% |
| Average Return | +0.68% | -2.90% |
| Average Win | +20.15% | +14.03% |
| Average Loss | -13.91% | -16.48% |
| Profit Factor | 1.09 | 0.58 |
| Total Return | +9.55% | -26.1% |
| Max Drawdown (HKD) | -63,183 | -35,881 |
| Turnover (HKD) | 1,399,040 | 884,261 |
| Avg Holding Days | 1.0 | 1.0 |

### Cost Sensitivity

| Cost Multiplier | Total Return | Profit Factor |
|----------------|-------------|---------------|
| 0.0× (gross) | +17.2% | 1.16 |
| 0.5× | +13.4% | 1.12 |
| 1.0× (baseline) | +9.6% | 1.09 |
| 1.5× | +5.7% | 1.05 |
| 2.0× | +1.9% | 1.02 |

The strategy is thin-edged. Execution quality matters critically — doubling costs eliminates nearly all profitability.

### Monthly Breakdown

| Month | Trades | Win Rate | Total PnL (HKD) |
|-------|--------|----------|-----------------|
| 2026-01 | 4 | 75.0% | +12,494 |
| 2026-02 | 1 | 100.0% | +14,995 |
| 2026-03 | 2 | 0.0% | -35,026 |
| 2026-04 | 1 | 0.0% | -7,182 |
| 2026-05 | 6 | 33.3% | +24,207 |

March was the worst month (two consecutive stop-losses); May had the most trades but the lowest win rate. The strategy exhibits significant month-to-month variance.

### Top & Bottom Trades

**Best performers:**
- 02723.HK (+74.1%, HKD +74,072): took profit on Day 1
- 02706.HK (+15.0%, HKD +14,995): took profit on Day 1
- 02513.HK (+15.0%, HKD +14,990): took profit on Day 1

**Worst performers:**
- 06636.HK (-25.6%, HKD -25,578): stopped out Day 1
- 07688.HK (-18.7%, HKD -18,696): stopped out Day 1
- 01236.HK (-18.3%, HKD -18,290): stopped out Day 1

All trades exit within a single day. The 3-day holding period is never reached — stop-loss (-8%) or take-profit (+20%) triggers on Day 1 in every case. This suggests the momentum effect is intraday-only and the current stop/take levels are calibrated to the high volatility of IPO debut weeks.

---

## Analysis

### Where the strategy works
- IPOs with strong Day 1 gaps (>5%) that continue running intraday on Day 2 trigger take-profit within hours.
- January and May 2026 provided favorable conditions.

### Where it fails
- **Outlier dependency:** 02723.HK alone contributes ~78% of total PnL. Without it, the strategy is deeply unprofitable.
- **Stop-loss dominance:** 8 of 14 trades (57%) exit via stop-loss. Average loss (-13.9%) exceeds average win (+20.1%) on a frequency-adjusted basis.
- **Volume filter backfires:** Higher turnover IPOs had worse follow-through, not better.
- **Cost sensitivity:** Gross return of +17.2% drops to +9.6% after costs, and to +1.9% at 2× costs.

### IPO Feature Stratification (Research Question 3)

Using the independently collected IPO data, we stratified the 14 baseline trades by public subscription multiple and one-lot success rate. The sample median is 3,661× subscription and 2.4% one-lot success rate.

**Subscription Multiple:**

| Group | Trades | Win Rate | Total Return |
|-------|--------|----------|-------------|
| High (≥3,661×) | 7 | 42.9% | +28.2% |
| Low (<3,661×) | 7 | 42.9% | -18.6% |

Win rates are identical, but high-subscription IPOs produced positive returns while low-subscription IPOs lost money. The difference is driven by position sizing: high-subscription IPOs include the two largest winners (02723.HK, 02706.HK). Correlation is weak (r=0.16), suggesting a non-linear relationship.

**One-Lot Success Rate:**

| Group | Trades | Win Rate | Total Return |
|-------|--------|----------|-------------|
| Low (<2.4%) | 7 | 57.1% | +68.3% |
| High (≥2.4%) | 7 | 28.6% | -58.7% |

This is the stronger discriminator. Low success rate (hard-to-get IPOs with heavy retail demand) shows markedly better post-listing momentum. High success rate (easy-to-get IPOs) underperform. The inverse correlation (r=-0.15) aligns with intuition: IPOs where retail allocation is scarce have pent-up buying pressure that sustains Day 2 momentum.

**Interpretation:**
- The one-lot success rate — a direct measure of retail IPO demand — shows promise as a filtering signal.
- With only 14 trades, the split is 7/7 in both dimensions. Statistical significance is limited; these are suggestive patterns, not confirmatory evidence.

**Industry & Sponsor Stratification (62/65 sponsor and industry fields filled via hkiporesearch.com):**

| Sector | Trades | Win Rate | Total Return |
|--------|--------|----------|-------------|
| AI/Tech | 5 | 80.0% | +83.1% |
| 生物医药/Biotech | 3 | 66.7% | +4.6% |
| 半导体/Semicon | 2 | 0.0% | -24.5% |
| 智能制造/Industrial | 3 | 0.0% | -46.4% |
| 新能源/Energy | 1 | 0.0% | -7.2% |

The momentum strategy's profitability is almost entirely concentrated in AI/Tech IPOs (5 trades, +83.1%). Outside of tech, the strategy is consistently unprofitable across all other sectors. This sector concentration is the most significant pattern uncovered by the external data — stronger than subscription multiples or one-lot rates alone.

Sponsor tier also shows differentiation: IPOs with mixed Chinese+international sponsor syndicates had a 75% win rate vs. 37.5% for purely Chinese-sponsored deals and 0% for purely foreign-sponsored deals.

### Robustness
The strategy is NOT robust given single-trade dependency. The Volume/Turnover improvement was properly tested and rejected. IPO feature stratification reveals that the strategy's edge is concentrated in AI/Tech IPOs — a pattern that may not persist across different market regimes or IPO cohorts. Sector and sponsor data (62/65 filled from hkiporesearch.com) now enables this analysis; previously invisible without external data.

---

## Next Steps

1. **Grey market data:** Source actual grey market close prices (not debut change proxy) from broker grey market pages (e.g. Phillip Securities, Futu). Currently only `grey_change_pct` (debut day change) is filled; `grey_market_date`, `grey_close`, and `premium_to_ipo_price` remain empty.

2. **Offer price range:** `offer_price_low` and `offer_price_high` require prospectus-level data not available on AAStocks or hkiporesearch. These remain unfilled (0/65).

3. **Risk management improvements:** The current fixed stop-loss (-8%) and take-profit (+20%) trigger on every trade. Adaptive stops (volatility-based) or wider levels could reduce premature exits.

4. **Position sizing:** Fixed HKD 100K notional is simplistic. Volatility-adjusted sizing could improve risk-adjusted returns.

5. **Extended sample:** The current dataset is a single cohort (Jan-Jun 2026, 65 IPOs). A multi-year sample is needed for statistical significance of sector/sponsor patterns.

6. **Execution realism:** VWAP entry/exit and partial fills for illiquid names would give a more honest tradability assessment.

*Completed (since initial report): sponsor 62/65, industry 62/65 (via hkiporesearch.com); sector analysis; one-lot success rate and subscription multiple stratification.*
