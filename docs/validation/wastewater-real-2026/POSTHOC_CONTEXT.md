# Post-hoc external contextualization — separate from analytical results

The primary outputs were frozen after the complete chronological run. Fixed first/middle/last repeats were then frozen in `raw/blind-phase-seal.json` before the first external lookup. No external metadata, event descriptions or explanations informed baseline selection, units, window selection or engine evaluation.

## Verified source match

[Zenodo record 21135508](https://zenodo.org/records/21135508), deposited by Anlei Wei on 2 July 2026, describes a full-scale wastewater plant in Denmark and the same monitoring dates and variables. The downloaded CSV is byte-identical to the uploaded source: 4,537,154 bytes and SHA-256 `29a2db4e54d5f5278d2c05732d62cf877f939f87312e035ddb700c385c3550a8`. See `raw/posthoc/source-match.json` and the saved API metadata. The deposit's license is CC BY 4.0; attribution: Wei, Anlei (2026), dataset, DOI `10.5281/zenodo.21135508`.

The repository description reports 74,173 observations, whereas parsing the identical CSV yields 74,172 data records plus one header. The one-record discrepancy is consistent with counting the header, but that explanation is not confirmed by the depositor. This validation uses the verified data-row count. Metadata describes five-minute sampling; the source audit identifies six longer gaps.

## Publication and operating-event evidence

A [publisher record with the same title](https://www.sciencedirect.com/science/article/abs/pii/S0960852426017190) was found, DOI `10.1016/j.biortech.2026.135637`. The available abstract concerns another analytical framework. A direct full-text request returned HTTP 403; the accessible metadata/abstract does not supply independently dated interventions linked to this CSV. Its prediction/causal/action claims are not claims made for Neraium.

Related [Avedøre plant research](https://backend.orbit.dtu.dk/ws/portalfiles/portal/264662910/_ES_T_Manuscript_rsl.pdf) and a [DANVA project report](https://www.danva.dk/media/6420/872016_lattergasstyring-vudp-slutrapport.pdf) describe wastewater monitoring and seasonal operating context during overlapping dates. These are contextual leads only: the matched Zenodo record does not name the facility or establish a row-level link to those studies. Their units, seasonal explanations and controller changes were not transferred to this dataset or used as ground truth.

**No independently documented operating-event correspondence was established for Neraium's four governed persistent pair-window findings.** The external evidence corroborates the dataset's published real full-scale wastewater provenance, not the correctness, cause, significance or event timing of a finding. No outputs were rerun or reclassified after this review. Units remain unknown in the blind analysis; no physical emission or resource consequence is quantified.

Search results, access failures, repository API metadata and source-match hashes are preserved under `raw/posthoc/`.
