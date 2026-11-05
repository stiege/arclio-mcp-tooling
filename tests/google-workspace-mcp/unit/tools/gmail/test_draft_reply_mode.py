"""
Unit tests for create_gmail_draft in reply mode (reply_to_message_id).
"""

from unittest.mock import MagicMock, patch

import pytest
from google_workspace_mcp.tools.gmail import create_gmail_draft

pytestmark = pytest.mark.anyio


@pytest.fixture
def mock_gmail_service():
    """Patch GmailService for tool tests."""
    with patch("google_workspace_mcp.tools.gmail.GmailService") as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        yield mock_service


class TestCreateGmailDraftReplyMode:
    async def test_reply_creates_threaded_draft(self, mock_gmail_service):
        """reply_to_message_id routes to reply_to_email as a draft, never a send."""
        mock_gmail_service.reply_to_email.return_value = {"id": "draft1", "message": {"threadId": "t1"}}

        result = await create_gmail_draft(
            body="Thanks", reply_to_message_id="msg123", reply_all=True, attachments=["/tmp/a.pdf"]
        )

        assert result == {"id": "draft1", "message": {"threadId": "t1"}}
        mock_gmail_service.reply_to_email.assert_called_once_with(
            email_id="msg123", reply_body="Thanks", send=False, reply_all=True, attachments=["/tmp/a.pdf"]
        )
        mock_gmail_service.create_draft.assert_not_called()

    @pytest.mark.parametrize(
        "extra",
        [{"to": "x@example.com"}, {"subject": "Re: Hi"}, {"cc": ["c@example.com"]}, {"bcc": ["b@example.com"]}],
    )
    async def test_reply_rejects_explicit_headers(self, mock_gmail_service, extra):
        """Recipients and subject come from the original; passing them is an error."""
        with pytest.raises(ValueError, match="omit to/subject/cc/bcc"):
            await create_gmail_draft(body="Thanks", reply_to_message_id="msg123", **extra)
        mock_gmail_service.reply_to_email.assert_not_called()

    async def test_reply_service_error(self, mock_gmail_service):
        mock_gmail_service.reply_to_email.return_value = {"error": True, "message": "Original email not found"}
        with pytest.raises(ValueError, match="Original email not found"):
            await create_gmail_draft(body="Thanks", reply_to_message_id="missing")

    async def test_reply_service_returns_none(self, mock_gmail_service):
        mock_gmail_service.reply_to_email.return_value = None
        with pytest.raises(ValueError, match="Error creating reply draft"):
            await create_gmail_draft(body="Thanks", reply_to_message_id="msg123")

    @pytest.mark.parametrize("subject", ["Re: Collection", "RE: Collection", "  re:x"])
    async def test_re_subject_without_reply_id_is_refused(self, mock_gmail_service, subject):
        """A 'Re:' subject on a new conversation is the unthreaded-reply mistake; refuse it."""
        with pytest.raises(ValueError, match="reply_to_message_id"):
            await create_gmail_draft(to="x@example.com", subject=subject, body="Hi")
        mock_gmail_service.create_draft.assert_not_called()

    async def test_reply_all_without_reply_id_is_refused(self, mock_gmail_service):
        with pytest.raises(ValueError, match="reply_all needs reply_to_message_id"):
            await create_gmail_draft(to="x@example.com", subject="Hello", body="Hi", reply_all=True)
