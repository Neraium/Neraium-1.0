# Deep evidence review of the frozen wastewater run

Review timestamp: 2026-09-23T07:22:39.212351+00:00

This is extraction and arithmetic over saved outputs. Neraium was not run, production code was not read or changed, no web lookup was made, and prior validation outputs were preserved. Existing prize artifacts are used only for the methodological comparison requested below.

## Principal findings and limits

Four graph promotions retain `persistent_relationship_change=true` in governed SII evidence. They are **not four unrestricted persistent insight classifications**: all corresponding insights are context-limited, with insight-level persistence `limited` / `persistent=false`. All four consequence records explicitly state that persistence is not established for that finding. This is a material cross-layer distinction, not a reason to rewrite either output.

All 501 temporally supported but unpromoted observations meet the saved eligibility, confidence (>=0.45), quality-factor (>=0.35), and temporal-support conditions. Their reduction cannot be attributed to those floors or context alone. The saved graph says promotion also requires deterministic change criteria, but retains neither the complete predicate nor per-edge rejection reasons. Therefore the exact change-rule branch that admits four and excludes 501 is **not demonstrable from this evidence package**. No threshold is reverse-engineered from desired outcomes.

None of the four promoted windows was repeated. The existing successful repeats were windows 0, 126 and 252. A matched repeat at 252 is evidence about the following nonpromoted window, not about promotion at 251.

## A. Filtering and coverage funnel

These are descriptive retention/coverage ratios, **not accuracy, precision, specificity or false-positive rates**. Rows, windows and relationships have different units; a ratio between unlike stages would not be a retention rate.

Stage | Count | Explicit denominator | Retained/covered
--- | ---: | ---: | ---:
source observations | 74,172 | 74,172 rows | 100.000000%
retained and analyzed complete-case observations | 74,171 | 74,172 rows | 99.998652%
chronological windows completed | 253 | 253 scheduled windows | 100.000000%
distinct relationships represented | 21 | 21 possible signal pairs | 100.000000%
pair-window evaluations returned | 5,265 | 5,313 possible pair-window slots | 99.096556%
graph temporal support | 505 | 5,265 returned pair-window evaluations | 9.591643%
promoted governed persistent observations | 4 | 505 temporally supported pair-window evaluations | 0.792079%
unique relationships promoted | 2 | 21 represented relationships | 9.523810%

Four promotions are 0.075973% of all evaluated pair-windows; 501/505 (99.207921%) of temporally supported evaluations were not promoted. Two promoted relationships are 2/12 (16.666667%) of relationships with any temporal support. These denominators remain distinct.

The 74,171 unique analyzed rows comprise 2,015 fixed reference rows and 72,156 comparison rows. There are 5,313 possible pair-window slots (21 × 253); 48 are unavailable because NH4 is constant in eight windows. Missing correlations are not stable negatives.

## Interpretation of timestamps and persistence

All times are unspecified source-clock times. Recurrence objects serialize `+00:00`, but source provenance does not establish UTC. `first_supported_observation` is the earliest retained supporting observation in the current bounded history, not necessarily the first time the relationship qualified. Promotion time is the comparison end. Retained support spans, consecutive supporting windows, consecutive graph-qualified windows and consecutive promoted windows are separate quantities. The saved temporal policy requires at least six supporting observations among up to eight and 0.75 direction agreement; it does not require six consecutive supporting windows.

## Observation 159: NH4 / NO3

