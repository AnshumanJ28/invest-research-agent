import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.schemas import (  # noqa: E402
    Citation,
    ClaimVerification,
    InvestmentMemo,
    MemoClaim,
    MemoSection,
    VerificationStatus,
)
from rag.verification import VerificationService, build_verified_memo, save_verification_outputs  # noqa: E402


class FakeClaimVerifier:
    model_name = "fake-verifier"

    def __init__(self, statuses=None):
        self.statuses = statuses or {}
        self.api_call_count = 0
        self.evidence_seen = []

    def verify(self, claim, evidence_text):
        self.api_call_count += 1
        self.evidence_seen.append(evidence_text)
        status = self.statuses.get(claim.claim_id, VerificationStatus.SUPPORTED)
        return ClaimVerification(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            citation_ids=claim.citation_ids,
            status=status,
            confidence=0.91,
            explanation=f"Mocked {status.value.lower()} result.",
            evidence_excerpt=evidence_text[:300],
        )


def _citation(
    citation_id="[S1]",
    ticker="RELIANCE.NS",
    text="Revenue increased by 12% year over year.",
):
    return Citation(
        citation_id=citation_id,
        chunk_id=f"chunk_{citation_id}",
        source_type="filing",
        source_id="1",
        ticker=ticker,
        section="Management Discussion and Analysis",
        text_excerpt=text,
    )


def _memo(claims, citations=None, ticker="RELIANCE.NS"):
    return InvestmentMemo(
        ticker=ticker,
        generated_at=datetime.now(timezone.utc),
        sections=[
            MemoSection(name="Financial Overview", content="Generated content.", claims=claims),
            MemoSection(name="Disclaimer", content="This is a research aid, not financial advice.", claims=[]),
        ],
        citations=citations or [_citation()],
    )


def test_valid_citation_passes_deterministic_validation():
    verifier = FakeClaimVerifier()
    service = VerificationService(claim_verifier=verifier)
    memo = _memo([MemoClaim(claim_id="CLM-001", text="Revenue increased by 12%.", citation_ids=["[S1]"])])

    verified = service.verify_memo(memo)

    assert verified.verifications[0].status == VerificationStatus.SUPPORTED
    assert verifier.api_call_count == 1


def test_fake_citation_id_becomes_unsupported_without_llm_call():
    verifier = FakeClaimVerifier()
    service = VerificationService(claim_verifier=verifier)
    memo = _memo([MemoClaim(claim_id="CLM-001", text="Revenue increased.", citation_ids=["[S999]"])])

    verified = service.verify_memo(memo)

    assert verified.verifications[0].status == VerificationStatus.UNSUPPORTED
    assert "does not exist" in verified.verifications[0].explanation
    assert verifier.api_call_count == 0


def test_wrong_ticker_citation_becomes_unsupported_without_llm_call():
    verifier = FakeClaimVerifier()
    service = VerificationService(claim_verifier=verifier)
    memo = _memo(
        [MemoClaim(claim_id="CLM-001", text="Revenue increased.", citation_ids=["[S1]"])],
        citations=[_citation(ticker="INFY.NS")],
    )

    verified = service.verify_memo(memo)

    assert verified.verifications[0].status == VerificationStatus.UNSUPPORTED
    assert "INFY.NS" in verified.verifications[0].explanation
    assert verifier.api_call_count == 0


def test_empty_source_becomes_unsupported_without_llm_call():
    verifier = FakeClaimVerifier()
    service = VerificationService(claim_verifier=verifier)
    memo = _memo(
        [MemoClaim(claim_id="CLM-001", text="Revenue increased.", citation_ids=["[S1]"])],
        citations=[_citation(text="")],
    )

    verified = service.verify_memo(memo)

    assert verified.verifications[0].status == VerificationStatus.UNSUPPORTED
    assert "empty evidence" in verified.verifications[0].explanation
    assert verifier.api_call_count == 0


def test_status_enum_validation():
    assert VerificationStatus("SUPPORTED") == VerificationStatus.SUPPORTED
    assert VerificationStatus("PARTIAL") == VerificationStatus.PARTIAL
    assert VerificationStatus("UNSUPPORTED") == VerificationStatus.UNSUPPORTED
    assert VerificationStatus("CONTRADICTED") == VerificationStatus.CONTRADICTED


def test_multiple_citations_work():
    verifier = FakeClaimVerifier()
    service = VerificationService(claim_verifier=verifier)
    memo = _memo(
        [MemoClaim(claim_id="CLM-001", text="Revenue increased while margin declined.", citation_ids=["[S1]", "[S2]"])],
        citations=[
            _citation("[S1]", text="Revenue increased by 12% year over year."),
            _citation("[S2]", text="Operating margin declined during the year."),
        ],
    )

    verified = service.verify_memo(memo)

    assert verified.verifications[0].status == VerificationStatus.SUPPORTED
    assert "[S1]" in verifier.evidence_seen[0]
    assert "[S2]" in verifier.evidence_seen[0]


