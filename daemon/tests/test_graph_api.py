from teams_notifications.graph_api import parse_chats_response, parse_channel_messages


def test_parse_chats_response_extracts_unread():
    response = {
        "value": [
            {
                "id": "chat1", "chatType": "oneOnOne",
                "viewpoint": {"lastMessageReadDateTime": "2026-04-03T09:00:00Z"},
                "lastMessagePreview": {
                    "createdDateTime": "2026-04-03T10:00:00Z",
                    "body": {"content": "Hello there"},
                    "from": {"user": {"id": "user-id-1", "displayName": "Alice Smith", "userIdentityType": "aadUser"}},
                },
            },
            {
                "id": "chat2", "chatType": "group",
                "viewpoint": {"lastMessageReadDateTime": "2026-04-03T11:00:00Z"},
                "lastMessagePreview": {
                    "createdDateTime": "2026-04-03T10:00:00Z",
                    "body": {"content": "Old message"},
                    "from": {"user": {"id": "user-id-2", "displayName": "Bob", "userIdentityType": "aadUser"}},
                },
            },
        ]
    }
    chats = parse_chats_response(response)
    assert len(chats) == 1
    assert chats[0].chat_id == "chat1"
    assert chats[0].sender_name == "Alice Smith"
    assert chats[0].last_message == "Hello there"
    assert chats[0].chat_type == "oneOnOne"


def test_parse_chats_response_handles_no_viewpoint():
    response = {
        "value": [{
            "id": "chat1", "chatType": "oneOnOne",
            "lastMessagePreview": {
                "createdDateTime": "2026-04-03T10:00:00Z",
                "body": {"content": "Hi"},
                "from": {"user": {"id": "uid", "displayName": "Alice", "userIdentityType": "aadUser"}},
            },
        }]
    }
    chats = parse_chats_response(response)
    assert len(chats) == 1


def test_parse_channel_messages_detects_mentions():
    my_user_id = "my-id-123"
    messages = [
        {
            "id": "msg1", "createdDateTime": "2026-04-03T12:00:00Z",
            "body": {"content": "<p>Hey <at>Denis</at></p>"},
            "from": {"user": {"id": "other-user", "displayName": "Carol", "userIdentityType": "aadUser"}},
            "mentions": [{"id": 0, "mentionText": "Denis", "mentioned": {"user": {"id": "my-id-123", "displayName": "Denis K"}}}],
        },
        {
            "id": "msg2", "createdDateTime": "2026-04-03T12:01:00Z",
            "body": {"content": "No mention here"},
            "from": {"user": {"id": "other-user", "displayName": "Carol", "userIdentityType": "aadUser"}},
            "mentions": [],
        },
    ]
    result = parse_channel_messages(messages, my_user_id, team_name="Engineering", channel_name="General")
    assert len(result) == 1
    assert result[0].sender_name == "Carol"
    assert result[0].channel_name == "General"


def test_parse_chats_response_empty():
    assert len(parse_chats_response({"value": []})) == 0