1. **Relationship:** NH4 / NO3; zero-based chronological window 159.
2. **First-support timestamps:** retained support starts `2018-11-22T07:25:00`; this promotion is observed at `2018-11-28 07:25:00`. First-ever graph temporal qualification for this pair: `2018-06-29 07:25:00`. First-ever governed promotion: `2018-11-28 07:25:00`.
3. **Reference:** `2018-06-14 07:30:00` through `2018-06-21 07:25:00`, 2015 retained samples; fixed seven-day interval ending exclusively 2018-06-21 07:30:00.
4. **Comparison/evidence:** `2018-11-27 07:30:00` through `2018-11-28 07:25:00`, 288 samples. Scheduled bin: `2018-11-27T07:30:00` to `2018-11-28T07:30:00` (exclusive). Retained supporting window indices: [153, 154, 155, 156, 157, 158, 159].
5. **Duration:** retained positive-observation span 6.000000 days (518400 seconds), from earliest to latest retained positive completion. One isolated promoted window means zero elapsed span between promoted observations, not zero underlying persistence. Continuous physical duration is not established.
6. **Consecutive support:** positive-window runs [[153, 154, 155, 156, 157, 158, 159]]; lengths [7]; trailing run 7, maximum run 7. Total retained support 7/8. Do not relabel that total as consecutive.
7. **Baseline statistics:** Pearson r=-0.179239; absolute strength=0.179239; n=2015.
8. **Changed statistics:** Pearson r=-0.771946; absolute strength=0.771946; n=288.
9. **Direction/magnitude:** graph type `new`, direction `negative`; signed delta r=-0.592707, absolute delta r=0.592707. Weighted edge displacement=0.247141. Insight comparison records signed delta=-0.592706 and absolute delta=0.592706; last-decimal differences are retained. Correlation changes have no physical unit.
10. **Temporal evidence:** graph status `supported`, support=true, governed persistent flag=true, direction agreement=0.875, direction=-1, persistence factor=0.875. The containing consecutive graph-qualified run is windows 155–160. Insight persistence nevertheless records `{'status': 'limited', 'persistent': False, 'summary': 'The existing persistence assessment did not confirm every signal in this relationship.', 'reasons': ['The existing persistence assessment did not confirm every signal in this relationship.']}`.
11. **Recurrence:** supported=False, status=unconfirmed, episodes=2, opposite-direction veto=True; reason=`opposite_direction_episode`. Requirement: three episodes with at least two supporting observations per episode within the recorded policy. Neither relationship has any supported recurrence in this full run.
12. **Confidence/sufficiency:** eligible=True; edge confidence=0.9266 (floor 0.45); data-quality factor=0.45 (floor 0.35); sample sufficiency factor=1.0. Insight confidence=`limited`, change detection=`high`, interpretation=`unknown`, evidence quality=`high`. The separate ranking factor `sample_sufficiency` is 0.0; it must not be substituted for the graph sample-sufficiency factor.
13. **Context:** baseline/recent modes and match are unavailable; context confidence is low. Exact reason: “No usable equipment-state, staging, load, schedule, weather, setpoint, or event signals were available.” Insight adds: “Operating context was not comparable enough to attribute the observed relationship change.” No known operational change is recorded; that is not evidence that none occurred.
14. **Data quality:** edge rating `high`; “Available telemetry passed the current completeness, timestamp, and signal-health checks.” Reasons=[]. This window-local assessment does not remove whole-record gaps, initial NH4 zeros, negative flow or unknown units.
15. **Sensor health:** NH4: healthy, NO3: healthy; all recorded conditions empty and factors 1.0. These are engine assessments, not independent calibration verification.
16. **Promotion:** `promoted_changed_edge=true`, category `new`, with recorded confidence, quality, eligibility and temporal conditions satisfied. Every one of the other 501 temporal-supported evaluations also passes those conditions. The exact distinguishing change-inclusion predicate/rejection trace is absent; category/strength differences can be reported, but an exact unrecorded branch cannot be asserted. Context did not prevent this promotion.
17. **Consequence:** `not_quantifiable`; exact reason: “Persistent relationship change is not established for this finding.” Insight persistence is limited/false. Profile is `unmapped`; observation_count=0 and contributing_interval_count=0. Unknown units and lack of mapped consequence evidence are further limitations, but the recorded rejection reason is the persistence statement, not a newly inferred physical explanation.
18. **Provenance:** `raw/checkpoints/159.json`; file SHA-256 `3e9cf7128eebb14e680184677ffb3090f315043be0f0083391c120c0f12dd932`; content/checkpoint digest `3724e2e0509719ebabce10c5865a3f7ca80e3c784fc684764c7706e80d53817d`. Comparison input hash `e1e6b4333a503b4ac8c4787e5982a6246b9fcac2b465d4c41d2b7d915c853a3b`. Exact comparison source-row list, reference source-row list, input timestamps, incoming/outgoing state hashes, predecessor digest, full supporting evidence and resolved insight references are embedded in the companion JSON. Common source/configuration/chain reconstruction is documented below.
19. **Repeat testing:** NOT directly repeated. Existing repeats at 0, 126, 252 cannot establish that this promoted output remained identical. No new repeat was run.
20. **Before/after:** see the neighboring saved evaluations below. These are observations of changes in recorded evidence, not inferred plant causes or reconstructed undocumented code decisions.

Window | Current r | Absolute delta | Type | Temporal | Support count | Confidence | Quality factor | Promoted | Demonstrated missing conditions
--- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- | ---
157 | -0.603606 | 0.424367 | strengthened | True | 6 | 0.848 | 0.45 | False | None recorded among these conditions; change branch untraced
158 | -0.719079 | 0.53984 | new | True | 7 | 0.9019 | 0.45 | False | None recorded among these conditions; change branch untraced
159 | -0.771946 | 0.592707 | new | True | 7 | 0.9266 | 0.45 | True | None
160 | -0.679209 | 0.49997 | new | True | 8 | 0.8833 | 0.45 | False | None recorded among these conditions; change branch untraced
161 | -0.272002 | 0.092763 | stable | False | 7 | 0.6933 | 0.45 | False | temporal_persistence_supported=false

