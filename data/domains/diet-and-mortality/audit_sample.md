# Audit sample — Diet and all-cause mortality

15-paper stratified sample from the diet-and-mortality snowball, drawn deterministically (`seed=42`). Read each line, then write `agree` or `disagree` in the third-to-last column. Any paper with `hard: [...]` is one the rubric might get wrong for a specific reason — those are the borders worth checking.

Discriminator, restated: **contribution, not vocabulary**. See `docs/rubrics/diet-and-mortality.md`.

## 1. `W2126726883` — Roles of Drinking Pattern and Type of Alcohol Consumed in Coronary Heart Disease in Men

- **Year**: 2003 · **Venue**: New England Journal of Medicine · **Cited**: 817
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: same-sentence pair: 'alcohol consumption' + 'cardiovascular disease'

> BACKGROUND: Although moderate drinking confers a decreased risk of myocardial infarction, the roles of the drinking pattern and type of beverage remain unclear. METHODS: We studied the association of alcohol consumption with the risk of myocardial infarction among 38,077 male health professionals who were free of cardiovascular disease and cancer at base line. We assessed the consumption of beer, red wine, white wine, and liquor individually every four years using validated food-frequency questi

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 2. `W2789317488` — Risk factors for type 2 diabetes mellitus: An exposure-wide umbrella review of meta-analyses

- **Year**: 2018 · **Venue**: PLoS ONE · **Cited**: 743
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: same-sentence pair: 'dietary pattern' + 'metabolic syndrome'

> BACKGROUND: Type 2 diabetes mellitus (T2DM) is a global epidemic associated with increased health expenditure, and low quality of life. Many non-genetic risk factors have been suggested, but their overall epidemiological credibility has not been assessed. METHODS: We searched PubMed to capture all meta-analyses and Mendelian randomization studies for risk factors of T2DM. For each association, we estimated the summary effect size, its 95% confidence and prediction interval, and the I2 metric. We

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 3. `W2049646863` — Dietary Prevention of Coronary Heart Disease: The Finnish Mental Hospital Study

- **Year**: 1979 · **Venue**: International Journal of Epidemiology · **Cited**: 386
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: anchor + topic co-occur in title

> Turpeinen O [Proofessor Emeritus of Biochemistry, College of Veterinary Medicine, Hämeentie 57, 00550 Helsinki 55, Finland], Karvonen M J, Pekkarinen M, Miettinen M, Elosuo R and Paavilainen E. Dietary prevention of coronary heart disease: the Finnish Mental Hospital Study. International Journal of Epidemiology 1979, 8: 99–118. A controlled intervention trial, with the purpose of testing the hypothesis that the incidence of coronary heart disease (CHD) could be decreased by the use of serum-chol

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 4. `W2323151514` — Beneficial Effects of High Dietary Fiber Intake in Patients with Type 2 Diabetes Mellitus

- **Year**: 2000 · **Venue**: New England Journal of Medicine · **Cited**: 1138
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: anchor + topic co-occur in title

