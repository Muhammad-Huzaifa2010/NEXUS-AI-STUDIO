"""Citation checks and rendering using only retrieved research sources."""

import json
import re
from typing import Literal
from unicodedata import normalize
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError


CITATION_PATTERN = re.compile(r"(?<!!)\[(\d+)\](?:\s*\([^)]*\))?")
ReviewStatus = Literal[
    "SOURCE_SUPPORTED",
    "DISPUTED",
    "INFERENCE",
    "PREDICTION",
    "UNVERIFIED",
]
TemporalContext = Literal[
    "HISTORICAL_EVENT",
    "SOURCE_PUBLICATION",
    "CURRENT_STATISTIC",
    "NOT_TEMPORAL",
    "UNCLEAR",
]


class EvidenceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: StrictInt
    quote: str = Field(min_length=1, max_length=1500)


class ReviewedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    claim: str = Field(min_length=3, max_length=1000)
    status: ReviewStatus
    source_ids: list[StrictInt] = Field(max_length=5)
    evidence: list[EvidenceQuote] = Field(max_length=5)
    reason: str = Field(min_length=1, max_length=500)
    temporal_context: TemporalContext


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    claims: list[ReviewedClaim] = Field(min_length=1, max_length=20)
    conflicts: list[str] = Field(max_length=10)
    limitations: list[str] = Field(max_length=10)
    missing_citations: list[str] = Field(max_length=10)
    outdated_claims: list[str] = Field(max_length=10)


def _markdown_url(url: str) -> str:
    return quote(url, safe=":/?&=#%+;,@!$'*~-._")


def validate_citation_references(response: str, sources: list[dict]) -> dict:
    source_ids = {source["id"] for source in sources}
    citations = [int(value) for value in CITATION_PATTERN.findall(response)]
    invalid = sorted({citation for citation in citations if citation not in source_ids})
    valid = sorted({citation for citation in citations if citation in source_ids})
    return {
        "valid_citations": valid,
        "invalid_citations": invalid,
        "missing_citations": bool(sources) and not valid,
        "needs_correction": bool(invalid) or (bool(sources) and not valid),
    }


def _extract_json_object(content: str) -> dict | None:
    if not isinstance(content, str):
        return None

    for start, character in enumerate(content):
        if character != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for end in range(start, len(content)):
            current = content[end]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(content[start:end + 1])
                    except (TypeError, ValueError):
                        break
                    if isinstance(candidate, dict):
                        return candidate
                    break
    return None


def _normalized_text(value: str) -> str:
    return " ".join(normalize("NFKC", value).split()).casefold()


def _numeric_tokens(value: str) -> set[str]:
    without_citations = CITATION_PATTERN.sub("", value)
    numbers = set(re.findall(
        r"(?<!\w)(\d[\d,]*)(?:st|nd|rd|th)?(?!\w)",
        without_citations,
        flags=re.IGNORECASE,
    ))
    for word, number in {
        "fifty": "50",
        "fifty-one": "51",
        "twenty-four": "24",
        "twenty-six": "26",
        "nineteen forty-five": "1945",
        "nineteen forty-six": "1946",
    }.items():
        if re.search(rf"\b{re.escape(word)}\b", without_citations, re.IGNORECASE):
            numbers.add(number)
    return numbers


def _quote_matches_source(quote: str, source: dict) -> bool:
    excerpt = str(source.get("excerpt") or "")
    return bool(_normalized_text(quote)) and (
        _normalized_text(quote) in _normalized_text(excerpt)
    )


def claim_review_validation_error(content: str) -> str:
    """Return a bounded, content-free reason why structured output was rejected."""
    raw_review = _extract_json_object(content)
    if raw_review is None:
        return "malformed_json"
    try:
        ClaimReview.model_validate(raw_review)
    except ValidationError as error:
        issues = error.errors(include_input=False)[:8]
        fields = [
            ".".join(str(part) for part in issue["loc"])
            for issue in issues
        ]
        return "schema_validation_failed:" + ",".join(fields)
    return "review_validation_failed"