Promotion begins and ends while temporal support remains true (7 supporting observations before, 7 at promotion, 8 afterward). Quality and confidence remain above floors. Current absolute correlation increases to 0.771946 then decreases; the saved outputs do not expose the exact change-rule branch responsible for the single promoted appearance.

## Observation 236: N2O / NO3

1. **Relationship:** N2O / NO3; zero-based chronological window 236.
2. **First-support timestamps:** retained support starts `2019-02-06T07:25:00`; this promotion is observed at `2019-02-13 07:25:00`. First-ever graph temporal qualification for this pair: `2019-02-11 07:25:00`. First-ever governed promotion: `2019-02-13 07:25:00`.
3. **Reference:** `2018-06-14 07:30:00` through `2018-06-21 07:25:00`, 2015 retained samples; fixed seven-day interval ending exclusively 2018-06-21 07:30:00.
4. **Comparison/evidence:** `2019-02-12 07:30:00` through `2019-02-13 07:25:00`, 288 samples. Scheduled bin: `2019-02-12T07:30:00` to `2019-02-13T07:30:00` (exclusive). Retained supporting window indices: [229, 230, 231, 233, 234, 236].
5. **Duration:** retained positive-observation span 7.000000 days (604800 seconds), from earliest to latest retained positive completion. One isolated promoted window means zero elapsed span between promoted observations, not zero underlying persistence. Continuous physical duration is not established.
6. **Consecutive support:** positive-window runs [[229, 230, 231], [233, 234], [236]]; lengths [3, 2, 1]; trailing run 1, maximum run 3. Total retained support 6/8. Do not relabel that total as consecutive.
7. **Baseline statistics:** Pearson r=0.347518; absolute strength=0.347518; n=2015.
8. **Changed statistics:** Pearson r=0.832692; absolute strength=0.832692; n=288.
9. **Direction/magnitude:** graph type `new`, direction `positive`; signed delta r=0.485174, absolute delta r=0.485174. Weighted edge displacement=0.191343. Insight comparison records signed delta=0.485174 and absolute delta=0.485174; last-decimal differences are retained. Correlation changes have no physical unit.
10. **Temporal evidence:** graph status `supported`, support=true, governed persistent flag=true, direction agreement=0.75, direction=1, persistence factor=0.75. The containing consecutive graph-qualified run is windows 236–236. Insight persistence nevertheless records `{'status': 'limited', 'persistent': False, 'summary': 'The existing persistence assessment did not confirm every signal in this relationship.', 'reasons': ['The existing persistence assessment did not confirm every signal in this relationship.']}`.
11. **Recurrence:** supported=False, status=unconfirmed, episodes=1, opposite-direction veto=False; reason=`insufficient_evidence`. Requirement: three episodes with at least two supporting observations per episode within the recorded policy. Neither relationship has any supported recurrence in this full run.
12. **Confidence/sufficiency:** eligible=True; edge confidence=0.8764 (floor 0.45); data-quality factor=0.45 (floor 0.35); sample sufficiency factor=1.0. Insight confidence=`limited`, change detection=`high`, interpretation=`unknown`, evidence quality=`high`. The separate ranking factor `sample_sufficiency` is 0.0; it must not be substituted for the graph sample-sufficiency factor.
13. **Context:** baseline/recent modes and match are unavailable; context confidence is low. Exact reason: “No usable equipment-state, staging, load, schedule, weather, setpoint, or event signals were available.” Insight adds: “Operating context was not comparable enough to attribute the observed relationship change.” No known operational change is recorded; that is not evidence that none occurred.
14. **Data quality:** edge rating `high`; “Available telemetry passed the current completeness, timestamp, and signal-health checks.” Reasons=[]. This window-local assessment does not remove whole-record gaps, initial NH4 zeros, negative flow or unknown units.
15. **Sensor health:** NO3: healthy, N2O: healthy; all recorded conditions empty and factors 1.0. These are engine assessments, not independent calibration verification.
16. **Promotion:** `promoted_changed_edge=true`, category `new`, with recorded confidence, quality, eligibility and temporal conditions satisfied. Every one of the other 501 temporal-supported evaluations also passes those conditions. The exact distinguishing change-inclusion predicate/rejection trace is absent; category/strength differences can be reported, but an exact unrecorded branch cannot be asserted. Context did not prevent this promotion.
17. **Consequence:** `not_quantifiable`; exact reason: “Persistent relationship change is not established for this finding.” Insight persistence is limited/false. Profile is `unmapped`; observation_count=0 and contributing_interval_count=0. Unknown units and lack of mapped consequence evidence are further limitations, but the recorded rejection reason is the persistence statement, not a newly inferred physical explanation.
18. **Provenance:** `raw/checkpoints/236.json`; file SHA-256 `ad2bab40f8c285d55e5f208159031a5696bac0cfec56c1c8d5418eefbb52a928`; content/checkpoint digest `546a15fbaf01129150c9dcf70893a0b6027bdae0fa4abe074bda344ddb6a2858`. Comparison input hash `1bc76717d26e90b4769f53982e19b826d6f7f8b834005b26a7b29f8a7d88deea`. Exact comparison source-row list, reference source-row list, input timestamps, incoming/outgoing state hashes, predecessor digest, full supporting evidence and resolved insight references are embedded in the companion JSON. Common source/configuration/chain reconstruction is documented below.
19. **Repeat testing:** NOT directly repeated. Existing repeats at 0, 126, 252 cannot establish that this promoted output remained identical. No new repeat was run.
20. **Before/after:** see the neighboring saved evaluations below. These are observations of changes in recorded evidence, not inferred plant causes or reconstructed undocumented code decisions.

