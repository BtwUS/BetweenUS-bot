"""Search tools for the conflict resolution bot."""

import os
from langchain_community.utilities import GoogleSearchAPIWrapper
from langchain_community.tools import GoogleSearchRun

# Initialize Google Search Tool
search = GoogleSearchAPIWrapper(
    google_api_key=os.environ.get("GOOGLE_API_KEY"),
    google_cse_id=os.environ.get("GOOGLE_CSE_ID")
)

google_search_tool = GoogleSearchRun(api_wrapper=search)