"""
Unit tests for Gmail attachment operations.
"""

import base64
import tempfile
from pathlib import Path
from unittest.mock import MagicMock  # , patch

# import pytest # Removed unused import
from googleapiclient.errors import HttpError

# from google_workspace_mcp.services.gmail import GmailService # Removed unused import


class TestGmailAttachments:
    """Tests for Gmail attachment operations."""

    # Removed local mock_gmail_service fixture

    def test_get_attachment_content_success(self, mock_gmail_service, tmp_path, monkeypatch):
        """Test successful attachment content retrieval."""
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        # Test data
        message_id = "msg123"
        attachment_id = "att123"
        content = b"%PDF-1.4 test"

        # Mock API response for attachment
        mock_attachment = {"size": len(content), "data": base64.urlsafe_b64encode(content).decode("ascii")}

        # Mock API response for message metadata
        mock_message = {
            "payload": {
                "parts": [
                    {
                        "filename": "test_file.pdf",
                        "mimeType": "application/pdf",
                        "body": {"attachmentId": "att123"},
                    }
                ]
            }
        }

        # Setup execute mocks
        mock_attachment_execute = MagicMock(return_value=mock_attachment)
        mock_message_execute = MagicMock(return_value=mock_message)

        mock_gmail_service.service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute = mock_attachment_execute
        mock_gmail_service.service.users.return_value.messages.return_value.get.return_value.execute = mock_message_execute

        # Call the method
        result = mock_gmail_service.get_attachment_content(message_id, attachment_id)

        # Verify API calls
        mock_gmail_service.service.users.return_value.messages.return_value.attachments.return_value.get.assert_called_once_with(
            userId="me", messageId=message_id, id=attachment_id
        )
        mock_gmail_service.service.users.return_value.messages.return_value.get.assert_called_once_with(
            userId="me", id=message_id, format="full"
        )

        # Verify result: the decoded content is saved to a temp file
        assert result["size"] == len(content)
        assert Path(result["file_path"]) == tmp_path / "gmail_attachments" / "test_file.pdf"
        assert Path(result["file_path"]).read_bytes() == content
        assert result["filename"] == "test_file.pdf"
        assert result["mimeType"] == "application/pdf"

    def test_get_attachment_content_error(self, mock_gmail_service):
        """Test attachment content retrieval failure."""
        # Test data
        message_id = "msg123"
        attachment_id = "nonexistent"

        # Create a mock HttpError
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.reason = "Not Found"
        http_error = HttpError(mock_resp, b'{"error": {"message": "Attachment not found"}}')

        # Setup the mock to raise the error
        mock_gmail_service.service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.side_effect = http_error

        # Mock error handling
        expected_error = {
            "error": True,
            "error_type": "http_error",
            "status_code": 404,
            "message": "Attachment not found",
            "operation": "get_attachment_content",
        }
        mock_gmail_service.handle_api_error = MagicMock(return_value=expected_error)

        # Call the method
        result = mock_gmail_service.get_attachment_content(message_id, attachment_id)

        # Verify error handling
        mock_gmail_service.handle_api_error.assert_called_once_with("get_attachment_content", http_error)
        assert result == expected_error