Window | Current r | Absolute delta | Type | Temporal | Support count | Confidence | Quality factor | Promoted | Demonstrated missing conditions
--- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- | ---
234 | 0.714992 | 0.367474 | new | True | 6 | 0.8215 | 0.45 | False | None recorded among these conditions; change branch untraced
235 | 0.748439 | 0.400921 | new | False | 6 | 0.544115 | 0.2925 | False | data_quality_factor 0.2925 < 0.35; temporal_persistence_supported=false
236 | 0.832692 | 0.485174 | new | True | 6 | 0.8764 | 0.45 | True | None
237 | 0.609859 | 0.262341 | strengthened | False | 5 | 0.50206 | 0.2925 | False | data_quality_factor 0.2925 < 0.35; temporal_persistence_supported=false; supporting observations 5 < 6
238 | 0.793122 | 0.445604 | new | False | 4 | 0.557635 | 0.2925 | False | data_quality_factor 0.2925 < 0.35; temporal_persistence_supported=false; supporting observations 4 < 6

The preceding window has six retained supports but current quality factor 0.2925 is below 0.35 and temporal support is false. At promotion quality is 0.45 and temporal support is true. The following window has quality 0.2925 and only five supports. The retained six positive windows at promotion are not consecutive.

## Observation 248: N2O / NO3

