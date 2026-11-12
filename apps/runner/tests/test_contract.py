import unittest

from runner.contract import ApiError, ClaimResponse, DraftRequest, Usage


class ContractTest(unittest.TestCase):
    def test_claim_response_parses_and_ignores_unknown_keys(self):
        body = {
            "job": {
                "job_id": "job_1", "type": "draft_reply", "lease_until": 1, "attempt": 1,
                "conversation": {"conversation_id": "cnv_1", "session_id": None, "session_turns": 0,
                                 "session_started_at": None, "session_reset_reason": "new_conversation",
                                 "catalog_version": "cv_seed", "future_field": 1},
                "turn_context": {}, "turn_context_text": "<turn_context>\n</turn_context>",
                "new_customer_messages": [{"message_id": "msg_1", "text": "gội đầu bao nhiêu", "kind": "text",
                                           "attachments": [], "sent_at": 1}],
                "sent_since_last_draft": [], "unsent_drafts_since_last": [], "history": [], "prompt_hash": "abc",
            },
            "poll_after_ms": 0,
        }
        r = ClaimResponse.from_dict(body)
        self.assertEqual(r.job.conversation.conversation_id, "cnv_1")
        self.assertIsNone(r.job.conversation.session_id)
        self.assertEqual(r.job.new_customer_messages[0].text, "gội đầu bao nhiêu")

    def test_empty_claim(self):
        self.assertIsNone(ClaimResponse.from_dict({"job": None, "poll_after_ms": 2000}).job)

    def test_draft_request_round_trip(self):
        d = DraftRequest(text="Dạ", session_id="s", account_label="ultra", model="claude-opus-5-5", effort="low",
                         usage=Usage(input_tokens=1), cost_usd_equiv=0.01, duration_ms=10, num_turns=2)
        self.assertEqual(d.to_dict()["usage"]["input_tokens"], 1)
        self.assertIsNone(d.to_dict()["error_kind"])

    def test_api_error(self):
        e = ApiError.from_body(409, {"error": {"code": "lease_expired", "message": "late"}})
        self.assertEqual((e.status, e.code), (409, "lease_expired"))


if __name__ == "__main__":
    unittest.main()
