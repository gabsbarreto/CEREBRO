from __future__ import annotations

import uuid
import re
from pathlib import Path

from app import config


DEFAULT_SYSTEM_PROMPT_SUFFIX = "Use the user-provided text to extract the information required."
DEFAULT_PROMPT_FILENAME = config.DEFAULT_RQ_PROMPT_FILENAME
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

RQ_SCREENING_PROMPT_TEMPLATE = """You are screening a full-text research article for a systematic review on children and young people seeking, presenting to, referred to, accessing, or attending specialist gender services or health services from which specialist gender services/treatments may be accessed.

Your task is NOT to make a final include/exclude decision for the whole review.

Your task is to determine whether the full text reports original empirical data that could answer any of the following review questions:

RQ1. How have numbers of children and young people seeking, presenting to, or referred to specialist gender services changed over time?

RQ3. What are the characteristics of children and young people recently seeking or attending specialist services for gender dysphoria or gender incongruence?

RQ4. What are the numbers or proportions of children and young people recently seeking or attending specialist services who progress to specific care pathway events?

RQ5. What are the wait times or time intervals between referral, assessment, diagnosis, and initiation of medical or psychological care?

This screening guidance applies only to RQ1, RQ3, RQ4 and RQ5. 

Core screening rule: own-study data only

Only tag an RQ as relevant if the article reports original empirical data generated or analysed by this study itself.

Do NOT tag an RQ based only on:
- background statements in the Introduction;
- claims in the Discussion that are not supported by the study’s own results;
- cited statistics from other papers, reviews, reports, registries, guidelines, or national databases, unless the present study directly analyses those data;
- author speculation;
- qualitative descriptions when the RQ requires quantitative numbers, proportions, or timings;
- outcomes, characteristics, or pathway events that are only mentioned as clinically important but are not measured in the study.

If uncertain whether the data come from the present study, mark the RQ as “Unclear / human check”.

Empirical research and publication type

The article should report empirical primary research.

Eligible study types may include:
- quantitative studies;
- qualitative studies only if they include extractable quantitative data relevant to RQ1, RQ3, RQ4 or RQ5;
- mixed-methods studies with relevant quantitative data;
- case series with clear methods.

Do NOT count as eligible empirical evidence for these RQs:
- systematic reviews;
- scoping reviews;
- narrative reviews;
- literature reviews;
- commentaries;
- opinion pieces;
- letters to the editor;
- conference abstracts or proceedings;
- dissertations or theses;
- protocols without results;
- single case reports.

Trial registries may be relevant only if they contain actual results/data. If a trial registry, protocol, brief report, or correction appears relevant but lacks sufficient data, mark “Unclear / human check” and state what follow-up is needed.

Population and setting rules

The population of interest is children and young people aged 0 to 25 years at presentation, referral, first measurement, or relevant care-pathway event.

The primary interest is people under 18, but studies may still be relevant if the eligible data concern people up to age 25.

For age eligibility:
- If the study focuses on people aged 0 to 25, it may be relevant.
- If mean or median age is under 25, it may be relevant. It will be included even if the lowest age range is 18 as long as mean or median is < 25 years of age.
- If the study includes both children/young people and adults over 25, only tag an RQ as “Yes” if data for individuals under 25 can be disaggregated from adult data.
- If adult and under-25 data are mixed and cannot be disaggregated, mark the relevant RQ as “No” or “Unclear / human check” depending on whether the issue is clear.
- If age eligibility is unclear but the study otherwise appears relevant, mark “Unclear / human check”.

The setting should involve:
- specialist gender services; OR
- a specialist gender services pathway; OR
- health services from which specialist gender services may be accessed; OR
- referrals/presentations for gender dysphoria, gender incongruence, gender identity concerns, or related specialist gender care.

Be inclusive when service labels are unclear. In some countries or health systems, specialist gender services may be integrated across departments and may not be explicitly called a “gender clinic”. If the study plausibly concerns a specialist gender service or pathway, do not exclude only because the label is different.

However, do NOT tag studies that only examine general medical records or general healthcare use without any reference to referral to, attendance at, or use of specialist gender services or a specialist gender services pathway.

Representativeness and sampling rules

Be flexible at screening.

A study may be treated as having a representative sample if the authors intended the sample to represent a relevant service/pathway population, or if anyone in the relevant service/pathway population had the opportunity or chance to participate.

Do NOT reject a study only because:
- only a proportion of eligible participants agreed to participate;
- response rate is imperfect;
- the study uses a convenience sample;
- the study is a case series.

These issues may be risk-of-bias/appraisal concerns rather than full-text screening exclusions.

Include convenience samples for now unless the methods explicitly show that the sample was selected to be unrepresentative, for example, selected only because participants had a specific unusual feature.

Include case series for now regardless of sample size, provided clear methods are stated.

Do NOT include single case reports.

Data collection period rules for RQ3, RQ4 and RQ5

These date rules apply only to RQ3, RQ4 and RQ5. They do NOT apply to RQ1.

For RQ3, RQ4 and RQ5, relevant data should have been collected in 2015 or later.

“Data collection period” means when the relevant participant/event/service exposure occurred, not when the researchers accessed records.

For studies with data collection periods spanning before and after 2015:
- Include for RQ3/RQ4/RQ5 if at least 50% of the data collection period falls in 2015 or later.
- If exactly half of the data collection period is in 2015 or later, count this as eligible.
- If only years are reported, assume full calendar years from January 1 to December 31.
- Example: 2012–2016 = exclude for RQ3/RQ4/RQ5 unless the article explicitly states that more than half the data were collected in 2015 or later.
- Example: 2013–2016 = include for RQ3/RQ4/RQ5 because at least half the period is 2015 or later.
- If the overall date range fails the ≥50% rule but the article explicitly states that more than half of the participants/events occurred in 2015 or later, count this as eligible.
- If the data collection period or event period is not stated but the study otherwise appears relevant, mark “Unclear / human check”.

RQ-specific rules

RQ1 — Change over time in numbers seeking/presenting/referred

Tag RQ1 as relevant only if the study reports quantitative numbers of children/young people:
- seeking care;
- presenting to health services with concerns about gender identity;
- being referred to specialist gender services;
- attending specialist gender services;
- entering a specialist gender services pathway;

AND these numbers are reported at two or more distinct time points at least one year apart.

RQ1 has no restriction to data collected since 2015.

Relevant examples:
- annual number of referrals to a gender identity clinic from 2010 to 2020;
- number of presentations by year;
- number of referrals by year, age group, and sex recorded at birth;
- time trends in clinic referrals;
- numbers presenting to health services with gender identity concerns at multiple calendar years.

Do NOT tag RQ1 if:
- the study reports only one time point;
- the repeated time points are less than one year apart;
- it reports only prevalence in the general population;
- it reports a time trend in attitudes, mental health, or treatment outcomes rather than numbers seeking/presenting/referred;
- the “time” element is only duration of follow-up within a cohort, not calendar changes in numbers presenting/referred.

RQ3 — Characteristics of young people seeking or attending specialist services

Tag RQ3 as relevant if the study reports numbers, proportions, averages, or other quantitative summaries of at least one characteristic of children/young people seeking, attending, or currently enrolled in specialist services for gender dysphoria or gender incongruence, AND the sample is intended to represent the wider clinic/service population rather than a selected subgroup based on treatment status or progression to a specific pathway stage.

For RQ3, the sample does not have to be limited to people at first presentation or referral. It may be relevant if it represents the broader service population at a defined point or period.

Examples of samples that can be relevant for RQ3:
- all referrals to a gender clinic between 2016 and 2020;
- all young people first assessed by a specialist gender service during a defined period;
- all new patients attending a clinic over a specified period;
- all patients currently enrolled in a specialist gender service;
- all active patients under the care of a clinic during a defined period;
- all patients in a clinic database, registry, or service cohort during a defined period;
- a general clinic cohort where participants were not selected because they had reached a specific treatment, intervention, diagnosis, or care pathway stage.

Do NOT tag RQ3 if the characteristics are reported only for a selected subgroup of the clinic population based on a specific treatment, intervention, diagnosis, eligibility status, or later stage of the care pathway.

Examples of samples that should NOT usually be tagged as RQ3:
- only patients who received puberty blockers;
- only patients who started masculinising or feminising hormones;
- only patients referred for endocrine assessment;
- only patients considered eligible for medical intervention;
- only patients who received fertility preservation;
- only patients who completed a particular treatment pathway stage;
- only patients who discontinued, desisted, de-transitioned, or re-transitioned;
- only patients with a specific comorbidity, unless the whole clinic/service population is explicitly defined by that condition.

These selected pathway-stage samples may still be relevant to RQ4 or RQ5 if they report numbers/proportions progressing through care pathway events or timing between pathway events, but they should not be tagged as RQ3 unless the study also reports characteristics for the broader unselected clinic/service population.

For RQ3, the characteristic may be measured at:
- referral;
- first approach to services;
- initial attempt to access services;
- presentation;
- first attendance;
- initial assessment;
- current enrolment in the clinic;
- active care within the clinic;
- another clearly defined point representing the broader service population.

If the timing of the characteristic measurement is unclear but the study appears to describe a general, non-selected clinic/service sample, mark “Unclear / human check” or “Yes with caution” depending on whether the article provides enough usable quantitative data.

For RQ3, if the study reports the number with a characteristic, it should also report the number without that characteristic, the denominator, or enough information to calculate a proportion.

Tag RQ3 as “Yes” if:
- at least one relevant characteristic is reported quantitatively;
- a denominator/proportion can be determined; and
- the sample represents the wider clinic/service population, rather than a selected subgroup defined by treatment receipt, intervention eligibility, diagnosis, or progression to a specific pathway stage.

Relevant characteristics include, but are not limited to:

Demographic/personal characteristics:
- age at referral, presentation, first attendance, assessment, or enrolment;
- ethnicity;
- geographical location;
- urban/rural location;
- sexual orientation;
- socioeconomic status;
- other PROGRESS-Plus factors.

Gender-related characteristics:
- gender identity;
- sex recorded at birth;
- diagnosis of gender dysphoria or gender incongruence;
- age at onset/progression/diagnosis;
- social transition status.

Mental health/health characteristics:
- anxiety;
- depression;
- eating disorders;
- autism;
- ADHD;
- neurodevelopmental conditions;
- self-harm;
- suicide attempts;
- suicidal ideation;
- resilience;
- self-confidence;
- self-esteem.

Other contextual characteristics:
- adverse childhood experiences;
- protective factors;
- bullying;
- discrimination;
- minority stress;
- stigma;
- micro-aggressions;
- school culture;
- family context;
- family support for transition.

Do NOT tag RQ3 if:
- the sample is selected because participants received, were eligible for, or progressed to a specific treatment/intervention/pathway stage;
- the study reports characteristics only for a pathway-stage subgroup rather than the general clinic/service population;
- characteristics are only described qualitatively without extractable quantitative data;
- characteristics are reported only for adults over 25;
- adult and under-25 data cannot be disaggregated;
- characteristics are only mentioned in the background or discussion;
- the study does not involve people seeking, referred to, attending, or currently enrolled in relevant specialist services;
- only the number with a characteristic is reported and no denominator or number without the characteristic can be determined.

RQ4 — Numbers/proportions progressing through care pathway events

Tag RQ4 as relevant if the study reports numbers or proportions of children/young people seeking or attending specialist services who experience at least one care pathway event.

RQ4 can be informed by data from any entry point in the specialist gender services pathway, including later pathway stages, if the data capture or inform progression through care.

For RQ4, if the study reports the number experiencing an event, it should also report the number not experiencing the event, the denominator, or enough information to calculate a proportion.

Tag RQ4 as “Yes” if at least one relevant pathway event is reported quantitatively and a denominator/proportion can be determined.

Relevant RQ4 events include numbers/proportions who:
- are assessed;
- are diagnosed with gender dysphoria or gender incongruence;
- are considered eligible for medical intervention;
- receive medical intervention;
- receive puberty blockers;
- receive masculinising or feminising hormones;
- receive surgery, if applicable;
- receive psychological care while under the care of a specialist gender service;
- are provided with fertility preservation options;
- access DIY medical treatments, especially hormones without direct medical supervision;
- desist, meaning leave the service pathway or cease assessment/intervention;
- de-transition or stop/reverse treatment, including reasons if reported;
- re-transition.

For medical interventions:
- Interest in an intervention is not enough.
- Preference for an intervention is not enough.
- Intention to pursue an intervention is not enough.
- The study must report provision, receipt, or access to the intervention, or eligibility for intervention if eligibility itself is the event being assessed.

Do NOT tag RQ4 if:
- the study only reports that a treatment exists but gives no numbers/proportions;
- treatment or diagnosis is mentioned only as an inclusion criterion and no pathway proportion is reported;
- it only reports qualitative experiences of care;
- the event is only a study procedure and not part of the care pathway;
- only the number experiencing an event is reported and no denominator or number not experiencing the event can be determined.

Important distinction:
Referral to a research follow-up visit does not count as a care pathway event unless it corresponds to actual referral, assessment, diagnosis, or initiation of care in clinical practice.

RQ5 — Wait times and time intervals in the care pathway

Tag RQ5 as relevant if the study reports quantitative information on waiting times or time intervals between relevant specialist gender services pathway events.

Relevant intervals include time between:
- referral and assessment;
- referral and first appointment;
- referral and diagnosis;
- assessment and diagnosis;
- diagnosis and medical intervention;
- diagnosis and psychological care;
- referral/assessment and initiation of puberty blockers;
- referral/assessment and initiation of gender-affirming hormones;
- referral/assessment and fertility preservation;
- referral/assessment and any other relevant medical or psychological care;
- other clearly defined stages of the specialist gender services pathway.

Relevant forms of timing data include:
- mean wait time;
- median wait time;
- range;
- interquartile range;
- numbers/proportions waiting longer than a specified time;
- time-to-event analyses;
- calendar wait-list duration;
- reported service waiting times if based on the study’s own data.

Do NOT tag RQ5 if:
- timing refers only to study follow-up duration;
- timing refers only to age at onset, age at referral, or age at treatment without an interval between care pathway events;
- waiting is discussed qualitatively without quantitative timing data;
- wait time is mentioned in the introduction/discussion but not measured in the study.

Handling uncertainty

Use “Unclear / human check” when:
- the study appears relevant but one key criterion is missing or unclear;
- the data collection period for RQ3/RQ4/RQ5 is not reported;
- the service/pathway appears plausibly relevant but is not clearly described;
- the age range is unclear;
- it is unclear whether under-25 data can be separated from adult data;
- it is unclear whether data are original study data or cited/background data;
- a protocol, registry, short report, correction, or brief report appears to contain or point to relevant data but not enough information is available.

Be conservative, but do not over-exclude at screening when the guidance says to be flexible.

Output format

Return your answer in the following format:

1. Overall judgement

State which RQs the full text is relevant to:
- Relevant RQs: RQ1, RQ3, RQ4, RQ5, or “None of RQ1/RQ3/RQ4/RQ5”
- Any uncertain RQs requiring human check

2. RQ-level assessment table

For each RQ, provide:

RQ | Decision | Information in the full text that makes it relevant or not relevant | Location in article | Notes for human reviewer

Use one of these decisions:
- Yes
- No
- Unclear / human check

3. Evidence summary

For each RQ marked “Yes”, briefly list the exact data type reported.

Examples:
- RQ1: annual referrals to a gender service from 2012 to 2021, stratified by sex recorded at birth.
- RQ3: age at referral, sex recorded at birth, gender identity, depression, anxiety, autism, with denominator/proportions.
- RQ4: numbers assessed, diagnosed, receiving puberty blockers, receiving hormones, with denominator/proportions.
- RQ5: median wait from referral to first appointment and from assessment to treatment initiation.

4. Screening concerns / human checks

List any issues that may need manual review, such as:
- unclear data collection period;
- unclear age eligibility;
- adult and youth data not clearly separated;
- unclear whether the service is a specialist gender service pathway;
- unclear denominator;
- possible relevant trial registry/protocol/brief report requiring follow-up.

**Do not over-extract**

Do not provide a full data extraction table.
Only identify whether the article is relevant to each RQ and what information makes it relevant.

**Conservative but flexible tagging rule**

Use “Yes” when the article clearly provides relevant original quantitative data for the RQ.

Use “Unclear / human check” when the article appears potentially relevant but one required item is missing, ambiguous, or needs human judgement.

Use “No” when the article clearly lacks the required population, setting, data type, date eligibility, or RQ-specific information.

Now assess the following full text:

{{FULL_TEXT}}
"""