1. **Relationship:** N2O / NO3; zero-based chronological window 248.
2. **First-support timestamps:** retained support starts `2019-02-18T07:25:00`; this promotion is observed at `2019-02-25 07:25:00`. First-ever graph temporal qualification for this pair: `2019-02-11 07:25:00`. First-ever governed promotion: `2019-02-13 07:25:00`.
3. **Reference:** `2018-06-14 07:30:00` through `2018-06-21 07:25:00`, 2015 retained samples; fixed seven-day interval ending exclusively 2018-06-21 07:30:00.
4. **Comparison/evidence:** `2019-02-24 07:30:00` through `2019-02-25 07:25:00`, 288 samples. Scheduled bin: `2019-02-24T07:30:00` to `2019-02-25T07:30:00` (exclusive). Retained supporting window indices: [241, 244, 245, 246, 247, 248].
5. **Duration:** retained positive-observation span 7.000000 days (604800 seconds), from earliest to latest retained positive completion. One isolated promoted window means zero elapsed span between promoted observations, not zero underlying persistence. Continuous physical duration is not established.
6. **Consecutive support:** positive-window runs [[241], [244, 245, 246, 247, 248]]; lengths [1, 5]; trailing run 5, maximum run 5. Total retained support 6/8. Do not relabel that total as consecutive.
7. **Baseline statistics:** Pearson r=0.347518; absolute strength=0.347518; n=2015.
8. **Changed statistics:** Pearson r=0.782814; absolute strength=0.782814; n=288.
9. **Direction/magnitude:** graph type `new`, direction `positive`; signed delta r=0.435296, absolute delta r=0.435296. Weighted edge displacement=0.167108. Insight comparison records signed delta=0.435296 and absolute delta=0.435296; last-decimal differences are retained. Correlation changes have no physical unit.
10. **Temporal evidence:** graph status `supported`, support=true, governed persistent flag=true, direction agreement=0.75, direction=1, persistence factor=0.75. The containing consecutive graph-qualified run is windows 247–248. Insight persistence nevertheless records `{'status': 'limited', 'persistent': False, 'summary': 'The existing persistence assessment did not confirm every signal in this relationship.', 'reasons': ['The existing persistence assessment did not confirm every signal in this relationship.']}`.
11. **Recurrence:** supported=False, status=unconfirmed, episodes=1, opposite-direction veto=False; reason=`insufficient_evidence`. Requirement: three episodes with at least two supporting observations per episode within the recorded policy. Neither relationship has any supported recurrence in this full run.
12. **Confidence/sufficiency:** eligible=True; edge confidence=0.8531 (floor 0.45); data-quality factor=0.45 (floor 0.35); sample sufficiency factor=1.0. Insight confidence=`limited`, change detection=`high`, interpretation=`unknown`, evidence quality=`high`. The separate ranking factor `sample_sufficiency` is 0.0; it must not be substituted for the graph sample-sufficiency factor.
13. **Context:** baseline/recent modes and match are unavailable; context confidence is low. Exact reason: “No usable equipment-state, staging, load, schedule, weather, setpoint, or event signals were available.” Insight adds: “Operating context was not comparable enough to attribute the observed relationship change.” No known operational change is recorded; that is not evidence that none occurred.
14. **Data quality:** edge rating `high`; “Available telemetry passed the current completeness, timestamp, and signal-health checks.” Reasons=[]. This window-local assessment does not remove whole-record gaps, initial NH4 zeros, negative flow or unknown units.
15. **Sensor health:** NO3: healthy, N2O: healthy; all recorded conditions empty and factors 1.0. These are engine assessments, not independent calibration verification.
16. **Promotion:** `promoted_changed_edge=true`, category `new`, with recorded confidence, quality, eligibility and temporal conditions satisfied. Every one of the other 501 temporal-supported evaluations also passes those conditions. The exact distinguishing change-inclusion predicate/rejection trace is absent; category/strength differences can be reported, but an exact unrecorded branch cannot be asserted. Context did not prevent this promotion.
17. **Consequence:** `not_quantifiable`; exact reason: “Persistent relationship change is not established for this finding.” Insight persistence is limited/false. Profile is `unmapped`; observation_count=0 and contributing_interval_count=0. Unknown units and lack of mapped consequence evidence are further limitations, but the recorded rejection reason is the persistence statement, not a newly inferred physical explanation.
18. **Provenance:** `raw/checkpoints/248.json`; file SHA-256 `5a5ac408dcacc0239696d4acb2888926ab8a7124082ff142f239aa9c503326d4`; content/checkpoint digest `7d2d1832bb8926ee44c43adc95def292fd669c2ebca4eff9a6f683591536dd34`. Comparison input hash `0e5fd738952d9c3879c2a03cc2941ab0ad5b6edc388936dbcaafbbd135046c0b`. Exact comparison source-row list, reference source-row list, input timestamps, incoming/outgoing state hashes, predecessor digest, full supporting evidence and resolved insight references are embedded in the companion JSON. Common source/configuration/chain reconstruction is documented below.
19. **Repeat testing:** NOT directly repeated. Existing repeats at 0, 126, 252 cannot establish that this promoted output remained identical. No new repeat was run.
20. **Before/after:** see the neighboring saved evaluations below. These are observations of changes in recorded evidence, not inferred plant causes or reconstructed undocumented code decisions.

Window | Current r | Absolute delta | Type | Temporal | Support count | Confidence | Quality factor | Promoted | Demonstrated missing conditions
--- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- | ---
246 | 0.60228 | 0.254762 | strengthened | False | 5 | 0.7689 | 0.45 | False | temporal_persistence_supported=false; supporting observations 5 < 6
247 | 0.734202 | 0.386684 | new | True | 6 | 0.8305 | 0.45 | False | None recorded among these conditions; change branch untraced
248 | 0.782814 | 0.435296 | new | True | 6 | 0.8531 | 0.45 | True | None
249 | 0.471118 | 0.1236 | stable | False | 5 | 0.460005 | 0.2925 | False | data_quality_factor 0.2925 < 0.35; temporal_persistence_supported=false; supporting observations 5 < 6
250 | 0.762004 | 0.414486 | new | False | 5 | 0.54821 | 0.2925 | False | data_quality_factor 0.2925 < 0.35; temporal_persistence_supported=false; supporting observations 5 < 6

The preceding window already has temporal support and passes confidence/quality, but is unpromoted; the exact change-rule difference is untraced. After promotion, displacement drops to 0.1236 (below the saved temporal 0.15 minimum), supporting count falls to five, and quality falls to 0.2925.

## Observation 251: N2O / NO3

