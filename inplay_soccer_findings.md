# In-Play Soccer Derivative-Market Model — Findings Inventory & Self-Audit

A reference checklist of research findings on modeling correlated in-play soccer
markets (match-winner, Asian handicap, totals, BTTS, 1H totals, correct score) on
a single binary prediction-market venue (Kalshi-style CLOB). Use the **Have it?**
column to diff against your current model.

Confidence legend: **H** = well-established / cross-confirmed · **M** = established
but estimate-on-your-own-data · **C** = contested in the literature · **V** =
single/secondhand source, verify before relying.

---

## 0. Core thesis (the spine everything hangs on)

| # | Finding | Modeling implication | Conf | Have it? |
|---|---------|----------------------|------|----------|
| 0.1 | A soccer match reduces to **two latent scoring rates** `λ_home, λ_away`; every market is a deterministic function of them | Model the two rates, not each market independently | H | ☐ |
| 0.2 | The **Asian Handicap is sharper than the 1X2 moneyline**; AH is an unbiased win-prob estimator, 1X2 carries favourite-longshot bias | Anchor fair value on AH (**supremacy**) + O/U (**total**), NOT on 1X2 | H | ☐ |
| 0.3 | Derivative/prop markets (BTTS, 1H O1.5, team totals, correct score) are **softer**: wider margins, lower limits, thinner liquidity, less informed flow | Treat props as the trade target; main lines as the signal | H | ☐ |
| 0.4 | All markets descend from one scoreline distribution ⇒ **mutually consistent by construction**; any prop disagreeing with the matrix is the mispriced one | Use the matrix as a coherence/consistency engine to flag soft props | H | ☐ |

Sources: Whelan et al. "A Tale of Two Markets" (IJF 2024); Buchdahl/Football-Data; Pinnacle limits.

---

## 1. Supremacy/Total → scoreline matrix (the pricing engine)

| # | Finding | Modeling implication | Conf | Have it? |
|---|---------|----------------------|------|----------|
| 1.1 | `Supremacy = λ_home − λ_away`, `Total = λ_home + λ_away` | Read AH line as supremacy, O/U line as total | H | ☐ |
| 1.2 | Invert: `λ_home = (Total+Sup)/2`, `λ_away = (Total−Sup)/2` | Two-equation solve for the rates | H | ☐ |
| 1.3 | Scoreline matrix = outer product of two Poisson vectors `P(x,y)=P_home(x)·P_away(y)` | Build grid 0–0 … ~8–8 | H | ☐ |
| 1.4 | **Dixon–Coles** low-score correction τ on (0,0),(0,1),(1,0),(1,1); ρ ≈ −0.03 to −0.15 | Fixes under-prediction of 0-0/1-1 draws | H | ☐ |
| 1.5 | Bivariate Poisson (shared λ₃≥0) only models *positive* correlation; real goal corr is ~0/slightly negative ⇒ DC usually preferred | Prefer DC-style ρ over bivariate Poisson | H | ☐ |
| 1.6 | De-vig each market before inverting: `fair_i = (1/odds_i)/Σ(1/odds_j)` | Strip margin first; use Shin/power for favourite-longshot skew | H | ☐ |
| 1.7 | Asian handicap = tails of the **Skellam** distribution (difference of two Poissons) | Price AH/margin directly from Skellam | H | ☐ |

Pricing each market off the one matrix:
- **1X2:** Home Σ(x>y), Draw Σ(x=y), Away Σ(x<y)
- **BTTS-Yes** = `1 − e^(−λ_home) − e^(−λ_away) + e^(−(λ_home+λ_away))`
- **Over N.5** = Σ cells x+y ≥ N+1
- **Team total Over k.5** = tail of that team's marginal Poisson
- **Correct score** = individual cell
- **DNB home** = `H/(H+A)`; **Double chance** `1X=H+D`, `12=H+A`, `X2=D+A`
- **Market equivalences:** AH 0.0 = DNB · AH −0.5 = 1X2 win · AH −0.25 = ½(0 line)+½(−0.5 line)

Sources: Dixon & Coles 1997 (JRSS-C); Maher 1982; Karlis & Ntzoufras 2003; Pinnacle; opisthokonta; penaltyblog.

---

## 2. Time-decay regime (smooth, no events)

