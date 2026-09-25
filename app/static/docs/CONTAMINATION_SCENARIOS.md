# Contamination Scenarios and Discrimination Guidance

Curated 2026-10-05. All claims below are sourced; safety notes are mandatory. Unknown compatibility is explicitly left unknown.

## Purpose

Help operators discriminate contaminants in hellish mixed contaminated bulk – e.g., unsorted post-consumer bales, shredder fines, or “mixed plastics” feedstock – and decide safe handling, sorting actions, and whether the material can be reclaimed.

## General discrimination principles

* Visual + tactile cues are indicative only; final identification requires resin code, density float/sink, hot needle, FTIR or lab test.
* Always surface safety notes for heated processing. Never infer compatibility; use recorded rules only.
* Record source_title and source_url for every risk entered.

## Scenario catalogue

### 1. PVC contamination in PET stream
* **Typical source**: clear PET bottles with PVC labels, caps, or window film.
* **Visual cues**: slightly cloudy film, chlorine smell when heated, density ~1.38 vs PVC ~1.4.
* **Impact**: PVC degrades before a clean melt and releases hydrogen chloride gas. Contamination harms PET recycling batches.
* **Safety**: Heating or burning PVC releases HCl gas – corrosive respiratory hazard per NIOSH Pocket Guide to Chemical Hazards – Hydrogen chloride. 
* **Source**: Polyvinyl chloride – Wikipedia; NIOSH Pocket Guide to Chemical Hazards – Hydrogen chloride https://www.cdc.gov/niosh/npg/npgd0332.html
* **Action**: Remove clear PVC labels by sink-float or manual sort. Do not melt mixed PET/PVC.

### 2. Black PP with printed inks and adhesive labels
* **Typical source**: black food trays, caps, multi-layer pouches.
* **Visual cues**: black opaque, printed graphics, paper or PE adhesive layers.
* **Impact**: Inks contain heavy metals/organic carriers; adhesives cause gel particles and odor. Black masterbatch limits optical sorting.
* **Safety**: Inks may release VOCs when heated; ensure ventilation.
* **Source**: Polypropylene – Wikipedia https://en.wikipedia.org/wiki/Polypropylene
* **Action**: Prefer mechanical recycling to downcycled applications. Record contaminant_name = “printed ink/adhesive”.

### 3. Food residue and organics in HDPE/LDPE
* **Typical source**: milk jugs, squeeze bottles, film with grease.
* **Visual cues**: oily film, discoloration, odor.
* **Impact**: Organics cause hydrolysis, off-gas, and microbial growth. Increases energy use in washing.
* **Safety**: Wash water aerosols; use PPE and ventilation.
* **Source**: High-density polyethylene – Wikipedia https://en.wikipedia.org/wiki/High-density_polyethylene
* **Action**: Hot wash/detergent step; reject heavily soiled items.

### 4. Rubber and foam PS in PP stream
* **Typical source**: packaging with EPS cushioning, gasket rubber.
* **Visual cues**: soft, elastic, low density.
* **Impact**: Rubber does not melt with PP; foam PS creates fines and static.
* **Safety**: Styrene monomer and fire hazard from PS foam per Polystyrene – Wikipedia.
* **Source**: Polystyrene – Wikipedia https://en.wikipedia.org/wiki/Polystyrene
* **Action**: Air classification + density separation.

### 5. Metal clips, staples and PET bottles
* **Typical source**: PET bales with bottle caps clips.
* **Visual cues**: metallic glint, magnetic response.
* **Impact**: Metal causes equipment wear, sparks, and contamination of flake.
* **Safety**: Cutting hazard; wear cut-resistant gloves.
* **Source**: Polyethylene terephthalate – Wikipedia https://en.wikipedia.org/wiki/Polyethylene_terephthalate
* **Action**: Magnet and eddy current separation before shredding.

### 6. Multi-layer packaging – PET/PE/Al laminate
* **Typical source**: stand-up pouches, coffee bags.
* **Visual cues**: crinkly, multiple layers, peelable.
* **Impact**: Layers cannot be separated economically; downcycling only.
* **Safety**: Aluminum dust inhalation risk during shredding.
* **Source**: Polyethylene terephthalate – Wikipedia; Polyethylene – Wikipedia
* **Action**: Exclude from mechanical recycling; consider energy recovery only if permitted.

## Discrimination matrix

| Material | Common contaminant | Key test | Impact | Safety note | Recommended action |
|----------|-------------------|----------|--------|-------------|--------------------|
| PET | PVC labels/film | Density, hot needle | Incompatible; HCl risk | HCl gas on heating | Manual/sink-float removal |
| PET | Metal clips | Magnet | Equipment damage | Cutting hazard | Magnet + eddy current |
| HDPE | Food residue | Wash water turbidity | Odor, hydrolysis | Aerosol exposure | Wash + dry |
| PP | Rubber/foam PS | Float/sink, elasticity | Gel, fines | Styrene VOC | Air classification |
| Mixed stream | Multi-layer laminate | Peel test | Non-recyclable | Dust | Exclude |

## Recording guidelines

* Always enter contaminant_name, material_code, impact_description, safety_notes, source_title, source_url, review_status.
* Do not invent risks. If unknown, leave compatibility/status as Unknown and note source limitation.
* Use GET /api/v1/contamination and MCP search_contamination_risks to surface recorded risks.

## Limitations

* Visual cues are indicative only.
* Unknown polymer compatibility must remain unknown; do not infer.
* Safety notes are mandatory and must be sourced.