1. **Relationship:** N2O / NO3; zero-based chronological window 251.
2. **First-support timestamps:** retained support starts `2019-02-21T07:25:00`; this promotion is observed at `2019-02-28 07:25:00`. First-ever graph temporal qualification for this pair: `2019-02-11 07:25:00`. First-ever governed promotion: `2019-02-13 07:25:00`.
3. **Reference:** `2018-06-14 07:30:00` through `2018-06-21 07:25:00`, 2015 retained samples; fixed seven-day interval ending exclusively 2018-06-21 07:30:00.
4. **Comparison/evidence:** `2019-02-28 01:05:00` through `2019-02-28 07:25:00`, 77 samples. Scheduled bin: `2019-02-27T07:30:00` to `2019-02-28T07:30:00` (exclusive). Retained supporting window indices: [244, 245, 246, 247, 248, 251].
5. **Duration:** retained positive-observation span 7.000000 days (604800 seconds), from earliest to latest retained positive completion. One isolated promoted window means zero elapsed span between promoted observations, not zero underlying persistence. Continuous physical duration is not established.
6. **Consecutive support:** positive-window runs [[244, 245, 246, 247, 248], [251]]; lengths [5, 1]; trailing run 1, maximum run 5. Total retained support 6/8. Do not relabel that total as consecutive.
7. **Baseline statistics:** Pearson r=0.347518; absolute strength=0.347518; n=2015.
8. **Changed statistics:** Pearson r=0.833239; absolute strength=0.833239; n=77.
9. **Direction/magnitude:** graph type `new`, direction `positive`; signed delta r=0.485721, absolute delta r=0.485721. Weighted edge displacement=0.191624. Insight comparison records signed delta=0.485721 and absolute delta=0.485721; last-decimal differences are retained. Correlation changes have no physical unit.
10. **Temporal evidence:** graph status `supported`, support=true, governed persistent flag=true, direction agreement=0.75, direction=1, persistence factor=0.75. The containing consecutive graph-qualified run is windows 251–251. Insight persistence nevertheless records `{'status': 'limited', 'persistent': False, 'summary': 'The existing persistence assessment did not confirm every signal in this relationship.', 'reasons': ['The existing persistence assessment did not confirm every signal in this relationship.']}`.
11. **Recurrence:** supported=False, status=unconfirmed, episodes=1, opposite-direction veto=False; reason=`insufficient_evidence`. Requirement: three episodes with at least two supporting observations per episode within the recorded policy. Neither relationship has any supported recurrence in this full run.
12. **Confidence/sufficiency:** eligible=True; edge confidence=0.8767 (floor 0.45); data-quality factor=0.45 (floor 0.35); sample sufficiency factor=1.0. Insight confidence=`limited`, change detection=`high`, interpretation=`unknown`, evidence quality=`high`. The separate ranking factor `sample_sufficiency` is 0.0; it must not be substituted for the graph sample-sufficiency factor.
13. **Context:** baseline/recent modes and match are unavailable; context confidence is low. Exact reason: “No usable equipment-state, staging, load, schedule, weather, setpoint, or event signals were available.” Insight adds: “Operating context was not comparable enough to attribute the observed relationship change.” No known operational change is recorded; that is not evidence that none occurred.
14. **Data quality:** edge rating `high`; “Available telemetry passed the current completeness, timestamp, and signal-health checks.” Reasons=[]. This window-local assessment does not remove whole-record gaps, initial NH4 zeros, negative flow or unknown units.
15. **Sensor health:** NO3: healthy, N2O: healthy; all recorded conditions empty and factors 1.0. These are engine assessments, not independent calibration verification.
16. **Promotion:** `promoted_changed_edge=true`, category `new`, with recorded confidence, quality, eligibility and temporal conditions satisfied. Every one of the other 501 temporal-supported evaluations also passes those conditions. The exact distinguishing change-inclusion predicate/rejection trace is absent; category/strength differences can be reported, but an exact unrecorded branch cannot be asserted. Context did not prevent this promotion.
17. **Consequence:** `not_quantifiable`; exact reason: “Persistent relationship change is not established for this finding.” Insight persistence is limited/false. Profile is `unmapped`; observation_count=0 and contributing_interval_count=0. Unknown units and lack of mapped consequence evidence are further limitations, but the recorded rejection reason is the persistence statement, not a newly inferred physical explanation.
18. **Provenance:** `raw/checkpoints/251.json`; file SHA-256 `26d6748b3073294e7f7fc7dc5deecae67016f5dfa3d7147dc60910fef752919c`; content/checkpoint digest `bee49b9aa315902db6a794ae1d059f80142cafb9482f21669f278fc3331e9137`. Comparison input hash `fceb313e2e92f6e46fe3f990033427f6132c4b210c5e222ed6c3d1a1c1f52900`. Exact comparison source-row list, reference source-row list, input timestamps, incoming/outgoing state hashes, predecessor digest, full supporting evidence and resolved insight references are embedded in the companion JSON. Common source/configuration/chain reconstruction is documented below.
19. **Repeat testing:** NOT directly repeated. Existing repeats at 0, 126, 252 cannot establish that this promoted output remained identical. No new repeat was run.
20. **Before/after:** see the neighboring saved evaluations below. These are observations of changes in recorded evidence, not inferred plant causes or reconstructed undocumented code decisions.

