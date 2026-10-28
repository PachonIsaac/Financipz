import datetime as dt

from app.schemas.common import Output


class ConnectOut(Output):
    # Where to send the person to allow read access to the mailbox.
    authorization_url: str


class GmailSyncOut(Output):
    # Messages read now, and what became of them.
    processed: int
    created: int
    duplicates: int
    ignored: int
    unrecognized: int
    last_synced_at: dt.datetime | None
    # True when there were more messages than one read takes. Reading again continues.
    more: bool
