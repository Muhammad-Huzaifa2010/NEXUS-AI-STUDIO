import json
import unittest
from unittest.mock import AsyncMock, patch

from app.workflows.agent_graph import (
    agent_graph,
    build_research_queries,
    deliver_response,
    research_agent,
    route_after_citation_validation,
    validate_citations_node,
)


def make_review(claim, status, source_id=1, quote=None):
    evidence = (
        [{"source_id": source_id, "quote": quote}]
        if quote else []
    )
    return json.dumps({
        "claims": [{
            "claim": claim,
            "status": status,
            "source_ids": [source_id],
            "evidence": evidence,
            "reason": "The retrieved evidence was compared with this claim.",
            "temporal_context": "NOT_TEMPORAL",
        }],
        "conflicts": [],
        "limitations": [],
        "missing_citations": [],
        "outdated_claims": [],
    })


class CitationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_un_history_facts_are_supported_by_retrieved_official_sources(self):
        source_facts = [
            (
                "UN foundation and original membership",
                "https://www.un.org/en/about-us/history-of-the-un",
                "Delegates of fifty nations met in San Francisco between 25 April and "
                "26 June 1945. The UN Charter was signed on 26 June 1945 by "
                "representatives of the 50 countries. Poland signed the Charter "
                "later and became the 51st original Member.",
            ),
            (
                "UN establishment",
                "https://www.un.org/en/about-us",
                "The United Nations officially came into existence on 24 October 1945.",
                "The United Nations officially came into existence on 24 October 1945.",
            ),
            (
                "International Court of Justice",
                "https://www.icj-cij.org/history",
                "The International Court of Justice began functioning in 1946.",
                "The International Court of Justice began functioning in 1946.",
            ),
            (
                "UNICEF",
                "https://www.unicef.org/about-us/overview",
                "UNICEF was established in 1946 by the United Nations.",
                "UNICEF was established in 1946 by the United Nations.",
            ),
            (
                "Member States",
                "https://www.un.org/en/about-us/member-states",
                "The United Nations has 193 Member States.",
                "The United Nations has 193 Member States.",
            ),
        ]
        sources = [{
            "title": f"History of the United Nations — {title}",
            "url": url,
            "content": excerpt,
            "score": 0.9,
        } for title, url, excerpt, *_ in source_facts]
        claims = [
            "The UN Charter was signed on 26 June 1945 by representatives of "
            "the 50 countries [1].",
            "Poland signed the Charter later and became the 51st original Member [1].",
            "The United Nations officially came into existence on 24 October 1945 [2].",
            "The International Court of Justice began functioning in 1946 [3].",
            "UNICEF was established in 1946 by the United Nations [4].",
            "The United Nations has 193 Member States [5].",
        ]
        report = "\n".join(f"- {claim}" for claim in claims)
        claim_evidence = [
            (1, "The UN Charter was signed on 26 June 1945 by representatives of "
             "the 50 countries."),
            (1, "Poland signed the Charter later and became the 51st original Member."),
            (2, "The United Nations officially came into existence on 24 October 1945."),
            (3, "The International Court of Justice began functioning in 1946."),
            (4, "UNICEF was established in 1946 by the United Nations."),
            (5, "The United Nations has 193 Member States."),
        ]
        review = {
            "claims": [{
                "claim": claim,
                "status": "SOURCE_SUPPORTED",
                "source_ids": [source_id],
                "evidence": [{
                    "source_id": source_id,
                    "quote": quote,
                }],
                "reason": "The official retrieved excerpt directly supports the claim.",
                "temporal_context": "HISTORICAL_EVENT" if index < 6
                else "CURRENT_STATISTIC",
            } for index, (claim, (source_id, quote)) in enumerate(
                zip(claims, claim_evidence, strict=True),
                start=1,
            )],
            "conflicts": [],
            "limitations": [],
            "missing_citations": [],
            "outdated_claims": [],
        }

        with (
            patch(
                "app.workflows.agent_graph.ask_model",
                new_callable=AsyncMock,
                side_effect=[
                    '{"agents":["research"]}',
                    report,
                    json.dumps(review),
                ],
            ) as mock_model,
            patch(
                "app.workflows.agent_graph.search_web",
                new_callable=AsyncMock,
                return_value={"status": "success", "results": sources},
            ) as mock_search,
            patch("app.workflows.agent_graph.publish_stream_event"),
        ):
            result = await agent_graph.ainvoke({
                "request": "Research the history of the United Nations."
            })

        validation = result["citation_validation_results"]
        self.assertEqual(mock_search.await_count, 5)
        self.assertEqual(result["task_plan"], ["research"])
        self.assertEqual(set(result["agent_outputs"]), {"research"})
        self.assertEqual(
            validation["validation_status"],
            "reviewed",
            msg=json.dumps(validation, indent=2),
        )
        self.assertEqual(mock_model.await_count, 3)
        self.assertFalse(validation["needs_correction"])
        self.assertTrue(all(
            claim["status"] == "SOURCE_SUPPORTED"
            for claim in validation["claims"]
        ))
        self.assertNotIn("Verification status: INCOMPLETE", result["response"])
        for expected_fact in (
            "50 countries",
            "51st original Member",
            "24 October 1945",
            "began functioning in 1946",
            "UNICEF was established in 1946",
            "193 Member States",
        ):
            self.assertIn(expected_fact, result["response"])

    def test_un_history_searches_cover_distinct_official_evidence_topics(self):
        searches = build_research_queries(
            "Research the historical development of the United Nations.",
            budget=5,
        )

        self.assertEqual(len(searches), 5)
        categories = {category for category, _ in searches}
        self.assertEqual(categories, {
            "official_history",
            "charter_signing",
            "charter_entry_into_force",
            "first_general_assembly",
            "membership_and_documents",
        })
        self.assertEqual(len({query for _, query in searches}), 5)

    async def test_first_search_failure_does_not_stop_the_bounded_search_plan(self):
        empty_success = {"status": "success", "results": []}
        with (
            patch(
                "app.workflows.agent_graph.search_web",
                new_callable=AsyncMock,
                side_effect=[
                    RuntimeError("temporary failure"),
                    empty_success,
                    empty_success,
                    empty_success,
                    empty_success,
                ],
            ) as mock_search,
            patch(
                "app.workflows.agent_graph.ask_model",
                new_callable=AsyncMock,
                return_value="No external evidence was returned.",
            ),
            patch("app.workflows.agent_graph.publish_stream_event"),
            self.assertLogs("app.workflows.agent_graph", level="ERROR"),
        ):
            result = await research_agent({
                "request": "Research the history of the United Nations.",
                "activity_events": [],
                "agent_outputs": {},
            })

        self.assertEqual(mock_search.await_count, 5)
        self.assertEqual(result["research_sources"], [])
        self.assertTrue(any(
            "official_history search" in item
            for item in result["research_limitations"]
        ))

    async def test_research_report_is_corrected_once_then_published_with_canonical_sources(self):
        source = {
            "id": 1,
            "title": "Official report",
            "url": "https://example.org/report",
            "domain": "example.org",
            "excerpt": "Corrected report with qualified finding.",
            "published_date": "2025-01-01",
            "source_type": "official",
            "relevance": 0.9,
        }
        model_responses = [
            '{"agents":["research","content"]}',
            "Research finding [1].",
            "Summary of finding [1].",
            "Final finding [1].",
            make_review("Final finding [1].", "UNVERIFIED"),
            "Corrected report with qualified finding [1].",
            make_review(
                "Corrected report with qualified finding [1].",
                "SOURCE_SUPPORTED",
                quote=source["excerpt"],
            ),
        ]

        with (
            patch(
                "app.workflows.agent_graph.ask_model",
                new_callable=AsyncMock,
            ) as mock_model,
            patch(
                "app.workflows.agent_graph.search_web",
                new_callable=AsyncMock,
                return_value={"status": "success", "results": [source]},
            ),
            patch("app.workflows.agent_graph.publish_stream_event"),
            patch("app.workflows.agent_graph.settings.citation_validation_retries", 1),
        ):
            mock_model.side_effect = model_responses
            result = await agent_graph.ainvoke({
                "request": "Research and summarize this finding."
            })

        self.assertIn("Corrected report", result["response"])
        self.assertIn("[1](https://example.org/report)", result["response"])
        self.assertIn("## Sources", result["response"])
        self.assertIn("SOURCE_SUPPORTED", result["response"])
        self.assertNotIn("UNVERIFIED", result["response"])
        self.assertEqual(result["citation_retry_count"], 1)
        self.assertEqual(mock_model.await_count, 7)

    def test_retry_limit_routes_to_delivery(self):
        state = {
            "needs_citation_correction": True,
            "citation_retry_count": 1,
        }
        with patch("app.workflows.agent_graph.settings.citation_validation_retries", 1):
            self.assertEqual(route_after_citation_validation(state), "deliver")

    def test_zero_retry_limit_skips_correction(self):
        state = {
            "needs_citation_correction": True,
            "citation_retry_count": 0,
        }
        with patch("app.workflows.agent_graph.settings.citation_validation_retries", 0):
            self.assertEqual(route_after_citation_validation(state), "deliver")

    async def test_validator_failure_reaches_final_response_with_warning(self):
        source = {
            "id": 1,
            "title": "Source",
            "url": "https://example.org/source",
            "domain": "example.org",
        }
        with (
            patch(
                "app.workflows.agent_graph.ask_model",
                new_callable=AsyncMock,
                side_effect=RuntimeError("provider unavailable"),
            ),
            patch("app.workflows.agent_graph.publish_stream_event"),
            patch("app.workflows.agent_graph.settings.citation_validation_retries", 0),
            self.assertLogs("app.workflows.agent_graph", level="ERROR"),
        ):
            validated = await validate_citations_node({
                "request": "Research this.",
                "task_plan": ["research"],
                "response": "A claim [1].",
                "research_sources": [source],
                "evidence_records": [],
                "activity_events": [],
            })

        self.assertTrue(
            validated["citation_validation_results"]["validator_unavailable"]
        )
        with patch("app.workflows.agent_graph.settings.citation_validation_retries", 0):
            self.assertEqual(route_after_citation_validation(validated), "deliver")
        delivered = await deliver_response({
            "request": "Research this.",
            "task_plan": ["research"],
            "response": "A claim [1].",
            "research_sources": [source],
            **validated,
        })
        self.assertIn("Verification status: INCOMPLETE", delivered["response"])
        self.assertIn("not passed citation validation", delivered["response"])

    async def test_malformed_review_is_recorded_and_reaches_final_response(self):
        source = {
            "id": 1,
            "title": "Official source",
            "url": "https://example.org/source",
            "domain": "example.org",
            "excerpt": "A verified historical fact.",
        }
        with (
            patch(
                "app.workflows.agent_graph.ask_model",
                new_callable=AsyncMock,
                return_value="The citation review could not be formatted.",
            ),
            patch("app.workflows.agent_graph.publish_stream_event"),
            patch("app.workflows.agent_graph.settings.citation_validation_retries", 0),
        ):
            validated = await validate_citations_node({
                "request": "Research this.",
                "task_plan": ["research"],
                "response": "A historical fact [1].",
                "research_sources": [source],
                "evidence_records": [],
                "activity_events": [],
            })

        validation = validated["citation_validation_results"]
        self.assertEqual(validation["validation_failure_reason"], "malformed_json")
        delivered = await deliver_response({
            "task_plan": ["research"],
            "response": "A historical fact [1].",
            "research_sources": [source],
            **validated,
        })
        self.assertIn("Verification status: INCOMPLETE", delivered["response"])
        self.assertIn("malformed_json", delivered["response"])


if __name__ == "__main__":
    unittest.main()
