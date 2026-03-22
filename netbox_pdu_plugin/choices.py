from utilities.choices import ChoiceSet


class VendorChoices(ChoiceSet):
    """PDU vendor / backend selector"""

    RARITAN = 'raritan'
    UBIQUITI = 'ubiquiti'

    CHOICES = [
        (RARITAN, 'Raritan'),
        (UBIQUITI, 'Ubiquiti (USP-PDU-Pro)'),
    ]


class OutletStatusChoices(ChoiceSet):
    """Power state of a PDU outlet"""

    ON = 'on'
    OFF = 'off'
    UNKNOWN = 'unknown'

    CHOICES = [
        (ON, 'ON', 'green'),
        (OFF, 'OFF', 'red'),
        (UNKNOWN, 'Unknown', 'grey'),
    ]


class SyncStatusChoices(ChoiceSet):
    """PDU synchronization status"""

    SUCCESS = 'success'
    FAILED = 'failed'
    NEVER = 'never'

    CHOICES = [
        (SUCCESS, 'Success', 'green'),
        (FAILED, 'Failed', 'red'),
        (NEVER, 'Never synced', 'grey'),
    ]
