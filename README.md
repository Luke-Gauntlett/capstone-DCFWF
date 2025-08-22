# ETL Project Walkthrough

## PROJECT REQUIREMENTS
---

The goal of this project is to build a robust ETL (Extract, Transform, Load) pipeline that will pull order data from my website's API. This data will then be cleaned, anonymized where necessary, and enriched to provide valuable insights. The processed data will be stored in a database, making it ready for analysis and display in a Streamlit dashboard. This analysis will focus on key business metrics such as average customer spend, identifying most and least commonly bought products, and calculating highest profit items, all to support marketing efforts.

---

## EPIC 1: Data Extraction from Website API

```text
As a Data Engineer,
I want to extract order, customer, product, and related data from my website's API,
So that I can obtain comprehensive raw data, allow for incremental updates, and comply with GDPR.
```

---

#### Epic 1 ACCEPTANCE CRITERIA

- [x] Data is extracted from the website API for orders
- [x] Full extraction runs if no previous timestamp exists
- [x] Supports incremental extraction based on last run timestamp
- [x] Extraction handles API pagination and rate limits
- [x] Data integrity is maintained (no missing data)
- [x] Extracted data is passed to transform script 
- [ ] tests verify extraction success
- [ ] Successful extractions are logged with timestamps
- [ ] API errors are logged and handled gracefully

---

## EPIC 2: Data Cleaning, Anonymization, and Enrichment

```text
As a Data Engineer,
I want to clean, anonymize, and enrich the extracted data,
So that it is ready for accurate analysis and complies with privacy regulations.
```

---

#### Epic 2 ACCEPTANCE CRITERIA

- [x] Remove duplicate and incomplete records
- [x] Standardize data types
- [x] Mask or hash or remove personally identifiable information (names, emails, phone numbers)
- [x] Enrich order data with calculated metrics
- [ ] Validate data against expected schema
- [ ] Transformation errors are logged and handled
- [ ] Successful transformations are logged with row counts
- [ ] Unit tests verify anonymisation and transformation accuracy

---

## EPIC 3: Data Loading into Analytical Database

```text
As a Data Engineer,
I want to load the transformed data into a database,
So that it is securely stored and readily available for analysis.
```

---

- [x] Database connection is established securely using environment variables
- [x] Transformed data is loaded into target tables without data loss
- [x] Existing data is updated or new data appended
- [ ] Data integrity is verified post-load
- [ ] Tests verify loading logic
- [ ] Load errors are logged and handled gracefully
- [ ] Successful loads are logged with timestamps and row counts

---

## EPIC 4: Streamlit Dashboard for Data Analysis

```text
As Data Analysis,
I want a Streamlit dashboard displaying analysis of the data,
So I can easily understand key business insights and inform marketing strategies.
```

---

- [x] Dashboard connects to the database
- [x] Displays key metrics (average customer spend, most/least bought products, highest profit items, uk heatmap)
- [x] Includes interactive filters (date range, product category)
- [x] Visualizations are clear and responsive
- [x] Dashboard updates reflect the latest available data
- [ ] testing verifies visualizations
- [ ] Errors in data retrieval are logged and handled

---

## Definition of Done

- [x] All tasks are completed
- [ ] All tests are passing
- [ ] Code coverage is at least 80%
- [ ] Code is linted and follows style guidelines
- [ ] Documentation is updated
- [ ] Code is merged into the main branch

---
