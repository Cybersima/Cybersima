from securetrade.journal import DecisionJournal


def test_journal_chain_is_verifiable() -> None:
    journal = DecisionJournal()
    journal.record("evaluate", "a", "ALLOW", ["coinbase"], 1.0, None, 90, "ALLOW", {"x": 1})
    journal.record("paper_lab_close", "a", "CAPTURED", ["coinbase"], 1.0, 0.8, 90, "CAPTURED", {"y": 2})
    assert journal.verify_chain() is True
    assert len(journal.entries) == 2


def test_tampered_journal_fails_verification() -> None:
    journal = DecisionJournal()
    journal.record("evaluate", "a", "ALLOW", ["coinbase"], 1.0, None, 90, "ALLOW", {"x": 1})
    journal.entries[0].decision = "TAMPERED"
    assert journal.verify_chain() is False