Window | Current r | Absolute delta | Type | Temporal | Support count | Confidence | Quality factor | Promoted | Demonstrated missing conditions
--- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- | ---
249 | 0.471118 | 0.1236 | stable | False | 5 | 0.460005 | 0.2925 | False | data_quality_factor 0.2925 < 0.35; temporal_persistence_supported=false; supporting observations 5 < 6
250 | 0.762004 | 0.414486 | new | False | 5 | 0.54821 | 0.2925 | False | data_quality_factor 0.2925 < 0.35; temporal_persistence_supported=false; supporting observations 5 < 6
251 | 0.833239 | 0.485721 | new | True | 6 | 0.8767 | 0.45 | True | None
252 | 0.719323 | 0.371805 | new | False | 5 | 0.535275 | 0.2925 | False | data_quality_factor 0.2925 < 0.35; temporal_persistence_supported=false; supporting observations 5 < 6

The comparison contains only 77 samples after the source gap from 2019-02-27 01:00:00 to 2019-02-28 01:05:00. The previous and following observations each have five supports and quality 0.2925. The promoted observation has six retained supports and quality 0.45, but only one trailing consecutive positive window. Its high data-confidence label must be read alongside this gap and short comparison.

## B–C. Clustering, episode status and overlap

Promotion indices are 159, 236, 248 and 251, with separations of 77, 12 and 3 source-clock days. One appears in November; the three NO3/N2O appearances fall in February across 15 days. They form four isolated consecutive-promotion runs. This supports a descriptive February cluster, not four independent physical episodes. All four recurrence flags are false; NH4/NO3 has an opposite-direction veto, and the NO3/N2O records have only one recurrence episode.

NH4/NO3 and NO3/N2O have **no overlapping promoted comparison periods**, no simultaneous promotion timestamps and no overlap in their retained supporting periods at these promotions. Within NO3/N2O, observations 248 and 251 reuse five positive support windows: 244–248, completing 2019-02-21 through 2019-02-25 at 07:25:00. Their retained support envelopes overlap, but their promoted comparison periods do not. This reuse precludes treating the two as independent evidence; it establishes no causality.

## D. Other relationships closest in observable evidence

No calibrated distance to promotion can be recovered without the full predicate. The table ranks one temporal-supported nonpromotion per other relationship by largest absolute Pearson displacement. Each passes the recorded temporal, eligibility, confidence and quality conditions. The exact additional change requirement preventing each promotion is **not individually logged**, so it cannot be named more precisely from these artifacts. This is an evidence-provenance limitation.

Relationship | Window | Baseline r | Current r | Absolute delta | Type | Missing explicit conditions
--- | ---: | ---: | ---: | ---: | --- | ---
NO3 / Temperature | 244 | -0.424307 | 0.951973 | 1.37628 | disrupted | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced
NH4 / Temperature | 62 | -0.431173 | 0.741045 | 1.172218 | disrupted | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced
NH4 / N2O | 233 | 0.029225 | -0.73889 | 0.768115 | new | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced
N2O / Temperature | 116 | -0.413023 | 0.342916 | 0.755939 | weakened | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced
DO / NH4 | 217 | 0.053818 | 0.646931 | 0.593113 | strengthened | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced
Influent flowrate / NO3 | 81 | -0.142823 | 0.260935 | 0.403758 | strengthened | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced
Influent flowrate / Temperature | 94 | 0.094989 | 0.470967 | 0.375978 | strengthened | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced
Temperature / N2O emission rate | 116 | -0.134334 | 0.238907 | 0.373241 | strengthened | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced
DO / N2O emission rate | 118 | 0.493935 | 0.831495 | 0.33756 | strengthened | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced
NO3 / N2O emission rate | 85 | -0.01512 | 0.149298 | 0.164418 | strengthened | None among saved temporal/confidence/quality/eligibility conditions; change rule untraced

A second descriptive ranking restricts to the same `new` category as all four promotions and orders by current absolute correlation. NH4/N2O at window 233 has r=-0.73889, delta=0.768115 and temporal support, yet no promotion. Window 234 has r=-0.730673 and delta=0.759898. These are observable close comparators, not evidence that an undocumented 0.75 boundary is the governing rule.

All 505 supported evaluations have absolute correlation displacement below the reported `change_inclusion_threshold=1.569345`; nevertheless four are promoted. That scalar is not a complete standalone predicate. The 501 nonpromotions comprise 210 weakened, 202 strengthened, 80 disrupted and 9 new edges.