| # | Finding | Modeling implication | Conf | Have it? |
|---|---------|----------------------|------|----------|
| 2.1 | Goals = **inhomogeneous Poisson / Cox process**; intensity λ(t) varies over the clock | In-play λ must be time-dependent, not static | H | ☐ |
| 2.2 | Goal rate **rises ~linearly over 90 min**, with ~50% dips just after each kickoff (1', 46') and a spike past ~87' | Shape the baseline λ₀(t); don't assume flat | H | ☐ |
| 2.3 | **~44% of goals in 1st half, ~56% in 2nd** (Eng. 44.3/55.7, n≈25,769) | Price 1H props off ≈0.44× full-match λ, not 0.5× | M | ☐ |
| 2.4 | Remaining expected goals decays continuously with no goal; one model `λ_rem ≈ λ_init × (frac_time_remaining)^0.84` | Bleed prop time-value every tick; soft props decay too stickily | V | ☐ |
| 2.5 | In-play win prob = current score + Poisson(remaining λ) over the matrix | Recompute W/D/L minute-by-minute | H | ☐ |
| 2.6 | Pre-match priors dominate early; in-game features dominate late | Time-weight feature importance over the clock | H | ☐ |

Sources: Dixon & Robinson 1998; PLOS ONE 2012; arXiv 2501.18606; thestatsdontlie; Robberechts et al. 2021.

---

## 3. Shock-jump regime (goal / red card / penalty)

| # | Finding | Modeling implication | Conf | Have it? |
|---|---------|----------------------|------|----------|
| 3.1 | A goal **co-jumps all markets**; contract-value jumps correlate **~80–89%** with a replicating portfolio | One goal reprices 1X2, BTTS, O/U, CS simultaneously | H | ☐ |
| 3.2 | Under independent Poisson, in-play markets are **spanned by the goal process** (arbitrage-free, complete) | Goal process is the common factor; price jumps off it | H | ☐ |
| 3.3 | **Red card = separate shock dimension** the pure-Poisson model does NOT span | Add a red-card sensitivity beyond goal intensity | H | ☐ |
| 3.4 | Red card: penalized team intensity **~×0.67**, opponent **~×1.25**, total impact **≈ −1.8 xG** | Discrete λ re-scaling on dismissal | V | ☐ |
| 3.5 | Red-card effect **front-loaded**: early dismissals swing odds hard, 2nd-half ones barely move outcome | Condition red-card jump on minute | H | ☐ |
| 3.6 | Score-state effect: intensity **~+10% down one, ~+20% down two** (league-dependent) | Optional game-state λ adjustment | C | ☐ |
| 3.7 | "More vulnerable right after scoring" is **empirically false**; "goals beget goals" is mostly a time artifact | Do NOT add a post-goal vulnerability term | H | ☐ |
| 3.8 | Goal jump hits each prop's payoff geometry differently (kills 1H O1.5 time value, may lift BTTS, shifts favourite) | Per-prop jump-beta, not a uniform shift | H | ☐ |

Sources: Divos/Rollin et al. 2018 (Appl. Math. Finance); Vecer et al. 2009; Empirical Economics 2017; Ridder et al. 1994; Maia et al. 2025; Heuer et al. 2012; arXiv 2501.18606.

---

## 4. Market efficiency & lead-lag (is the lag exploitable?)

