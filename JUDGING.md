# ChameleonOS Judging & Cross-Judge Score Normalization

## Overview

In multi-track hackathons and competitive technical evaluations, raw numerical scores are vulnerable to systematic grader biases. Some judges grade harshly (e.g., awarding scores between 3.0 and 6.0), while others grade leniently (awarding scores between 8.0 and 10.0). Furthermore, some judges utilize wide score variances while others score tightly around a narrow band.

Without normalization, project outcomes become a **judge lottery**: a superior project assigned to a strict judge may lose to a mediocre project evaluated by an overly generous judge.

ChameleonOS solves this through **Deterministic Cross-Judge Z-Score Normalization with Benchmark Rescaling**, ensuring fair, reproducible, and mathematically grounded rankings.

---

## 1. Mathematical Formulation

### Step 1: Weighted Raw Project Score per Judge

For a given judge $j$ evaluating project $p$, let $C_{j,p}$ represent the set of rubric criteria evaluated by judge $j$ for project $p$. Each criterion $c$ possesses an assigned weight $w_c > 0$ and an awarded score $s_{j, p, c} \in [\text{min\_score}_c, \text{max\_score}_c]$.

The raw weighted project score $R_{j, p}$ is defined as:

$$R_{j, p} = \frac{\sum_{c \in C_{j, p}} w_c \cdot s_{j, p, c}}{\sum_{c \in C_{j, p}} w_c}$$

*Missing Score Handling*: If a judge omits scoring an optional criterion, that criterion is excluded from both numerator and denominator, preserving exact proportional weighting without artificial penalty.

---

### Step 2: Individual Judge Distribution Parameters

Let $P_j = \{p_1, p_2, \dots, p_{N_j}\}$ represent the set of all projects evaluated by judge $j$, where $N_j = |P_j|$ is the total number of projects reviewed by judge $j$.

The judge's empirical mean $\mu_j$ is calculated as:

$$\mu_j = \frac{1}{N_j} \sum_{p \in P_j} R_{j, p}$$

The judge's empirical variance $\sigma_j^2$ and standard deviation $\sigma_j$ are calculated as:

$$\sigma_j^2 = \frac{1}{N_j} \sum_{p \in P_j} (R_{j, p} - \mu_j)^2, \quad \sigma_j = \sqrt{\sigma_j^2}$$

---

### Step 3: Global Benchmark Parameters

To project normalized scores back into an intuitive scale matching the hackathon's rubric dimensions, global population benchmarks are derived across all judge-project evaluations:

$$\mu_{\text{global}} = \frac{1}{M} \sum_{j} \sum_{p \in P_j} R_{j, p}$$

$$\sigma_{\text{global}} = \sqrt{\frac{1}{M} \sum_{j} \sum_{p \in P_j} (R_{j, p} - \mu_{\text{global}})^2}$$

*(If all judges evaluate identically or $\sigma_{\text{global}} < \epsilon$, a standard default of $\sigma_{\text{global}} = 1.5$ is applied).*

---

### Step 4: Standardized Z-Score Calculation

For each evaluation $(j, p)$, the standardized score $z_{j, p}$ measures the number of standard deviations the project's performance falls above or below judge $j$'s personal scoring baseline:

$$z_{j, p} = \begin{cases} 
\frac{R_{j, p} - \mu_j}{\sigma_j} & \text{if } \sigma_j > \epsilon \text{ and } N_j > 1 \\
0.0 & \text{if } \sigma_j \le \epsilon \text{ or } N_j \le 1
\end{cases}$$

where $\epsilon = 10^{-6}$ is a numerical threshold preventing division by zero.

---

### Step 5: Multi-Judge Aggregation in Standardized Space

Let $J_p$ denote the set of judges who evaluated project $p$. The project's aggregate normalized z-score $\bar{z}_p$ is the mean of the standardized scores assigned by its evaluators:

$$\bar{z}_p = \frac{1}{|J_p|} \sum_{j \in J_p} z_{j, p}$$

If a project has not yet been reviewed ($|J_p| = 0$), $\bar{z}_p = 0.0$.

---

### Step 6: Benchmark Rescaling to Final Aggregate Score