## E. Substantial movement not promoted

“Correctly not promoted” here can mean consistent with recorded software conditions only. Without independent ground truth it cannot mean a correct plant-event rejection. Largest-movement examples are selected descriptively after the frozen run, with no engine reevaluation or outcome tuning.

Selection | Relationship | Window | Absolute delta r | Demonstrated missing conditions
--- | --- | ---: | ---: | ---
largest unconfirmed movement | NO3 / Temperature | 168 | 1.244473 | temporal_persistence_supported=false; supporting observations 4 < 6
largest movement with quality below floor | NO3 / Temperature | 68 | 1.130458 | data_quality_factor 0.2925 < 0.35; temporal_persistence_supported=false; supporting observations 5 < 6
largest movement with confidence below floor | NH4 / Temperature | 40 | 1.116853 | edge_confidence 0.25 < 0.45; data_quality_factor 0.1125 < 0.35; temporal_persistence_supported=false

These include large raw correlation movement with too few supporting observations, insufficient data-quality factor, or confidence below its recorded floor. They show why movement alone is not evidence sufficiency. No context-only rejection is established: operating context is unavailable for all pair-window evaluations, including the four promoted ones. The four themselves provide examples of additional interpretive/consequence restraint despite graph promotion.

## F. Architectural meaning

The saved outputs distinguish association estimation, bounded temporal support, graph promotion, governed relationship evidence, insight classification and consequence qualification. The 505-to-4 reduction shows that temporal support alone does not trigger promotion. It does not demonstrate that confidence or quality removed those 501, since they all pass those recorded floors. It also does not establish correctness of the four plant-event detections. Context and insight persistence continue to limit interpretation after graph promotion, and consequence remains unquantifiable. The absent change-decision trace and inconsistent persistence statuses across layers limit auditability; both are findings of this extraction.

## G. Methodological comparison with the controlled prize evidence

Consistent behavior: the controlled campaign distinguished sustained displacement from stable/noisy/transient/alternating controls and tracked recurrence separately. The wastewater outputs also retain temporal history and separate recurrence from promotion. The controlled new-context case gained temporal support despite weak comparability; similarly, wastewater context limitations do not universally prohibit graph promotion. Both campaigns preserve limited outcomes and replay provenance rather than forcing positive conclusions.

Not comparable: controlled correlation shifts are deliberately constructed with known reference conditions; wastewater has unknown operating context, a reference with quality limitations, seasonal variation in the observed record and no independent event labels. Controlled 0/320 control-window promotions and 48/48 sustained-case support results cannot estimate wastewater accuracy. The counts, windows, variables and denominators must not be pooled. The synthetic sixth-window behavior is not a universal real-data support-time claim.

Still unvalidated: independent plant-event correctness, false-positive behavior, physical significance, consequence attribution, generalization to other plants, prospective/field deployment behavior, and repeatability of these four specific promoted windows. The prior campaign exposed dictionary-order sensitivity; this run preserved order and repeated only three different windows. The current extraction does not resolve that limitation or the missing promotion-decision trace.

## Reproduction provenance and evidence map

Original recorded path: `/home/ubuntu/Data.csv`; source SHA-256 `29a2db4e54d5f5278d2c05732d62cf877f939f87312e035ddb700c385c3550a8`. Engine commit `97d267d317fcce4b4424cf2141e97e87680acfc0`. Derived normalized CSV SHA-256 `77bb043db42645dcae4b0b47ec0c2d0f622b755bdeeb607ddda67362a473fc34`. Reference input hash `6419ff5d5ca4366d84b17fd1a9a935334f070271777c0706813d7729165892d8`.

For each observation the companion JSON retains the complete graph edge, governed record, relevant insight, source-row lists, supplied-reference contract, state handoff and resolved evidence references. Reconstruct inputs from raw/normalized.csv preserving header/dictionary order and verbatim numeric cells; use the reference and comparison 1-based source-row lists. Edge-local row numbers are not original file row numbers. Exact columns, numeric profiles, units (all null), timestamp policy and configuration are in raw/checkpoints/manifest.json and raw/config.json. The preceding checkpoint supplies both original incoming states; the entire predecessor chain establishes chronological provenance. Package manifests, raw/freeze.json, raw/external-dependency.json and the saved wrapper snapshot identify code and environment. This review did not execute that reconstruction through Neraium.

The companion JSON records SHA-256 of every artifact read for substantive extraction and embeds the extraction program. Existing SHA256SUMS is deliberately unchanged; it predates these two new review artifacts. The extraction checks that every pre-existing package file remains byte-identical. All review calculations can be repeated using saved outputs alone.
