# Audit sample — Algorithmic fairness in machine learning

15-paper stratified sample from the ml-fairness snowball, drawn deterministically (`seed=42`). Read each line, then write `agree` or `disagree` in the third-to-last column. Any paper with `hard: [...]` is one the rubric might get wrong for a specific reason — those are the borders worth checking.

Discriminator, restated: **contribution, not vocabulary**. See `docs/rubrics/ml-fairness.md`.

## 1. `W4362714312` — Fairness in Graph Mining: A Survey

- **Year**: 2023 · **Venue**: IEEE Transactions on Knowledge and Data Engineering · **Cited**: 139
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: strong in-domain term: 'algorithmic fairness'

> Graph mining algorithms have been playing a significant role in myriad fields over the years. However, despite their promising performance on various graph analytical tasks, most of these algorithms lack fairness considerations. As a consequence, they could lead to discrimination towards certain populations when exploited in human-centered applications. Recently, algorithmic fairness has been extensively studied in graph-based applications. In contrast to algorithmic fairness on independent and 

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 2. `W2510508396` — Algorithmic Transparency via Quantitative Input Influence: Theory and Experiments with Learning Systems

- **Year**: 2016 · **Venue**: None · **Cited**: 718
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: strong in-domain term: 'disparate impact'

> Algorithmic systems that employ machine learning play an increasing role in making substantive decisions in modern society, ranging from online personalization to insurance and credit decisions to predictive policing. But their decision-making processes are often opaque-it is difficult to explain why a certain decision was made. We develop a formal foundation to improve the transparency of such decision-making systems. Specifically, we introduce a family of Quantitative Input Influence (QII) mea

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 3. `W2790025105` — The cost of fairness in binary classification

- **Year**: 2018 · **Venue**: None · **Cited**: 162
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: anchor + topic co-occur in title

> (no abstract)

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 4. `W4386712902` — AI Fairness in Data Management and Analytics: A Review on Challenges, Methodologies and Applications

- **Year**: 2023 · **Venue**: Applied Sciences · **Cited**: 155
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: anchor + topic co-occur within 30 tokens

> This article provides a comprehensive overview of the fairness issues in artificial intelligence (AI) systems, delving into its background, definition, and development process. The article explores the fairness problem in AI through practical applications and current advances and focuses on bias analysis and fairness training as key research directions. The paper explains in detail the concept, implementation, characteristics, and use cases of each method. The paper explores strategies to reduce

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 5. `W2725155646` — Data Decisions and Theoretical Implications when Adversarially Learning Fair Representations

- **Year**: 2017 · **Venue**: arXiv (Cornell University) · **Cited**: 295
- **Label (heuristic)**: `on-domain` (`core`)
- **Rationale**: strong in-domain term: 'fair representation'

> How can we learn a classifier that is "fair" for a protected or sensitive group, when we do not know if the input to the classifier belongs to the protected group? How can we train such a classifier when data on the protected group is difficult to attain? In many settings, finding out the sensitive input attribute can be prohibitively expensive even during model training, and sometimes impossible during model serving. For example, in recommender systems, if we want to predict if a user will clic

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 6. `W4385416124` — Algorithmic fairness and bias mitigation for clinical machine learning with deep reinforcement learning

- **Year**: 2023 · **Venue**: Nature Machine Intelligence · **Cited**: 138
- **Label (heuristic)**: `on-domain` (`core`) — **hard**: medical-ml with fairness section
- **Rationale**: anchor + topic co-occur in title

> As models based on machine learning continue to be developed for healthcare applications, greater effort is needed to ensure that these technologies do not reflect or exacerbate any unwanted or discriminatory biases that may be present in the data. Here we introduce a reinforcement learning framework capable of mitigating biases that may have been acquired during data collection. In particular, we evaluated our model for the task of rapidly predicting COVID-19 for patients presenting to hospital

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 7. `W4366998893` — Toward fairness in artificial intelligence for medical image analysis: identification and mitigation of potential biases in the roadmap from data collection to model deployment

- **Year**: 2023 · **Venue**: Journal of medical imaging · **Cited**: 143
- **Label (heuristic)**: `on-domain` (`core`) — **hard**: medical-ml with fairness section
- **Rationale**: anchor + topic co-occur in title

> Purpose: To recognize and address various sources of bias essential for algorithmic fairness and trustworthiness and to contribute to a just and equitable deployment of AI in medical imaging, there is an increasing interest in developing medical imaging-based machine learning methods, also known as medical imaging artificial intelligence (AI), for the detection, diagnosis, prognosis, and risk assessment of disease with the goal of clinical implementation. These tools are intended to help improve

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 8. `W3213776081` — Towards Green Automated Machine Learning: Status Quo and Future Directions

- **Year**: 2023 · **Venue**: Journal of Artificial Intelligence Research · **Cited**: 50
- **Label (heuristic)**: `off-domain` (`—`)
- **Rationale**: no domain signal (default-exclude)

> Automated machine learning (AutoML) strives for the automatic configuration of machine learning algorithms and their composition into an overall (software) solution — a machine learning pipeline — tailored to the learning task (dataset) at hand. Over the last decade, AutoML has developed into an independent research field with hundreds of contributions. At the same time, AutoML is being criticized for its high resource consumption as many approaches rely on the (costly) evaluation of many machin

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 9. `W4211098450` — Evaluation Methods and Measures for Causal Learning Algorithms

- **Year**: 2022 · **Venue**: IEEE Transactions on Artificial Intelligence · **Cited**: 76
- **Label (heuristic)**: `off-domain` (`—`)
- **Rationale**: no domain signal (default-exclude)

> The convenient access to copious multifaceted data has encouraged machine learning researchers to reconsider correlation-based learning and embrace the opportunity of causality-based learning, i.e., causal machine learning (causal learning). Recent years have, therefore, witnessed great effort in developing causal learning algorithms aiming to help artificial intelligence (AI) achieve human-level intelligence. Due to the lack of ground-truth data, one of the biggest challenges in current causal 

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 

## 10. `W4405412195` — Leveraging artificial intelligence to reduce diagnostic errors in emergency medicine: Challenges, opportunities, and future directions

- **Year**: 2024 · **Venue**: Academic Emergency Medicine · **Cited**: 58
- **Label (heuristic)**: `off-domain` (`—`) — **hard**: medical-ml with fairness section
- **Rationale**: primary field is off-domain: 'medicine'

> Diagnostic errors in health care pose significant risks to patient safety and are disturbingly common. In the emergency department (ED), the chaotic and high-pressure environment increases the likelihood of these errors, as emergency clinicians must make rapid decisions with limited information, often under cognitive overload. Artificial intelligence (AI) offers promising solutions to improve diagnostic errors in three key areas: information gathering, clinical decision support (CDS), and feedba

- **Reviewer**: agree / disagree — 
- **Note (if disagree)**: 
