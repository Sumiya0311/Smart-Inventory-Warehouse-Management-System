import logging
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)


SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM")


def send_email(
    recipient: str,
    subject: str,
    body: str
):
    try:

        if not recipient:
            logger.warning(
                "Email skipped: recipient is missing"
            )
            return

        if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD:
            logger.error(
                "SMTP configuration is missing"
            )
            return

        message = EmailMessage()

        message["From"] = EMAIL_FROM or SMTP_USERNAME
        message["To"] = recipient
        message["Subject"] = subject

        message.set_content(body)

        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=20
        ) as server:

            server.starttls()

            server.login(
                SMTP_USERNAME,
                SMTP_PASSWORD
            )

            server.send_message(message)

    except Exception:
        logger.exception(
            "Failed to send email to %s",
            recipient
        )


def queue_email(
    background_tasks,
    recipient: str,
    subject: str,
    body: str
):
    background_tasks.add_task(
        send_email,
        recipient,
        subject,
        body
    )