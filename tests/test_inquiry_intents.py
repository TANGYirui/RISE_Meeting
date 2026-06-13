from rise.inquiry.intents import classify_inquiry, resolve_follow_up
from rise.inquiry.models import ConversationTurn


def test_priority_and_general_intents_are_classified():
    assert classify_inquiry("Retrieve all UAC papers on tuition fees").intent == "retrieve_topics"
    assert classify_inquiry("Who discussed tuition fees?").intent == "people_by_topic"
    assert classify_inquiry("Did Leonard Cheng present this topic?").intent == "person_topic_check"
    assert classify_inquiry("Is there any discussion on net zero?").intent == "topic_discussion"
    assert classify_inquiry("Compare the roles of two vice-presidents").intent == "general_inquiry"


def test_follow_up_resolution_is_conservative():
    turns = [ConversationTurn("assistant", "There are 20 confirmed results.")]
    assert resolve_follow_up("What about ITSO?", turns).is_follow_up is False
    assert resolve_follow_up("Continue summarizing", turns).is_follow_up is True