def default_system_prompt() -> str:
    system_prompt = RQ_SCREENING_PROMPT_TEMPLATE.rsplit("Now assess the following full text:", maxsplit=1)[0].strip()
    return f"{system_prompt}\n\n{DEFAULT_SYSTEM_PROMPT_SUFFIX}\n"


def ensure_default_prompt_file() -> Path:
    config.PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.PROMPTS_DIR / DEFAULT_PROMPT_FILENAME
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        _write_prompt_file(path, default_system_prompt(), overwrite=True)
    return path


def list_prompt_files() -> list[dict[str, str]]:
    ensure_default_prompt_file()
    files: list[dict[str, str]] = []
    for path in sorted(config.PROMPTS_DIR.glob("*.txt"), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        files.append({"filename": path.name, "path": str(path)})
    return files


def read_prompt_file(filename: str | None = None) -> dict[str, str]:
    ensure_default_prompt_file()
    safe_name = sanitize_prompt_filename(filename or DEFAULT_PROMPT_FILENAME)
    path = _prompt_path(safe_name)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {safe_name}")
    return {"filename": safe_name, "path": str(path), "system_prompt": path.read_text(encoding="utf-8")}


def save_prompt_file(filename: str, system_prompt: str) -> dict[str, str]:
    system_prompt = system_prompt.strip()
    if not system_prompt:
        raise ValueError("Prompt cannot be empty.")
    safe_name = sanitize_prompt_filename(filename)
    path = _prompt_path(safe_name)
    if path.exists():
        raise FileExistsError(f"Prompt file already exists: {safe_name}")
    _write_prompt_file(path, system_prompt, overwrite=False)
    return {"filename": safe_name, "path": str(path), "system_prompt": path.read_text(encoding="utf-8")}


def build_prompt_transcript(system_prompt: str, user_prompt: str) -> str:
    return (
        "SYSTEM PROMPT\n"
        "=============\n\n"
        f"{system_prompt.strip()}\n\n"
        "USER PROMPT\n"
        "===========\n\n"
        f"{user_prompt.strip()}\n"
    )


def sanitize_prompt_filename(filename: str) -> str:
    raw_name = Path(str(filename or "")).name.strip()
    if not raw_name:
        raise ValueError("Prompt filename is required.")
    if raw_name.lower().endswith(".txt"):
        raw_name = raw_name[:-4]
    safe_stem = _SAFE_FILENAME_RE.sub("_", raw_name).strip("._-")
    if not safe_stem:
        raise ValueError("Prompt filename must contain at least one letter or number.")
    return f"{safe_stem}.txt"


def _prompt_path(filename: str) -> Path:
    path = (config.PROMPTS_DIR / filename).resolve()
    prompts_dir = config.PROMPTS_DIR.resolve()
    if path.parent != prompts_dir:
        raise ValueError("Prompt filename must stay inside the prompts folder.")
    return path


def _write_prompt_file(path: Path, prompt: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Prompt file already exists: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(prompt.strip() + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
