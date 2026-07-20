# Structured Sheet Import Guide

This guide explains how to prepare a structured PDF worksheet outside CEREBRO and paste it into the structured PDF dashboard.

Use this when you want to ask another LLM to help design a CEREBRO worksheet, then copy the result into CEREBRO using `Paste sheet / columns`.

## Accepted Paste Modes

CEREBRO accepts two paste modes in the same import box.

### Full Sheet Import

Use this when you want to populate the sheet name, context, more information / other preferences, and columns at once.

```text
Sheet name ### Species characteristics

Context ###
General context for this worksheet.

More information / other preferences ###
One row per eligible captive wild animal species.

Columns ###

Column name ### SpeciesLatinArticle

Question ### State the scientific name, in Latin/binomial nomenclature, of the captive wild animal species studied, exactly as it appears in the study.

Rules ###
* Extract the scientific name used in the article for the animal species, not the microorganism.
* If no scientific name is used in the study, enter `NA`.

---

Column name ### SpeciesCommonArticle

Question ### State the common name of the captive wild animal species studied, exactly as it appears in the study.

Rules ###
* Use the common name reported in the article.
* If no common name is reported, enter `NA`.
```

### Columns-Only Import

Use this when the sheet name, context, and preferences are already correct, and you only want to add or update columns.

```text
Column name ### SpeciesLatinArticle

Question ### State the scientific name, in Latin/binomial nomenclature, of the captive wild animal species studied, exactly as it appears in the study.

Rules ###
* Extract the scientific name used in the article for the animal species, not the microorganism.
* If no scientific name is used in the study, enter `NA`.

---

Column name ### SpeciesCommonArticle

Question ### State the common name of the captive wild animal species studied, exactly as it appears in the study.

Rules ###
* Use the common name reported in the article.
* If no common name is reported, enter `NA`.
```

## Import Rules

- Use `###` exactly after each heading.
- Use `---` on its own line to separate columns.
- Every column must have:
  - `Column name ###`
  - `Question ###`
  - `Rules ###`
- Column names must be unique within the pasted text.
- Column names must not contain tabs or line breaks.
- Prefer short, stable Excel-friendly column names.
- Good column names are descriptive but compact, for example:
  - `SpeciesLatinArticle`
  - `SpeciesCommonArticle`
  - `AnimalGroup`
  - `CaptivitySetting`
  - `OutcomeMeasured`
  - `WelfareIndicator`
  - `SampleSize`
  - `Country`
  - `StudyDesign`
- Avoid vague names such as `Info`, `Data`, `Result`, or `Column1`.
- If a field or column already exists in CEREBRO, the app will show one overwrite prompt listing all conflicts.
- Imported changes autosave after they are applied.
- A sheet can only be edited before its first run. After a sheet has been run, duplicate it to edit the schema.

## Standard Prompt For Another LLM

Copy the prompt below into another LLM. Replace the final blank section with the extraction plan or rough notes you want converted into CEREBRO format.

```text
You are helping me create a structured PDF extraction worksheet for CEREBRO.

Return only plain text in the exact format below. Do not include Markdown code fences, explanations, bullets outside the Rules sections, or any extra commentary.

Required format:

Sheet name ### <short worksheet name>

Context ###
<A concise paragraph describing the overall extraction context. Include the review topic, population/materials, and what kind of studies or PDFs the sheet is intended for.>

More information / other preferences ###
<Additional sheet-level instructions. Include what one row should represent, how to handle missing information, units, multiple values, eligibility boundaries, and any conventions that should apply across all columns.>

Columns ###

Column name ### <Excel-friendly column name>

Question ### <The exact question CEREBRO should answer for this column.>

Rules ###
* <Rule, expected values, examples, missing-value instruction, or extraction boundary.>
* <Another rule if needed.>

---

Column name ### <NextExcelFriendlyColumnName>

Question ### <The exact question CEREBRO should answer for this column.>

Rules ###
* <Rule, expected values, examples, missing-value instruction, or extraction boundary.>

Column requirements:
* Create short, stable, unique column names.
* Use only letters, numbers, and underscores when possible.
* Do not put tabs or line breaks inside column names.
* Do not use duplicate column names.
* Make each question specific enough that an extractor can answer it from a scientific PDF.
* Include rules for missing data, usually instructing CEREBRO to enter `NA` when not reported.
* Include allowed values or examples where useful.
* If multiple values may belong in one cell, say how they should be separated.
* Keep column names suitable for Excel headers.

Suggested column name style:
* Use names such as `SpeciesLatinArticle`, `SpeciesCommonArticle`, `AnimalGroup`, `Country`, `StudyDesign`, `SampleSize`, `Intervention`, `OutcomeMeasured`, `WelfareIndicator`, or similarly compact names adapted to the extraction task.
* Avoid vague names such as `Info`, `Data`, `Result`, `Column1`, or names that are too long.

Information I want to extract:

<PASTE MY EXTRACTION GOAL, NOTES, DRAFT PROMPT, VARIABLE LIST, OR REVIEW QUESTION HERE>
```

## After Pasting Into CEREBRO

1. Open a structured PDF project.
2. Select or create a sheet.
3. Click `Paste sheet / columns`.
4. Paste the LLM output.
5. Click `Import sheet / columns`.
6. If CEREBRO reports conflicts, review the list and choose `Overwrite` or `Cancel`.
7. Review the spreadsheet headers and column instruction boxes.
8. Wait for autosave to show that the draft is saved.
9. Run extraction only when the schema is ready.

## Exporting A Sheet For Reuse

To reuse an existing worksheet in another structured PDF workbook:

1. Open the source sheet in CEREBRO.
2. Click `Export sheet text` beside `Paste sheet / columns`.
3. Copy the generated text, or download it as a `.txt` file.
4. Open the target workbook sheet.
5. Click `Paste sheet / columns` and paste the exported text.

The exported text uses the same full sheet import format described above.