> BACKGROUND: The effect of increasing the intake of dietary fiber on glycemic control in patients with type 2 diabetes mellitus is controversial. METHODS: In a randomized, crossover study, we assigned 13 patients with type 2 diabetes mellitus to follow two diets, each for six weeks: a diet containing moderate amounts of fiber (total, 24 g; 8 g of soluble fiber and 16 g of insoluble fiber), as recommended by the American Diabetes Association (ADA), and a high-fiber diet (total, 50 g; 25 g of solub

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 5. `W4229029536` — Long-term secondary prevention of cardiovascular disease with a Mediterranean diet and a low-fat diet (CORDIOPREV): a randomised controlled trial

- **Year**: 2022 · **Venue**: The Lancet · **Cited**: 639
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: anchor + topic co-occur in title

> (no abstract)

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 6. `W2109401990` — Red and Processed Meat Consumption and Risk of Incident Coronary Heart Disease, Stroke, and Diabetes Mellitus

- **Year**: 2010 · **Venue**: Circulation · **Cited**: 1268
- **Label (heuristic)**: `on-domain` (`core`) — **hard**: meta-analysis contradiction target
- **Rationale**: strong term in title: 'processed meat' + pair anywhere: 'coronary heart disease'

> BACKGROUND: Meat consumption is inconsistently associated with development of coronary heart disease (CHD), stroke, and diabetes mellitus, limiting quantitative recommendations for consumption levels. Effects of meat intake on these different outcomes, as well as of red versus processed meat, may also vary. METHODS AND RESULTS: We performed a systematic review and meta-analysis of evidence for relationships of red (unprocessed), processed, and total meat consumption with incident CHD, stroke, an

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 7. `W2109129984` — Association of alcohol consumption with selected cardiovascular disease outcomes: a systematic review and meta-analysis

- **Year**: 2011 · **Venue**: BMJ · **Cited**: 1629
- **Label (heuristic)**: `on-domain` (`core`) — **hard**: food-chemistry co-mention, meta-analysis contradiction target
- **Rationale**: strong term in title: 'alcohol consumption' + pair anywhere: 'cardiovascular disease'

> OBJECTIVE: To conduct a comprehensive systematic review and meta-analysis of studies assessing the effect of alcohol consumption on multiple cardiovascular outcomes. DESIGN: Systematic review and meta-analysis. DATA SOURCES: A search of Medline (1950 through September 2009) and Embase (1980 through September 2009) supplemented by manual searches of bibliographies and conference proceedings. Inclusion criteria Prospective cohort studies on the association between alcohol consumption and overall m

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 8. `W1996559225` — Independent predictors of liver fibrosis in patients with nonalcoholic steatohepatitis

- **Year**: 1999 · **Venue**: Hepatology · **Cited**: 1618
- **Label (heuristic)**: `borderline` (`peripheral`)
- **Rationale**: pair (outcome) term without required exposure

> Nonalcoholic steatohepatitis (NASH) may present with increased hepatic fibrosis progressing to end-stage liver disease. No factors that determine increasing fibrosis and histologically advanced disease have been recognized, thus, liver biopsy is recommended in all patients for diagnosis and prognosis. Our aim was to identify independent predictors of severe hepatic fibrosis in patients with NASH. One hundred and forty-four patients were studied. All patients underwent liver biopsy. Clinical and 

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 9. `W1520609538` — Ezetimibe Added to Statin Therapy after Acute Coronary Syndromes

- **Year**: 2015 · **Venue**: New England Journal of Medicine · **Cited**: 4525
- **Label (heuristic)**: `borderline` (`peripheral`)
- **Rationale**: pair (outcome) term without required exposure

> BACKGROUND: Statin therapy reduces low-density lipoprotein (LDL) cholesterol levels and the risk of cardiovascular events, but whether the addition of ezetimibe, a nonstatin drug that reduces intestinal cholesterol absorption, can reduce the rate of cardiovascular events further is not known. METHODS: We conducted a double-blind, randomized trial involving 18,144 patients who had been hospitalized for an acute coronary syndrome within the preceding 10 days and had LDL cholesterol levels of 50 to

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 10. `W2225912682` — Beverage purchases from stores in Mexico under the excise tax on sugar sweetened beverages: observational study

- **Year**: 2016 · **Venue**: BMJ · **Cited**: 835
- **Label (heuristic)**: `borderline` (`peripheral`)
- **Rationale**: strong term without required pair: 'sugar sweetened beverage'

> STUDY QUESTION: What has been the effect on purchases of beverages from stores in Mexico one year after implementation of the excise tax on sugar sweetened beverages? METHODS: In this observational study the authors used data on the purchase of beverages in Mexico from January 2012 to December 2014 from an unbalanced panel of 6253 households providing 205 112 observations in 53 cities with more than 50 000 inhabitants. To test whether the post-tax trend in purchases was significantly different f

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 11. `W1922087192` — Meta-Analysis: High-Dosage Vitamin E Supplementation May Increase All-Cause Mortality

- **Year**: 2005 · **Venue**: Annals of Internal Medicine · **Cited**: 2576
- **Label (heuristic)**: `borderline` (`peripheral`) — **hard**: food-chemistry co-mention, supplement not diet, meta-analysis contradiction target
- **Rationale**: pair (outcome) term without required exposure

> BACKGROUND: Experimental models and observational studies suggest that vitamin E supplementation may prevent cardiovascular disease and cancer. However, several trials of high-dosage vitamin E supplementation showed non-statistically significant increases in total mortality. PURPOSE: To perform a meta-analysis of the dose-response relationship between vitamin E supplementation and total mortality by using data from randomized, controlled trials. PATIENTS: 135,967 participants in 19 clinical tria

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 12. `W2121393149` — The State of US Health, 1990-2010

- **Year**: 2013 · **Venue**: JAMA · **Cited**: 2480
- **Label (heuristic)**: `borderline` (`peripheral`) — **hard**: meta-analysis contradiction target
- **Rationale**: pair (outcome) term without required exposure

> IMPORTANCE: Understanding the major health problems in the United States and how they are changing over time is critical for informing national health policy. OBJECTIVES: To measure the burden of diseases, injuries, and leading risk factors in the United States from 1990 to 2010 and to compare these measurements with those of the 34 countries in the Organisation for Economic Co-operation and Development (OECD) countries. DESIGN: We used the systematic analysis of descriptive epidemiology of 291 

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 13. `W2987944394` — Dietary linoleic acid and human health: Focus on cardiovascular and cardiometabolic effects

- **Year**: 2019 · **Venue**: Atherosclerosis · **Cited**: 426
- **Label (heuristic)**: `off-domain` (`—`)
- **Rationale**: no domain signal (default-exclude)

> (no abstract)

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 14. `W2970686316` — The Microbiota-Gut-Brain Axis

- **Year**: 2019 · **Venue**: Physiological Reviews · **Cited**: 5235
- **Label (heuristic)**: `off-domain` (`—`)
- **Rationale**: primary field is off-domain: 'biochemistry, genetics and molecular biology'

> The importance of the gut-brain axis in maintaining homeostasis has long been appreciated. However, the past 15 yr have seen the emergence of the microbiota (the trillions of microorganisms within and on our bodies) as one of the key regulators of gut-brain function and has led to the appreciation of the importance of a distinct microbiota-gut-brain axis. This axis is gaining ever more traction in fields investigating the biological and physiological basis of psychiatric, neurodevelopmental, age

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 15. `W2146476358` — The Guild Concept and the Structure of Ecological Communities

- **Year**: 1991 · **Venue**: Annual Review of Ecology and Systematics · **Cited**: 891
- **Label (heuristic)**: `off-domain` (`—`)
- **Rationale**: no domain signal (default-exclude)

> (Uploaded by Plazi for the Bat Literature Project) No abstract provided.

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 
