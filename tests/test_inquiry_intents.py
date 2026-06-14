from rise.inquiry.intents import (
    classify_inquiry,
    extract_topic,
    resolve_contextual_question,
    resolve_follow_up,
)
from rise.inquiry.models import ConversationTurn


def test_priority_and_general_intents_are_classified():
    assert classify_inquiry("Retrieve all UAC papers on tuition fees").intent == "retrieve_topics"
    assert classify_inquiry("Who discussed tuition fees?").intent == "people_by_topic"
    assert classify_inquiry("Did Leonard Cheng present this topic?").intent == "person_topic_check"
    assert classify_inquiry("Is there any discussion on net zero?").intent == "topic_discussion"
    assert classify_inquiry("Compare the roles of two vice-presidents").intent == "general_inquiry"
    assert classify_inquiry("Who is Kar Yan Tam?").intent == "person_profile"
    assert classify_inquiry("Tam Kar Yan 是谁？").intent == "person_profile"


def test_follow_up_resolution_is_conservative():
    turns = [ConversationTurn("assistant", "There are 20 confirmed results.")]
    assert resolve_follow_up("What about ITSO?", turns).is_follow_up is False
    assert resolve_follow_up("Continue summarizing", turns).is_follow_up is True


def test_topic_is_extracted_for_complete_exact_scan():
    assert extract_topic("Retrieve all UAC papers on tuition fees", "retrieve_topics") == "tuition fees"
    assert extract_topic("Who discussed student housing?", "people_by_topic") == "student housing"
    assert extract_topic("Who have discussed about adjustment of tuition fee?", "people_by_topic") == "adjustment of tuition fee"
    assert extract_topic("Is there any discussion on net zero?", "topic_discussion") == "net zero"


def test_contextual_question_resolution_uses_recent_subject_only_for_explicit_follow_up():
    turns = [
        ConversationTurn("user", "Who is Nancy Ip?"),
        ConversationTurn("assistant", "Nancy Ip: President, Chair."),
    ]

    resolved = resolve_contextual_question("What topics did she discuss?", turns)
    unrelated = resolve_contextual_question("Who is Kar Yan Tam?", turns)

    assert resolved.resolved_question == "What topics did Nancy Ip discuss?"
    assert resolved.used_memory is True
    assert unrelated.resolved_question == "Who is Kar Yan Tam?"
    assert unrelated.used_memory is False
