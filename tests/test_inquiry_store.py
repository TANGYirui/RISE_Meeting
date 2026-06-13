from pathlib import Path

from rise.inquiry.models import ConversationTurn, Inquiry
from rise.inquiry.store import InquiryStore


def test_store_round_trips_inquiry_and_enforces_memory_window(tmp_path: Path):
    store = InquiryStore(tmp_path / "state.sqlite", memory_window=2)
    inquiry = Inquiry("inq", "session", "q", "q", "general_inquiry")
    store.save_inquiry(inquiry)
    store.append_turn("session", ConversationTurn("user", "one"))
    store.append_turn("session", ConversationTurn("assistant", "two"))
    store.append_turn("session", ConversationTurn("user", "three"))

    assert store.get_inquiry("inq").original_question == "q"
    assert [turn.content for turn in store.get_turns("session")] == ["two", "three"]

    store.reset_session("session")
    assert store.get_turns("session") == []
    assert store.get_inquiry("inq") is None