To present organizers and participants with human-readable ratings rather than raw z-scores (which center around 0.0), the aggregate z-score is rescaled onto the global benchmark distribution:

$$S_{\text{norm}, p} = \mu_{\text{global}} + (\bar{z}_p \cdot \sigma_{\text{global}})$$

---

## 2. Handling Edge Cases

| Edge Case | Mathematical Challenge | ChameleonOS Resolution |
| :--- | :--- | :--- |
| **Zero Variance (Uniform Judge)** | A judge assigns identical scores to every project (e.g. 8.0 to all). Standard deviation $\sigma_j = 0$, causing division by zero $\frac{R - \mu}{0}$. | **Safe Nullification**: When $\sigma_j \le 10^{-6}$, $z_{j, p}$ is defined strictly as $0.0$. The judge's uniform scores contribute neutrally without distorting relative standings or crashing calculations. |
| **Single Project Judge ($N_j = 1$)** | A judge evaluates only one project before dropping out. Sample variance cannot be estimated from $N=1$. | **Neutral Imputation**: $z_{j, p}$ defaults to $0.0$. The project receives the population average from this evaluator. |
| **Missing Criterion Scores** | A judge submits scores for only 2 out of 3 criteria on a project. | **Proportional Redistribution**: Raw score $R_{j,p}$ divides by the sum of weights of completed criteria only, avoiding unfair penalties for omitted optional fields. |
| **Unequal Judges per Project** | Project A has 3 judges; Project B has 2 judges. Summing scores or comparing raw averages across uneven judge panels introduces severe bias. | **Standardized Mean**: Aggregation occurs in normalized $z$-space before scaling. A project with 2 judges is compared on standard deviation units rather than raw score sums. |
| **Score Ties** | Two or more projects produce identical final normalized scores. | **Deterministic 4-Tier Tie-Breaker**: Ranked strictly in reproducible priority order: (1) Normalized Score, (2) Raw Score, (3) Evaluation Count, (4) Project ID lexicographically. |

---

## 3. Deterministic Tie-Breaking Hierarchy

When sorting projects, ChameleonOS applies a strict lexicographical tuple comparison:

```python
sort_key = (
    -round(normalized_score, 4),  # Tier 1: Highest normalized score
    -round(raw_score, 4),         # Tier 2: Highest raw weighted average
    -evaluations_count,           # Tier 3: Most evaluations received
    project_id,                   # Tier 4: Deterministic UUID/string sort
)
```

This guarantees 100% deterministic ranking across different database engines and execution environments with zero randomness.

---

## 4. The Organizer Normalization Lab

ChameleonOS includes an interactive **Normalization Lab** accessible by organizers and administrators at `/events/{slug}/normalization-lab`:

1. **Judge Calibration Matrix**: Categorizes each judge's scoring behavior:
   - **Well-Calibrated**: Mean score within $\pm 0.75 \sigma$ of global average.
   - **Harsh Grader**: Mean score significantly below global average.
   - **Lenient Grader**: Mean score significantly above global average.
   - **Zero Variance (Uniform)**: Identical score assigned across all evaluations ($\sigma = 0$).
2. **Rank Shift Tracking ($\Delta$ Rank)**:
   $$\Delta \text{Rank} = \text{Raw Rank} - \text{Normalized Rank}$$
   - **$\Delta > 0$ (Green)**: Project was evaluated by stricter-than-average judges and climbed to its rightful position.
   - **$\Delta < 0$ (Red)**: Project was evaluated by overly generous judges and had its inflated standing corrected.
   - **$\Delta = 0$ (Neutral)**: Project maintained position after calibration.
3. **Audit Trail**: Every normalization calculation is transparently verifiable via JSON API at `/api/v1/normalization/events/{event_id}`.

---

## 5. Security Architecture

All normalization endpoints adhere strictly to the role-based security boundaries established in Milestone T2:

- **Participants**: Forbidden (`403 Forbidden`) from accessing the Normalization Lab or API.
- **Judges**: Forbidden (`403 Forbidden`) from viewing aggregate normalization tables, preventing strategic voting or evaluation tampering.
- **Organizers & Admins**: Full access to inspect bias metrics, rank shifts, and export verified results.
