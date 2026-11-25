import json
import unittest

from app.services.citation_service import (
    claim_review_validation_error,
    parse_claim_review,
    render_sources,
    validate_citation_references,
)


SOURCES = [{
    "id": 1,
    "title": "Official [Report]",
    "url": "https://example.org/report",
    "domain": "example.org",
    "excerpt": "The report states the finding and identifies fifty participants.",
}]


def review_for(
    claim="The finding involved 50 participants [1].",
    quote="The report states the finding and identifies fifty participants.",
    **overrides,
):
    review = {
        "claims": [{
            "claim": claim,
            "status": "SOURCE_SUPPORTED",
            "source_ids": [1],
            "evidence": [{"source_id": 1, "quote": quote}],
            "reason": "The excerpt supports the claim.",
            "temporal_context": "NOT_TEMPORAL",
        }],
        "conflicts": [],
        "limitations": [],
        "missing_citations": [],
        "outdated_claims": [],
    }
    review.update(overrides)
    return json.dumps(review)


class CitationServiceTests(unittest.TestCase):
    def test_valid_and_duplicate_citations_map_to_retrieved_ids(self):
        result = validate_citation_references("A claim [1]. Another [1].", SOURCES)
        self.assertEqual(result["valid_citations"], [1])
        self.assertEqual(result["invalid_citations"], [])
        self.assertFalse(result["needs_correction"])

    def test_missing_and_invalid_citations_are_reported(self):
        missing = validate_citation_references("A factual claim.", SOURCES)
        self.assertTrue(missing["missing_citations"])
        self.assertTrue(missing["needs_correction"])

        invalid = validate_citation_references("A claim [4].", SOURCES)
        self.assertEqual(invalid["invalid_citations"], [4])

    def test_markdown_citation_cannot_keep_a_forged_target(self):
        result = validate_citation_references(
            "A claim [1](https://attacker.invalid).", SOURCES
        )
        self.assertEqual(result["valid_citations"], [1])
        rendered = render_sources(
            "A claim [1](https://attacker.invalid) and [9]. "
            "[Fake link](https://attacker.invalid)",
            SOURCES,
        )
        self.assertIn("[1](https://example.org/report)", rendered)
        self.assertIn("[9]", rendered)
        self.assertIn("Fake link", rendered)
        self.assertNotIn("attacker.invalid", rendered)
        self.assertIn("[Official \\[Report\\]](https://example.org/report)", rendered)

    def test_unknown_source_ids_and_claims_are_unverified(self):
        review = json.loads(review_for(claim="Known evidence [1]."))
        review["claims"][0]["source_ids"] = [1, 99]
        review["claims"].append({
            "claim": "Unknown evidence [99].",
            "status": "SOURCE_SUPPORTED",
            "source_ids": [99],
            "evidence": [{"source_id": 99, "quote": "Invented evidence."}],
            "reason": "Claimed support.",
            "temporal_context": "NOT_TEMPORAL",
        })

        parsed = parse_claim_review(json.dumps(review), SOURCES)
        self.assertTrue(parsed["invalid_source_ids"])
        self.assertEqual(parsed["claims"][0]["status"], "UNVERIFIED")
        self.assertEqual(parsed["claims"][1]["status"], "UNVERIFIED")
        self.assertEqual(parsed["claims"][1]["source_ids"], [])

    def test_inference_is_not_mislabeled_as_unverified(self):
        review = json.loads(review_for(
            claim="A cautious inference.",
            quote="The report states the finding.",
        ))
        review["claims"][0].update({
            "status": "INFERENCE",
            "source_ids": [],
            "evidence": [],
            "reason": "Derived cautiously from the evidence.",
        })
        parsed = parse_claim_review(json.dumps(review), SOURCES)
        self.assertEqual(parsed["claims"][0]["status"], "INFERENCE")

    def test_wrong_historical_date_is_disputed(self):
        source = {
            **SOURCES[0],
            "excerpt": "The organization came into existence on 24 October 1945.",
        }
        claim = "The organization came into existence on 25 October 1945 [1]."
        parsed = parse_claim_review(review_for(
            claim=claim,
            quote=source["excerpt"],
        ), [source], report=claim)

        self.assertEqual(parsed["claims"][0]["status"], "DISPUTED")
        self.assertTrue(parsed["conflicts"])

    def test_conflicting_sources_are_disputed(self):
        sources = [
            {**SOURCES[0], "excerpt": "The organization has 193 members."},
            {
                **SOURCES[0],
                "id": 2,
                "url": "https://example.org/older",
                "excerpt": "The organization has 192 members.",
            },
        ]
        claim = "The organization has 193 members [1] [2]."
        review = json.loads(review_for(
            claim=claim,
            quote=sources[0]["excerpt"],
        ))
        review["claims"][0].update({
            "source_ids": [1, 2],
            "evidence": [
                {"source_id": 1, "quote": sources[0]["excerpt"]},
                {"source_id": 2, "quote": sources[1]["excerpt"]},
            ],
        })
        parsed = parse_claim_review(json.dumps(review), sources, report=claim)

        self.assertEqual(parsed["claims"][0]["status"], "DISPUTED")
        self.assertTrue(parsed["conflicts"])

    def test_outdated_statistics_are_downgraded(self):
        claim = "The organization has 193 members [1]."
        parsed = parse_claim_review(review_for(
            claim=claim,
            quote="The organization has 193 members.",
            outdated_claims=[claim],
        ), [{**SOURCES[0], "excerpt": "The organization has 193 members."}],
        report=claim)

        self.assertEqual(parsed["claims"][0]["status"], "UNVERIFIED")

    def test_evidence_must_be_an_exact_source_excerpt_and_support_numbers(self):
        claim = "The report identifies 50 participants [1]."
        parsed = parse_claim_review(review_for(
            claim=claim,
            quote="The report identifies 40 participants.",
        ), SOURCES, report=claim)

        self.assertTrue(parsed["invalid_evidence"])
        self.assertEqual(parsed["claims"][0]["status"], "UNVERIFIED")

    def test_missing_fields_invalid_status_and_malformed_json_are_rejected(self):
        self.assertIsNone(parse_claim_review("not json", SOURCES))
        self.assertEqual(
            claim_review_validation_error("not json"),
            "malformed_json",
        )
        self.assertIsNone(parse_claim_review(
            '{"claims":[{"claim":"Missing required fields"}]}',
            SOURCES,
        ))
        self.assertTrue(
            claim_review_validation_error(
                '{"claims":[{"claim":"Missing required fields"}]}'
            ).startswith("schema_validation_failed:")
        )
        invalid_status = json.loads(review_for())
        invalid_status["claims"][0]["status"] = "VERIFIED"
        self.assertIsNone(parse_claim_review(json.dumps(invalid_status), SOURCES))

    def test_review_must_match_report_claim_and_citation_associations(self):
        claim = "The finding involved 50 participants [1]."
        parsed = parse_claim_review(
            review_for(claim="A different claim [1]."),
            SOURCES,
            report=claim,
        )
        self.assertTrue(parsed["invalid_claim_associations"])
        self.assertEqual(parsed["claims"][0]["status"], "UNVERIFIED")

    def test_library_guide_cannot_be_direct_evidence(self):
        guide = {
            **SOURCES[0],
            "source_kind": "reference_guide",
            "excerpt": "The Charter was signed in 1945.",
        }
        claim = "The Charter was signed in 1945 [1]."
        review = json.loads(review_for(
            claim=claim,
            quote=guide["excerpt"],
        ))
        parsed = parse_claim_review(json.dumps(review), [guide], report=claim)

        self.assertEqual(parsed["claims"][0]["status"], "UNVERIFIED")
        self.assertTrue(parsed["invalid_evidence"])

    def test_empty_sources_do_not_invent_links_or_sources_section(self):
        self.assertEqual(render_sources("Plain response", []), "Plain response")


if __name__ == "__main__":
    unittest.main()