def test_unsupported_and_contradicted_claims_are_removed_from_safe_output():
    memo = _memo(
        [
            MemoClaim(claim_id="CLM-001", text="Supported claim.", citation_ids=["[S1]"]),
            MemoClaim(claim_id="CLM-002", text="Unsupported claim.", citation_ids=["[S1]"]),
            MemoClaim(claim_id="CLM-003", text="Contradicted claim.", citation_ids=["[S1]"]),
        ]
    )
    verifications = [
        ClaimVerification(claim_id="CLM-001", claim_text="Supported claim.", citation_ids=["[S1]"], status=VerificationStatus.SUPPORTED, confidence=0.9, explanation="ok"),
        ClaimVerification(claim_id="CLM-002", claim_text="Unsupported claim.", citation_ids=["[S1]"], status=VerificationStatus.UNSUPPORTED, confidence=0.9, explanation="bad"),
        ClaimVerification(claim_id="CLM-003", claim_text="Contradicted claim.", citation_ids=["[S1]"], status=VerificationStatus.CONTRADICTED, confidence=0.9, explanation="bad"),
    ]

    safe = build_verified_memo(memo, verifications)
    safe_claims = safe.sections[0].claims

    assert [claim.claim_id for claim in safe_claims] == ["CLM-001"]
    assert "Unsupported claim" not in safe.sections[0].content
    assert "Contradicted claim" not in safe.sections[0].content


def test_supported_claims_remain_and_original_memo_is_unchanged():
    memo = _memo(
        [
            MemoClaim(claim_id="CLM-001", text="Supported claim.", citation_ids=["[S1]"]),
            MemoClaim(claim_id="CLM-002", text="Unsupported claim.", citation_ids=["[S1]"]),
        ]
    )
    original_content = memo.sections[0].content
    verifications = [
        ClaimVerification(claim_id="CLM-001", claim_text="Supported claim.", citation_ids=["[S1]"], status=VerificationStatus.SUPPORTED, confidence=0.9, explanation="ok"),
        ClaimVerification(claim_id="CLM-002", claim_text="Unsupported claim.", citation_ids=["[S1]"], status=VerificationStatus.UNSUPPORTED, confidence=0.9, explanation="bad"),
    ]

    safe = build_verified_memo(memo, verifications)

    assert "Supported claim." in safe.sections[0].content
    assert memo.sections[0].content == original_content
    assert len(memo.sections[0].claims) == 2


def test_verification_json_serializes_correctly(tmp_path):
    service = VerificationService(claim_verifier=FakeClaimVerifier())
    memo = _memo([MemoClaim(claim_id="CLM-001", text="Revenue increased by 12%.", citation_ids=["[S1]"])])

    verified = service.verify_memo(memo)
    verification_path, verified_json_path, verified_md_path = save_verification_outputs(verified, tmp_path)
    parsed = json.loads(verification_path.read_text(encoding="utf-8"))

    assert parsed["original_memo"]["ticker"] == "RELIANCE.NS"
    assert parsed["verifications"][0]["status"] == "SUPPORTED"
    assert verified_json_path.exists()
    assert verified_md_path.exists()


def test_deliberately_bad_claim_examples_are_classified_with_mock_verifier():
    statuses = {
        "TEST-A": VerificationStatus.SUPPORTED,
        "TEST-B": VerificationStatus.CONTRADICTED,
        "TEST-C": VerificationStatus.UNSUPPORTED,
        "TEST-D": VerificationStatus.PARTIAL,
    }
    service = VerificationService(claim_verifier=FakeClaimVerifier(statuses))
    memo = _memo(
        [
            MemoClaim(claim_id="TEST-A", text="Revenue increased by 12% year over year.", citation_ids=["[S1]"]),
            MemoClaim(claim_id="TEST-B", text="Revenue increased by 25%.", citation_ids=["[S1]"]),
            MemoClaim(claim_id="TEST-C", text="The stock price is likely to rise.", citation_ids=["[S3]"]),
            MemoClaim(claim_id="TEST-D", text="Revenue increased substantially.", citation_ids=["[S4]"]),
            MemoClaim(claim_id="TEST-E", text="Missing citation claim.", citation_ids=["[S999]"]),
        ],
        citations=[
            _citation("[S1]", text="Revenue increased by 12% year over year."),
            _citation("[S3]", text="Management expects demand to remain stable."),
            _citation("[S4]", text="Revenue increased by 2%."),
        ],
    )

    verified = service.verify_memo(memo)
    by_id = {item.claim_id: item.status for item in verified.verifications}

    assert by_id["TEST-A"] == VerificationStatus.SUPPORTED
    assert by_id["TEST-B"] == VerificationStatus.CONTRADICTED
    assert by_id["TEST-C"] == VerificationStatus.UNSUPPORTED
    assert by_id["TEST-D"] == VerificationStatus.PARTIAL
    assert by_id["TEST-E"] == VerificationStatus.UNSUPPORTED
