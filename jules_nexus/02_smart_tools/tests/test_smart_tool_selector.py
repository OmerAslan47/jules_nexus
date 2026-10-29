import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from smart_tool_selector import SmartToolSelector


def test_smart_tool_selector_basic():
    selector = SmartToolSelector()

    # Instant UI command detection
    directive = selector.detect_ui_directive("ekrana yaz merhaba")
    assert isinstance(directive, dict)

    # High relevance query requiring tools
    all_tools = [
        {"name": "read_file", "description": "Dosya oku test.txt"},
        {"name": "write_file", "description": "Dosya yaz test.txt"},
        {"name": "run_cmd", "description": "Komut çalıştır"},
        {"name": "search", "description": "Arama yap"},
        {"name": "weather", "description": "Hava durumu"},
    ]
    selected = selector.select_relevant_tools("dosya oku test.txt ve içeriğini getir", all_tools=all_tools, max_tools=4)
    assert isinstance(selected, list)
    assert len(selected) <= 4

    # Direct conversational query with low tool affinity
    selected_chat = selector.select_relevant_tools("selam nasılsın bugün hava nasıl", all_tools=all_tools, max_tools=4)
    assert isinstance(selected_chat, list)
    assert len(selected_chat) <= 4