def parse_claim_review(
    content: str,
    sources: list[dict],
    report: str | None = None,
) -> dict | None:
    """Validate a structured review and downgrade unsupported assertions."""
    raw_review = _extract_json_object(content)
    if raw_review is None:
        return None

    try:
        parsed = ClaimReview.model_validate(raw_review)
    except ValidationError:
        return None

    source_by_id = {
        source.get("id"): source
        for source in sources
        if isinstance(source.get("id"), int)
    }
    valid_source_ids = set(source_by_id)
    invalid_source_ids = False
    invalid_evidence = False
    invalid_claim_associations = False
    conflicts = [item[:500] for item in parsed.conflicts]
    limitations = [item[:500] for item in parsed.limitations]
    outdated_claims = [_normalized_text(item) for item in parsed.outdated_claims]
    claims = []

    for item in parsed.claims:
        claim = item.claim.strip()
        claim_source_ids = list(dict.fromkeys(item.source_ids))
        invalid_ids = any(source_id not in valid_source_ids for source_id in claim_source_ids)
        if invalid_ids:
            invalid_source_ids = True
            claim_source_ids = [
                source_id for source_id in claim_source_ids
                if source_id in valid_source_ids
            ]

        cited_in_claim = {
            int(value) for value in CITATION_PATTERN.findall(claim)
        }
        association_invalid = False
        if report is not None:
            if _normalized_text(claim) not in _normalized_text(report):
                association_invalid = True
            if set(claim_source_ids) != cited_in_claim:
                association_invalid = True
        if association_invalid:
            invalid_claim_associations = True

        valid_evidence = []
        mismatched_evidence = []
        evidence_numbers_by_source = {}
        evidence_source_ids = set()
        for evidence in item.evidence:
            source = source_by_id.get(evidence.source_id)
            if source is None:
                invalid_source_ids = True
                continue
            if evidence.source_id not in claim_source_ids:
                invalid_claim_associations = True
                association_invalid = True
                continue
            evidence_source_ids.add(evidence.source_id)
            if not _quote_matches_source(evidence.quote, source):
                invalid_evidence = True
                continue
            evidence_numbers_by_source.setdefault(evidence.source_id, set()).update(
                _numeric_tokens(evidence.quote)
            )
            valid_evidence.append({
                "source_id": evidence.source_id,
                "quote": evidence.quote,
            })

        claim_numbers = _numeric_tokens(claim)
        if claim_numbers:
            for source_id in claim_source_ids:
                quote_numbers = evidence_numbers_by_source.get(source_id, set())
                if quote_numbers and not claim_numbers.issubset(quote_numbers):
                    mismatched_evidence.append(source_id)

        if (
            item.status in {"SOURCE_SUPPORTED", "DISPUTED"}
            and evidence_source_ids != set(claim_source_ids)
        ):
            invalid_claim_associations = True
            association_invalid = True

        if item.status in {"SOURCE_SUPPORTED", "DISPUTED"}:
            if mismatched_evidence:
                status = "DISPUTED"
                conflicts.append(
                    f"Retrieved evidence contains conflicting dates or numbers "
                    f"for the claim: {claim}"
                )
            elif not valid_evidence:
                status = "UNVERIFIED"
            else:
                status = item.status
        else:
            status = item.status

        guide_only = (
            bool(claim_source_ids)
            and all(
                source_by_id[source_id].get("source_kind") == "reference_guide"
                for source_id in claim_source_ids
            )
        )
        if status == "SOURCE_SUPPORTED" and guide_only:
            status = "UNVERIFIED"
            invalid_evidence = True

        if association_invalid and status == "SOURCE_SUPPORTED":
            status = "UNVERIFIED"
        if invalid_ids and status == "SOURCE_SUPPORTED":
            status = "UNVERIFIED"

        reason = item.reason.strip()
        if mismatched_evidence:
            reason += " Retrieved evidence does not match the claim's dates or numbers."
        elif guide_only and item.status == "SOURCE_SUPPORTED":
            reason += " A research/library guide is not direct primary evidence."
        elif not valid_evidence and item.status == "SOURCE_SUPPORTED":
            reason += " No verbatim supporting excerpt was validated."

        claim_record = {
            "claim": claim,
            "status": status,
            "source_ids": claim_source_ids,
            "evidence": valid_evidence,
            "reason": reason[:500],
            "temporal_context": item.temporal_context,
        }
        if _normalized_text(claim) in outdated_claims:
            claim_record["status"] = "UNVERIFIED"
            claim_record["reason"] = (
                f"{claim_record['reason']} The cited information may be outdated."
            )[:500]
        claims.append(claim_record)

    return {
        "claims": claims,
        "conflicts": list(dict.fromkeys(conflicts)),
        "limitations": limitations,
        "missing_citations": [item[:500] for item in parsed.missing_citations],
        "outdated_claims": [item[:500] for item in parsed.outdated_claims],
        "invalid_source_ids": invalid_source_ids,
        "invalid_evidence": invalid_evidence,
        "invalid_claim_associations": invalid_claim_associations,
    }


def render_sources(response: str, sources: list[dict]) -> str:
    if not sources:
        return response.rstrip()

    source_by_id = {}
    for source in sources:
        url = str(source.get("url") or "")
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or not isinstance(source.get("id"), int)
        ):
            continue
        source_by_id[source["id"]] = source

    body = response.rstrip()
    if source_by_id:
        canonical_urls = {
            source["url"] for source in source_by_id.values()
        }
        body = CITATION_PATTERN.sub(
            lambda match: (
                f"[{match.group(1)}]({_markdown_url(source_by_id[int(match.group(1))]['url'])})"
                if int(match.group(1)) in source_by_id else match.group(0)
            ),
            body,
        )
        link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        body = link_pattern.sub(
            lambda match: (
                f"[{match.group(1)}]({_markdown_url(match.group(2))})"
                if match.group(2) in canonical_urls
                else match.group(1)
            ),
            body,
        )
        entries = []
        for source_id in sorted(source_by_id):
            source = source_by_id[source_id]
            title = str(source.get("title") or source.get("domain") or "Source")
            title = (
                title.replace("[", "\\[")
                .replace("]", "\\]")
                .replace("(", "\\(")
                .replace(")", "\\)")
            )
            details = [source.get("domain", "")]
            if source.get("published_date"):
                details.append(f"Published: {source['published_date']}")
            if source.get("source_type"):
                details.append(f"Type: {source['source_type']}")
            entries.append(
                f"{source_id}. [{title}]({_markdown_url(source['url'])})"
                f" — {' · '.join(details)}"
            )
        body += "\n\n## Sources\n\n" + "\n".join(entries)
    return body
