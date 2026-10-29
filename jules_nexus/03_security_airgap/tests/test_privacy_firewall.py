import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from privacy_airgap_firewall import PrivacyAirGapFirewall


def test_privacy_firewall_sanitization():
    fw = PrivacyAirGapFirewall(strict_airgap_mode=False)

    # Test Credit card masking
    cc_text = "Kart numaram: 4532 1234 5678 9012 son kullanma 12/26"
    sanitized_cc = fw.sanitize_outbound_payload(cc_text)
    assert "4532 1234 5678 9012" not in sanitized_cc
    assert "[GİZLİ_KART_NO]" in sanitized_cc or "GİZLİ" in sanitized_cc

    # Test Email masking
    email_text = "E-posta adresim test.user@domain.com, ekle."
    sanitized_email = fw.sanitize_outbound_payload(email_text)
    assert "test.user@domain.com" not in sanitized_email
    assert "[GİZLİ_EPOSTA]" in sanitized_email or "GİZLİ" in sanitized_email


def test_command_safety_inspection():
    fw = PrivacyAirGapFirewall()

    safe, msg = fw.inspect_command_safety("echo Hello World")
    assert safe is True

    unsafe, msg = fw.inspect_command_safety("rm -rf /")
    assert unsafe is False
    assert "engellendi" in msg.lower() or "güvenlik" in msg.lower()