| # | Finding | Modeling implication | Conf | Have it? |
|---|---------|----------------------|------|----------|
| 4.1 | Croxson & Reade: deep Betfair match-odds are **semi-strong efficient** — jump at goal, no post-goal drift | Main market on liquid games is fast; don't expect lag there | H | ☐ |
| 4.2 | Gil & Levitt: **10–15 min post-goal drift** on a thin market (~2.4% net) | Lag exists in thin/soft markets | H | ☐ |
| 4.3 | Choi & Hui: **underreact to expected goals, overreact to surprising ones** | Condition edge on goal "surprise" | H | ☐ |
| 4.4 | Angelini et al.: in-play mispricing via **reverse favourite-longshot bias**; ROI only from *selective* betting | Bet only where edge is statistically significant | H | ☐ |
| 4.5 | "Surprise" = pre-shock win-prob gap between scoring/non-scoring side | Use surprise magnitude as an edge moderator | H | ☐ |
| 4.6 | Momentum/"hot-hand" strategies are **unprofitable** on average | Don't build a naïve momentum signal | H | ☐ |
| 4.7 | Markets do **not anticipate** goals (react, don't predict) | Don't expect pre-goal "sensing" | M | ☐ |
| 4.8 | Tick-level cross-market Granger lead-lag is a **literature gap** (least-competed edge) | Your thin-prop lag signal is novel territory | M | ☐ |

Net: lag is **real but conditional** — largest in thin soft props after *surprising* shocks, ~zero in deep main markets. Kalshi soccer is thinner than Betfair, so Betfair efficiency is an *upper bound*.

Sources: Croxson & Reade 2014 (Econ. Journal); Gil & Levitt 2007; Choi & Hui 2014; Angelini et al. 2022; Winkelmann & Deutscher 2025; Ötting et al. 2021.

---

## 5. Single-venue (Kalshi) microstructure & execution

| # | Finding | Modeling implication | Conf | Have it? |
|---|---------|----------------------|------|----------|
| 5.1 | Binary YES/NO contracts settle 0/100; multi-outcome events = separate mutually-exclusive binaries | 3-way soccer = 3 independent books | H | ☐ |
| 5.2 | Three outcomes can **sum ≠ 100** (internal over/under-round) | Scan HDA leg-sum for internal arb | H | ☐ |
| 5.3 | Taker fee ≈ `⌈0.07 × C × P × (1−P)⌉`, **max ~1.75¢/contract at P=0.50**, ~0 in tails | Bake fee(P) into every EV; tilt to lopsided contracts | V | ☐ |
| 5.4 | Maker fee = 25% of taker, often **zero** on non-flagged series | Prefer making over taking when possible | V | ☐ |
| 5.5 | YES bid at X = NO ask at (100−X); books are complementary | Use both sides for synthetic pricing | H | ☐ |
| 5.6 | Takers lose ~32%, makers ~10% on average; favourite-longshot bias present | Be the maker quoting post-shock fair | H | ☐ |
| 5.7 | Soccer resolves on **90 min + stoppage, not extra time** | Match λ-model window to settlement window | H | ☐ |
| 5.8 | Void/postponement may settle at **"last traded fair price," not void** | Model abandonment risk; "locked" positions aren't risk-free | V | ☐ |
| 5.9 | On illiquid games YES/NO spread can be 5–10¢; markets suspend on goals | Model fill probability & spread in EV | M | ☐ |

Sources: Kalshi fee schedule/help (secondhand, re-verify live); Bürgi/Deng/Whelan SSRN 5502658; settlement loss accounts.

---

## 6. Feature inventory (diff against your feature set)

**Latent-rate / state features**
- ☐ `λ_home(t), λ_away(t)` inverted live from sharp AH-supremacy + O/U-total
- ☐ `remaining_xG` per team, time- and score-state-adjusted (44/56 half-split)
- ☐ Cox-intensity regressors: goal-diff, red-card diff, minute, recent post-shot xG/threat

**Cross-market coherence (the alpha)**
- ☐ Per prop: `matrix_fair − kalshi_price`, **net of fee(P) and spread**
- ☐ `HDA_leg_sum` over/under-round magnitude
- ☐ Synthetic-vs-direct price gap per leg
- ☐ Per-prop **jump-beta to goal process** vs. observed Kalshi move (lag signal)

**Shock/event features**
- ☐ Event flags (goal/red/penalty) with **timing-conditioned** repricing
- ☐ "Surprise" magnitude (pre-shock win-prob gap)
- ☐ Time-value-collapse flags for capped props (1H O1.5, correct score)

**Microstructure / execution**
- ☐ Bid-ask width, depth/imbalance, queue position, taker-flow toxicity proxy
- ☐ Fill-probability estimate; fee(P) in EV

**Validation discipline**
- ☐ Isotonic/Platt calibration + reliability diagrams
- ☐ Walk-forward CV with purge/embargo around each fixture
- ☐ Label & reward **CLV vs both Kalshi close and sharp close**

---

## 7. Anti-patterns (things the research says NOT to do)

- ☐ Don't model each prop independently — they share two latent rates (#0.1)
- ☐ Don't anchor fair value on 1X2 — use AH/supremacy (#0.2)
- ☐ Don't use proportional de-vig blindly — favourite-longshot skew (#1.6)
- ☐ Don't assume 50/50 half split — it's ~44/56 (#2.3)
- ☐ Don't add post-goal "vulnerability" or naïve momentum (#3.7, #4.6)
- ☐ Don't apply a uniform shift on a goal — use per-prop jump-betas (#3.8)
- ☐ Don't expect lag in deep main markets — only thin soft props after surprise (#4.1, #4.8)
- ☐ Don't ignore fee(P) near 50¢ or assume void-on-DNP (#5.3, #5.8)

---

## Key sources

- Whelan et al., "A Tale of Two Markets" (Int. J. Forecasting, 2024) — AH vs 1X2 sharpness
- Dixon & Coles (1997, JRSS-C) — scoreline matrix + ρ correction
- Dixon & Robinson (1998, JRSS-D) — time/score-dependent in-play intensity
- Karlis & Ntzoufras (2003) — bivariate Poisson
- Divos, Rollin et al. (2018, Appl. Math. Finance) — goal-process spanning, jump correlation
- Ridder, Cramer & Hopstaken (1994, JASA) — red-card hazard effect
- Croxson & Reade (2014, Econ. Journal) — in-play efficiency
- Choi & Hui (2014, JEBO); Angelini et al. (2022, IJF) — conditional inefficiency
- Robberechts, Van Haaren & Davis (2021, KDD) — Bayesian in-game win probability
- Bürgi, Deng & Whelan (SSRN 5502658) — Kalshi maker/taker economics

*Confidence flags: re-estimate M-rated values (ρ, 44/56 split, red-card magnitudes) on
your own data; re-verify V-rated values (Kalshi fees, decay exponent, void rules)
against live primary sources before relying on them.*
