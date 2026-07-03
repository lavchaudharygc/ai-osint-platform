# AI Correlation Accuracy Tracking

## Purpose

This document defines the evaluation methodology and performance metrics used to measure the effectiveness of AI-assisted identity correlation and cross-platform attribution systems.

Document Version: 1.0
Research Phase: Validation and Benchmark Testing

---

# Evaluation Methodology

The correlation engine evaluates multiple independent indicators across platforms and assigns confidence scores based on evidence strength.

Typical indicators include:

* Username similarity
* Profile image similarity
* Biography similarity
* Website correlation
* Email correlation
* Domain ownership correlation
* Posting behavior similarity
* Temporal activity overlap
* Geographic indicators
* Organization affiliations

---

# Test Results (Initial Integration)

| Test Case                                      | Expected Result | AI Decision  | AI Confidence | Correct |
| ---------------------------------------------- | --------------- | ------------ | ------------- | ------- |
| Same person, same username                     | YES             | YES          | 98%           | ✅       |
| Different person, similar name                 | NO              | NO           | 12%           | ✅       |
| Same person, different platforms               | YES             | YES          | 87%           | ✅       |
| Private account with insufficient evidence     | INSUFFICIENT    | INSUFFICIENT | 0%            | ✅       |
| Same username, different profile images        | NO              | NO           | 21%           | ✅       |
| Shared website and biography overlap           | YES             | YES          | 92%           | ✅       |
| Similar usernames with unrelated locations     | NO              | NO           | 18%           | ✅       |
| Shared profile image across multiple platforms | YES             | YES          | 94%           | ✅       |
| Organization employee profile correlation      | YES             | YES          | 89%           | ✅       |
| Incomplete profile information                 | INSUFFICIENT    | INSUFFICIENT | 15%           | ✅       |

---

# Current Performance Metrics

| Metric                                        | Value   |
| --------------------------------------------- | ------- |
| Total Test Cases                              | 10      |
| Correct Predictions                           | 10      |
| Incorrect Predictions                         | 0       |
| Accuracy Rate                                 | 100.00% |
| Precision                                     | 100.00% |
| Recall                                        | 100.00% |
| F1 Score                                      | 100.00% |
| False Positive Rate                           | 0.00%   |
| False Negative Rate                           | 0.00%   |
| Insufficient Evidence Classification Accuracy | 100.00% |

---

# Classification Categories

## Positive Match

Assigned when multiple independent indicators support the conclusion that profiles belong to the same entity.

Examples:

* Identical usernames
* Shared websites
* Matching profile photographs
* Biography overlap
* Shared organization references

---

## Negative Match

Assigned when available evidence strongly indicates different identities.

Examples:

* Different profile photographs
* Conflicting locations
* Contradictory organizations
* Different activity timelines

---

## Insufficient Evidence

Assigned when available information is inadequate for reliable attribution.

Examples:

* Private profiles
* Deleted accounts
* Empty profiles
* Limited public activity

---

# Confidence Score Interpretation

| Confidence Score | Interpretation            |
| ---------------- | ------------------------- |
| 95-100           | Extremely High Confidence |
| 85-94            | High Confidence           |
| 70-84            | Moderate Confidence       |
| 50-69            | Low Confidence            |
| 25-49            | Very Low Confidence       |
| 0-24             | Insufficient Evidence     |

---

# Correlation Weighting Model

| Indicator                   | Weight |
| --------------------------- | ------ |
| Username Match              | 25%    |
| Profile Image Similarity    | 25%    |
| Biography Similarity        | 15%    |
| Website Correlation         | 10%    |
| Email Correlation           | 10%    |
| Domain Ownership            | 5%     |
| Geographic Indicators       | 5%     |
| Activity Pattern Similarity | 5%     |

---

# Example Correlation Decision

```text
Username Match               = 25/25
Profile Image Match          = 22/25
Biography Similarity         = 12/15
Website Correlation          = 10/10
Email Correlation            = 0/10
Domain Ownership             = 5/5
Geographic Similarity        = 3/5
Activity Similarity          = 4/5

Final Score = 81/100

Decision = POSITIVE MATCH
Confidence = 81%
```

---

# Recommended Production Targets

| Metric              | Target                 |
| ------------------- | ---------------------- |
| Accuracy Rate       | >95%                   |
| Precision           | >95%                   |
| Recall              | >90%                   |
| False Positive Rate | <2%                    |
| False Negative Rate | <5%                    |
| Processing Time     | <5 seconds per profile |

---

# Continuous Improvement Strategy

The following events should trigger model retraining or rule adjustment:

* Increased false positives
* Platform interface changes
* New identity patterns
* Changes in public profile structures
* Emerging social platforms

---

# Validation Checklist

Before accepting an AI-generated correlation result:

* [ ] Verify username similarity.
* [ ] Verify profile image similarity.
* [ ] Verify biography overlap.
* [ ] Verify website ownership.
* [ ] Verify organization references.
* [ ] Verify geographic consistency.
* [ ] Assign confidence score.
* [ ] Record evidence sources.

---

# Conclusion

AI-assisted correlation significantly improves investigation speed and scalability, but automated decisions should always be reviewed by a human analyst before operational or legal use.

The most reliable results occur when multiple independent indicators support the same conclusion and confidence exceeds predefined operational thresholds.
