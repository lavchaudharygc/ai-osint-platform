/**
 * Isolated Email Investigation UI for Beta-v2.
 *
 * This module intentionally keeps only a whitelisted, sanitized view model.
 * Raw provider records and credential values are never rendered or exported.
 */
(function () {
    "use strict";

    const EMAIL_API_BASE = typeof API_BASE !== "undefined"
        ? API_BASE
        : (window.API_BASE || "http://127.0.0.1:8010");
    const EMAIL_ENDPOINT = `${EMAIL_API_BASE}/api/v1/email-investigation`;
    const REQUEST_TIMEOUT_MS = 120000;
    const CASE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:/-]{2,63}$/;
    const REASON_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:\- ]{1,63}$/;
    const EMAIL_PATTERN = /^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$/i;
    const DISCOVERED_EMAIL_PATTERN = /[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,63}/gi;
    const CREDENTIAL_TYPE_PATTERN = /password|passwd|credential|authentication|security answer|secret|token|cookie|hash/i;
    const SENSITIVE_KEY_PATTERN = /password|passwd|pwd|hash|token|cookie|secret|security.?answer|cvv|card.?number|bank.?account|routing.?number|ssn|passport|driver.?licen[cs]e|government.?id|medical|diagnosis|treatment/i;
    const RESTRICTED_CONTACT_FIELDS = new Map([
        ["email", "Email"],
        ["full_name", "Full Name"],
        ["phone", "Phone"],
        ["address", "Address"],
        ["city", "City"],
        ["state", "State"],
        ["district", "District"],
        ["postal_code", "Postal Code"],
        ["country", "Country"],
        ["username", "Username"],
        ["company", "Company"],
        ["job_title", "Job Title"],
    ]);

    let currentEmailResult = null;
    let activeController = null;
    let requestSerial = 0;

    function el(id) {
        return document.getElementById(id);
    }

    function escapeEmailHTML(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function stringValue(value, fallback = "") {
        if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
            return String(value);
        }
        return fallback;
    }

    function objectValue(value) {
        return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    }

    function arrayValue(value) {
        if (Array.isArray(value)) return value;
        if (value == null || value === "") return [];
        return [value];
    }

    function firstDefined(...values) {
        return values.find(value => value !== undefined && value !== null && value !== "");
    }

    function integerValue(value, fallback = 0, minimum = 0, maximum = Number.MAX_SAFE_INTEGER) {
        const parsed = Number.parseInt(value, 10);
        if (!Number.isFinite(parsed)) return fallback;
        return Math.max(minimum, Math.min(maximum, parsed));
    }

    function booleanValue(value) {
        if (typeof value === "boolean") return value;
        if (typeof value === "string") return value.toLowerCase() === "true";
        return Boolean(value);
    }

    function humanize(value) {
        return stringValue(value)
            .replace(/[_-]+/g, " ")
            .replace(/\b\w/g, character => character.toUpperCase())
            .trim();
    }

    function safeHttpUrl(value) {
        const raw = stringValue(value).trim();
        if (!raw) return "";
        try {
            const parsed = new URL(raw);
            if (!["http:", "https:"].includes(parsed.protocol)) return "";
            if (parsed.username || parsed.password) return "";
            const hostname = parsed.hostname.toLowerCase().replace(/^\[|\]$/g, "");
            if (hostname === "localhost" || hostname.endsWith(".localhost") || hostname.endsWith(".local")) return "";
            if (/^(?:127\.|10\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(hostname)) return "";
            if (hostname === "::" || hostname === "::1" || hostname.startsWith("::ffff:") || /^(?:fc|fd|fe[89ab]|ff)/i.test(hostname)) return "";
            return parsed.href;
        } catch (_error) {
            return "";
        }
    }

    function safeGravatarUrl(value) {
        const safe = safeHttpUrl(value);
        if (!safe) return "";
        try {
            const host = new URL(safe).hostname.toLowerCase();
            const allowed = host === "gravatar.com"
                || host.endsWith(".gravatar.com")
                || host === "gravatarusercontent.com"
                || host.endsWith(".gravatarusercontent.com");
            return allowed ? safe : "";
        } catch (_error) {
            return "";
        }
    }

    function proxiedGravatarImageUrl(value) {
        const safeSource = safeGravatarUrl(value);
        if (!safeSource) return "";
        try {
            const configuredBase = window.API_BASE
                || (window.location.hostname
                    ? `${window.location.protocol}//${window.location.hostname}:8010`
                    : "http://127.0.0.1:8010");
            const apiBase = new URL(configuredBase);
            if (!["http:", "https:"].includes(apiBase.protocol) || apiBase.username || apiBase.password) return "";
            const endpoint = new URL("/api/v1/investigation/proxy_image", apiBase);
            endpoint.searchParams.set("url", safeSource);
            return endpoint.href;
        } catch (_error) {
            return "";
        }
    }

    function redactSensitiveText(value) {
        let text = stringValue(value);
        if (!text) return "";
        const labels = "password|passwd|pwd|token|cookie|secret|security answer|cvv|card number|bank account|passport|ssn";
        text = text.replace(new RegExp(`\\b(${labels})\\b\\s*[:=]\\s*[^,;|\\s]+`, "gi"), "$1: [REDACTED]");
        return text.slice(0, 2000);
    }

    function hasSensitiveMaterial(value, depth = 0) {
        if (!value || depth > 4) return false;
        if (Array.isArray(value)) return value.some(item => hasSensitiveMaterial(item, depth + 1));
        if (typeof value !== "object") return false;
        return Object.entries(value).some(([key, nested]) => (
            SENSITIVE_KEY_PATTERN.test(key) || hasSensitiveMaterial(nested, depth + 1)
        ));
    }

    function uniqueStrings(values, maximum = 100) {
        const seen = new Set();
        const output = [];
        for (const value of values) {
            const clean = redactSensitiveText(value).trim();
            const key = clean.toLowerCase();
            if (!clean || seen.has(key)) continue;
            seen.add(key);
            output.push(clean);
            if (output.length >= maximum) break;
        }
        return output;
    }

    function normalizeEmailAddress(raw) {
        const trimmed = stringValue(raw).trim();
        const separator = trimmed.lastIndexOf("@");
        if (separator < 1) return trimmed;
        return `${trimmed.slice(0, separator)}@${trimmed.slice(separator + 1).toLowerCase()}`;
    }

    function inspectEmailSyntax(raw) {
        const email = normalizeEmailAddress(raw);
        if (!email) return { valid: false, empty: true, message: "Enter one complete email address." };
        if (email.length > 254) return { valid: false, message: "Email address exceeds the 254-character limit." };
        if (/\s|,|;/.test(email)) return { valid: false, message: "Only one email address is allowed; spaces and list separators are invalid." };
        const parts = email.split("@");
        if (parts.length !== 2 || !parts[0] || !parts[1]) return { valid: false, message: "Email must contain one local part and one domain." };
        if (parts[0].length > 64 || parts[0].startsWith(".") || parts[0].endsWith(".") || parts[0].includes("..")) {
            return { valid: false, message: "The email local part is not structurally valid." };
        }
        if (!EMAIL_PATTERN.test(email)) return { valid: false, message: "Enter a syntactically valid address such as subject@example.com." };
        return { valid: true, email, message: "Syntax valid. The backend will perform authoritative domain and provider checks." };
    }

    function normalizeStatus(rawStatus, fallback = "not_run") {
        const status = stringValue(rawStatus).toLowerCase().replace(/[\s-]+/g, "_");
        const aliases = {
            success: "completed",
            ok: "completed",
            complete: "completed",
            found: "found",
            compromised: "found",
            no_hits: "no_results",
            not_found: "no_results",
            clean: "no_results",
            unavailable: "not_configured",
            error: "provider_error",
            failed: "provider_error",
            not_run: "skipped",
        };
        return aliases[status] || status || fallback;
    }

    function statusLabel(status) {
        const labels = {
            completed: "COMPLETED",
            found: "FOUND",
            no_results: "NO RESULTS",
            partial: "PARTIAL",
            not_configured: "NOT CONFIGURED",
            disabled: "DISABLED",
            skipped: "SKIPPED",
            provider_error: "PROVIDER ERROR",
            not_run: "NOT RUN",
        };
        return labels[status] || humanize(status || "unknown").toUpperCase();
    }

    function statusColor(status) {
        if (status === "completed" || status === "found" || status === "no_results") return "var(--status-success)";
        if (status === "partial" || status === "not_configured" || status === "disabled" || status === "skipped") return "var(--risk-medium)";
        if (status === "provider_error") return "var(--risk-high)";
        return "var(--text-muted)";
    }

    function normalizeProvenance(value) {
        const provenance = objectValue(value);
        return {
            provider: redactSensitiveText(firstDefined(provenance.provider, provenance.source, "")),
            method: redactSensitiveText(provenance.method),
            collectedAt: stringValue(firstDefined(provenance.collected_at, provenance.timestamp)),
            callsMade: integerValue(provenance.calls_made, 0, 0, 1000),
            scope: redactSensitiveText(provenance.scope),
        };
    }

    function normalizeMxRecord(value) {
        if (typeof value === "string") return { priority: null, host: value.slice(0, 255) };
        const record = objectValue(value);
        return {
            priority: Number.isFinite(Number(record.priority)) ? integerValue(record.priority, 0, 0, 65535) : null,
            host: stringValue(firstDefined(record.host, record.exchange, record.value)).slice(0, 255),
        };
    }

    function collectRecordFieldTypes(database) {
        const explicit = arrayValue(firstDefined(database.data_types, database.dataClasses, database.exposed_data));
        const recordContainers = arrayValue(firstDefined(database.records, database.data, database.rows));
        const recordKeys = [];
        recordContainers.forEach(record => {
            if (record && typeof record === "object" && !Array.isArray(record)) {
                recordKeys.push(...Object.keys(record));
            }
        });
        return uniqueStrings([...explicit, ...recordKeys].map(humanize), 80);
    }

    function computeBreachRisk(compromised, databases, recordCount) {
        if (compromised === null) return { score: null, level: "unknown", rationale: "Risk unavailable because breach coverage is incomplete or unavailable." };
        if (!compromised) return { score: 0, level: "low", rationale: "No matches were returned by the configured provider. This is not proof that the address has never been exposed." };

        const credentialSources = databases.filter(item => item.credentialMaterialPresent).length;
        const sensitiveTypeCount = uniqueStrings(databases.flatMap(item => item.dataTypes), 100)
            .filter(type => /financial|government|medical|phone|address|date of birth/i.test(type)).length;
        const volumePoints = Math.min(25, Math.round(Math.log10(Math.max(1, recordCount) + 1) * 9));
        const score = Math.min(100, 18 + Math.min(30, databases.length * 8) + volumePoints + Math.min(12, sensitiveTypeCount * 3) + (credentialSources ? 25 : 0));
        const level = score >= 80 ? "critical" : (score >= 60 ? "high" : (score >= 30 ? "medium" : "low"));
        const rationale = `Client-side triage score based on ${databases.length} attributed breach source(s), ${recordCount} reported record(s), exposed data types, and credential-material indicators.`;
        return { score, level, rationale };
    }

    function deriveHarvestedEmails(results, targetEmail) {
        const found = new Map();
        const targetDomain = normalizeEmailAddress(targetEmail).split("@")[1]?.toLowerCase() || "";
        if (!targetDomain) return [];
        for (const result of results) {
            const text = `${result.title} ${result.snippet}`;
            const matches = text.match(DISCOVERED_EMAIL_PATTERN) || [];
            for (const match of matches) {
                const inspected = inspectEmailSyntax(match);
                if (!inspected.valid) continue;
                const matchDomain = inspected.email.split("@")[1]?.toLowerCase() || "";
                if (matchDomain !== targetDomain) continue;
                const key = inspected.email.toLowerCase();
                if (!found.has(key)) {
                    found.set(key, {
                        email: inspected.email,
                        sourceUrl: result.url,
                        sourceTitle: result.title,
                        crawlDepth: 0,
                        matchType: key === normalizeEmailAddress(targetEmail).toLowerCase() ? "target" : "same_domain",
                    });
                }
                if (found.size >= 50) break;
            }
            if (found.size >= 50) break;
        }

        if (!found.size && targetEmail) return [];
        return Array.from(found.values());
    }

    function normalizeEmailResponse(rawResponse) {
        const raw = objectValue(rawResponse);
        const addressRaw = objectValue(firstDefined(raw.address_analysis, raw.email_validation, raw.validation));
        const domainRaw = objectValue(firstDefined(raw.domain_intelligence, raw.domain_analysis));
        const gravatarRaw = objectValue(firstDefined(raw.gravatar, raw.gravatar_identity));
        const breachRaw = objectValue(firstDefined(raw.breach_intelligence, raw.breach_summary));
        const discoveryRaw = objectValue(firstDefined(raw.web_discovery, raw.discovery_results, raw.dorking_results));
        const riskRaw = objectValue(raw.risk_summary);
        const authorizationRaw = objectValue(raw.authorization);
        const normalizedEmail = normalizeEmailAddress(firstDefined(raw.normalized_email, raw.target_email, raw.email, el("email-target-input")?.value));
        const restrictedDisclosureAudited = authorizationRaw.restricted_disclosure === "audited"
            && Boolean(stringValue(authorizationRaw.audit_event_id));

        const databaseItems = arrayValue(firstDefined(breachRaw.databases, breachRaw.breaches, breachRaw.results)).slice(0, 100);
        const canViewRestricted = Boolean(
            window.SocAuth?.hasRole("investigator")
            && window.SocAuth?.hasRole("breach_pii_viewer")
            && restrictedDisclosureAudited
        );
        const databases = databaseItems.map(itemValue => {
            const item = objectValue(itemValue);
            const dataTypes = collectRecordFieldTypes(item);
            const sensitiveFields = uniqueStrings(arrayValue(item.sensitive_fields_redacted).map(humanize), 80);
            const credentialMaterialPresent = booleanValue(firstDefined(
                item.credential_exposure_detected,
                item.credential_material_present,
                item.credentials_present,
                false
            )) || [...dataTypes, ...sensitiveFields].some(type => CREDENTIAL_TYPE_PATTERN.test(type)) || hasSensitiveMaterial(item);
            const restrictedRecords = canViewRestricted
                ? arrayValue(item.restricted_records).slice(0, 10).map(recordValue => {
                    const record = objectValue(recordValue);
                    const fields = arrayValue(record.fields).slice(0, 30).map(fieldValue => {
                        const field = objectValue(fieldValue);
                        const key = stringValue(firstDefined(field.key, field.canonical_key, field.name))
                            .trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
                        if (!RESTRICTED_CONTACT_FIELDS.has(key)) return null;
                        const value = redactSensitiveText(firstDefined(field.value, field.display_value));
                        if (!value) return null;
                        if (key === "email" && normalizeEmailAddress(value).toLowerCase() !== normalizedEmail.toLowerCase()) {
                            return null;
                        }
                        return {
                            key,
                            label: RESTRICTED_CONTACT_FIELDS.get(key),
                            category: redactSensitiveText(firstDefined(field.category, "contact")),
                            value,
                        };
                    }).filter(Boolean);
                    if (!fields.length) return null;
                    return {
                        recordId: redactSensitiveText(firstDefined(record.record_id, "Restricted record")),
                        targetEmailMatch: record.target_email_match === true,
                        fields,
                        suppressedCategories: uniqueStrings(
                            arrayValue(record.suppressed_categories).map(humanize),
                            12,
                        ),
                        additionalFieldsDetected: integerValue(
                            record.additional_fields_detected,
                            0,
                            0,
                            50,
                        ),
                    };
                }).filter(Boolean)
                : [];
            return {
                name: redactSensitiveText(firstDefined(item.name, item.title, item.database, "Attributed breach source")),
                source: redactSensitiveText(firstDefined(item.source, item.provider, breachRaw.provenance?.provider, "Configured breach provider")),
                breachDate: stringValue(firstDefined(item.breach_date, item.date)),
                recordCount: integerValue(firstDefined(item.record_count, item.records_count, item.count), 0, 0, 1000000000),
                dataTypes,
                credentialMaterialPresent,
                sensitiveFields,
                incidentSummary: redactSensitiveText(item.incident_summary),
                restrictedRecords,
                recordsTruncated: booleanValue(item.records_truncated),
                disclosurePolicy: redactSensitiveText(item.disclosure_policy),
            };
        });

        const breachStatus = normalizeStatus(breachRaw.status, databaseItems.length ? "found" : "not_run");
        let compromised = typeof breachRaw.compromised === "boolean" ? breachRaw.compromised : null;
        if (compromised === null && riskRaw.overall_status === "compromised") compromised = true;
        if (compromised === null && riskRaw.overall_status === "not_found") compromised = false;
        if (compromised === null && (breachStatus === "found" || databases.length > 0)) compromised = true;
        if (compromised === null && breachStatus === "no_results") compromised = false;
        const recordCount = integerValue(firstDefined(breachRaw.record_count, breachRaw.total_records), databases.reduce((sum, item) => sum + item.recordCount, 0), 0, 1000000000);
        const fallbackRisk = computeBreachRisk(compromised, databases, recordCount);
        const hasServerRisk = Object.keys(riskRaw).length > 0;
        const rawRiskScore = riskRaw.score;
        const serverRiskScore = rawRiskScore === null || rawRiskScore === undefined
            ? null
            : integerValue(rawRiskScore, 0, 0, 100);
        const risk = hasServerRisk ? {
            score: serverRiskScore,
            level: stringValue(riskRaw.label, "unknown").toLowerCase() === "moderate" ? "medium" : stringValue(riskRaw.label, "unknown").toLowerCase(),
            label: stringValue(riskRaw.label, "unknown").toLowerCase(),
            overallStatus: stringValue(riskRaw.overall_status, "unknown"),
            independentEvidenceGroups: integerValue(riskRaw.independent_evidence_groups, 0, 0, 1000),
            corroborated: riskRaw.corroborated === true,
            rationale: uniqueStrings(arrayValue(riskRaw.rationale), 20).join(" ") || "The backend did not return risk rationale.",
            source: "backend",
        } : {
            ...fallbackRisk,
            label: fallbackRisk.level,
            overallStatus: compromised === true ? "compromised" : (compromised === false ? "not_found" : "unknown"),
            independentEvidenceGroups: databases.length,
            corroborated: databases.length >= 2,
            source: "client_fallback",
        };

        let discoveryItems = arrayValue(firstDefined(discoveryRaw.results, raw.discovery_results));
        if (!Array.isArray(discoveryItems)) discoveryItems = [];
        const seenDiscovery = new Set();
        const discoveryResults = [];
        discoveryItems.slice(0, 200).forEach(value => {
            const item = objectValue(value);
            const url = safeHttpUrl(firstDefined(item.url, item.link));
            const title = redactSensitiveText(firstDefined(item.title, item.name, url || "Public web result"));
            const dedupeKey = `${url}|${title}`.toLowerCase();
            if (seenDiscovery.has(dedupeKey)) return;
            seenDiscovery.add(dedupeKey);
            discoveryResults.push({
                resultId: redactSensitiveText(item.result_id),
                title,
                url,
                domain: redactSensitiveText(item.domain),
                snippet: redactSensitiveText(firstDefined(item.snippet, item.description)),
                category: humanize(firstDefined(item.category, "Uncategorized")),
                query: redactSensitiveText(item.query),
                matchType: redactSensitiveText(item.match_type),
                credibility: redactSensitiveText(item.credibility),
                capturedAt: stringValue(item.captured_at),
                sourceEngines: uniqueStrings(arrayValue(item.source_engines), 10),
            });
        });

        const queryItems = arrayValue(discoveryRaw.queries).slice(0, 20).map(value => {
            const item = objectValue(value);
            return {
                query: redactSensitiveText(firstDefined(item.query, value)),
                engine: redactSensitiveText(item.engine),
                status: normalizeStatus(item.status, "completed"),
                resultCount: integerValue(item.result_count, 0, 0, 100000),
            };
        });
        const auditedQueryCount = new Set(queryItems.map(item => item.query).filter(Boolean)).size;

        const verifiedAccounts = arrayValue(gravatarRaw.verified_accounts).slice(0, 50).map(value => {
            const item = objectValue(value);
            return {
                service: redactSensitiveText(firstDefined(item.service, item.name, "Verified account")),
                url: safeHttpUrl(firstDefined(item.url, item.profile_url)),
            };
        }).filter(item => item.service || item.url);

        const backendHarvest = arrayValue(discoveryRaw.harvested_emails).slice(0, 50).map(value => {
            const item = objectValue(value);
            const inspection = inspectEmailSyntax(firstDefined(item.email, value));
            if (!inspection.valid) return null;
            return {
                email: inspection.email,
                sourceUrl: safeHttpUrl(item.source_url),
                sourceTitle: redactSensitiveText(firstDefined(item.source_title, item.source_url, "Attributed web result")),
                crawlDepth: integerValue(item.crawl_depth, 0, 0, 3),
                matchType: redactSensitiveText(item.match_type),
            };
        }).filter(Boolean);
        const harvestedEmails = backendHarvest.length ? backendHarvest : deriveHarvestedEmails(discoveryResults, normalizedEmail);

        const limitations = uniqueStrings([
            ...arrayValue(raw.limitations),
            ...arrayValue(breachRaw.limitations),
            ...arrayValue(discoveryRaw.limitations),
            "No breach source is comprehensive; private or unindexed incidents may be missed and false negatives are possible.",
            "Breach results contain source names, counts, and data-type indicators only. Credential and other sensitive field values are suppressed.",
            "Public-web findings are investigative leads. Confirm identity and relevance through at least two independent sources before attribution.",
            "Harvested addresses are derived only from returned search titles and snippets; this module does not recursively crawl websites.",
            "Search-engine coverage is limited to source engines attributed by the backend; unavailable engines are not simulated.",
            "Risk uses the backend summary when available; any labeled UI fallback remains a triage aid, not a provider or legal conclusion.",
        ], 30);

        const addressStatus = normalizeStatus(addressRaw.status, Object.keys(addressRaw).length ? "completed" : "not_run");
        const domainStatus = normalizeStatus(domainRaw.status, Object.keys(domainRaw).length ? "completed" : "not_run");
        const discoveryStatus = normalizeStatus(discoveryRaw.status, discoveryResults.length ? "completed" : "not_run");
        const gravatarStatus = normalizeStatus(gravatarRaw.status, booleanValue(gravatarRaw.profile_found) ? "found" : "not_run");

        return {
            schemaVersion: "email-investigation-ui-v1",
            investigationId: stringValue(raw.investigation_id),
            status: normalizeStatus(raw.status, "completed"),
            caseId: stringValue(firstDefined(raw.case_id, el("email-case-id")?.value)),
            reasonCode: stringValue(firstDefined(raw.reason_code, el("email-reason-code")?.value)),
            normalizedEmail,
            timestamp: stringValue(firstDefined(raw.timestamp, new Date().toISOString())),
            authorizationConfirmed: authorizationRaw.attested === true || authorizationRaw.authorized === true,
            authenticatedUser: redactSensitiveText(authorizationRaw.authenticated_user),
            restrictedDisclosureAudited,
            auditEventId: restrictedDisclosureAudited ? redactSensitiveText(authorizationRaw.audit_event_id) : "",
            address: {
                status: addressStatus,
                localPart: redactSensitiveText(addressRaw.local_part),
                domain: redactSensitiveText(firstDefined(addressRaw.domain, domainRaw.domain)),
                localPartPattern: redactSensitiveText(addressRaw.local_part_pattern),
                providerCategory: redactSensitiveText(addressRaw.provider_category),
                providerName: redactSensitiveText(addressRaw.provider_name),
                disposable: redactSensitiveText(addressRaw.disposable),
                notes: uniqueStrings(arrayValue(addressRaw.notes), 20),
                provenance: normalizeProvenance(addressRaw.provenance),
            },
            domain: {
                status: domainStatus,
                domain: redactSensitiveText(firstDefined(domainRaw.domain, addressRaw.domain)),
                resolves: firstDefined(domainRaw.domain_resolves, null),
                hasMx: firstDefined(domainRaw.has_mx, null),
                mxRecords: arrayValue(domainRaw.mx_records).slice(0, 50).map(normalizeMxRecord).filter(item => item.host),
                addresses: uniqueStrings(arrayValue(domainRaw.addresses), 50),
                mailProvider: redactSensitiveText(domainRaw.mail_provider),
                provenance: normalizeProvenance(domainRaw.provenance),
            },
            breach: {
                status: breachStatus,
                compromised,
                databaseCount: integerValue(breachRaw.database_count, databases.length, 0, 100000),
                recordCount,
                truncated: booleanValue(breachRaw.truncated),
                databases,
                risk,
                provenance: normalizeProvenance(breachRaw.provenance),
            },
            discovery: {
                status: discoveryStatus,
                provider: redactSensitiveText(firstDefined(discoveryRaw.provider, discoveryRaw.provenance?.provider)),
                queryCap: integerValue(discoveryRaw.query_cap, 0, 0, 3),
                queriesPlanned: integerValue(discoveryRaw.queries_planned, auditedQueryCount, 0, 3),
                queriesRun: integerValue(discoveryRaw.queries_run, auditedQueryCount, 0, 3),
                callCap: integerValue(discoveryRaw.call_cap, 0, 0, 6),
                providerCallsMade: integerValue(
                    firstDefined(discoveryRaw.provider_calls_made, discoveryRaw.provenance?.calls_made),
                    0,
                    0,
                    6,
                ),
                resultCount: integerValue(discoveryRaw.result_count, discoveryResults.length, 0, 100000),
                truncated: booleanValue(discoveryRaw.truncated),
                queries: queryItems,
                results: discoveryResults,
                provenance: normalizeProvenance(discoveryRaw.provenance),
            },
            harvest: {
                status: discoveryStatus === "completed" || discoveryStatus === "found" || discoveryStatus === "no_results" ? "completed" : discoveryStatus,
                emails: harvestedEmails,
                pagesCrawled: 0,
                crawlDepth: harvestedEmails.reduce((maximum, item) => Math.max(maximum, integerValue(item.crawlDepth, 0, 0, 3)), 0),
                method: backendHarvest.length
                    ? "Backend-attributed addresses from bounded public-search results"
                    : "Derived from bounded public-search result titles and snippets",
            },
            gravatar: {
                status: gravatarStatus,
                profileFound: booleanValue(gravatarRaw.profile_found),
                displayName: redactSensitiveText(gravatarRaw.display_name),
                username: redactSensitiveText(gravatarRaw.username),
                profileUrl: safeGravatarUrl(gravatarRaw.profile_url),
                avatarUrl: safeGravatarUrl(gravatarRaw.avatar_url),
                location: redactSensitiveText(gravatarRaw.location),
                about: redactSensitiveText(gravatarRaw.about),
                verifiedAccounts,
                provenance: normalizeProvenance(gravatarRaw.provenance),
            },
            limitations,
        };
    }

    function renderProvenance(provenance) {
        const parts = [];
        if (provenance.provider) parts.push(`Provider: ${provenance.provider}`);
        if (provenance.method) parts.push(`Method: ${provenance.method}`);
        parts.push(`Calls: ${provenance.callsMade}`);
        if (provenance.collectedAt) parts.push(`Collected: ${formatTimestamp(provenance.collectedAt)}`);
        if (provenance.scope) parts.push(`Scope: ${provenance.scope}`);
        return parts.length
            ? `<div class="email-result-provenance">${parts.map(escapeEmailHTML).join(" · ")}</div>`
            : "";
    }

    function renderStatusNotice(status, noun) {
        const notices = {
            not_configured: `${noun} provider is not configured. No safety conclusion can be drawn.`,
            disabled: `${noun} collection is disabled by policy or configuration.`,
            skipped: `${noun} collection was not requested or did not run.`,
            provider_error: `${noun} provider returned an error. Treat this section as unavailable, not as a negative result.`,
            partial: `${noun} collection completed only partially; review provenance and limitations.`,
        };
        const message = notices[status];
        if (!message) return "";
        const cssClass = status === "provider_error" ? "email-error-state" : "email-not-run-state";
        return `<div class="${cssClass}">${escapeEmailHTML(message)}</div>`;
    }

    function renderKeyValueGrid(items) {
        return `<div class="email-kv-grid">${items.map(item => `
            <div class="email-kv-item">
                <span class="email-kv-label">${escapeEmailHTML(item.label)}</span>
                <span class="email-kv-value">${escapeEmailHTML(item.value || "N/A")}</span>
            </div>
        `).join("")}</div>`;
    }

    function yesNoUnknown(value) {
        if (value === true) return "Yes";
        if (value === false) return "No";
        return "Unknown";
    }

    function setSectionBadge(id, text, status) {
        const badge = el(id);
        if (!badge) return;
        badge.textContent = text;
        badge.style.color = statusColor(status);
    }

    function renderValidationAndDomain(result) {
        const body = el("email-validation-domain-body");
        if (!body) return;
        const address = result.address;
        const domain = result.domain;
        const mxRows = domain.mxRecords.map(item => `
            <tr>
                <td class="mono">${item.priority == null ? "—" : item.priority}</td>
                <td class="mono">${escapeEmailHTML(item.host)}</td>
            </tr>
        `).join("");

        body.innerHTML = `
            ${renderStatusNotice(address.status, "Address analysis")}
            ${renderKeyValueGrid([
                { label: "Normalized Email", value: result.normalizedEmail },
                { label: "Local-Part Pattern", value: address.localPartPattern },
                { label: "Provider Category", value: address.providerCategory },
                { label: "Provider Name", value: address.providerName },
                { label: "Disposable Domain", value: address.disposable },
                { label: "Domain", value: domain.domain || address.domain },
            ])}
            ${renderProvenance(address.provenance)}
            <div class="email-subsection-title">Domain Infrastructure</div>
            ${renderStatusNotice(domain.status, "Domain intelligence")}
            ${renderKeyValueGrid([
                { label: "DNS Resolves", value: yesNoUnknown(domain.resolves) },
                { label: "MX Present", value: yesNoUnknown(domain.hasMx) },
                { label: "Mail Provider", value: domain.mailProvider },
                { label: "Resolved Addresses", value: domain.addresses.join(", ") || "None returned" },
            ])}
            ${mxRows ? `
                <div class="email-subsection-title">MX Records</div>
                <div class="table-scroll"><table class="soc-table">
                    <thead><tr><th>Priority</th><th>Mail Host</th></tr></thead>
                    <tbody>${mxRows}</tbody>
                </table></div>
            ` : ""}
            ${address.notes.length ? `<div class="email-result-provenance">Notes: ${address.notes.map(escapeEmailHTML).join(" · ")}</div>` : ""}
            ${renderProvenance(domain.provenance)}
        `;
        setSectionBadge("email-validation-result-badge", statusLabel(domain.status), domain.status);
    }

    function renderDataTypeChips(types, credentialMaterialPresent) {
        const safeTypes = uniqueStrings(types, 100);
        const chips = safeTypes.map(type => {
            const credential = CREDENTIAL_TYPE_PATTERN.test(type);
            const label = credential ? `${type} [REDACTED]` : type;
            return `<span class="email-data-type-chip${credential ? " credential" : ""}">${escapeEmailHTML(label)}</span>`;
        }).join("");
        const indicator = credentialMaterialPresent
            ? `<span class="email-credential-indicator">CREDENTIAL MATERIAL PRESENT · VALUES SUPPRESSED</span>`
            : "";
        return `<div class="email-data-type-list">${chips || '<span class="email-data-type-chip">No data types reported</span>'}</div>${indicator}`;
    }

    function renderRestrictedRecords(database) {
        if (!database.restrictedRecords.length) return "";
        return `
            <section class="email-restricted-evidence">
                <div class="email-restricted-evidence-header">
                    <span>Restricted Contact Evidence · Audited View</span>
                    <span class="mono">${database.restrictedRecords.length} RECORD(S)${database.recordsTruncated ? " · TRUNCATED" : ""}</span>
                </div>
                ${database.incidentSummary ? `<div class="email-result-snippet" style="padding:9px 11px;">${escapeEmailHTML(database.incidentSummary)}</div>` : ""}
                ${database.restrictedRecords.map((record, index) => `
                    <article class="email-restricted-record">
                        <div class="email-result-provenance">${escapeEmailHTML(record.recordId || `Record ${index + 1}`)} · ${record.targetEmailMatch ? "TARGET EMAIL MATCH" : "PROVIDER-ATTRIBUTED RECORD"}</div>
                        <div class="email-restricted-field-grid">
                            ${record.fields.map(field => `
                                <div class="email-restricted-field">
                                    <span class="email-restricted-field-label">${escapeEmailHTML(field.label)}</span>
                                    <span class="email-restricted-field-value">${escapeEmailHTML(field.value)}</span>
                                </div>
                            `).join("")}
                        </div>
                        ${(record.suppressedCategories.length || record.additionalFieldsDetected) ? `
                            <div class="email-result-provenance">
                                ${record.suppressedCategories.length ? `SUPPRESSED VALUE CATEGORIES: ${record.suppressedCategories.map(escapeEmailHTML).join(", ")}` : ""}
                                ${record.suppressedCategories.length && record.additionalFieldsDetected ? " · " : ""}
                                ${record.additionalFieldsDetected ? `${record.additionalFieldsDetected} UNREVIEWED FIELD(S) NOT DISCLOSED` : ""}
                            </div>
                        ` : ""}
                    </article>
                `).join("")}
            </section>
        `;
    }

    function renderBreachIntelligence(result) {
        const summaryBody = el("email-breach-summary-body");
        const listBody = el("email-breach-list-body");
        if (!summaryBody || !listBody) return;
        const breach = result.breach;
        const unavailable = ["not_configured", "disabled", "skipped", "provider_error"].includes(breach.status);
        const compromisedLabel = breach.compromised === true ? "COMPROMISED" : (breach.compromised === false ? "NO HITS RETURNED" : "UNKNOWN");
        const risk = breach.risk;

        summaryBody.innerHTML = `
            ${renderStatusNotice(breach.status, "Breach intelligence")}
            ${!unavailable ? `
                <div class="email-risk-overview">
                    <div class="email-risk-score">
                        <span class="email-kv-label">${risk.source === "backend" ? "SERVER RISK SCORE" : "UI FALLBACK TRIAGE"}</span>
                        <span class="email-risk-number ${escapeEmailHTML(risk.level)}">${risk.score == null ? "N/A" : `${risk.score}/100`}</span>
                        <span class="email-risk-label">${escapeEmailHTML(statusLabel(risk.label))}</span>
                        ${risk.score == null ? "" : `<div class="email-risk-track"><div class="email-risk-fill" style="width:${risk.score}%"></div></div>`}
                    </div>
                    <div class="email-risk-details">
                        <strong style="color:${breach.compromised ? 'var(--risk-high)' : 'var(--status-success)'};">${compromisedLabel}</strong><br>
                        ${escapeEmailHTML(risk.rationale)}<br>
                        <span class="mono">${breach.databaseCount} source(s) · ${breach.recordCount} record(s) · ${risk.independentEvidenceGroups} evidence group(s) · ${risk.corroborated ? "CORROBORATED" : "NOT CORROBORATED"}${breach.truncated ? " · RESULTS TRUNCATED" : ""}</span>
                    </div>
                </div>
            ` : ""}
            ${renderProvenance(breach.provenance)}
        `;

        if (!breach.databases.length) {
            const message = breach.status === "no_results"
                ? "No breach matches were returned by the configured source. Coverage limitations still apply."
                : "No attributable breach source records are available for display.";
            listBody.innerHTML = `<div class="email-empty-state">${escapeEmailHTML(message)}</div>`;
        } else {
            listBody.innerHTML = `
                <div class="email-subsection-title">Attributed Breach Sources</div>
                ${breach.databases.map(database => `
                    <article class="email-breach-card">
                        <div class="email-breach-card-header">
                            <strong>${escapeEmailHTML(database.name)}</strong>
                            <span class="email-breach-source">${escapeEmailHTML(database.source)} · ${database.breachDate ? `${escapeEmailHTML(database.breachDate)} · ` : ""}${database.recordCount} RECORD(S)</span>
                        </div>
                        ${renderDataTypeChips([...database.dataTypes, ...database.sensitiveFields], database.credentialMaterialPresent)}
                        ${renderRestrictedRecords(database)}
                    </article>
                `).join("")}
            `;
        }
        setSectionBadge("email-breach-result-badge", `${statusLabel(breach.status)} · ${breach.databaseCount} SOURCE(S)`, breach.status);
    }

    function renderDiscovery(result) {
        const body = el("email-discovery-results-body");
        if (!body) return;
        const discovery = result.discovery;
        const groups = new Map();
        discovery.results.forEach(item => {
            const category = item.category || "Uncategorized";
            if (!groups.has(category)) groups.set(category, []);
            groups.get(category).push(item);
        });

        const groupsHTML = Array.from(groups.entries()).map(([category, items]) => `
            <section class="email-discovery-group">
                <div class="email-discovery-group-header">
                    <strong>${escapeEmailHTML(category)}</strong>
                    <span class="email-discovery-count">${items.length} RESULT(S)</span>
                </div>
                ${items.map(item => `
                    <article class="email-discovery-result">
                        ${item.url
                            ? `<a class="email-safe-link" href="${escapeEmailHTML(item.url)}" target="_blank" rel="noopener noreferrer">${escapeEmailHTML(item.title || item.url)} ↗</a>`
                            : `<strong>${escapeEmailHTML(item.title)}</strong>`}
                        ${item.snippet ? `<div class="email-result-snippet">${escapeEmailHTML(item.snippet)}</div>` : ""}
                        <div class="email-result-provenance">
                            ${escapeEmailHTML([
                                item.resultId ? `ID: ${item.resultId}` : "",
                                item.domain,
                                item.matchType ? `Match: ${item.matchType}` : "",
                                item.credibility ? `Credibility: ${item.credibility}` : "",
                                item.sourceEngines.length ? `Engines: ${item.sourceEngines.join(", ")}` : "",
                                item.capturedAt ? `Captured: ${formatTimestamp(item.capturedAt)}` : "",
                                item.query ? `Query: ${item.query}` : "",
                            ].filter(Boolean).join(" · "))}
                        </div>
                    </article>
                `).join("")}
            </section>
        `).join("");

        body.innerHTML = `
            ${renderStatusNotice(discovery.status, "Public-web discovery")}
            <div class="email-discovery-meta">
                <span class="tag-chip mono">PROVIDER: ${escapeEmailHTML(discovery.provider || "N/A")}</span>
                <span class="tag-chip mono">QUERIES: ${discovery.queriesRun}/${discovery.queryCap || discovery.queriesPlanned || 0}</span>
                <span class="tag-chip mono">PROVIDER CALLS: ${discovery.providerCallsMade}/${discovery.callCap || discovery.providerCallsMade || 0}</span>
                <span class="tag-chip mono">RESULTS: ${discovery.resultCount}</span>
                ${discovery.truncated ? '<span class="risk-badge medium">TRUNCATED</span>' : ""}
            </div>
            ${groupsHTML || '<div class="email-empty-state">No categorized public-web results were returned.</div>'}
            ${discovery.queries.length ? `
                <div class="email-subsection-title">Bounded Query Audit</div>
                <div class="email-result-provenance">${discovery.queries.map(item => `${escapeEmailHTML(item.query)} [${item.engine ? `${escapeEmailHTML(item.engine.toUpperCase())} &middot; ` : ""}${escapeEmailHTML(statusLabel(item.status))}: ${item.resultCount}]`).join("<br>")}</div>
            ` : ""}
            ${renderProvenance(discovery.provenance)}
        `;
        setSectionBadge("email-discovery-result-badge", `${statusLabel(discovery.status)} · ${discovery.results.length} UNIQUE`, discovery.status);
    }

    function renderHarvest(result) {
        const body = el("email-harvest-results-body");
        if (!body) return;
        const harvest = result.harvest;
        const rows = harvest.emails.map(item => `
            <tr>
                <td class="mono">${escapeEmailHTML(item.email)}</td>
                <td>${item.sourceUrl
                    ? `<a class="email-safe-link" href="${escapeEmailHTML(item.sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeEmailHTML(item.sourceTitle || item.sourceUrl)} ↗</a>`
                    : escapeEmailHTML(item.sourceTitle || "Search snippet")}</td>
                <td><span class="tag-chip mono">${escapeEmailHTML(item.matchType || "same_domain")}</span></td>
            </tr>
        `).join("");
        body.innerHTML = `
            ${renderStatusNotice(harvest.status, "Email harvesting")}
            <div class="email-discovery-meta">
                <span class="tag-chip mono">UNIQUE EMAILS: ${harvest.emails.length}</span>
                <span class="tag-chip mono">CRAWL DEPTH: ${harvest.crawlDepth}</span>
                <span class="tag-chip mono">PAGES CRAWLED: ${harvest.pagesCrawled}</span>
            </div>
            ${rows ? `
                <div class="table-scroll"><table class="soc-table">
                    <thead><tr><th>Discovered Email</th><th>Attributed Source</th><th>Match Type</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table></div>
            ` : '<div class="email-empty-state">No additional valid email addresses were observed in returned search snippets.</div>'}
            <div class="email-result-provenance">${escapeEmailHTML(harvest.method)}</div>
        `;
        setSectionBadge("email-harvest-result-badge", `${harvest.emails.length} UNIQUE`, harvest.status);
    }

    function renderGravatar(result) {
        const body = el("email-gravatar-results-body");
        if (!body) return;
        const gravatar = result.gravatar;
        const avatarProxyUrl = proxiedGravatarImageUrl(gravatar.avatarUrl);
        const accounts = gravatar.verifiedAccounts.map(account => account.url
            ? `<a class="email-safe-link" href="${escapeEmailHTML(account.url)}" target="_blank" rel="noopener noreferrer">${escapeEmailHTML(account.service)} ↗</a>`
            : `<span class="tag-chip">${escapeEmailHTML(account.service)}</span>`).join("<br>");

        body.innerHTML = `
            ${renderStatusNotice(gravatar.status, "Gravatar identity")}
            ${gravatar.profileFound ? `
                <div class="email-gravatar-layout">
                    ${avatarProxyUrl ? `<img class="email-gravatar-image" src="${escapeEmailHTML(avatarProxyUrl)}" crossorigin="use-credentials" alt="Public Gravatar profile" referrerpolicy="no-referrer" onerror="this.style.display='none'">` : ""}
                    <div style="flex:1; min-width:0;">
                        ${renderKeyValueGrid([
                            { label: "Display Name", value: gravatar.displayName },
                            { label: "Username", value: gravatar.username },
                            { label: "Location", value: gravatar.location },
                            { label: "Profile Status", value: "Public profile found" },
                        ])}
                        ${gravatar.about ? `<div class="email-result-snippet">${escapeEmailHTML(gravatar.about)}</div>` : ""}
                        ${gravatar.profileUrl ? `<div style="margin-top:7px;"><a class="email-safe-link" href="${escapeEmailHTML(gravatar.profileUrl)}" target="_blank" rel="noopener noreferrer">Open public Gravatar profile ↗</a></div>` : ""}
                    </div>
                </div>
                ${accounts ? `<div class="email-subsection-title">Verified Public Accounts</div>${accounts}` : ""}
            ` : '<div class="email-empty-state">No public Gravatar identity was returned.</div>'}
            ${renderProvenance(gravatar.provenance)}
        `;
        setSectionBadge("email-gravatar-result-badge", gravatar.profileFound ? "PROFILE FOUND" : statusLabel(gravatar.status), gravatar.status);
    }

    function renderLimitations(result) {
        const body = el("email-limitations-body");
        if (!body) return;
        body.innerHTML = `<ul class="email-limitations-list">${result.limitations.map(item => `<li>${escapeEmailHTML(item)}</li>`).join("")}</ul>`;
    }

    function formatTimestamp(value) {
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? stringValue(value) : date.toLocaleString();
    }

    function renderEmailResult(result) {
        el("email-result-target").textContent = result.normalizedEmail || "Unknown target";
        el("email-result-meta").textContent = [
            result.investigationId ? `Investigation ${result.investigationId}` : "",
            result.caseId ? `Case ${result.caseId}` : "",
            result.reasonCode ? `Reason ${result.reasonCode}` : "",
            result.authorizationConfirmed ? "AUTHORIZATION ATTESTED" : "AUTHORIZATION NOT ATTESTED",
            result.restrictedDisclosureAudited ? `RESTRICTED VIEW AUDITED ${result.auditEventId}` : "",
            statusLabel(result.status),
            formatTimestamp(result.timestamp),
        ].filter(Boolean).join(" · ");
        renderValidationAndDomain(result);
        renderBreachIntelligence(result);
        renderDiscovery(result);
        renderHarvest(result);
        renderGravatar(result);
        renderLimitations(result);
        el("email-investigation-results").style.display = "block";
        el("email-investigation-results").scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function setSyntaxIndicator(inspection) {
        const badge = el("email-syntax-badge");
        const message = el("email-validation-message");
        if (!badge || !message) return;
        const state = inspection.empty ? "neutral" : (inspection.valid ? "valid" : "invalid");
        badge.className = `email-syntax-badge ${state}`;
        badge.textContent = inspection.empty ? "NOT CHECKED" : (inspection.valid ? "SYNTAX VALID" : "INVALID");
        message.className = `email-validation-message${inspection.empty ? "" : ` ${state}`}`;
        message.textContent = inspection.message;
    }

    function showFormError(message) {
        const box = el("email-form-error");
        if (!box) return;
        box.textContent = message;
        box.style.display = message ? "block" : "none";
    }

    function setEmailLoading(isLoading, message = "Validating target and domain infrastructure...") {
        const loading = el("email-investigation-loading");
        const button = el("email-investigate-button");
        const cancel = el("email-cancel-button");
        const state = el("email-form-state");
        if (loading) loading.style.display = isLoading ? "flex" : "none";
        if (button) {
            button.disabled = isLoading;
            button.textContent = isLoading ? "INVESTIGATION RUNNING..." : "INVESTIGATE EMAIL";
        }
        if (cancel) cancel.style.display = isLoading ? "inline-flex" : "none";
        if (state) {
            state.textContent = isLoading ? "REQUEST ACTIVE" : "READY";
            state.style.color = isLoading ? "var(--accent-cyan)" : "var(--text-muted)";
        }
        const loadingMessage = el("email-loading-message");
        if (loadingMessage) loadingMessage.textContent = message;
    }

    async function extractApiError(response) {
        try {
            const data = await response.json();
            if (Array.isArray(data.detail)) {
                return data.detail.map(item => stringValue(item.msg)).filter(Boolean).join("; ") || `Request failed with HTTP ${response.status}.`;
            }
            return stringValue(firstDefined(data.detail, data.message, data.error), `Request failed with HTTP ${response.status}.`);
        } catch (_error) {
            return `Request failed with HTTP ${response.status}.`;
        }
    }

    async function submitEmailInvestigation(event) {
        event.preventDefault();
        if (activeController) return;

        const inspection = inspectEmailSyntax(el("email-target-input")?.value);
        setSyntaxIndicator(inspection);
        const caseId = stringValue(el("email-case-id")?.value).trim();
        const reasonCode = stringValue(el("email-reason-code")?.value).trim();
        const authorized = Boolean(el("email-authorization-confirmed")?.checked);

        if (!inspection.valid) {
            showFormError(inspection.message);
            el("email-target-input")?.focus();
            return;
        }
        if (!CASE_ID_PATTERN.test(caseId)) {
            showFormError("Case ID is required (3–64 characters: letters, numbers, _, ., :, /, or -). ");
            el("email-case-id")?.focus();
            return;
        }
        if (!REASON_PATTERN.test(reasonCode)) {
            showFormError("Select a valid documented authorization reason code.");
            el("email-reason-code")?.focus();
            return;
        }
        if (!authorized) {
            showFormError("Explicit authorization confirmation is mandatory before any provider call.");
            el("email-authorization-confirmed")?.focus();
            return;
        }

        showFormError("");
        el("email-investigation-results").style.display = "none";
        const requestedDorkLimit = integerValue(el("email-dork-query-limit")?.value, 3, 0, 3);
        const includeWebDiscovery = Boolean(el("email-option-dorking")?.checked) && requestedDorkLimit > 0;
        const canViewRestricted = Boolean(
            window.SocAuth?.hasRole("investigator")
            && window.SocAuth?.hasRole("breach_pii_viewer")
        );
        const includeRestricted = canViewRestricted
            && Boolean(el("email-option-breaches")?.checked)
            && Boolean(el("email-option-restricted-records")?.checked);
        const payload = {
            email: inspection.email,
            authorized: true,
            reason_code: reasonCode,
            case_id: caseId,
            include_gravatar: Boolean(el("email-option-gravatar")?.checked),
            include_breach_lookup: Boolean(el("email-option-breaches")?.checked),
            include_restricted_breach_details: includeRestricted,
            include_web_discovery: includeWebDiscovery,
            dork_query_limit: includeWebDiscovery ? requestedDorkLimit : 0,
        };

        const controller = new AbortController();
        const serial = ++requestSerial;
        activeController = controller;
        const timeoutId = window.setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
        setEmailLoading(true);

        try {
            const response = await window.SocAuth.fetch(EMAIL_ENDPOINT, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                signal: controller.signal,
            });
            if (!response.ok) throw new Error(await extractApiError(response));
            const responseData = await response.json();
            if (serial !== requestSerial) return;
            currentEmailResult = normalizeEmailResponse(responseData);
            renderEmailResult(currentEmailResult);
        } catch (error) {
            if (serial !== requestSerial) return;
            const aborted = controller.signal.aborted || error?.name === "AbortError";
            const timeout = controller.signal.reason === "timeout";
            showFormError(aborted
                ? (timeout ? "Email investigation timed out after 120 seconds. No safety conclusion was recorded." : "Email investigation was cancelled by the analyst.")
                : `Email investigation failed: ${stringValue(error?.message, "Unknown request error")}`);
        } finally {
            window.clearTimeout(timeoutId);
            if (serial === requestSerial) {
                activeController = null;
                setEmailLoading(false);
            }
        }
    }

    function syncRestrictedControl() {
        const row = el("email-restricted-option-row");
        const input = el("email-option-restricted-records");
        const allowed = Boolean(
            window.SocAuth?.hasRole("investigator")
            && window.SocAuth?.hasRole("breach_pii_viewer")
        );
        if (row) row.style.display = allowed ? "flex" : "none";
        if (input) {
            input.disabled = !allowed;
            if (!allowed) input.checked = false;
        }
    }

    function openEmailInvestigation() {
        syncRestrictedControl();
        el("hero-search-view").style.display = "none";
        el("results-workspace").style.display = "none";
        el("email-investigation-view").style.display = "block";
        el("nav-username-investigation")?.classList.remove("is-active");
        el("nav-email-investigation")?.classList.add("is-active");
        const leaExport = el("nav-lea-export");
        if (leaExport) leaExport.style.display = "none";

        const targetInput = el("email-target-input");
        if (targetInput && !targetInput.value) {
            const candidates = [el("provider-email")?.value, el("hero-target-username")?.value, el("target-username")?.value];
            const candidate = candidates.find(value => inspectEmailSyntax(value).valid);
            if (candidate) {
                targetInput.value = normalizeEmailAddress(candidate);
                setSyntaxIndicator(inspectEmailSyntax(candidate));
            }
        }
        window.scrollTo({ top: 0, behavior: "smooth" });
        window.setTimeout(() => targetInput?.focus(), 100);
    }

    function cancelEmailInvestigation() {
        if (!activeController) return;
        activeController.abort("analyst_cancelled");
    }

    function clearEmailInvestigationState() {
        requestSerial += 1;
        if (activeController) activeController.abort("logout");
        activeController = null;
        currentEmailResult = null;
        el("email-investigation-form")?.reset();
        if (el("email-investigation-results")) el("email-investigation-results").style.display = "none";
        if (el("email-investigation-view")) el("email-investigation-view").style.display = "none";
        if (el("hero-search-view")) el("hero-search-view").style.display = "block";
        el("nav-username-investigation")?.classList.add("is-active");
        el("nav-email-investigation")?.classList.remove("is-active");
        if (el("nav-lea-export")) el("nav-lea-export").style.display = "inline-flex";
        [
            "email-validation-domain-body",
            "email-breach-summary-body",
            "email-breach-list-body",
            "email-discovery-results-body",
            "email-harvest-results-body",
            "email-gravatar-results-body",
            "email-limitations-body",
        ].forEach(id => {
            const node = el(id);
            if (node) node.replaceChildren();
        });
        showFormError("");
        setEmailLoading(false);
        setSyntaxIndicator(inspectEmailSyntax(""));
        syncRestrictedControl();
    }

    function csvCell(value) {
        let text = stringValue(value).replace(/\r?\n/g, " ");
        if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
        return `"${text.replace(/"/g, '""')}"`;
    }

    function buildExportRows(result) {
        const rows = [
            ["record_type", "category", "name", "value", "source", "url", "status"],
            ["case", "metadata", "investigation_id", result.investigationId, "Beta-v2", "", result.status],
            ["case", "metadata", "case_id", result.caseId, "Analyst input", "", result.status],
            ["case", "governance", "reason_code", result.reasonCode, "Backend attestation", "", result.status],
            ["case", "governance", "authorization_attested", result.authorizationConfirmed, "Backend attestation", "", result.authorizationConfirmed ? "attested" : "not_attested"],
            ["target", "email", "normalized_email", result.normalizedEmail, "Address analysis", "", result.address.status],
            ["validation", "address", "provider_category", result.address.providerCategory, result.address.provenance.provider, "", result.address.status],
            ["validation", "domain", "mail_provider", result.domain.mailProvider, result.domain.provenance.provider, "", result.domain.status],
            ["breach_summary", "risk", "ui_triage_score", result.breach.risk.score == null ? "N/A" : result.breach.risk.score, result.breach.provenance.provider, "", result.breach.status],
        ];
        result.breach.databases.forEach(database => rows.push([
            "breach_source", "breach", database.name,
            `records=${database.recordCount}; data_types=${database.dataTypes.join("|")}; credential_material_present=${database.credentialMaterialPresent}`,
            database.source, "", result.breach.status,
        ]));
        result.discovery.results.forEach(item => rows.push([
            "web_result", item.category, item.title, item.snippet,
            result.discovery.provider || item.domain, item.url, result.discovery.status,
        ]));
        rows.push([
            "web_discovery", "audit", "query_count",
            `${result.discovery.queriesRun}/${result.discovery.queryCap}`,
            result.discovery.provider, "", result.discovery.status,
        ]);
        rows.push([
            "web_discovery", "audit", "provider_call_count",
            `${result.discovery.providerCallsMade}/${result.discovery.callCap}`,
            result.discovery.provider, "", result.discovery.status,
        ]);
        result.harvest.emails.forEach(item => rows.push([
            "harvested_email", "public_web", item.email, "Derived from returned search snippet",
            item.sourceTitle, item.sourceUrl, result.harvest.status,
        ]));
        if (result.gravatar.profileFound) rows.push([
            "identity", "gravatar", result.gravatar.displayName || result.gravatar.username,
            result.gravatar.location, result.gravatar.provenance.provider, result.gravatar.profileUrl, result.gravatar.status,
        ]);
        result.limitations.forEach(item => rows.push(["limitation", "handling", "limitation", item, "Beta-v2", "", "applicable"]));
        return rows;
    }

    function buildTextExport(result) {
        const lines = [
            "UP POLICE CYBER CELL — EMAIL INVESTIGATION",
            `Investigation ID: ${result.investigationId}`,
            `Case ID: ${result.caseId}`,
            `Reason Code: ${result.reasonCode}`,
            `Target Email: ${result.normalizedEmail}`,
            `Status: ${statusLabel(result.status)}`,
            `Completed: ${formatTimestamp(result.timestamp)}`,
            "",
            "VALIDATION & DOMAIN",
            `Address status: ${statusLabel(result.address.status)}`,
            `Pattern: ${result.address.localPartPattern || "N/A"}`,
            `Provider: ${result.address.providerName || result.domain.mailProvider || "N/A"}`,
            `Disposable: ${result.address.disposable || "N/A"}`,
            `Domain resolves: ${yesNoUnknown(result.domain.resolves)}`,
            `MX present: ${yesNoUnknown(result.domain.hasMx)}`,
            "",
            "BREACH INTELLIGENCE",
            `Status: ${statusLabel(result.breach.status)}`,
            `Compromised: ${result.breach.compromised == null ? "UNKNOWN" : (result.breach.compromised ? "YES" : "NO HITS RETURNED")}`,
            `${result.breach.risk.source === "backend" ? "Server risk" : "UI fallback triage risk"}: ${result.breach.risk.score == null ? "N/A" : `${result.breach.risk.score}/100 (${result.breach.risk.level})`}`,
            ...result.breach.databases.map(item => `- ${item.name}: ${item.recordCount} record(s); data types: ${item.dataTypes.join(", ") || "not reported"}; credential material present: ${item.credentialMaterialPresent ? "YES — VALUES SUPPRESSED" : "NO INDICATOR"}`),
            "",
            "PUBLIC-WEB DISCOVERY",
            `Status: ${statusLabel(result.discovery.status)}; provider: ${result.discovery.provider || "N/A"}; queries: ${result.discovery.queriesRun}/${result.discovery.queryCap}; provider calls: ${result.discovery.providerCallsMade}/${result.discovery.callCap}; results: ${result.discovery.results.length}`,
            ...result.discovery.results.map(item => `- [${item.category}] ${item.title} | ${item.url || "No safe URL"} | ${item.snippet}`),
            "",
            "HARVESTED EMAILS",
            ...result.harvest.emails.map(item => `- ${item.email} | ${item.sourceUrl || item.sourceTitle}`),
            "",
            "LIMITATIONS",
            ...result.limitations.map(item => `- ${item}`),
        ];
        return lines.join("\r\n");
    }

    function downloadExport(content, mimeType, extension, result) {
        const safeCase = (result.caseId || result.investigationId || "email-case").replace(/[^A-Za-z0-9_.-]/g, "_").slice(0, 64);
        const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${safeCase}_email_investigation.${extension}`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function exportSafeResult(result) {
        return {
            ...result,
            breach: {
                ...result.breach,
                databases: result.breach.databases.map(database => {
                    const {
                        restrictedRecords: _restrictedRecords,
                        incidentSummary: _incidentSummary,
                        recordsTruncated: _recordsTruncated,
                        disclosurePolicy: _disclosurePolicy,
                        ...safeDatabase
                    } = database;
                    return safeDatabase;
                }),
                restrictedDataExported: false,
            },
            limitations: uniqueStrings([
                ...result.limitations,
                "Restricted contact-record values are intentionally excluded from browser-generated exports.",
            ], 40),
        };
    }

    function exportEmailInvestigation(format) {
        if (!currentEmailResult) {
            showFormError("Run an email investigation before exporting evidence.");
            return;
        }
        const normalizedFormat = stringValue(format).toLowerCase();
        if (normalizedFormat === "csv") {
            const content = buildExportRows(currentEmailResult).map(row => row.map(csvCell).join(",")).join("\r\n");
            downloadExport(content, "text/csv", "csv", currentEmailResult);
        } else if (normalizedFormat === "txt") {
            downloadExport(buildTextExport(currentEmailResult), "text/plain", "txt", currentEmailResult);
        } else if (normalizedFormat === "json") {
            downloadExport(JSON.stringify(exportSafeResult(currentEmailResult), null, 2), "application/json", "json", currentEmailResult);
        }
    }

    window.openEmailInvestigation = openEmailInvestigation;
    window.cancelEmailInvestigation = cancelEmailInvestigation;
    window.clearEmailInvestigationState = clearEmailInvestigationState;
    window.exportEmailInvestigation = exportEmailInvestigation;

    window.addEventListener("DOMContentLoaded", function () {
        const form = el("email-investigation-form");
        const input = el("email-target-input");
        const dorkToggle = el("email-option-dorking");
        const dorkLimit = el("email-dork-query-limit");
        form?.addEventListener("submit", submitEmailInvestigation);
        input?.addEventListener("input", () => {
            setSyntaxIndicator(inspectEmailSyntax(input.value));
            showFormError("");
        });
        dorkToggle?.addEventListener("change", () => {
            if (dorkLimit) {
                dorkLimit.disabled = !dorkToggle.checked;
                if (!dorkToggle.checked) dorkLimit.value = "0";
                if (dorkToggle.checked && dorkLimit.value === "0") dorkLimit.value = "3";
            }
        });
        dorkLimit?.addEventListener("change", () => {
            if (dorkToggle) dorkToggle.checked = dorkLimit.value !== "0";
        });
        setSyntaxIndicator(inspectEmailSyntax(input?.value));
        syncRestrictedControl();
    });
    window.addEventListener("soc:authenticated", syncRestrictedControl);
    window.addEventListener("soc:unauthenticated", () => {
        clearEmailInvestigationState();
        syncRestrictedControl();
    });
})();
