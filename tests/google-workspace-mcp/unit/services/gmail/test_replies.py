"""
Unit tests for GmailService reply methods.
"""

import base64
import email
from unittest.mock import patch

ORIGINAL_MESSAGE = {
    "id": "orig123",
    "threadId": "thread456",
    "from": "sender@example.com",
    "cc": "a@example.com, b@example.com",
    "subject": "Original Subject",
    "date": "Mon, 1 Jan 2024 12:00:00 +0000",
    "body": "Original body",
    "message_id": "<orig@example.com>",
}


def _decode_raw(message_body):
    raw = base64.urlsafe_b64decode(message_body["raw"])
    return email.message_from_bytes(raw)


class TestCreateReply:
    """Tests for GmailService.create_reply."""

    def test_draft_without_attachments(self, mock_gmail_service):
        """Without attachments the reply is a threaded plain-text draft."""
        drafts = mock_gmail_service.service.users.return_value.drafts.return_value
        drafts.create.return_value.execute.return_value = {"id": "draft1"}

        result = mock_gmail_service.create_reply(ORIGINAL_MESSAGE, "My reply")

        assert result == {"id": "draft1"}
        body = drafts.create.call_args.kwargs["body"]["message"]
        assert body["threadId"] == "thread456"
        msg = _decode_raw(body)
        assert msg["to"] == "sender@example.com"
        assert msg["subject"] == "Re: Original Subject"
        assert msg["In-Reply-To"] == "<orig@example.com>"
        assert not msg.is_multipart()
        mock_gmail_service.service.users.return_value.messages.return_value.send.assert_not_called()

    def test_send_with_attachments(self, mock_gmail_service, tmp_path):
        """With send=True and attachments the reply is sent as multipart."""
        attachment = tmp_path / "evidence.pdf"
        attachment.write_bytes(b"%PDF-1.4 test")
        messages = mock_gmail_service.service.users.return_value.messages.return_value
        messages.send.return_value.execute.return_value = {"id": "sent1"}

        result = mock_gmail_service.create_reply(
            ORIGINAL_MESSAGE, "See attached", send=True, attachments=[str(attachment)]
        )

        assert result == {"id": "sent1"}
        body = messages.send.call_args.kwargs["body"]
        assert body["threadId"] == "thread456"
        msg = _decode_raw(body)
        assert msg.is_multipart()
        assert msg["In-Reply-To"] == "<orig@example.com>"
        parts = msg.get_payload()
        assert parts[0].get_payload(decode=True).decode("utf-8").startswith("See attached")
        assert parts[1].get_filename() == "evidence.pdf"
        assert parts[1].get_payload(decode=True) == b"%PDF-1.4 test"
        mock_gmail_service.service.users.return_value.drafts.return_value.create.assert_not_called()

    def test_missing_attachment_returns_error(self, mock_gmail_service):
        """A missing attachment path fails the reply rather than dropping the file."""
        result = mock_gmail_service.create_reply(
            ORIGINAL_MESSAGE, "See attached", attachments=["/nonexistent/file.pdf"]
        )

        assert result["error"] is True
        mock_gmail_service.service.users.return_value.drafts.return_value.create.assert_not_called()


class TestReplyToEmail:
    """Tests for GmailService.reply_to_email."""

    def _set_own_address(self, mock_gmail_service, address="me@example.com"):
        profile = mock_gmail_service.service.users.return_value.getProfile.return_value
        profile.execute.return_value = {"emailAddress": address}

    def test_passes_send_and_attachments(self, mock_gmail_service):
        """send, reply_all CCs and attachments reach create_reply."""
        self._set_own_address(mock_gmail_service)
        with (
            patch.object(mock_gmail_service, "get_email_by_id", return_value=ORIGINAL_MESSAGE),
            patch.object(mock_gmail_service, "create_reply", return_value={"id": "sent1"}) as create_reply,
        ):
            result = mock_gmail_service.reply_to_email(
                "orig123", "Reply", send=True, reply_all=True, attachments=["/tmp/x.pdf"]
            )

        assert result == {"id": "sent1"}
        create_reply.assert_called_once_with(
            original_message=ORIGINAL_MESSAGE,
            reply_body="Reply",
            send=True,
            cc=["a@example.com", "b@example.com"],
            attachments=["/tmp/x.pdf"],
        )

    def test_reply_all_includes_to_and_cc(self, mock_gmail_service):
        """reply_all CCs original To and Cc, minus own address, sender and duplicates."""
        self._set_own_address(mock_gmail_service, "Me@Example.com")
        original = {
            **ORIGINAL_MESSAGE,
            "from": "Sender <sender@example.com>",
            "to": '"Gao, Michael" <michael@example.com>, me@example.com, sender@example.com',
            "cc": '"Scougal, Catherine" <catherine@example.com>, michael@example.com',
        }
        with (
            patch.object(mock_gmail_service, "get_email_by_id", return_value=original),
            patch.object(mock_gmail_service, "create_reply", return_value={"id": "draft1"}) as create_reply,
        ):
            mock_gmail_service.reply_to_email("orig123", "Reply", reply_all=True)

        assert create_reply.call_args.kwargs["cc"] == [
            '"Gao, Michael" <michael@example.com>',
            '"Scougal, Catherine" <catherine@example.com>',
        ]

    def test_reply_all_with_no_other_recipients(self, mock_gmail_service):
        """reply_all with only ourselves on the original leaves cc empty."""
        self._set_own_address(mock_gmail_service)
        original = {**ORIGINAL_MESSAGE, "to": "me@example.com"}
        del original["cc"]
        with (
            patch.object(mock_gmail_service, "get_email_by_id", return_value=original),
            patch.object(mock_gmail_service, "create_reply", return_value={"id": "draft1"}) as create_reply,
        ):
            mock_gmail_service.reply_to_email("orig123", "Reply", reply_all=True)

        assert create_reply.call_args.kwargs["cc"] is None

    def test_defaults_to_draft(self, mock_gmail_service):
        """Without send the reply is saved as a draft."""
        with (
            patch.object(mock_gmail_service, "get_email_by_id", return_value=ORIGINAL_MESSAGE),
            patch.object(mock_gmail_service, "create_reply", return_value={"id": "draft1"}) as create_reply,
        ):
            mock_gmail_service.reply_to_email("orig123", "Reply")

        assert create_reply.call_args.kwargs["send"] is False
        assert create_reply.call_args.kwargs["attachments"] is None
