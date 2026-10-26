"""Shared logo for CommunityConnect page headers."""
import base64
from pathlib import Path

def header_logo():
    image = Path(__file__).parent / "assets" / "community_connect_logo.png"
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    return f'<div class="cc-logo"><img src="data:image/png;base64,{encoded}" alt="CommunityConnect logo" style="width:100%;height:100%;object-fit:contain"></div>'
